"""Project -> RGBDS assembly for a dual-mode ROM.

On a Game Boy Color the ROM loads palettes and per-tile palette numbers; on an original Game Boy it
uses one grayscale mapping (slot 0 = white ... slot 3 = black), which matches because the editor
keeps every palette ordered lightest to darkest.

Only what a project uses is generated:
  - Scenes nothing can reach are left out.
  - A single still screen compiles to straight-line loading code and a sleep loop.
  - Menus add input, the cursor sprite, blinking and fades.

Interrupts stay disabled. HALT still wakes when VBlank starts (IE enables the wake-up without a
handler), so there is no interrupt dispatch, no register saving and no RETI: the frame's VBlank work
runs straight after waking.
"""

import re

from . import sfx
from .build import build_rom
from .project import CH, CW, FADE_STEPS, ProjectError, dmg_fade, fade_palettes, validate  # noqa: F401

STACK_SIZE = 64
# Read once with the rest of the engine, so a running server never pairs new kit code with old Python.
KIT_PUZZLE = __import__("pathlib").Path(__file__).with_name("kit_puzzle.asm").read_text()
KIT_SFX = __import__("pathlib").Path(__file__).with_name("kit_sfx.asm").read_text()
KIT_FIGHT = __import__("pathlib").Path(__file__).with_name("kit_fight.asm").read_text()
KIT_NES = __import__("pathlib").Path(__file__).with_name("kit_nes.asm").read_text()
KIT_NES_SOUND = __import__("pathlib").Path(__file__).with_name("kit_nes_sound.asm").read_text()


# The template's effects as Punch-Out!!'s (its SQ1 effect numbers): what plays when a project has its engine.
NES_SFX = {"menu_move": 0x14, "menu_back": 0x14, "option_change": 0x12, "menu_confirm": 0x01, "press_start": 0x01,
           "bell": 0x0C, "count": 0x10, "knockdown": 0x02, "ko": 0x0E, "punch": 0x06, "hit": 0x03, "block": 0x04,
           "dodge": 0x11, "star_wind": 0x16}


def _dmc_tables(nes):
    """The NES's DMC samples (crowd, laughs, grunt) for the GB noise channel: per sample its address byte
    ($4012), a noise clock from how often it crosses its average, and its loudness each frame (RMS of the
    decoded 1-bit delta stream at the rate the game plays it, 33144 Hz)."""
    import math
    fixed, data = nes["sound_fixed"], nes["samples"]
    rate, per = 1789773 / 54, int(1789773 / 54 / 60)
    addrs, clocks, envs = [], [], []
    for k in range(7):
        a, n = fixed[0x368 + 2 * k], fixed[0x369 + 2 * k] * 16 + 1
        start = 0xC000 + a * 64 - 0xE000
        level, seq = 64, []
        for b in data[start:start + n]:
            for i in range(8):
                level = min(level + 2, 126) if b >> i & 1 and level <= 125 else (level - 2 if not b >> i & 1 and level >= 2 else level)
                seq.append(level)
        vols, crossings = [], 0
        for f in range(0, len(seq), per):
            c = seq[f:f + per]
            m = sum(c) / len(c)
            vols.append(max(1, min(15, round(math.sqrt(sum((x - m) ** 2 for x in c) / len(c)) / 2))))
            crossings += sum(1 for i in range(1, len(c)) if (c[i] - m) * (c[i - 1] - m) < 0)
        target = 2 * crossings / (len(seq) / rate)             # white noise crosses at about half its clock
        best = min(((s, r) for s in range(14) for r in range(8)),
                   key=lambda sr: abs(math.log(524288 / (0.5 if sr[1] == 0 else sr[1]) / 2 ** (sr[0] + 1) / target)))
        addrs.append(a); clocks.append(best[0] << 4 | best[1]); envs.append(vols)
    lines = ["DmcAddr:                    ; each sample's $4012, as the engine starts it",
             _db(addrs), "DmcClock:                   ; its noise clock (NR43)", _db(clocks),
             "DmcEnvelope:                ; its loudness by frame: the count first", "    dw " + ", ".join(f"DmcEnv{k}" for k in range(7))]
    for k, v in enumerate(envs):
        lines += [f"DmcEnv{k}:", _db([len(v)] + v)]
    return "\n".join(lines)


def _nes_parts():
    """kit_nes.asm by where it goes: ";;PART common" (ROM0), "fighter" and "mac" (each in the ROM bank of the
    NES data it reads, after it at $6000, so it never has to switch banks)."""
    parts, cur = {"head": [], "common": [], "fighter": [], "mac": []}, "head"
    for line in KIT_NES.splitlines():
        if line.startswith(";;PART "):
            cur = line.split()[1]
            continue
        parts[cur].append(line)
    return {k: "\n".join(v) for k, v in parts.items()}
BLINK_FRAMES = 4
BOB = [0, 0, 1, 2, 2, 2, 1, 0]          # cursor x offsets, one step every 8 frames
MARKER = [3, 3, 3, 3, 3, 3, 3, 3,       # slider marker sprite: a framed block
          3, 1, 1, 1, 1, 1, 1, 3,
          3, 1, 2, 2, 2, 2, 1, 3,
          3, 1, 2, 2, 2, 2, 1, 3,
          3, 1, 2, 2, 2, 2, 1, 3,
          3, 1, 2, 2, 2, 2, 1, 3,
          3, 1, 1, 1, 1, 1, 1, 3,
          3, 3, 3, 3, 3, 3, 3, 3]
# Directions repeat while held: first after REPEAT_DELAY frames, then every REPEAT_RATE frames.
REPEAT_CODE = """    ld a, b                 ; repeat held directions
    and $F0
    jr z, .noRepeat
    ldh a, [hPadNew]
    and $F0
    jr z, .holding
    ld a, REPEAT_DELAY
    ldh [hRepeatTimer], a
    jr .noRepeat
.holding:
    ld hl, hRepeatTimer
    dec [hl]
    jr nz, .noRepeat
    ld [hl], REPEAT_RATE
    ld a, b
    and $F0
    ld c, a
    ldh a, [hPadNew]
    or c
    jr .repeat
.noRepeat:
    ldh a, [hPadNew]
.repeat:
    ldh [hPadRepeat], a
"""
LCDC_BG = 0b10000001                    # LCD on, BG on, BG tiles at $8800-$97FF (signed), map $9800
LCDC_OBJ = 0b00000010                   # sprites on (8x8), sprite tiles at $8000
HW_DEFS = """DEF rP1    EQU $FF00
DEF rIF    EQU $FF0F
DEF rLCDC  EQU $FF40
DEF rSCY   EQU $FF42
DEF rSCX   EQU $FF43
DEF rLY    EQU $FF44
DEF rBGP   EQU $FF47
DEF rOBP0  EQU $FF48
DEF rVBK   EQU $FF4F
DEF rHDMA1 EQU $FF51
DEF rHDMA2 EQU $FF52
DEF rHDMA3 EQU $FF53
DEF rHDMA4 EQU $FF54
DEF rHDMA5 EQU $FF55
DEF rBCPS  EQU $FF68
DEF rBCPD  EQU $FF69
DEF rOCPS  EQU $FF6A
DEF rOCPD  EQU $FF6B
DEF rIE    EQU $FFFF
DEF OAM_CURSOR EQU $FE00
"""


def encode_tile(slots):
    """64 slots -> 16 bytes of Game Boy 2bpp tile data (low bit plane, then high, per row)."""
    out = []
    for y in range(8):
        row = slots[y * 8:(y + 1) * 8]
        out.append(sum(((s & 1) << (7 - x)) for x, s in enumerate(row)))
        out.append(sum(((s >> 1) << (7 - x)) for x, s in enumerate(row)))
    return out


def rom_title(name):
    title = re.sub(r"[^A-Z0-9 ]", "", name.upper()).strip()[:11]
    return title or "GBSTAGE"


def cursor_x(menu):
    """Screen x of the menu cursor (before bobbing): just left of the labels."""
    return menu["x"] * 8 - 11


def sfx_groups(scenes):
    """The sound effect groups a game's scenes need (menus always: every interactive screen beeps)."""
    groups = ["menu"]
    if any(s.get("puzzle") for s in scenes):
        groups.append("puzzle")
    if any(s.get("fight") for s in scenes):
        groups.append("fight")
    return groups


def reachable_scenes(project):
    """Scene indexes the game can get to from the start scene, in project order."""
    seen, todo = set(), [project["start"]]
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        s = project["scenes"][i]
        if s["back"] is not None:
            todo.append(s["back"])
        if s["menu"]:
            todo += [it["target"] for it in s["menu"]["items"]]
        if s["press"]:
            todo.append(s["press"]["target"])
        if s["options"]:
            todo.append(s["options"]["target"])
        if s.get("pass_key"):
            todo.append(s["pass_key"]["target"])
        for kit in ("puzzle", "fight"):
            if s.get(kit):
                todo += [s[kit]["win"], s[kit]["lose"]]
        if s.get("fight") and s["fight"]["corner"] is not None:
            todo.append(s["fight"]["corner"])
    return sorted(seen)


def _db(values, per_line=16):
    return "\n".join("    db " + ", ".join(f"${v:02X}" for v in values[i:i + per_line])
                     for i in range(0, len(values), per_line))


def _rgb555(colors):
    return ", ".join(f"${r | g << 5 | b << 10:04X}" for r, g, b in colors)


def _pad_rows(values, edge=False):
    """CW-wide rows -> 32-wide rows (the padding is off screen) so DMA can copy whole rows. edge: pad with
    each row's last tile, for rows that scroll sideways (the padding then shows at the edges)."""
    out = []
    for i in range(0, len(values), CW):
        row = list(values[i:i + CW])
        out += row + [row[-1] if edge else 0] * (32 - CW)
    return out


def _runs(indexes, slot=lambda i: i):
    """[0, 1, 3] -> [(0, 2), (3, 1)]: (first, count) runs of consecutive numbers (whose slots are
    consecutive too, so one index write covers the run)."""
    runs = []
    for i in indexes:
        if runs and runs[-1][0] + runs[-1][1] == i and slot(runs[-1][0]) + runs[-1][1] == slot(i):
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((i, 1))
    return runs


def _upload_runs(indexes, spec, data_reg, at_label=None, slots=None):
    """Code uploading the given palette indexes through BCPS/BCPD or OCPS/OCPD, 16 cycles per byte.

    HL walks a table holding every palette in order; runs of consecutive palettes share one index
    write and one loop, and palettes the scene doesn't use are skipped. slots: palette index -> the
    hardware palette it goes to, when that isn't the same number (see hw_palettes)."""
    lines, pos = [f"    ld c, LOW({data_reg})"], 0
    if at_label:
        lines.insert(0, f"    ld hl, {at_label}")
    slot = (slots or {}).get
    for first, count in _runs(indexes, lambda i: slot(i, i)):
        skip = (first - pos) * 8
        if skip:
            lines += [f"    ld de, {skip}", "    add hl, de"]
        lines += [f"    ld a, $80 | {slot(first, first) * 8}", f"    ldh [{spec}], a"]
        body = ["        ld a, [hl+]", "        ldh [c], a"]
        if count == 1:
            lines += ["    REPT 8"] + body + ["    ENDR"]
        else:
            label = f".palettes{first}"
            lines += [f"    ld b, {count}", f"{label}:", "    REPT 8"] + body + ["    ENDR", "    dec b", f"    jr nz, {label}"]
        pos = first + count
    return lines


POP_TILES = """    REPT 8
        pop de
        ld a, e
        ld [hl+], a
        ld a, d
        ld [hl+], a
    ENDR"""

POP_MAP_ROW = """    REPT MAP_W / 2
        pop de
        ld a, e
        ld [hl+], a
        ld a, d
        ld [hl+], a
    ENDR
    add sp, 32 - MAP_W      ; skip the off-screen padding
    ld a, l                 ; HL += 32 - MAP_W
    add 32 - MAP_W
    ld l, a
    adc h
    sub l
    ld h, a"""


def _gdma(src, dest, size):
    lines = []
    for off in range(0, size, 2048):
        blocks = min(128, (size - off) // 16)
        lines += [f"    ld a, HIGH({src} + {off})", "    ldh [rHDMA1], a", f"    ld a, LOW({src} + {off})", "    ldh [rHDMA2], a",
                  f"    ld a, HIGH(${dest:04X} + {off})", "    ldh [rHDMA3], a", f"    ld a, LOW(${dest:04X} + {off})", "    ldh [rHDMA4], a",
                  f"    ld a, {blocks - 1}", f"    ldh [rHDMA5], a         ; {blocks * 16} bytes; the CPU waits {blocks * 32} cycles"]
    return "\n".join(lines)


def _scene_data(i, s, banked=False):
    tile_bytes = [b for t in s["tiles"] for b in encode_tile(t)]
    if banked:      # one section per scene, so its tiles and maps share a bank
        head = f"""SECTION "Data: Scene {i}", ROMX, ALIGN[4]   ; DMA needs 16-byte alignment
Scene{i}Tiles:              ; "{s['name']}": {len(s['tiles'])} unique tiles
{_db(tile_bytes)}
Scene{i}Map:                ; rows padded to 32 tiles so DMA can copy them whole"""
    else:
        head = f"""SECTION "Data: Scene {i} tiles", ROM0, ALIGN[4]   ; DMA needs 16-byte alignment
Scene{i}Tiles:              ; "{s['name']}": {len(s['tiles'])} unique tiles
{_db(tile_bytes)}

SECTION "Data: Scene {i} maps", ROM0, ALIGN[4]    ; rows padded to 32 tiles so DMA can copy them whole
Scene{i}Map:"""
    return head + f"""
{_db(_pad_rows(s['cell_tiles'], bool(s.get('fight'))), 32)}
Scene{i}Attr:               ; palette number per tile (Game Boy Color only)
{_db(_pad_rows(s['cell_pal'], bool(s.get('fight'))), 32)}
"""


# ---- palettes per scene ----------------------------------------------------------

def hw_palettes(s):
    """A project can have more background palettes than the 8 the hardware holds, as long as each scene
    uses 8 at most. Returns the scene with its palette map in hardware slots and, when any palette moved,
    "pal_slots" (palette -> slot) and "pal_used" (the project palettes it uploads). Palettes 0-7 keep their
    own slot, so a project with 8 or fewer builds exactly as before."""
    used = sorted(set(s["cell_pal"]))
    if all(g < 8 for g in used):
        return s
    slots = {g: g for g in used if g < 8}
    free = [k for k in range(8) if k not in slots.values()]
    for g in used:
        if g >= 8:
            slots[g] = free.pop(0)
    return dict(s, cell_pal=[slots[g] for g in s["cell_pal"]], pal_slots=slots, pal_used=used)


# ---- one still screen: straight-line code ------------------------------------

def _static_asm(project, s):
    n = len(s["tiles"])
    used = s.get("pal_used") or sorted(set(s["cell_pal"]))
    tiles_color = _gdma("Scene0Tiles", 0x9000, min(n, 128) * 16)
    tiles_cpu = ["    ld sp, Scene0Tiles", "    ld hl, $9000            ; tiles 0-127", f"    ld b, {min(n, 128)}",
                 ".tiles:", POP_TILES, "    dec b", "    jr nz, .tiles"]
    if n > 128:
        tiles_color += "\n" + _gdma("Scene0Tiles + 128 * 16", 0x8800, (n - 128) * 16)
        tiles_cpu += ["    ld hl, $8800            ; tiles 128-255 (SP has moved on to them)", f"    ld b, {n - 128}",
                      ".tilesHigh:", POP_TILES, "    dec b", "    jr nz, .tilesHigh"]
    palettes = "\n".join(_upload_runs(used, "rBCPS", "rBCPD", at_label="BgPalettes", slots=s.get("pal_slots")))
    nl = "\n"
    return f"""; Generated by gbstage from "{project['name']}". Changes here are overwritten on the next build.

{HW_DEFS}
DEF MAP_W EQU {CW}
DEF MAP_H EQU {CH}

SECTION "Header", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0

SECTION "Code: Start", ROM0
Start:
    ld b, a                 ; the boot ROM leaves A = $11 on Game Boy Color hardware
.waitVBlank:                ; the LCD may only be switched off during VBlank
    ldh a, [rLY]
    cp 144
    jr c, .waitVBlank
.waitVBlankDone:            ; labels named .waitX/.waitXDone mark idle loops for the profiler
    xor a
    ldh [rLCDC], a
    ld a, b
    cp $11
    jp nz, .original

    ; Game Boy Color: DMA the tiles, map and palette map, then load the palettes this screen uses.
{tiles_color}
{_gdma("Scene0Map", 0x9800, CH * 32)}
    ld a, 1
    ldh [rVBK], a
{_gdma("Scene0Attr", 0x9800, CH * 32)}
    xor a
    ldh [rVBK], a
{palettes}
    jp .show

.original:                  ; original Game Boy: pop the data off the stack, 2 bytes at a time
{nl.join(tiles_cpu)}
    ld sp, Scene0Map
    ld hl, $9800
    ld b, MAP_H
.mapRow:
{POP_MAP_ROW}
    dec b
    jr nz, .mapRow
    ld a, %11100100         ; slot 0 white ... slot 3 black
    ldh [rBGP], a           ; (nothing below uses the stack, so SP can stay where the copy left it)

.show:
    xor a
    ldh [rSCY], a
    ldh [rSCX], a
    ld a, %{LCDC_BG:08b}
    ldh [rLCDC], a
    ld a, 1                 ; VBlank wakes HALT; interrupts stay disabled, so no handler runs
    ldh [rIE], a
MainLoop:
    xor a
    ldh [rIF], a
    halt
    nop                     ; HALT may run the next byte twice if VBlank arrives just before it
    jr MainLoop

SECTION "Data: Palettes", ROM0
BgPalettes:                 ; RGB555
{nl.join(f"    dw {_rgb555(c)}  ; {name}" for c, name in zip(project['palettes'], project['palette_names']))}

{_scene_data(0, s)}"""


# ---- menus and transitions -----------------------------------------------------

# Sliding in: the scene starts scrolled down by a screen. The map's 14 spare rows, filled with the scene's
# most common tile (its background), fill the screen above its top 32 pixels, and the scroll climbs a pixel a
# frame until it wraps to 0. The hardware scroll does the work: no tiles move, nothing extra per frame.
SLIDE_DEFS = f"""DEF SLIDE_START EQU {CH * 8}          ; SCY: the scene's top 32 rows at the bottom of the screen
DEF SLIDE_STEP EQU 1            ; pixels per frame: {256 - CH * 8} frames to slide all the way up
"""
SLIDE_STEP_CODE = """    ldh a, [hScrollY]       ; sliding in: climb (wraps to 0, the resting place)
    and a
    jr z, .still
    add SLIDE_STEP
    ldh [hScrollY], a
.still:
"""
SLIDE_FILL = """; Fill the map rows below the screen (18-31) with tile D, palette E on Game Boy Color. Screen off.
SlideFill:
    ld hl, $9800 + MAP_H * 32
    ld bc, (32 - MAP_H) * 32
    call .fill
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, 1
    ldh [rVBK], a
    ld d, e
    ld hl, $9800 + MAP_H * 32
    ld bc, (32 - MAP_H) * 32
    call .fill
    xor a
    ldh [rVBK], a
    ret
.fill:
    ld a, d
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .fill
    ret
"""

def _scene_load(i, s, sprites, opt_index=None, markers=False):
    n = len(s["tiles"])
    lines = [f"Scene{i}Load:", f"    ld hl, Scene{i}Tiles", "    ld de, $9000            ; tiles 0-127",
             f"    ld c, {min(n, 128)}", "    call CopyTiles"]
    if n > 128:
        lines += [f"    ld hl, Scene{i}Tiles + 128 * 16", "    ld de, $8800            ; tiles 128-255",
                  f"    ld c, {n - 128}", "    call CopyTiles"]
    lines += [f"    ld hl, Scene{i}Map", "    call CopyMap", f"    ld hl, Scene{i}Attr", "    call CopyAttr"]
    if s.get("slide"):
        pairs = list(zip(s["cell_tiles"], s["cell_pal"]))
        tile, pal = max(set(pairs), key=lambda tp: (pairs.count(tp), -pairs.index(tp)))
        lines += [f"    ld de, ${tile:02X} << 8 | {pal}       ; the scene's background: its most common tile and palette",
                  "    call SlideFill", f"    ld a, SLIDE_START", "    ldh [hScrollY], a"]
    if s.get("puzzle"):
        lines.append("    call PuzzleLoad")
    if s.get("fight"):
        lines.append("    call FightLoad")
    if s.get("pass_key"):
        lines.append(f"    call Scene{i}PassLoad")
    if s.get("nes_dmc"):
        lines += ["IF DEF(FT_NES_SOUND)", f"    ld a, {s['nes_dmc']}             ; its NES sample (the crowd), as the game starts it",
                  "    call NesDmc", "ENDC"]
    if (s["menu"] or {}).get("confirm"):
        n = len(s["menu"]["confirm"]["tiles"]) * 16
        lines += [f"    ld hl, Scene{i}ConfirmTiles  ; the confirm sprite's tiles, from sprite tile 2",
                  "    ld de, $8020", f"    ld bc, {n}", ".confirmTiles:", "    ld a, [hl+]", "    ld [de], a", "    inc de",
                  "    dec bc", "    ld a, b", "    or c", "    jr nz, .confirmTiles",
                  "    ld hl, $FE08             ; sprites 2-39 hidden", "    ld b, 38 * 4", "    xor a", ".confirmOam:",
                  "    ld [hl+], a", "    dec b", "    jr nz, .confirmOam"]
    if sprites:
        if s["menu"]:
            m = s["menu"]
            lines += [f"    ld a, {m['y'] * 8 + 16}               ; cursor on the first item", "    ldh [hCursorY], a",
                      f"    ld a, {cursor_x(m) + 8}", "    ldh [hCursorX], a"]
        elif s["options"]:
            lines += _options_load(i, s, opt_index, markers)
        else:
            lines += ["    xor a                   ; no menu: cursor off screen", "    ldh [hCursorY], a"]
        if markers and not s["options"]:
            lines += ["    xor a", "    ldh [hMarkerY], a"]
    lines.append("    ret")
    return "\n".join(lines)


def _scene_palettes(i, s, project, sprites):
    """Upload this scene's palettes from the fade row in DE: only the background palettes its tiles
    use, plus the cursor's sprite palette if it has a menu."""
    lines = [f"Scene{i}Palettes:", "    ld h, d", "    ld l, e"]
    used = s.get("pal_used") or sorted(set(s["cell_pal"]))
    lines += _upload_runs(used, "rBCPS", "rBCPD", slots=s.get("pal_slots"))
    pal = None
    if sprites and (s["menu"] or s["options"]):
        pal = project["cursor"]["palette"]
    obj_pals = [pal] if pal is not None else []
    if s.get("fight"):
        f = s["fight"]
        obj_pals = sorted({f["player"]["palette"], f["player"]["tired_palette"], f["referee"]["palette"]})
    at = (max(used) + 1) * 8                            # HL's offset into the fade row so far
    for pal in obj_pals:
        skip = (len(project["palettes"]) + pal) * 8 - at
        if skip:
            lines += [f"    ld de, {skip}", "    add hl, de"]
        lines += [f"    ld a, $80 | {pal * 8}", "    ldh [rOCPS], a", "    ld c, LOW(rOCPD)",
                  "    REPT 8", "        ld a, [hl+]", "        ldh [c], a", "    ENDR"]
        at = (len(project["palettes"]) + pal + 1) * 8
    lines.append("    ret")
    return "\n".join(lines)


def _patch_routine(name, rows, comment):
    """A fully unrolled map patch: HL = source tiles, row by row. rows = [(map offset, width)].
    About 20 cycles per tile, run during VBlank."""
    lines = [f"{name}:                ; {comment}"]
    for offset, width in rows:
        lines.append(f"    ld de, $9800 + {offset}")
        lines += ["    REPT " + str(width), "        ld a, [hl+]", "        ld [de], a", "        inc e", "    ENDR"]
    lines.append("    ret")
    return "\n".join(lines)


def _press_code(i, s, index_of, corner=False):
    p = s["press"]
    pr = p["prompt"]
    blink = pr and pr["blink"]
    idle = f"""    ldh a, [hFrame]         ; the prompt blinks every 32 frames
    and 31
    ret nz
    ldh a, [hPromptHidden]
    xor 1
    ldh [hPromptHidden], a
    ld hl, Scene{i}PromptShown
    jr z, .queue
    ld hl, Scene{i}PromptHidden
.queue:
    QUEUE_PATCH Scene{i}PromptPatch
    ret""" if blink else "    ret"
    reshow = f"""    ldh a, [hPromptHidden]  ; make sure the prompt is showing
    and a
    ret z
    xor a
    ldh [hPromptHidden], a
    ld hl, Scene{i}PromptShown
    QUEUE_PATCH Scene{i}PromptPatch
""" if blink else ""
    flip = f"""    and 1                   ; odd counts show the pressed frame, so it ends pressed
    ld hl, Scene{i}AreaPressed
    jr nz, .queue
    ld hl, Scene{i}AreaNormal
.queue:
    QUEUE_PATCH Scene{i}AreaPatch
    ret""" if p["area"] else "    ret"
    select = """    ldh a, [hPadNew]        ; the corner: Select gets the trainer working faster
    and PADF_SELECT
    call nz, FtCornerSelect
""" if corner else ""
    return f"""Scene{i}Update:              ; press-start screen: wait for Start or A
{select}    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr nz, .press
{idle}
.press:
    ld a, SFX_PRESS_START
    call PlaySfx
    ld a, {p['flashes'] * 2 - 1}
    ldh [hCounter], a
    ld a, 1
    ldh [hTimer], a
    SET_UPDATE Scene{i}Press
{reshow}    ret

Scene{i}Press:              ; flip the flash area, then go
    ld hl, hTimer
    dec [hl]
    ret nz
    ld [hl], BLINK_FRAMES
    ld hl, hCounter
    ld a, [hl]
    and a
    jr z, .go
    dec [hl]
{flip}
.go:
    ld a, {index_of[p['target']]}
    jp StartTransition
"""


def _press_data(i, s):
    lines = []
    if s["prompt_cells"]:
        lines += [f"Scene{i}PromptShown:", "    db " + ", ".join(f"${c[1]:02X}" for c in s["prompt_cells"]),
                  f"Scene{i}PromptHidden:", "    db " + ", ".join(f"${c[2]:02X}" for c in s["prompt_cells"])]
    if s["area_cells"]:
        lines.append(f"Scene{i}AreaNormal:")
        lines += ["    db " + ", ".join(f"${c[1]:02X}" for c in row) for row in s["area_cells"]]
        lines.append(f"Scene{i}AreaPressed:")
        lines += ["    db " + ", ".join(f"${c[2]:02X}" for c in row) for row in s["area_cells"]]
    return "\n".join(lines)


def _press_patches(i, s):
    p, out = s["press"], []
    if p["prompt"] and p["prompt"]["blink"]:
        pr = p["prompt"]
        out.append(_patch_routine(f"Scene{i}PromptPatch", [(pr["y"] * 32 + pr["x"], len(pr["label"]))], "prompt"))
    if p["area"]:
        a = p["area"]
        out.append(_patch_routine(f"Scene{i}AreaPatch", [((a["y"] + r) * 32 + a["x"], a["w"]) for r in range(a["h"])],
                                  f"flash area, {a['w']}x{a['h']} tiles"))
    return "\n\n".join(out)


def _options_code(i, s, index_of, opt_index):
    o = s["options"]
    rows = o["rows"]
    n = len(rows)
    back = f"""    ldh a, [hPadNew]
    and PADF_B
    jr z, .cursor
    ld a, SFX_MENU_BACK
    call PlaySfx
    ld a, {index_of[s['back']]}
    jp StartTransition
""" if s["back"] is not None else ""
    out = [f"""Scene{i}Update:              ; options: up/down pick a row, left/right change it, Start or A continues
    ldh a, [hPadRepeat]
    and a
    jr z, .cursor
    ld b, a
    and PADF_UP | PADF_DOWN
    jr z, .notMove
    ld a, SFX_MENU_MOVE
    call PlaySfx
.notMove:
    bit PAD_DOWN, b
    jr z, .notDown
    ldh a, [hOptRow]
    inc a
    cp {n}
    jr c, .down
    xor a
.down:
    ldh [hOptRow], a
.notDown:
    bit PAD_UP, b
    jr z, .notUp
    ldh a, [hOptRow]
    sub 1
    jr nc, .up
    ld a, {n - 1}
.up:
    ldh [hOptRow], a
.notUp:
    ld c, 1
    bit PAD_RIGHT, b
    call nz, .change
    ld c, -1
    bit PAD_LEFT, b
    call nz, .change
    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr z, .notStart
    ld a, SFX_MENU_CONFIRM
    call PlaySfx
    ld a, {index_of[o['target']]}
    jp StartTransition
.notStart:
{back}.cursor:                    ; ease the cursor to the row's label
    ldh a, [hOptRow]
    add LOW(Scene{i}RowY)
    ld l, a
    adc HIGH(Scene{i}RowY)
    sub l
    ld h, a
    ldh a, [hCursorY]
    ld c, a
    ld a, [hl]
    sub c
    jr z, .yDone
    ld d, a
    sra a
    jr nz, .move
    ld a, d
.move:
    add c
    ldh [hCursorY], a
.yDone:
    ldh a, [hOptRow]
    add LOW(Scene{i}RowX)
    ld l, a
    adc HIGH(Scene{i}RowX)
    sub l
    ld h, a
    ld a, [hl]
    ldh [hCursorX], a
    ret
.change:                    ; C = +1 or -1 for the current row
    ldh a, [hOptRow]
    add a
    add LOW(Scene{i}RowChange)
    ld l, a
    adc HIGH(Scene{i}RowChange)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl
"""]
    for r_i, r in enumerate(rows):
        g = opt_index[(i, r_i)]
        slider = ""
        if r.get("slider"):
            slider = f"""    push af
    add LOW(Scene{i}Row{r_i}Slider)
    ld l, a
    adc HIGH(Scene{i}Row{r_i}Slider)
    sub l
    ld h, a
    ld a, [hl]
    ldh [hMarkerX], a
    pop af
"""
        out.append(f"""Scene{i}Row{r_i}Change:       ; "{r['label']}": add C, staying within {r['count']} values
    ld hl, wOptions + {r['symbol']}
    ld a, [hl]
    add c
    cp {r['count']}
    ret nc
    ld [hl], a
    push af
    ld a, SFX_OPTION_CHANGE
    call PlaySfx
    pop af
{slider}    call Scene{i}Row{r_i}Source
    QUEUE_PATCH Scene{i}Row{r_i}Patch
    ret

Scene{i}Row{r_i}Source:       ; HL = the value area's tiles for value A
    add a
    add LOW(Scene{i}Row{r_i}Strips)
    ld l, a
    adc HIGH(Scene{i}Row{r_i}Strips)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ret
""")
    return "\n".join(out)


def _pass_code(i, s, index_of):
    """A pass key: left/right picks a digit, up/down changes it (both repeat), Start or A goes on. The chosen
    digit blinks; one map patch a frame (the digit left behind first)."""
    pk = s["pass_key"]
    back = f"""    ldh a, [hPadNew]
    and PADF_B
    jr z, .show
    ld a, SFX_MENU_BACK
    call PlaySfx
    ld a, {index_of[s['back']]}
    jp StartTransition
""" if s["back"] is not None else ""
    return f"""Scene{i}Update:              ; pass key: left/right pick a digit, up/down change it, Start goes on
    ldh a, [hPadRepeat]
    ld b, a
    ld c, 0                 ; C: a digit changed (show it now)
    bit PAD_RIGHT, b
    jr z, .notRight
    call .leave
    inc a
    cp {len(pk['cells'])}
    jr c, .right
    xor a
.right:
    ldh [hPassPos], a
.notRight:
    bit PAD_LEFT, b
    jr z, .notLeft
    call .leave
    sub 1
    jr nc, .left
    ld a, {len(pk['cells']) - 1}
.left:
    ldh [hPassPos], a
.notLeft:
    ld a, b
    and PADF_UP | PADF_DOWN
    jr z, .notChange
    ld a, SFX_OPTION_CHANGE
    call PlaySfx
    ld c, 1
    call .digit
    bit PAD_UP, b
    jr z, .notUp
    inc a
    cp 10
    jr c, .up
    xor a
.up:
    ld [hl], a
.notUp:
    bit PAD_DOWN, b
    jr z, .notChange
    ld a, [hl]
    sub 1
    jr nc, .down
    ld a, 9
.down:
    ld [hl], a
.notChange:
    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr z, .notStart
    ld a, SFX_MENU_CONFIRM
    call PlaySfx
    ld a, {index_of[pk['target']]}
    jp StartTransition
.notStart:
{back}.show:                      ; the digit left behind, else the chosen one: shown, or every 16 frames not
    ldh a, [hPassOld]
    cp $FF
    jr z, .chosen
    ld d, a
    ld a, $FF
    ldh [hPassOld], a
    ld a, d
    ld e, 0
    jr .patch
.chosen:
    ldh a, [hPassPos]
    ld d, a
    ld e, c
    dec e                   ; changed: E = 0, shown
    jr z, .patch
    ldh a, [hFrame]
    and $10
    ld e, a
.patch:                     ; D = digit position, E nonzero: hide it
    ld a, d
    add a
    add d
    add a
    add a
    sub d                   ; 11 tiles per digit: 0-9 and blank
    ld c, a
    ld a, e
    and a
    ld a, 10
    jr nz, .tile
    push bc
    ld a, d
    call .digitAt
    pop bc
.tile:
    add c
    add LOW(Scene{i}PassTiles)
    ld l, a
    adc HIGH(Scene{i}PassTiles)
    sub l
    ld h, a
    ld a, [hl]
    ld [wPassPatch], a
    ld a, d
    add a
    add LOW(Scene{i}PassCells)
    ld l, a
    adc HIGH(Scene{i}PassCells)
    sub l
    ld h, a
    ld a, [hl+]
    ld [wPassPatch + 1], a
    ld a, [hl]
    ld [wPassPatch + 2], a
    ld hl, wPassPatch
    QUEUE_PATCH PassPatch
    ret
.leave:                     ; moving: the digit left behind is shown again; A = position
    ld a, SFX_MENU_MOVE
    call PlaySfx
    ldh a, [hPassPos]
    ldh [hPassOld], a
    ret
.digit:                     ; HL -> the chosen digit, A = it
    ldh a, [hPassPos]
.digitAt:                   ; (A = position)
    add LOW(wPassKey)
    ld l, a
    adc HIGH(wPassKey)
    sub l
    ld h, a
    ld a, [hl]
    ret

Scene{i}PassLoad:            ; (screen off) every digit shown, the first chosen
    ld a, [wPassSet]        ; the first visit since power on: all zeros
    cp $A5
    jr z, .set
    ld a, $A5
    ld [wPassSet], a
    ld hl, wPassKey
    ld b, {len(pk['cells'])}
    xor a
.zero:
    ld [hl+], a
    dec b
    jr nz, .zero
.set:
    xor a
    ldh [hPassPos], a
    ld a, $FF
    ldh [hPassOld], a
    ld a, {len(pk['cells'])}
    ld [wPassPatch], a      ; (the count, here)
    ld hl, wPassKey
    ld de, Scene{i}PassCells
    ld bc, Scene{i}PassTiles
.digit:
    ld a, [hl]              ; (anything but 0-9 is 0)
    cp 10
    jr c, .ok
    xor a
    ld [hl], a
.ok:
    inc hl
    push hl
    add c
    ld l, a
    adc b
    sub l
    ld h, a
    ld a, [hl]              ; its tile
    push af
    ld a, [de]
    ld l, a
    inc de
    ld a, [de]
    ld h, a
    inc de
    pop af
    ld [hl], a
    ld a, c
    add 11
    ld c, a
    adc b
    sub c
    ld b, a
    pop hl
    ld a, [wPassPatch]
    dec a
    ld [wPassPatch], a
    jr nz, .digit
    ret

Scene{i}PassTiles:           ; per digit: its tile showing 0-9, then without it
{_db([t for cell in s['pass_tiles'] for t in cell], 11)}
Scene{i}PassCells:           ; their map addresses
    dw {", ".join(f"$9800 + {(c // CW) * 32 + c % CW}" for c in pk["cells"])}
"""


def _options_load(i, s, opt_index, markers):
    """At scene load (screen off): cursor on the first row, every row showing its current value."""
    o = s["options"]
    first = o["rows"][0]
    lines = [f"    ld a, {first['labelY'] * 8 + 16}", "    ldh [hCursorY], a", f"    ld a, {first['labelX'] * 8 - 11 + 8}",
             "    ldh [hCursorX], a", "    xor a", "    ldh [hOptRow], a"]
    has_slider = False
    for r_i, r in enumerate(o["rows"]):
        lines += [f"    ld a, [wOptions + {r['symbol']}]", f"    call Scene{i}Row{r_i}Source", f"    call Scene{i}Row{r_i}Patch"]
        if r.get("slider"):
            has_slider = True
            lines += [f"    ld a, [wOptions + {r['symbol']}]", f"    add LOW(Scene{i}Row{r_i}Slider)", "    ld l, a",
                      f"    adc HIGH(Scene{i}Row{r_i}Slider)", "    sub l", "    ld h, a", "    ld a, [hl]", "    ldh [hMarkerX], a",
                      f"    ld a, {r['slider']['y'] + 16}", "    ldh [hMarkerY], a"]
    if markers and not has_slider:
        lines += ["    xor a", "    ldh [hMarkerY], a"]
    return lines


def _options_data(i, s):
    o, lines = s["options"], []
    lines += [f"Scene{i}RowY:", "    db " + ", ".join(str(r["labelY"] * 8 + 16) for r in o["rows"]),
              f"Scene{i}RowX:", "    db " + ", ".join(str(r["labelX"] * 8 - 11 + 8) for r in o["rows"]),
              f"Scene{i}RowChange:", "    dw " + ", ".join(f"Scene{i}Row{k}Change" for k in range(len(o["rows"])))]
    for r_i, (r, strips) in enumerate(zip(o["rows"], s["option_strips"])):
        lines += [f"Scene{i}Row{r_i}Strips:", "    dw " + ", ".join(f".v{v}" for v in range(r["count"]))]
        for v, tiles in enumerate(strips):
            lines += [f".v{v}:", "    db " + ", ".join(f"${t:02X}" for t in tiles)]
        if r.get("slider"):
            b = r["slider"]
            xs = [b["x0"] + round((b["x1"] - b["x0"]) * v / (r["count"] - 1)) + 8 for v in range(r["count"])]
            lines += [f"Scene{i}Row{r_i}Slider:", "    db " + ", ".join(str(x) for x in xs)]
    return "\n".join(lines)


GRID_ROWS_PER_FRAME = 12   # rows the puzzle redraws per VBlank at most; the rest wait a frame


def _puzzle_asm(i, s, index_of, opt_rows):
    """Constants, tables and generated drawing code for the puzzle scene, plus the hand-written kit."""
    from . import puzzle as kit
    pz = s["puzzle"]
    g = pz["grid"]
    w, h = g["w"], g["h"]
    by_symbol = {r["symbol"]: r for r in opt_rows}
    nl = "\n"
    speed = pz["speed_option"]
    if speed and speed in by_symbol:
        read_speed = f"""    ld a, [wOptions + {speed}]
    cp 3
    jr c, .speed\\@
    ld a, 2
.speed\\@:"""
    else:
        read_speed = "    ld a, 1"
    lvl = pz["level_option"]
    read_level = f"    ld a, [wOptions + {lvl}]\n    add {by_symbol[lvl]['min']}" if lvl and lvl in by_symbol else "    ld a, 3"
    rows = []
    for r in range(h):
        rows.append(f"""GridRow{r}:
    xor a
    ld [wDirtyRows + {r}], a
    ld hl, wGridTiles + {r * w}
    ld de, $9800 + {(g['y'] + r) * 32 + g['x']}
    REPT {w}
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ret""")
    draw = []
    for r in range(h):
        draw.append(f"""    ld a, [wDirtyRows + {r}]
    and a
    jr z, .row{r}
    call GridRow{r}
    dec c
    jp z, .later
.row{r}:""")
    hud_cells = []
    if pz["score"]:
        hud_cells += [(k, c) for k, c in enumerate(pz["score"]["cells"])]
    if pz["virus_count"]:
        hud_cells += [(6 + k, c) for k, c in enumerate(pz["virus_count"]["cells"])]
    addr = lambda c: f"$9800 + {(c // CW) * 32 + c % CW}"
    hud_draw = nl.join(f"    ld a, [wHudTiles + {k}]\n    ld [{addr(c)}], a" for k, c in hud_cells)
    if pz["next"]:
        n0, n1 = pz["next"]["cells"]
        next_draw = f"""    ldh a, [hPzNext1]
    or SH_LEFT << 2
    ld e, a
    ld d, HIGH(KitTileLUT)
    ld a, [de]
    ld [{addr(n0)}], a
    ldh a, [hPzNext2]
    or SH_RIGHT << 2
    ld e, a
    ld a, [de]
    ld [{addr(n1)}], a"""
    else:
        next_draw = ""
    if pz["level"]:
        l0, l1 = pz["level"]["cells"]
        level_draw = f"""    PZ_READ_LEVEL
    ld b, -1
.tens:
    inc b
    sub 10
    jr nc, .tens
    add 10 + 10             ; ones digit, offset into the second cell's table
    ld c, a
    ld a, b
    ld hl, LevelDigits
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
    ld [{addr(l0)}], a
    ld a, c
    ld hl, LevelDigits
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
    ld [{addr(l1)}], a"""
    else:
        level_draw = ""
    hud = s["hud"]
    score_tables = [d for cell in hud.get("score", [[0] * 10] * 6) for d in cell]
    virus_tables = [d for cell in hud.get("virus_count", [[0] * 10] * 2) for d in cell]
    level_tables = [d for cell in hud.get("level", [[0] * 10] * 2) for d in cell]
    row_of = [i // w for i in range(w * h)]
    col_of = [i % w for i in range(w * h)]
    return f"""; ---- Puzzle grid: "{s['name']}" ----
DEF PZ_W EQU {w}
DEF PZ_H EQU {h}
DEF PZ_SIZE EQU {w * h}
DEF PZ_VIRUS_TOP EQU {kit.virus_top(h)}
DEF PZ_MAX_VIRUSES EQU {kit.max_viruses(w, h)}
DEF PZ_WIN_SCENE EQU {index_of[pz['win']]}
DEF PZ_LOSE_SCENE EQU {index_of[pz['lose']]}

MACRO PZ_READ_SPEED         ; A = speed 0-2 ({speed or "default MED"})
{read_speed}
ENDM

MACRO PZ_READ_LEVEL         ; A = level ({lvl or "default 3"})
{read_level}
ENDM

{KIT_PUZZLE}
Scene{i}Update:
    jp PuzzleUpdate

; Redraw changed rows during VBlank, at most {GRID_ROWS_PER_FRAME} per frame.
GridDraw:
    xor a
    ldh [hGridDirty], a
    ld c, {GRID_ROWS_PER_FRAME}
{nl.join(draw)}
    ret
.later:
    ld a, 1
    ldh [hGridDirty], a
    ret

GridDrawAll:                ; with the screen off
{nl.join(f"    call GridRow{r}" for r in range(h))}
    ret

{nl.join(rows)}

HudDraw:
    xor a
    ldh [hHudDirty], a
{hud_draw}
    ret

NextDraw:
    xor a
    ldh [hNextDirty], a
{next_draw}
    ret

LevelDraw:                  ; with the screen off
{level_draw}
    ret

PuzzleLoad:                 ; with the screen off
    call PuzzleStart
    call GridDrawAll
    call HudDraw
    call NextDraw
    call LevelDraw
    xor a
    ldh [hGridDirty], a
    ret

SECTION "Data: Puzzle tiles", ROM0, ALIGN[8]
KitTileLUT:                 ; cell byte (shape << 2 | color) -> tile
    db {", ".join(f"${t:02X}" for t in s["kit_lut"])}

SECTION "Data: Puzzle rows", ROM0, ALIGN[8]
RowOf:                      ; cell index -> row
{_db(row_of)}
    ds 256 - PZ_SIZE
ColOf:                      ; cell index -> column (the page after RowOf)
{_db(col_of)}

SECTION "Data: Puzzle", ROM0
RowStart:
    db {", ".join(str(r * w) for r in range(h))}
SpeedFrames:
    db {", ".join(str(v) for v in kit.SPEED_FRAMES)}
PointsBySpeed:              ; BCD hundreds per virus
    db {", ".join(f"${v:02X}" for v in kit.POINTS)}
HudScoreDigits:
{_db(score_tables, 10)}
HudVirusDigits:
{_db(virus_tables, 10)}
LevelDigits:
{_db(level_tables, 10)}
"""


MAP_BYTES = 2 * 18 * 32              # a scene's map and palette map
FIGHT_BYTES = 12 * 1024             # a fight's poses, sprite tiles and tables (about)
BANK_THRESHOLD = 20 * 1024          # scene data beyond this leaves too little of 32 KB for code


def _bank_switch():
    """Map the scene's data bank (MBC5) before its load routine runs; it stays mapped while the scene runs."""
    return """    push hl
    ldh a, [hScene]
    add LOW(SceneBanks)
    ld l, a
    adc HIGH(SceneBanks)
    sub l
    ld h, a
    ld a, [hl]
    ld [$2000], a
    pop hl
"""


def _fight_asm(i, s, index_of, project, banked=False):
    """Constants, tables and generated HUD code for the fight scene, plus the hand-written kit."""
    from . import fight as kit
    ft = s["fight"]
    nl = "\n"
    tiles = s["cell_tiles"]
    pose_ids = "\n".join(f"DEF RP_{p.upper()} EQU {k}" for k, p in enumerate(kit.RIVAL_POSES))
    pp_ids = "\n".join(f"DEF PP_{p.upper()} EQU {k}" for k, p in enumerate(kit.PLAYER_POSES))
    tuning = "\n".join(f"DEF FT_{k} EQU {v}" for k, v in kit.TUNING.items())

    def rows(values_for_pose, static):
        """The rival's map rows in full (32 wide, as DMA writes them), with the pose in his area."""
        padded = _pad_rows(static, True)
        out = []
        for r in range(kit.REGION_H):
            row = list(padded[(ft["y"] + r) * 32:(ft["y"] + r + 1) * 32])
            row[ft["x"]:ft["x"] + kit.REGION_W] = values_for_pose[r * kit.REGION_W:(r + 1) * kit.REGION_W]
            out += row
        return out
    poses = [f"RivalMap_{p}:\n" + _db(rows(s["fight_maps"][p], tiles), 32) + "\n"
             + _db(rows(s["fight_attrs"][p], s["cell_pal"]), 32) for p in kit.RIVAL_POSES]
    sprites = []
    for p in kit.PLAYER_POSES:
        sp = s["fight_sprites"][p]
        sprites.append(f"Player_{p}:                 ; {len(sp)} sprites: dy, dx, tile, attributes\n    db {len(sp)}\n"
                       + "\n".join(f"    db {dy}, {dx}, {t}, ${a:02X}" for dy, dx, t, a in sp))
    ref_sprites = []
    for p in kit.REF_POSES:
        sp = s["fight_ref_sprites"][p]
        ref_sprites.append(f"Ref_{p}:\n    db {len(sp)}\n" + "\n".join(f"    db {dy}, {dx}, {t}, ${a:02X}" for dy, dx, t, a in sp))
    hud_draw = nl.join(f"    ld a, [wFtHud + {k}]\n    ld [$9800 + {(c // CW) * 32 + c % CW}], a"
                       for k, c in enumerate(s["fight_hud_cells"]))
    script = lambda items: nl.join(f"    db OP_{op.upper()}, {arg}" for op, arg in items)
    timed = nl.join(f"    db {r}, {m}, ${sec // 10}{sec % 10}, OP_{op.upper()}, {arg}" for r, m, sec, op, arg in ft["timed"])
    obj_bytes = [b for t in s["fight_obj"] for b in encode_tile(list(t))]
    rival_pals = sorted(set(ft["palettes"].values()))
    sw = s["fight_swap"]
    swap_a = max(0, min(sw["count"], 128 - sw["first"]))
    vram_a = 0x9000 + 16 * sw["first"] if swap_a else 0
    vram_b = 0x8800 + 16 * (max(sw["first"], 128) - 128)
    swap_sets = [[b for t in tiles_ for b in encode_tile(list(t))] for tiles_ in sw["sets"]]
    crowd_y = ft["crowd_row"]
    flash_upload = nl.join(f"    ld a, $80 | {k * 8}\n    ldh [rBCPS], a\n    ld c, LOW(rBCPD)\n    REPT 8\n        ld a, [hl+]\n        ldh [c], a\n    ENDR"
                           for k in rival_pals)
    nes = ft.get("nes")
    nes_defs, nes_data = "", ""
    if nes:
        parts = _nes_parts()
        hx, hy = nes["home"]
        off = lambda v, home: max(-127, min(127, round((((v - home + 128) & 0xFF) - 128) * nes["scale"])))
        sound_head, _, sound_code = KIT_NES_SOUND.partition(";;PART sound")
        nes_defs = (f"DEF FT_NES EQU 1\nDEF FT_NES_OFFSET EQU {nes['offset']}   ; the fighter's entry in its bank\n"
                    "DEF FT_NES_DOWN_MAX EQU 8       ; pixels he may move down (his band moves over the floor)\n"
                    "DEF FT_NES_UP_MAX EQU 48        ; and up (his band rises to the HUD; inside it, over the tail rows)\n"
                    )
        set_of = {p: k for k, (name, ps) in enumerate(kit.POSE_SETS.items()) for p in ps}
        nes_data = f"""
SECTION "NES fighter", ROMX[$4000]
NesFighter::                ; Punch-Out!!'s fighter bank, as it was at $8000 (see kit_nes.asm)
{_db(list(nes["bank"]))}
NesPoseMap:                 ; NES frame number -> our pose; then the same drawn mirrored
{_db(nes["frames"])}
NesOffsetX:                 ; NES X -> pixels right of his place
{_db([off(v, hx) & 0xFF for v in range(256)])}
NesOffsetY:                 ; NES Y -> pixels down
{_db([off(v, hy) & 0xFF for v in range(256)])}
RivalPoseSet:               ; per pose: the set whose tiles it needs ($FF: always in video memory)
{_db([set_of.get(p, 0xFF) for p in kit.RIVAL_POSES])}
{parts["fighter"]}

SECTION "NES Mac", ROMX[$4000]
NesMac::                    ; Little Mac: Punch-Out!!'s PRG bank B, as it was at $8000
{_db(list(nes["mac"]))}
MacPoseMap:                 ; NES Mac frame number -> our player pose
{_db(nes["mac_frames"])}
MacOffsetX:                 ; NES $15 -> pixels right of his place ($15 scrolls the NES background, Mac in it: up is left)
{_db([max(-127, min(127, round((((nes["mac_home"] - v + 128) & 0xFF) - 128) * nes["mac_scale"]))) & 0xFF for v in range(256)])}
{parts["mac"]}

{parts["head"]}
SECTION "NES engine: shared", ROM0
{parts["common"]}
"""
        if nes.get("sound"):
            nes_data += f"""
{sound_head}
SECTION "NES sound", ROMX[$4000]
NesSnd::                    ; Punch-Out!!'s sound bank (PRG bank 8), as it was at $8000 (see kit_nes_sound.asm)
{_db(list(nes["sound"]))}
NesSndFix:                  ; and its tables in the fixed bank, NES $F400-$F8FF
{_db(list(nes["sound_fixed"]))}
{_dmc_tables(nes)}
{sound_code}
"""
    # his band's last two rows without him: the scene's own tiles, his columns filled from the one beside them
    tail_t, tail_p = [], []
    for row in range(ft["y"] + kit.REGION_H - 6, ft["y"] + kit.REGION_H):
        side = ft["x"] - 1 if ft["x"] > 0 else ft["x"] + kit.REGION_W
        cols = [side if ft["x"] <= c < ft["x"] + kit.REGION_W else c for c in range(CW)]
        tail_t += [s["cell_tiles"][row * CW + c] for c in cols]
        tail_p += [s["cell_pal"][row * CW + c] for c in cols]
    nes_data += f"""
SECTION "Fight: band tail", ROM0
FtTailTiles:
{_db(_pad_rows(tail_t, True), 32)}
FtTailAttr:
{_db(_pad_rows(tail_p, True), 32)}
"""
    return f"""; ---- Fight: "{s['name']}" ----
{nes_defs}
DEF FT_WIN_SCENE EQU {index_of[ft['win']]}
DEF FT_LOSE_SCENE EQU {index_of[ft['lose']]}
DEF FT_CORNER_SCENE EQU {index_of[ft['corner']] if ft['corner'] is not None else '$FF'}   ; between rounds
DEF FT_REGION_X EQU {ft['x']}
DEF FT_REGION_W EQU {kit.REGION_W}
DEF FT_REGION_H EQU {kit.REGION_H}
DEF FT_REGION_ROW EQU $9800 + {ft['y'] * 32}     ; the rival's first map row
DEF FT_CROWD_ROW EQU $9800 + {crowd_y * 32}
DEF FT_CROWD_W EQU {CW}
DEF FT_FLASH_TILE EQU {s['fight_flash_tile']}
DEF FT_BAND_TOP EQU {ft['y'] * 8 - 1}               ; LY where his band's scroll starts (a line early: the change lands in time)
DEF FT_BAND_BOTTOM EQU {(ft['y'] + kit.REGION_H) * 8 - 1}
DEF FT_TAIL_ROWS EQU 6                              ; off-screen map rows: the background of his band's last rows,
DEF FT_TAIL_ROW EQU 24                              ; without him, for when he's shown higher in it
DEF FT_TAIL_SCY EQU (FT_TAIL_ROW - {ft['y'] + kit.REGION_H} + FT_TAIL_ROWS) * 8 & $FF
DEF FT_HEADROOM EQU 0                               ; his band never rises over the crowd and ropes
DEF FT_STAND_UP EQU 6                               ; standing, he shifts up into his frame's empty top only
DEF FT_POSE_BYTES EQU {kit.REGION_H * 32}          ; map rows per pose; the same again for palettes
DEF FT_HUD_CELLS EQU {len(s['fight_hud_cells'])}
DEF FT_SWAP_COUNT EQU {sw['count']}                 ; tiles in the shared area (one pose set at a time)
DEF SET_ATTACK EQU 0
DEF SET_KNOCKDOWN EQU 1
DEF SET_SPECIAL EQU 2
DEF FT_SWAP_A_COUNT EQU {swap_a}
DEF FT_SWAP_VRAM_A EQU ${vram_a:04X}
DEF FT_SWAP_VRAM_B EQU ${vram_b:04X}
DEF FT_SWAP_PER_FRAME EQU 6                         ; original: by CPU (unrolled), a few tiles per VBlank
DEF FT_SWAP_PER_FRAME_CGB EQU 32                    ; Color: by GDMA
DEF FT_BAR_CELLS EQU {kit.BAR_CELLS}
DEF FT_HEALTH EQU {kit.HEALTH}
DEF FT_OBJ_FIRST EQU {kit.OBJ_FIRST_TILE}
DEF FT_OBJ_TILES EQU {len(s['fight_obj'])}
DEF FT_COUNT_TILE EQU {s['fight_count_tile']}
DEF FT_PLAYER_W EQU {kit.PLAYER_W}
DEF FT_PLAYER_X EQU {kit.PLAYER_X + 8}       ; OAM coordinates of the player's top-left
DEF FT_PLAYER_Y EQU {144 - kit.PLAYER_H + 16}
DEF FT_PLAYER_PAL EQU {ft['player']['palette']}
DEF FT_TIRED_PAL EQU {ft['player']['tired_palette']}
DEF FT_REF_ATTR EQU {ft['referee']['palette'] | 0x10}
DEF FT_STAR_TILE EQU {s['fight_star_tile']}
DEF FT_DROP_TILE EQU {s['fight_drop_tile']}
DEF FT_SPARK_TILE EQU {s['fight_spark_tile']}
DEF FT_FX_STARS EQU {int(ft['effects']['stars'])}             ; sprite effects over the art: 1 on, 0 off
DEF FT_FX_SWEAT EQU {int(ft['effects']['sweat'])}
DEF FT_FX_SPARK EQU {int(ft['effects']['spark'])}
DEF FT_BUBBLE_LEFT EQU {s['fight_bubble'][0]}
DEF FT_BUBBLE_RIGHT EQU {s['fight_bubble'][1]}
DEF FT_STAR_X EQU {ft['x'] * 8 + 32 + 8 - 4}       ; OAM x/y of the circle around his head (standing)
DEF FT_STAR_Y EQU {ft['y'] * 8 + 16 + 2}
DEF FT_REF_Y EQU {kit.REF_Y}
DEF FT_SAY_Y EQU {kit.REF_Y - 4}
DEF FT_PLAYER_GETUP_1 EQU {kit.PLAYER_GETUP_HEALTH[0]}
DEF FT_PLAYER_GETUP_2 EQU {kit.PLAYER_GETUP_HEALTH[1]}
{pose_ids}
{pp_ids}
{tuning}

{KIT_FIGHT}
Scene{i}Update:
    jp FightUpdate

FtHudDraw:                  ; during VBlank: every HUD tile
{hud_draw}
    ret

FtFlashPalettes:            ; during VBlank, Color only: the rival's palettes, white-flashed or normal
    ldh a, [hIsCGB]
    and a
    ret z
    ldh a, [hFtFlashShown]
    and a
    ld hl, RivalPalNormal
    jr z, .upload
    ld hl, RivalPalFlash
.upload:
{flash_upload}
    ret

SECTION "Data: Rival poses", {"ROMX" if banked else "ROM0"}, ALIGN[4]   ; per pose: 10 full map rows, then their palettes
{nl.join(poses)}

SECTION "Data: Rival swap", {"ROMX" if banked else "ROM0"}, ALIGN[4]
FtSwapSet0:                 ; attack poses (loaded with the scene, and put back)
{_db(swap_sets[0])}
FtSwapSet1:                 ; knockdown
{_db(swap_sets[1])}
FtSwapSet2:                 ; special: the taunt, the arm pop
{_db(swap_sets[2])}

SECTION "Data: Fight", {"ROMX" if banked else "ROM0"}   ; mapped while the fight runs
RivalMaps:
    dw {", ".join(f"RivalMap_{p}" for p in kit.RIVAL_POSES)}
CrowdMap:                   ; the crowd row's tiles, put back after each camera flash
    db {", ".join(f"${t:02X}" for t in s['cell_tiles'][crowd_y * CW:(crowd_y + 1) * CW])}
RivalPalNormal:
    dw {", ".join(_rgb555(project["palettes"][k]).split(", ")[j] for k in rival_pals for j in range(4))}
RivalPalFlash:              ; a hit flushes him red; the background and outline stay
    dw {", ".join(_rgb555([c if j in (0, 3) else ([31, 16, 12] if j == 1 else [26, 4, 4]) for j, c in enumerate(project["palettes"][k])]).split(", ")[j] for k in rival_pals for j in range(4))}
GetupPlan:                  ; per knockdown: count he gets up at, health then
    db {", ".join(f"{c}, {h}" for c, h in kit.GETUP_PLAN)}
RivalScript:                ; op, argument
{script(ft['opening'])}
RivalLoop:
{script(ft['loop'])}
    db $FF
RivalTimed:                 ; round, minute, second (BCD), op, argument
{timed}
    db $FF
FtHudLUT:                   ; per HUD cell: its tile for each value (digits 0-9, bars 0-8)
{_db(s['fight_lut'], 10)}
PlayerPoses:
    dw {", ".join(f"Player_{p}" for p in kit.PLAYER_POSES)}
{nl.join(sprites)}
RefPoses:
    dw {", ".join(f"Ref_{p}" for p in kit.REF_POSES)}
{nl.join(ref_sprites)}
FtObjTiles:                 ; the player's {len(s['fight_obj']) - len(kit.COUNT_GLYPHS)} tiles, then the count's glyphs
{_db(obj_bytes)}
{nes_data}
SECTION "Code: Scenes after the fight", ROM0   ; the next scenes' code must not land in the data bank

"""


def _confirm_asm(i, s, project):
    """A menu choice played out (menu["confirm"]): the steps as data, and the sprite's OAM template."""
    nl = "\n"
    c = s["menu"]["confirm"]
    slots = s.get("pal_slots") or {p: p for p in range(8)}
    lum = lambda col: 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
    shade = lambda col: 3 - min(3, int(lum(col) / 31 * 4))
    used = set(s.get("pal_used") or s["cell_pal"])
    rows = []
    for st in c["steps"]:
        flags = (1 if st["colors"] else 0) | (2 if st["front"] else 0)
        cols = st["colors"] or [[0, 0, 0]] * 3
        rgb = [b for col in cols for b in (col[0] | col[1] << 5 & 0xFF, (col[1] >> 3) | col[2] << 2)]
        obp = sum(shade(col) << (2 * (k + 1)) for k, col in enumerate(cols))
        # the original Game Boy: one palette for all, so a shade lighter for the flash, all dark when they go black
        black = st["bg"] and all(max(max(col) for col in cs) == 0 for cs in st["bg"].values())
        lighter = any(lum(cs[0]) > 4 for cs in st["bg"].values())
        bgp = 0xFF if black else 0b10010000 if lighter else 0b11100100
        recolor = []
        for pal, cs in sorted(st["bg"].items()):
            if pal not in used:
                raise ProjectError([f'Scene "{s["name"]}": the confirm animation recolors a palette the scene doesn\'t use.'])
            recolor += [slots[pal]] + [b for col in cs for b in (col[0] | col[1] << 5 & 0xFF, (col[1] >> 3) | col[2] << 2)]
        rows.append(_db([st["frames"], st["sfx"], flags] + rgb + [obp, bgp, len(st["bg"])] + recolor))
    oam = [b for y, x, t in c["oam"] for b in (y + 16, x + 8, 2 + t)]
    return f"""Scene{i}ConfirmSteps:        ; per step: frames, NES effect, shown/in front, 3 colors, original's OBP1 and BGP, palettes
{nl.join(rows)}
    db 0
Scene{i}ConfirmOAM:          ; y, x, tile per sprite
{_db(oam, 24)}
    db 0
Scene{i}ConfirmTiles:
{_db([b for t in c["tiles"] for b in encode_tile(t)])}
"""


def _menu_code(i, s, fade=False):
    nl = "\n"
    m = s["menu"]
    n = len(m["items"])
    confirm_start = f"""    ld hl, Scene{i}ConfirmSteps  ; the choice plays out first
    ld a, l
    ld [wConfirmPtr], a
    ld a, h
    ld [wConfirmPtr + 1], a
    ld hl, Scene{i}ConfirmOAM
    ld a, l
    ld [wConfirmOAM], a
    ld a, h
    ld [wConfirmOAM + 1], a
    ld a, 1
    ldh [hTimer], a
    SET_UPDATE Scene{i}Confirm
    ret""" if m.get("confirm") else f"""    ld a, {m['blinks'] * 2 + 1}
    ldh [hCounter], a
    ld a, 1
    ldh [hTimer], a
    SET_UPDATE Scene{i}Blink"""
    confirm = f"""
Scene{i}Confirm:            ; a step at a time (VBlank shows it), then the chosen item's scene
    ld hl, hTimer
    dec [hl]
    ret nz
    ld a, [wConfirmPtr]
    ld l, a
    ld a, [wConfirmPtr + 1]
    ld h, a
    ld a, [hl+]
    and a
    jr z, .done
    ldh [hTimer], a
    ld a, [hl+]             ; its sound: the NES game's effect, with its engine
IF DEF(FT_NES_SOUND)
    and a
    jr z, .quiet
    push hl
    call NesSfx
    pop hl
.quiet:
ENDC
    ld de, wConfirmStep     ; the step, for VBlank
    ld a, [hl+]
    ld [de], a
    inc de
    ld b, 9                 ; colors, OBP1, BGP, count
.copy:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copy
    dec de
    ld a, [de]              ; and its palettes: 9 bytes each
    inc de
    ld c, a
    and a
    jr z, .copied
.palette:
    ld b, 9
.palByte:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .palByte
    dec c
    jr nz, .palette
.copied:
    ld a, l
    ld [wConfirmPtr], a
    ld a, h
    ld [wConfirmPtr + 1], a
    ld a, 1
    ldh [hConfirmDirty], a
    ret
.done:
    ld a, [wConfirmStep]
    and a
    jr z, .go
    xor a                   ; the sprite away first (next VBlank), then go
    ld [wConfirmStep], a
    ld [wConfirmStep + 9], a
    inc a
    ldh [hConfirmDirty], a
    ldh [hTimer], a
    ret
.go:
{"    ld a, FADE_STEPS        ; the steps left the screen faded: on with the fade from there" + nl + "    ldh [hFadeStep], a" + nl if fade and m["confirm"]["faded"] else ""}    ldh a, [hSel]
    add LOW(Scene{i}ItemTarget)
    ld l, a
    adc HIGH(Scene{i}ItemTarget)
    sub l
    ld h, a
    ld a, [hl]
    jp StartTransition
""" if m.get("confirm") else ""
    bob = f"""    ldh a, [hFrame]         ; the bob only changes every 8 frames
    ld b, a
    and 7
    ret nz
    ld a, b
    rrca
    rrca
    rrca
    and 7
    add LOW(BobTable)
    ld l, a
    adc HIGH(BobTable)
    sub l
    ld h, a
    ld a, [hl]
    add {cursor_x(m) + 8}
    ldh [hCursorX], a
""" if m["cursor_bob"] else ""
    select = """    bit 2, a                ; Select moves down too
    jr z, .noSelect
    or PADF_DOWN
.noSelect:
""" if m.get("select_moves") else ""
    return f"""Scene{i}Update:              ; menu: up/down{"/Select" if select else ""} to move, A or Start to choose
    ldh a, [hPadRepeat]
    and a
    jr z, .cursor           ; nothing pressed: just animate
{select}    ld b, a
    and PADF_UP | PADF_DOWN
    jr z, .notMove
    ld a, SFX_MENU_MOVE
    call PlaySfx
.notMove:
    bit PAD_DOWN, b
    jr z, .notDown
    ldh a, [hSel]
    inc a
    cp {n}
    jr c, .down
    xor a
.down:
    ldh [hSel], a
.notDown:
    bit PAD_UP, b
    jr z, .notUp
    ldh a, [hSel]
    sub 1
    jr nc, .up
    ld a, {n - 1}
.up:
    ldh [hSel], a
.notUp:
    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr z, .cursor
    ld a, SFX_MENU_CONFIRM
    call PlaySfx
{confirm_start}
.cursor:                    ; ease toward the chosen item: half the distance each frame
    ldh a, [hSel]
    add LOW(Scene{i}CursorY)
    ld l, a
    adc HIGH(Scene{i}CursorY)
    sub l
    ld h, a
    ldh a, [hCursorY]
    ld c, a
    ld a, [hl]
    sub c
    jr z, .yDone
    ld d, a
    sra a
    jr nz, .move
    ld a, d
.move:
    add c
    ldh [hCursorY], a
.yDone:
{bob}    ret

Scene{i}Blink:              ; flash the chosen item, then go to its scene
    ld hl, hTimer
    dec [hl]
    ret nz
    ld [hl], BLINK_FRAMES
    ld hl, hCounter
    dec [hl]
    jr z, .go
    ld b, [hl]
    ldh a, [hSel]
    add a
    ld e, a
    ld d, 0
    ld hl, Scene{i}ItemPatch  ; this item's patch routine
    add hl, de
    ld a, [hl+]
    ldh [hPatchJump + 1], a
    ld a, [hl]
    ldh [hPatchJump + 2], a
    ld hl, Scene{i}ItemShown  ; odd counts show the label, even counts hide it
    bit 0, b
    jr nz, .source
    ld hl, Scene{i}ItemHidden
.source:
    add hl, de
    ld a, [hl+]
    ldh [hPatchSrc], a
    ld a, [hl]
    ldh [hPatchSrc + 1], a
    ld a, 1
    ldh [hPatchPending], a  ; set last: the next VBlank applies the patch
    ret
.go:
    ldh a, [hSel]
    add LOW(Scene{i}ItemTarget)
    ld l, a
    adc HIGH(Scene{i}ItemTarget)
    sub l
    ld h, a
    ld a, [hl]
    jp StartTransition
{confirm}"""


def _menu_data(i, s, index_of):
    m = s["menu"]
    rows = [m["y"] + n * m["spacing"] for n in range(len(m["items"]))]
    lines = [f"Scene{i}CursorY:", "    db " + ", ".join(str(r * 8 + 16) for r in rows),
             f"Scene{i}ItemTarget:", "    db " + ", ".join(str(index_of[it["target"]]) for it in m["items"]),
             f"Scene{i}ItemPatch:", "    dw " + ", ".join(f"Scene{i}Item{n}Patch" for n in range(len(rows)))]
    for kind, idx in (("Shown", 1), ("Hidden", 2)):
        lines += [f"Scene{i}Item{kind}:", "    dw " + ", ".join(f".{kind.lower()}{n}" for n in range(len(rows)))]
        for n, cells in enumerate(s["item_cells"]):
            lines += [f".{kind.lower()}{n}:", "    db " + ", ".join(f"${c[idx]:02X}" for c in cells)]
    return "\n".join(lines)


def generate_asm(project):
    keep = reachable_scenes(project)
    index_of = {orig: new for new, orig in enumerate(keep)}
    scenes = [hw_palettes(project["scenes"][i]) for i in keep]
    menus = any(s["menu"] for s in scenes)
    presses = any(s["press"] for s in scenes)
    options = any(s["options"] for s in scenes)
    passes = any(s.get("pass_key") for s in scenes)
    confirms = any((s["menu"] or {}).get("confirm") for s in scenes)
    markers = any(r.get("slider") for s in scenes if s["options"] for r in s["options"]["rows"])
    puzzles = [i for i, sc in enumerate(scenes) if sc.get("puzzle")]
    if len(puzzles) > 1:
        raise ProjectError(["A project can have one puzzle grid scene for now."])
    fights = [i for i, sc in enumerate(scenes) if sc.get("fight")]
    if len(fights) > 1:
        raise ProjectError(["A project can have one fight scene for now."])
    slides = any(s.get("slide") for s in scenes)
    repeat = menus or options or bool(puzzles) or passes
    opt_index, opt_rows = {}, []
    for i, sc in enumerate(scenes):
        for r_i, r in enumerate((sc["options"] or {}).get("rows", [])):
            opt_index[(i, r_i)] = len(opt_rows)
            opt_rows.append(r)
    names = [r["symbol"] for r in opt_rows]
    if len(set(names)) != len(names):
        dup = sorted({n for n in names if names.count(n) > 1})
        raise ProjectError([f"Two options screens use the same option name ({', '.join(dup)}); rename one."])
    patches = options or menus or passes or any(s["press"] and (s["press"]["area"] or (s["press"]["prompt"] and s["press"]["prompt"]["blink"]))
                           for s in scenes)
    prompt_blink = any(s["press"] and s["press"]["prompt"] and s["press"]["prompt"]["blink"] for s in scenes)
    interactive = menus or presses or options or passes or bool(puzzles) or bool(fights) or slides or \
        any(s["back"] is not None for s in scenes)
    if len(scenes) == 1 and not interactive:
        return _static_asm(project, scenes[0])

    cursor_on = (menus or options) and project["cursor"] is not None
    sprites = cursor_on or bool(fights)
    # Past what a plain 32 KB cartridge holds, scene data moves to switchable banks (MBC5).
    data_bytes = sum(len(s["tiles"]) * 16 + MAP_BYTES for s in scenes) + sum(FIGHT_BYTES for s in scenes if s.get("fight")) \
        + sum(0x4800 + (0x4000 if s["fight"]["nes"].get("sound") else 0)
              for s in scenes if (s.get("fight") or {}).get("nes"))
    banked = data_bytes > BANK_THRESHOLD
    fade = project["transition"]
    nes_sound_any = any((s.get("fight") or {}).get("nes", {}).get("sound") for s in scenes)
    n_bg, n_obj = len(project["palettes"]), len(project["obj_palettes"]) if sprites else 0
    lcdc = LCDC_BG | (LCDC_OBJ if sprites else 0)
    steps = FADE_STEPS if fade else 0
    to = fade["color"] if fade else "white"
    nl = "\n"

    cgb_rows, dmg_rows = [], []
    for step in range(steps + 1):
        row = [f"    dw {_rgb555(fade_palettes(c, step, to))}" for c in project["palettes"]]
        row += [f"    dw {_rgb555(fade_palettes(c, step, to))}" for c in project["obj_palettes"][:n_obj]]
        cgb_rows.append(f".step{step}:\n" + nl.join(row))
        dmg_rows.append(dmg_fade(step, to))

    hram = ["hIsCGB: db", "hScene: db", "hVars:"]
    if interactive:
        hram += ["hUpdateJump: ds 3        ; JP to the current update routine", "hFrame: db", "hPad: db", "hPadNew: db",
                 "hTimer: db", "hNextScene: db", "hSfxTranspose: db       ; semitones up for the next PlaySfx"]
    if fade:
        hram += ["hFadeStep: db", "hPalDirty: db"]
    if menus or presses:
        hram += ["hCounter: db"]
    if menus:
        hram += ["hSel: db"]
    if options:
        hram += ["hOptRow: db"]
    if passes:
        hram += ["hPassPos: db", "hPassOld: db"]
    if confirms:
        hram += ["hConfirmDirty: db        ; a menu choice's animation step for VBlank"]
    if repeat:
        hram += ["hPadRepeat: db          ; pressed this frame, or held long enough to repeat", "hRepeatTimer: db"]
    if markers:
        hram += ["hMarkerY: db", "hMarkerX: db"]
    if puzzles:
        hram += [f"{v}: db" for v in ("hPzState", "hPzTimer", "hPzRow", "hPzCol", "hPzVert", "hPzC1", "hPzC2",
                                       "hPzNext1", "hPzNext2", "hPzDrop", "hPzSpeed", "hPzCapsules", "hPzViruses",
                                       "hPzBase", "hPzEndScene", "hPzStep", "hPzMarked", "hPzCleared", "hPzMoved",
                                       "hRunStart", "hIdx", "hLoop", "hRandLo", "hRandHi", "hGridDirty", "hHudDirty",
                                       "hNextDirty", "hMarkCount", "hPzDownLock", "hPzChain")]
    if patches:
        hram += ["hPatchJump: ds 3         ; JP to the pending map patch", "hPatchSrc: dw", "hPatchPending: db"]
    if prompt_blink:
        hram += ["hPromptHidden: db"]
    if slides:
        hram += ["hScrollY: db            ; SCY: nonzero while a scene slides up into view"]
    if cursor_on:
        hram += ["hCursorY: db", "hCursorX: db"]
    if fights:
        hram += ["hFtActive: db", "hFtHudReady: db", "hFtScx: db", "hFtBandX: db", "hFtBandY: db", "hFtBandTop: db", "hFtBandBottom: db", "hFtBandOn: db", "hFtFlash: db",
                 "hFtFlashShown: db", "hOAMDMA: ds 8           ; OAM DMA routine (runs from HRAM)"]
        if any((scenes[i]["fight"].get("nes") or {}).get("sound") for i in fights):
            hram += ["hNesSound: db           ; nonzero: the NES's sound engine has the sound hardware"]
    hram.append("hVarsEnd:")

    vblank_work = []
    if slides:
        vblank_work.append("""    ldh a, [hScrollY]       ; a scene sliding in: this frame's scroll
    ldh [rSCY], a""")
    if fights:
        vblank_work.append("""    ldh a, [hFtActive]      ; fight: sprites, the rival's pose, the HUD
    and a
    call nz, FtVBlank""")
    if cursor_on:
        vblank_work.append("""    ldh a, [hCursorY]       ; a few sprites: write them straight to OAM (cheaper than DMA)
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""")
    if markers:
        vblank_work.append("""    ldh a, [hMarkerY]
    ld [OAM_CURSOR + 4], a
    ldh a, [hMarkerX]
    ld [OAM_CURSOR + 5], a""")
    if confirms:
        vblank_work.append("""    ldh a, [hConfirmDirty]  ; a menu choice's animation: its sprite and colors
    and a
    call nz, ConfirmApply""")
    if fade:
        vblank_work.append("    ldh a, [hPalDirty]\n    and a\n    call nz, UploadPalettes")
    if puzzles:
        vblank_work.append("""    ldh a, [hGridDirty]     ; puzzle: changed rows, score, next capsule
    and a
    call nz, GridDraw
    ldh a, [hHudDirty]
    and a
    call nz, HudDraw
    ldh a, [hNextDirty]
    and a
    call nz, NextDraw""")
    if patches:
        vblank_work.append("""    ldh a, [hPatchPending]  ; a queued map patch (blink, flash, prompt)
    and a
    jr z, .noPatch
    xor a
    ldh [hPatchPending], a
    ld hl, hPatchSrc
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    call hPatchJump
.noPatch:""")

    boot = []
    if sprites:
        boot.append("""    call ResetOAM           ; OAM is random at power-on""")
    if fights:
        boot.append("""    xor a                   ; RAM is random at power-on: the first fight is a new one
    ld [wFtResume], a""")
    if cursor_on:
        boot.append(f"""    ld a, {project['cursor']['palette']}
    ld [OAM_CURSOR + 3], a  ; cursor palette (Color) / OBP0 (original); tile 0
    ld hl, CursorTile       ; sprite tile 0
    ld de, $8000
    ld b, 16
.cursorTile:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .cursorTile""")
    if markers:
        boot.append(f"""    ld a, 1                 ; slider marker: sprite 1 uses tile 1
    ld [OAM_CURSOR + 6], a
    ld a, {project['cursor']['palette']}
    ld [OAM_CURSOR + 7], a
    ld hl, MarkerTile
    ld de, $8010
    ld b, 16
.markerTile:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .markerTile""")
    if options:
        boot.append("""    ld hl, OptionDefaults   ; options start at their default values and keep them between scenes
    ld de, wOptions
    ld b, OPTION_COUNT
.defaults:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .defaults""")
    boot.append("""    ld hl, hVars            ; clear the HRAM variables
    xor a
    ld b, hVarsEnd - hVars
.clearVars:
    ld [hl+], a
    dec b
    jr nz, .clearVars""")
    if interactive:
        boot.append("    call SfxInit")
        boot.append("    ld a, $C3               ; JP opcode for the update trampoline\n    ldh [hUpdateJump], a")
    if patches:
        boot.append("    ldh [hPatchJump], a     ; ... and for the patch trampoline")

    finish = []
    reset = (["ldh [hSel], a"] if menus else []) + (["ldh [hPatchPending], a"] if patches else []) + \
        (["ldh [hPromptHidden], a"] if prompt_blink else [])
    if reset:
        finish.append("    xor a\n" + "\n".join("    " + r for r in reset))
    if fade:
        finish.append("""    ld a, FADE_STEPS        ; start fully faded; FadeIn brings the colors up
    ldh [hFadeStep], a
    ld a, FADE_FRAMES
    ldh [hTimer], a
    SET_UPDATE FadeIn""")
    elif interactive:
        finish.append("    call SetSceneUpdate")
    if cursor_on:
        finish.append("""    ldh a, [hCursorY]       ; OAM is writable while the screen is off
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""")

    updates = [f"Scene{i}Update" if s["menu"] or s["press"] or s["options"] or s.get("puzzle") or s.get("fight") or s.get("pass_key")
               or s["back"] is not None else "NoUpdate"
               for i, s in enumerate(scenes)]
    scene_code = []
    for i, s in enumerate(scenes):
        if s["menu"]:
            scene_code.append(_menu_code(i, s, bool(fade)))
        elif s["press"]:
            scene_code.append(_press_code(i, s, index_of, corner=any(
                f.get("fight") and f["fight"]["corner"] is not None and index_of[f["fight"]["corner"]] == i for f in scenes)))
        elif s["options"]:
            scene_code.append(_options_code(i, s, index_of, opt_index))
        elif s.get("pass_key"):
            scene_code.append(_pass_code(i, s, index_of))
        elif s.get("puzzle"):
            scene_code.append(_puzzle_asm(i, s, index_of, opt_rows))
        elif s.get("fight"):
            scene_code.append(_fight_asm(i, s, index_of, project, banked))
        elif s["back"] is not None:
            scene_code.append(f"""Scene{i}Update:              ; B goes back
    ldh a, [hPadNew]
    and PADF_B
    ret z
    ld a, SFX_MENU_BACK
    call PlaySfx
    ld a, {index_of[s['back']]}
    jp StartTransition
""")

    sfx_defs, sfx_data = sfx.asm_data(project.get("sound", "arcade"), sfx_groups(scenes))
    option_defs = "\n".join([f"DEF OPTION_COUNT EQU {len(opt_rows)}"] + [f"DEF {r['symbol']} EQU {k}   ; {r['label']}" for k, r in enumerate(opt_rows)]) if options else ""
    out = [f"""; Generated by gbstage from "{project['name']}". Changes here are overwritten on the next build.

{HW_DEFS}
DEF MAP_W EQU {CW}
DEF MAP_H EQU {CH}
DEF FADE_STEPS EQU {steps}
DEF FADE_FRAMES EQU {fade['frames'] if fade else 1}
DEF BLINK_FRAMES EQU {BLINK_FRAMES}
DEF LCDC_ON EQU %{lcdc:08b}
{SLIDE_DEFS if slides else ""}
{"DEF FT_NES_SOUND EQU 1         ; the fight's NES sound engine plays the game's sounds" + nl if nes_sound_any else ""}; joypad bits in hPad / hPadNew (d-pad in the high nibble)
DEF PAD_A EQU 0
DEF PAD_B EQU 1
DEF PAD_START EQU 3
DEF PAD_UP EQU 6
DEF PAD_DOWN EQU 7
DEF PADF_A EQU 1 << PAD_A
DEF PADF_B EQU 1 << PAD_B
DEF PADF_START EQU 1 << PAD_START
DEF PAD_RIGHT EQU 4
DEF PAD_LEFT EQU 5
DEF PADF_UP EQU 1 << PAD_UP
DEF PADF_DOWN EQU 1 << PAD_DOWN
DEF PADF_LEFT EQU 1 << PAD_LEFT
DEF PADF_RIGHT EQU 1 << PAD_RIGHT
{sfx_defs}
{'DEF rOBP1 EQU $FF49' + nl + 'DEF PADF_SELECT EQU 1 << 2' + nl if fights else ('DEF rOBP1 EQU $FF49' + nl if confirms else '')}
MACRO PZ_SFX                ; play sound effect \\1
    ld a, \\1
    call PlaySfx
ENDM

MACRO PZ_SFX_A              ; play sound effect A
    call PlaySfx
ENDM

MACRO PZ_CLEAR_SFX          ; play the clear sound A semitones up
    ldh [hSfxTranspose], a
    ld a, SFX_CLEAR
    call PlaySfx
ENDM
DEF REPEAT_DELAY EQU 16       ; frames a direction is held before it repeats
DEF REPEAT_RATE EQU 4         ; frames between repeats after that
{option_defs}

MACRO QUEUE_PATCH           ; apply patch routine \\1 to the tiles at HL during the next VBlank
    ld a, l
    ldh [hPatchSrc], a
    ld a, h
    ldh [hPatchSrc + 1], a
    ld a, LOW(\\1)
    ldh [hPatchJump + 1], a
    ld a, HIGH(\\1)
    ldh [hPatchJump + 2], a
    ld a, 1
    ldh [hPatchPending], a  ; set last
ENDM

MACRO SET_UPDATE            ; run \\1 every frame from now on
    ld a, LOW(\\1)
    ldh [hUpdateJump + 1], a
    ld a, HIGH(\\1)
    ldh [hUpdateJump + 2], a
ENDM

{"SECTION " + chr(34) + "Interrupt: VBlank" + chr(34) + ", ROM0[$40]" + nl + "    reti                    ; VBlank only wakes HALT; the work runs in the main loop" + nl + nl + "SECTION " + chr(34) + "Interrupt: STAT" + chr(34) + ", ROM0[$48]" + nl + "    jp FtStat               ; the fight's mid-frame scroll for the rival's band" + nl + nl if fights else ""}SECTION "Header", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0

SECTION "Stack", WRAM0
    ds {STACK_SIZE}
wStackTop:
wSavedSP: dw

SECTION "Code: Start", ROM0
Start:
    ; The boot ROM leaves A = $11 on Game Boy Color hardware, and interrupts disabled (they stay that way).
    cp $11
    ld a, 0
    jr nz, .notCGB
    inc a
.notCGB:
    ldh [hIsCGB], a
    ld sp, wStackTop
.waitVBlank:                ; the LCD may only be switched off during VBlank
    ldh a, [rLY]
    cp 144
    jr c, .waitVBlank
.waitVBlankDone:            ; labels named .waitX/.waitXDone mark idle loops for the profiler
    xor a
    ldh [rLCDC], a
    ldh [rSCY], a
    ldh [rSCX], a
{nl.join(boot)}
    ld a, 1                 ; VBlank wakes HALT; no interrupt handler ever runs
    ldh [rIE], a
    ld a, {index_of[project['start']]}
    call LoadScene
MainLoop:
    xor a
    ldh [rIF], a
    halt                    ; sleep until VBlank
    nop                     ; HALT may run the next byte twice if VBlank arrives just before it
{"    ldh a, [rLY]            ; a fight's mid-frame scroll interrupt also wakes HALT: sleep on until VBlank" + nl + "    cp 144" + nl + "    jr c, MainLoop" + nl if fights else ""}{nl.join(vblank_work)}
VBlankDone:                 ; everything that must happen during VBlank is done
    ld hl, hFrame
    inc [hl]
    ld a, $20               ; read the d-pad
    ldh [rP1], a
    ldh a, [rP1]
    ldh a, [rP1]
    cpl
    and $0F
    swap a
    ld b, a
    ld a, $10               ; read the buttons
    ldh [rP1], a
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    cpl
    and $0F
    or b
    ld b, a
    ld a, $30
    ldh [rP1], a
    ldh a, [hPad]
    xor b
    and b
    ldh [hPadNew], a        ; pressed this frame
    ld a, b
    ldh [hPad], a           ; held
{REPEAT_CODE if repeat else ""}{SLIDE_STEP_CODE if slides else ""}    call hUpdateJump
    call SfxUpdate
    jp MainLoop

SECTION "Code: Scenes", ROM0
; Load scene A with the screen off. Tiles, map and palette map go by DMA on Game Boy Color.
LoadScene:
    ldh [hScene], a
    ldh a, [rLCDC]
    add a                   ; screen already off (at boot)? bit 7 -> carry
    jr nc, .screenOff
.waitVBlank:
    ldh a, [rLY]
    cp 144
    jr c, .waitVBlank
.waitVBlankDone:
    xor a
    ldh [rLCDC], a
.screenOff:
{"    call ResetOAM           ; no sprites left over from the last scene" + nl if fights else ""}    ldh a, [hScene]
    add a
    add LOW(SceneLoads)
    ld l, a
    adc HIGH(SceneLoads)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
{"    xor a                   ; not sliding unless this scene starts one" + nl + "    ldh [hScrollY], a" + nl if slides else ""}{_bank_switch() if banked else ""}    call JumpHL
{nl.join(finish)}
    call UploadPalettes
{"    ldh a, [hScrollY]" + nl + "    ldh [rSCY], a" + nl if slides else ""}    ld a, LCDC_ON
    ldh [rLCDC], a
    ret

JumpHL:
    jp hl

SceneLoads:
    dw {", ".join(f"Scene{i}Load" for i in range(len(scenes)))}
{"SceneBanks:" + nl + "    db " + ", ".join(f"BANK(Scene{i}Tiles)" for i in range(len(scenes))) if banked else ""}

{nl.join(_scene_load(i, s, cursor_on, opt_index, markers) for i, s in enumerate(scenes))}{nl + nl + SLIDE_FILL.rstrip() if slides else ""}

; Copy C tiles (1-128) from HL to DE.
CopyTiles:
    ldh a, [hIsCGB]
    and a
    jr z, .byCPU
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, d
    ldh [rHDMA3], a
    ld a, e
    ldh [rHDMA4], a
    ld a, c
    dec a
    ldh [rHDMA5], a         ; 16 bytes per tile; the CPU waits 32 cycles per tile
    ret
.byCPU:                     ; original Game Boy: pop the tiles off the stack, 16 bytes per loop
    ld [wSavedSP], sp
    ld sp, hl
    ld h, d
    ld l, e
.tile:
{POP_TILES}
    dec c
    jr nz, .tile
    jp RestoreSP

; Copy a 32-wide padded map from HL to $9800 (in the current VRAM bank).
CopyMap:
    ldh a, [hIsCGB]
    and a
    jr z, .byCPU
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, $98
    ldh [rHDMA3], a
    xor a
    ldh [rHDMA4], a
    ld a, MAP_H * 32 / 16 - 1
    ldh [rHDMA5], a
    ret
.byCPU:
    ld [wSavedSP], sp
    ld sp, hl
    ld hl, $9800
    ld b, MAP_H
.row:
{POP_MAP_ROW}
    dec b
    jr nz, .row
RestoreSP:
    ld hl, wSavedSP
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld sp, hl
    ret

; Palette numbers live in VRAM bank 1 on Game Boy Color; the original has no such thing.
CopyAttr:
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, 1
    ldh [rVBK], a
    call CopyMap
    xor a
    ldh [rVBK], a
    ret

; Upload the current scene's palettes at the current fade step (step 0 = the real colors).
UploadPalettes:
{'    xor a' + nl + '    ldh [hPalDirty], a' + nl + '    ldh a, [hFadeStep]' if fade else '    xor a'}
    ld b, a
    ldh a, [hIsCGB]
    and a
    jr z, .original
    ld a, b
    add a
    add LOW(FadeColor)
    ld l, a
    adc HIGH(FadeColor)
    sub l
    ld h, a
    ld a, [hl+]
    ld e, a
    ld d, [hl]
    ldh a, [hScene]
    add a
    add LOW(ScenePalettes)
    ld l, a
    adc HIGH(ScenePalettes)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl
.original:
    ld a, b
    add LOW(FadeGray)
    ld l, a
    adc HIGH(FadeGray)
    sub l
    ld h, a
    ld a, [hl]
    ldh [rBGP], a
{'    ldh [rOBP0], a' + nl if sprites else ''}{'    ldh [rOBP1], a' + nl if fights else ''}    ret

ScenePalettes:
    dw {", ".join(f"Scene{i}Palettes" for i in range(len(scenes)))}

{nl.join(_scene_palettes(i, s, project, cursor_on) for i, s in enumerate(scenes))}

SECTION "Data: Palettes", ROM0
FadeColor:                  ; RGB555: {n_bg} background{f" + {n_obj} sprite" if n_obj else ""} palettes per fade step
    dw {", ".join(f"FadeColor.step{k}" for k in range(steps + 1))}
{nl.join(cgb_rows)}
FadeGray:                   ; original Game Boy BGP{'/OBP0' if sprites else ''} per fade step
    db {", ".join(f"%{v:08b}" for v in dmg_rows)}

SECTION "Code: Frame", ROM0
; Point the update trampoline at the current scene's own update routine.
SetSceneUpdate:
    ldh a, [hScene]
    add a
    add LOW(SceneUpdates)
    ld l, a
    adc HIGH(SceneUpdates)
    sub l
    ld h, a
    ld a, [hl+]
    ldh [hUpdateJump + 1], a
    ld a, [hl]
    ldh [hUpdateJump + 2], a
    ret

SceneUpdates:
    dw {", ".join(updates)}

NoUpdate:
    ret
"""]
    if fade:
        out.append("""; Fade out, then load scene A.
StartTransition:
    ldh [hNextScene], a
    ld a, FADE_FRAMES
    ldh [hTimer], a
    SET_UPDATE FadeOut
    ret

FadeOut:
    ld hl, hTimer
    dec [hl]
    ret nz
    ld [hl], FADE_FRAMES
    ldh a, [hFadeStep]
    cp FADE_STEPS
    jr z, .load             ; the last step has been on screen for a full step: load
    inc a
    ldh [hFadeStep], a
    ld a, 1
    ldh [hPalDirty], a
    ret
.load:
    ldh a, [hNextScene]
    jp LoadScene

FadeIn:
    ld hl, hTimer
    dec [hl]
    ret nz
    ld [hl], FADE_FRAMES
    ld hl, hFadeStep
    dec [hl]
    ld a, 1
    ldh [hPalDirty], a
    ld a, [hl]
    and a
    ret nz
    jp SetSceneUpdate       ; fully faded in: hand over to the scene
""")
    out += scene_code
    patch_code, patch_data = [], []
    for i, s in enumerate(scenes):
        if s["menu"]:
            m = s["menu"]
            for n, it in enumerate(m["items"]):
                row = m["y"] + n * m["spacing"]
                patch_code.append(_patch_routine(f"Scene{i}Item{n}Patch", [(row * 32 + m["x"], len(it["label"]))],
                                                 f'menu item "{it["label"]}"'))
            patch_data.append(_menu_data(i, s, index_of))
            if s["menu"].get("confirm"):
                patch_data.append(_confirm_asm(i, s, project))
        elif s["options"]:
            for r_i, r in enumerate(s["options"]["rows"]):
                cells = len(s["option_strips"][r_i][0])
                patch_code.append(_patch_routine(f"Scene{i}Row{r_i}Patch", [(r["valueY"] * 32 + r["valueX"], cells)],
                                                 f'option "{r["label"]}"'))
            patch_data.append(_options_data(i, s))
        elif s["press"]:
            code = _press_patches(i, s)
            if code:
                patch_code.append(code)
            data = _press_data(i, s)
            if data:
                patch_data.append(data)
    if patch_code:
        out.append('SECTION "Code: Map patches", ROM0\n' + "\n\n".join(patch_code) + "\n")
    if patch_data:
        out.append('SECTION "Data: Menus and screens", ROM0\n' + nl.join(patch_data) + "\n")
    if sprites:
        reset = ["    ld hl, $FE00", "    ld b, 160", "    xor a", ".clear:", "    ld [hl+], a", "    dec b", "    jr nz, .clear"]
        if cursor_on:
            reset += [f"    ld a, {project['cursor']['palette']}", "    ld [OAM_CURSOR + 3], a  ; cursor: tile 0, its palette"]
        if markers:
            reset += ["    ld a, 1", "    ld [OAM_CURSOR + 6], a  ; slider marker: tile 1", f"    ld a, {project['cursor']['palette']}",
                      "    ld [OAM_CURSOR + 7], a"]
        out.append('SECTION "Code: OAM", ROM0\nResetOAM:                   ; screen off or VBlank: every sprite hidden\n' + nl.join(reset) + "\n    ret\n")
    if cursor_on:
        out.append(f"""SECTION "Data: Sprites", ROM0
CursorTile:
    db {", ".join(f"${b:02X}" for b in encode_tile(project['cursor']['pixels']))}
BobTable:
    db {", ".join(str(v) for v in BOB)}
""")
    if markers:
        out.append(f"""SECTION "Data: Slider marker", ROM0
MarkerTile:
    db {", ".join(f"${b:02X}" for b in encode_tile(MARKER))}
""")
    if confirms:
        out.append("""SECTION "Menu confirm", WRAM0
wConfirmPtr: dw             ; the next step
wConfirmOAM: dw             ; the sprite's OAM template
wConfirmStep: ds 1 + 9 + 9 * 8  ; the step VBlank shows: flags, colors, OBP1, BGP, count, palettes

SECTION "Code: Menu confirm", ROM0
ConfirmApply:               ; (VBlank) the step: its sprites (shown or not, in front or behind), their colors, the palettes
    xor a
    ldh [hConfirmDirty], a
    ld a, [wConfirmStep]
    ld b, a                 ; bit 0 shown, bit 1 in front
    ld c, $17               ; attributes: Color palette 7, OBP1, behind the background...
    bit 1, a
    jr nz, .front
    set 7, c
.front:
    ld a, [wConfirmOAM]
    ld l, a
    ld a, [wConfirmOAM + 1]
    ld h, a
    ld de, $FE08
.sprite:
    ld a, [hl+]
    and a
    jr z, .colors
    bit 0, b
    jr nz, .y
    xor a                   ; hidden
.y:
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
    ld a, c
    ld [de], a
    inc e
    jr .sprite
.colors:
    ldh a, [hIsCGB]
    and a
    jr z, .original
    ld a, $80 | 7 * 8 + 2   ; Color: sprite palette 7, colors 1-3
    ldh [rOCPS], a
    ld hl, wConfirmStep + 1
    ld c, LOW(rOCPD)
    REPT 6
        ld a, [hl+]
        ldh [c], a
    ENDR
    ld a, [wConfirmStep + 9]
    and a
    ret z
    ld b, a
    ld hl, wConfirmStep + 10
.palette:
    ld a, [hl+]             ; its slot
    add a
    add a
    add a
    or $80
    ldh [rBCPS], a
    ld c, LOW(rBCPD)
    REPT 8
        ld a, [hl+]
        ldh [c], a
    ENDR
    dec b
    jr nz, .palette
    ret
.original:
    ld a, [wConfirmStep + 7]
    ldh [rOBP1], a
    ld a, [wConfirmStep + 8]
    ldh [rBGP], a
    ret
""")
    if passes:
        out.append("""SECTION "Pass key", WRAM0
wPassKey: ds 10             ; the digits entered (kept between visits)
wPassPatch: ds 3            ; the digit tile being drawn, and where
wPassSet: db                ; $A5 once the digits are set up

SECTION "Code: Pass key patch", ROM0
PassPatch:                  ; (VBlank) HL -> tile, map address
    ld a, [hl+]
    ld e, [hl]
    inc hl
    ld d, [hl]
    ld [de], a
    ret
""")
    if options:
        out.append(f"""SECTION "Options", WRAM0
wOptions: ds OPTION_COUNT   ; current value of each option (0 = first choice / minimum)

SECTION "Data: Option defaults", ROM0
OptionDefaults:
    db {", ".join(str(r["default"]) for r in opt_rows)}
""")
    nes_sound = any((s.get("fight") or {}).get("nes", {}).get("sound") for s in scenes)
    out.append(KIT_SFX if nes_sound else re.sub(r"IF DEF\(FT_NES_SOUND\)\n.*?ENDC\n", "", KIT_SFX, flags=re.S))
    out.append('SECTION "Data: Sound effects", ROM0\n' + sfx_data + "\n")
    if nes_sound:                   # each effect's counterpart in the NES game (an SQ1 effect; 0: none)
        out.append("SfxNes:\n" + _db([NES_SFX.get(n, 0) for n in sfx.effects(project.get("sound", "arcade"), sfx_groups(scenes))]) + "\n")
    out += [_scene_data(i, s, banked) for i, s in enumerate(scenes)]
    out.append('SECTION "Variables", HRAM\n' + nl.join(hram) + "\n")
    return nl.join(out)


def auto_session(project):
    """A profiling session that exercises the project: for a menu, move down, choose, and follow the
    transition into the next scene; otherwise just a few frames of the first scene."""
    start = project["scenes"][project["start"]]
    if start["press"]:
        return {"frames": 160, "presses": [{"frame": 40, "buttons": ["start"], "hold": 2}], "checkpoints": {}}
    if not start["menu"]:
        return {"frames": 8, "presses": [], "checkpoints": {}}
    presses = [{"frame": 34, "buttons": ["down"], "hold": 2}, {"frame": 52, "buttons": ["a"], "hold": 2}]
    return {"frames": 200, "presses": presses, "checkpoints": {}}


def build_project(data):
    """Validate, generate and build. Returns (Build, asm source, stats, normalized project)."""
    project = validate(data)
    asm = generate_asm(project)
    build = build_rom(asm, rom_title(project["name"]), cgb=True)
    kept = reachable_scenes(project)
    return build, asm, {"tiles": max(len(project["scenes"][i]["tiles"]) for i in kept),
                        "scenes": len(kept), "unreachable": len(project["scenes"]) - len(kept),
                        "palettes": len(project["palettes"]), "bytes": len(build.rom)}, project
