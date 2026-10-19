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
KIT_PASSKEY = __import__("pathlib").Path(__file__).with_name("kit_passkey.asm").read_text()


# The template's effects as Punch-Out!!'s (its SQ1 effect numbers): what plays when a project has its engine.
NES_SFX = {"pass_digit": 0x0B, "pass_next": 0x09,   # (Punch-Out!!'s pass key: a digit changed, on to the next)
           "type": 0x0A, "type_alt": 0x0B,          # (its typed words: Doc's, the rival's)
           "menu_move": 0xFF, "menu_back": 0x14,     # (moving between its title's items: no sound, $FF)
           "option_change": 0x12, "menu_confirm": 0x01, "press_start": 0x01,
           "bell": 0x0C, "count": 0x10, "knockdown": 0x02, "ko": 0x0E, "punch": 0x06, "hit": 0x03, "block": 0x04,
           "dodge": 0x11, "star_wind": 0x16}



# The NES's colors (2C02), RGB: a fighter's dodge-cue outline is one of these, by number ($05EC).
NES_RGB = [(84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136), (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
           (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0), (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0),
           (152, 150, 152), (8, 76, 196), (48, 50, 236), (92, 30, 228), (136, 20, 176), (160, 20, 100), (152, 34, 32),
           (120, 60, 0), (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40), (0, 102, 120), (0, 0, 0), (0, 0, 0), (0, 0, 0),
           (236, 238, 236), (76, 154, 236), (120, 124, 236), (176, 98, 236), (228, 84, 236), (236, 88, 180), (236, 106, 100),
           (212, 136, 32), (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108), (56, 180, 204), (60, 60, 60), (0, 0, 0), (0, 0, 0),
           (236, 238, 236), (168, 204, 236), (188, 188, 236), (212, 178, 236), (236, 174, 236), (236, 174, 212), (236, 180, 176),
           (228, 196, 144), (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180), (160, 214, 228), (160, 162, 160), (0, 0, 0), (0, 0, 0)]

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
        held, steady = vols[0], []                              # a wobble of one step held: each change of
        for v in vols:                                          # the GB's noise volume restarts it, a click
            if abs(v - held) >= 2:
                held = v
            steady.append(held)
        vols = steady
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
    if any((s["menu"] or {}).get("pass_key") for s in scenes):
        groups.append("pass")
    if any(s.get("typed") or (s.get("cutscene") or {}).get("box") for s in scenes):
        groups.append("typed")
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
        if s.get("fight") and s["fight"].get("game_over") is not None:
            todo.append(s["fight"]["game_over"])
        if s.get("fight") and s["fight"].get("win_tko") is not None:
            todo.append(s["fight"]["win_tko"])
    return sorted(seen)


def _db(values, per_line=16):
    return "\n".join("    db " + ", ".join(f"${v:02X}" for v in values[i:i + per_line])
                     for i in range(0, len(values), per_line))


def _pic_next(s, pics):
    """The original's grey pictures: per picture (by number), the one likely next ($FF: none known), the picture
    before it that changes that, and the one next then (pic_next.py's, from the bot's fights)."""
    order = pics["order"]
    nxt = (s["fight"].get("nes") or {}).get("pictures", {}).get("next") or {}
    num = lambda k: order.index(k) if k in order else 0xFF
    out = []
    for k in range(128):
        v = nxt.get(order[k]) if k < len(order) else None
        out += [num(v[0]), num(v[1]), num(v[2])] if v else [0xFF] * 3
    return out


def _crowd_pulse(s, project):
    """The crowd going wild at his KO, as Punch-Out!!'s: its color a brightness down every 4 frames, twice, and
    back up ($26, $16, $06, $16): its palette's hardware slot (as BCPS: color 1), then the four colors."""
    slot = s["cell_pal"][s["fight"]["crowd_row"] * CW + CW // 2]       # (a hardware slot by now: its palette's)
    k = {v: p for p, v in (s.get("pal_slots") or {}).items()}.get(slot, slot)
    r, g, b = (v * 8 for v in project["palettes"][k][1])
    nes = min(range(64), key=lambda i: (NES_RGB[i][0] - r) ** 2 + (NES_RGB[i][1] - g) ** 2 + (NES_RGB[i][2] - b) ** 2)
    steps = [nes, max(nes - 0x10, nes & 0x0F), max(nes - 0x20, nes & 0x0F)]
    col = lambda i: (NES_RGB[i][2] >> 3) << 10 | (NES_RGB[i][1] >> 3) << 5 | NES_RGB[i][0] >> 3
    return f"    db ${0x80 | slot * 8 + 2:02X}\n    dw " + ", ".join(f"${col(i):04X}" for i in steps + [steps[1]])


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


def _upload_runs(indexes, spec, data_reg, at_label=None, slots=None, inline=False):
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
        copy = ["    REPT 8", "        ld a, [hl+]", "        ldh [c], a", "    ENDR"] if inline else ["    call PalCopy8"]
        if count == 1:
            lines += copy
        else:
            label = f".palettes{first}"
            lines += [f"    ld b, {count}", f"{label}:"] + copy + ["    dec b", f"    jr nz, {label}"]
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
{_db(s['cell_tiles'] if s.get('cutscene') else _pad_rows(s['cell_tiles'], bool(s.get('fight'))), 32)}
Scene{i}Attr:               ; palette number per tile (Game Boy Color only)
{_db(s['cell_pal'] if s.get('cutscene') else _pad_rows(s['cell_pal'], bool(s.get('fight'))), 32)}
""" + "".join(f"Scene{i}Record{n}:             ; Mac's record's glyphs: 0-9, -, K, O, blank\n    db {', '.join(map(str, g))}\n"
              for n, (_, _, g) in enumerate(s.get("record_glyphs") or ())) + (
        f"Scene{i}Aw:                 ; Another World Circuit's words: cells, then each's address and tile\n    db {len(s['aw_patch'])}\n"
        + "".join(f"    dw $9800 + {c // CW * 32 + c % CW}\n    db {tile}\n" for c, tile in s["aw_patch"])
        if s.get("aw_patch") else "")


# ---- palettes per scene ----------------------------------------------------------

def hw_palettes(s):
    """A project can have more background palettes than the 8 the hardware holds, as long as each scene
    uses 8 at most. Returns the scene with its palette map in hardware slots and, when any palette moved,
    "pal_slots" (palette -> slot) and "pal_used" (the project palettes it uploads). Palettes 0-7 keep their
    own slot, so a project with 8 or fewer builds exactly as before."""
    fight = s.get("fight")
    card = (s.get("press") or {}).get("card")       # (a round card's two: up with the scene, its rows drawn later)
    extra = {card["palette"], card["text_palette"]} if card else set()
    used = sorted(set(s["cell_pal"]) | (set(fight["palettes"].values()) if fight else set()) | extra)   # (a fight:
    if all(g < 8 for g in used):                                                    # his palettes, every pose's)
        return s if extra <= set(s["cell_pal"]) else dict(s, pal_used=used)
    slots = {g: g for g in used if g < 8}
    free = [k for k in range(8) if k not in slots.values()]
    for g in used:
        if g >= 8:
            slots[g] = free.pop(0)
    out = dict(s, cell_pal=[slots[g] for g in s["cell_pal"]], pal_slots=slots, pal_used=used)
    if card:
        out["card_rows"] = [[[(t, slots[g]) for t, g in row] for row in rows] for rows in s["card_rows"]]
    if fight:                           # his poses' cells too
        out["fight_attrs"] = {pose: [slots[g] for g in cells] for pose, cells in s["fight_attrs"].items()}
        if s.get("fight_cgb"):
            cgb = s["fight_cgb"]
            out["fight_cgb"] = dict(cgb, attrs={pose: [slots[g] for g in cells] for pose, cells in cgb["attrs"].items()})
        if s.get("fight_pics"):         # (his NES pictures' cells, and their top rows' sprites)
            pc = s["fight_pics"]
            out["fight_pics"] = dict(pc, attrs=[[slots[g] for g in cells] for cells in pc["attrs"]],
                                     heads=[[(dy, dx, t, slots[a], f) for dy, dx, t, a, f in hl] for hl in pc["heads"]])
    return out


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
    palettes = "\n".join(_upload_runs(used, "rBCPS", "rBCPD", at_label="BgPalettes", slots=s.get("pal_slots"), inline=True))
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
CARD_HOLD_CHECK = """    ld a, [wCardOn]         ; a round card up: its scroll is its own
    and a
    jr nz, .still
"""
SLIDE_STEP_CODE = """    ldh a, [hScrollY]       ; sliding in: climb (wraps to 0, the resting place)
    and a
    jr z, .still
    add SLIDE_STEP
    ldh [hScrollY], a
.still:
"""
SCREEN_ON_CHECK = """    ldh a, [hScene]         ; a plain screen: the display stays on (black, faded out), interrupts off
    add LOW(SceneScreenOn)
    ld l, a
    adc HIGH(SceneScreenOn)
    sub l
    ld h, a
    ld a, [hl]
    and a
    jr z, .waitVBlank
{fight_check}    ld a, 1                 ; (interrupts are off outside a fight: nothing comes between)
    ldh [hLoadOn], a
    call VWait              ; every palette black, not just the faded ones the last scene used (the new
    call BlackPalettes      ; scene's others would show it loading)
    jr .screenOff
"""
SCREEN_ON_FIGHT = """    cp 2                    ; (a fight: on Color)
    jr nz, .loadOn
    ldh a, [hIsCGB]
    and a
    jr z, .waitVBlank
.loadOn:
"""
SCREEN_ON_END = """    ldh a, [hLoadOn]
    and a
    jr z, .loaded
    xor a
    ldh [hLoadOn], a
.loaded:
"""
VWAIT_CODE = """
; Loading with the display on: wait for the next VBlank's start (VRAM and OAM are free till it ends). Off: none.
VWait:
    ldh a, [hLoadOn]
    and a
    ret z
.leave:
    ldh a, [rLY]
    cp 144
    jr nc, .leave
.wait:
    ldh a, [rLY]
    cp 144
    jr c, .wait
    ret

; Every palette black (in VBlank): Color's 8 background and 8 sprite palettes, the original's three.
BlackPalettes:
    ld a, $FF
    ldh [$FF47], a          ; BGP, OBP0, OBP1
    ldh [$FF48], a
    ldh [$FF49], a
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, $80
    ldh [rBCPS], a
    ldh [rOCPS], a
    xor a
    ld b, 64
.color:
    ldh [rBCPD], a
    ldh [rOCPD], a
    dec b
    jr nz, .color
    ret
"""
COPY_TILES_CHUNKS = """    ldh a, [hLoadOn]        ; the display on: a VBlank's worth at a time (Color 64 by DMA, the original 12)
    and a
    jr z, CopyTilesNow
.chunk:
    ldh a, [hIsCGB]
    and a
    ld b, 12
    jr z, .n
    ld b, 64
.n:
    ld a, c
    cp b
    jr nc, .some
    ld b, a
.some:                      ; B = tiles now
    push bc
    push hl
    push de
    call VWait
    pop de
    pop hl
    pop bc
    push bc
    push hl
    push de
    ld c, b
    call CopyTilesNow
    pop de
    pop hl
    pop bc
    ld a, c                 ; on past them
    sub b
    ld c, a
    push bc
    ld c, b
    ld b, 0
    REPT 4
        sla c
        rl b
    ENDR
    add hl, bc
    ld a, e
    add c
    ld e, a
    ld a, d
    adc b
    ld d, a
    pop bc
    ld a, c
    and a
    jr nz, .chunk
    ret
"""
COPY_MAP_CHUNKS = """    ldh a, [hLoadOn]        ; the display on: six rows a VBlank
    and a
    jr z, .whole
    ld de, $9800
    ld c, MAP_H / 6
.chunk:
    push bc
    push hl
    push de
    call VWait
    pop de
    pop hl
    ld b, 6
    call .rows
    pop bc
    dec c
    jr nz, .chunk
    ret
.rows:                      ; B rows from HL to DE (32 wide both): HL, DE past them after
    ld [wSavedSP], sp
    ld sp, hl
    ld h, d
    ld l, e
.chunkRow:
    REPT MAP_W / 2
        pop de
        ld a, e
        ld [hl+], a
        ld a, d
        ld [hl+], a
    ENDR
    add sp, 32 - MAP_W
    ld de, 32 - MAP_W
    add hl, de
    dec b
    jr nz, .chunkRow
    ld d, h
    ld e, l
    ld hl, sp + 0
    ld a, l
    ld [wLoadSrc], a
    ld a, h
    ld [wLoadSrc + 1], a
    ld hl, wSavedSP
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld sp, hl
    ld a, [wLoadSrc]
    ld l, a
    ld a, [wLoadSrc + 1]
    ld h, a
    ret
.whole:
"""
SLIDE_FILL_ON = """; Fill the map rows below the screen (18-31) with tile D, palette E on Game Boy Color. Screen off, or on (a
; VBlank's worth at a time).
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
.fill:                      ; BC bytes (a multiple of 32) of D from HL
    push de
    call VWait
    pop de
    ld a, b                 ; 128 at most at a time
    and a
    ld e, 128
    jr nz, .run
    ld a, c
    cp 128
    jr nc, .run
    ld e, a
.run:
    ld a, c
    sub e
    ld c, a
    jr nc, .runs
    dec b
.runs:
    ld a, d
.byte:
    ld [hl+], a
    dec e
    jr nz, .byte
    ld a, b
    or c
    jr nz, .fill
    ret
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

def _scene_load_banked(i, s, sprites, opt_index=None, markers=False):
    """A scene's load in its own bank (ROM0 has no room for every scene's): its bank mapped again after the
    calls that map another (the NES sound engine's)."""
    out = []
    for line in _scene_load(i, s, sprites, opt_index, markers).split("\n"):
        out.append(line)
        if line.strip() in ("call NesDmc", "call NesMusic"):
            out += [f"    ld a, BANK(Scene{i}Tiles)", "    ld [$2000], a"]
    return "\n".join(out)


def _scene_load(i, s, sprites, opt_index=None, markers=False):
    n = len(s["tiles"])
    lines = [f"Scene{i}Load:", f"    ld hl, Scene{i}Tiles", "    ld de, $9000            ; tiles 0-127",
             f"    ld c, {min(n, 128)}", "    call CopyTiles"]
    if n > 128:
        lines += [f"    ld hl, Scene{i}Tiles + 128 * 16", "    ld de, $8800            ; tiles 128-255",
                  f"    ld c, {n - 128}", "    call CopyTiles"]
    lines += [f"    ld hl, Scene{i}Map", "    call CopyMap", f"    ld hl, Scene{i}Attr", "    call CopyAttr"]
    if s.get("aw_patch"):               # (Punch-Out!!'s Another World Circuit on: its words)
        lines += ["    ld a, [wAw]", "    and a", "    jr z, .notAw", f"    ld hl, Scene{i}Aw", "    call AwPatch", ".notAw:"]
    for n, (x, y, _) in enumerate(s.get("record_glyphs") or ()):    # Mac's record, as it stands
        lines += [f"    ld hl, $9800 + {y * 32 + x}", f"    ld de, Scene{i}Record{n}", "    call RecordDraw"]
    if s.get("_rec_reset"):
        lines.append("    call RecReset")
    if (s.get("cut_key") or {}).get("circuit") is not None:     # Punch-Out!!'s pass key, from his record
        lines += [f"    ld b, {s['cut_key']['circuit']}", "    call PwKeyFar"]
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
    if (s["menu"] or {}).get("pass_key"):
        lines += ["    xor a                   ; its pass key hidden, forgotten", "    ld [wPkShown], a", "    call PkReset"]
    if s.get("cutscene"):
        cs = s["cutscene"]
        n_obj = len(s["cut_obj"])
        lines += [f"    ld hl, Scene{i}CutObj   ; its actors' tiles, from sprite tile 2 (by the CPU: 4 a VBlank)",
                  "    ld de, $8020", f"    ld b, {n_obj}", ".cutTile:", "    push bc", "    ld a, b", "    and 3",
                  "    call z, VWait" if any(True for _ in [0]) else "", "    ld c, 16", ".cutByte:", "    ld a, [hl+]",
                  "    ld [de], a", "    inc de", "    dec c", "    jr nz, .cutByte", "    pop bc", "    dec b", "    jr nz, .cutTile"]
        after = cs["box"]["after"] if cs["box"] else 0
        lines += [f"    ld hl, Scene{i}CutFrames", "    call CutStart",
                  f"    ld hl, Scene{i}CutBands   ; each band from where it stops at its endX as the box comes up",
                  "    ld b, [hl]", "    inc hl", "    ld de, wCutBands", ".cutBand:", "    inc hl", "    inc hl", "    inc hl",
                  "    ld a, [hl+]", "    ld [de], a", "    inc de", "    ld a, [hl+]", "    ld [de], a", "    inc de",
                  "    dec b", "    jr nz, .cutBand",
                  f"    ld a, LOW({after})", "    ld [wCutWait], a",
                  f"    ld a, HIGH({after})", "    ld [wCutWait + 1], a"]
        if cs["music"]:
            lines += ["IF DEF(FT_NES_SOUND)", f"    ld a, ${cs['music']:02X}            ; its NES music", "    call NesMusic", "ENDC"]
    if s.get("typed"):
        ty = s["typed"]
        pick = (["    ld a, [wFtRound]        ; the corner after round 1 the first group", "    sub 2", "    jr nc, .group",
                 "    xor a", ".group:"] if ty["pick"] == "round" else ["    xor a"])
        lines += [f"    ld a, {ty['every']}               ; its words: a letter every few frames", "    ld [wTyEvery], a",
                  *pick, f"    ld hl, Scene{i}Typed", "    call TypeStart"]
    if s.get("nes_music"):
        lines += ["IF DEF(FT_NES_SOUND)", f"    ld a, ${s['nes_music']:02X}            ; its NES song, as the game starts it",
                  "    call NesMusic", "ENDC"]
    if (s.get("press") or {}).get("auto"):
        lines += [f"    ld a, LOW({s['press']['auto']})         ; on by itself after a while", "    ld [wAutoLeft], a",
                  f"    ld a, HIGH({s['press']['auto']})", "    ld [wAutoLeft + 1], a"]
        if s["press"].get("ring"):
            lines += [f"    ld a, {s['press']['ring']['gaps'][0]}                 ; its effect's first frame", "    ld [wRingTick], a",
                      "    ld a, 1", "    ld [wRingNext], a"]
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
            if m.get("gloves"):
                lines += [f"    ld hl, Scene{i}GloveTiles   ; its gloves for a cursor: their tiles (sprite tile 64 on)",
                          "    ld de, $8400", "    ld b, 6 * 16", ".gloveTiles:", "    ld a, [hl+]", "    ld [de], a", "    inc de",
                          "    dec b", "    jr nz, .gloveTiles", "    xor a                   ; (the plain cursor off screen)",
                          "    ldh [hCursorX], a"]
        elif s["options"]:
            lines += _options_load(i, s, opt_index, markers)
        else:
            lines += ["    xor a                   ; no menu: cursor off screen", "    ldh [hCursorY], a"]
        if markers and not s["options"]:
            lines += ["    xor a", "    ldh [hMarkerY], a"]
    lines.append("    ret")
    return "\n".join(lines)


GLOVE_PAL = 1                       # the menu gloves' sprite palette on Color (a menu's scene uses only the cursor's)


def _scene_palettes(i, s, project, sprites):
    """Upload this scene's palettes from the fade row in DE: only the background palettes its tiles
    use, plus the cursor's sprite palette if it has a menu."""
    lines = [f"Scene{i}Palettes:", "    ld h, d", "    ld l, e"]
    ft = s.get("fight")
    if ft and ft.get("rope_row"):       # a rival in front of the ropes: his top rows are sprites in his colors
        lines.append("    push de")
        for k, g in enumerate(sorted(set(ft["palettes"].values()))):
            lines += ["    pop de", "    push de", f"    ld hl, {g * 8}", "    add hl, de", f"    ld a, $80 | {(5 + k) * 8}",
                      "    ldh [rOCPS], a", "    ld c, LOW(rOCPD)", "    call PalCopy8"]
        lines += ["    pop de", "    ld h, d", "    ld l, e"]
    used = s.get("pal_used") or sorted(set(s["cell_pal"]))
    lines += _upload_runs(used, "rBCPS", "rBCPD", slots=s.get("pal_slots"))
    pal = None
    if sprites and (s["menu"] or s["options"]):
        pal = project["cursor"]["palette"]
    obj_pals = [pal] if pal is not None else []
    if s.get("cutscene"):
        obj_pals = sorted({c for a in s["cutscene"]["actors"] for f in a["frames"] for c in f["cells"]})
    if s.get("fight"):
        f = s["fight"]
        obj_pals = sorted({f["player"]["palette"], f["player"]["tired_palette"], f["player"]["down_palette"],
                           f["referee"]["palette"]} | ({f["referee"]["shirt_palette"]} if f["referee"].get("shirt_palette") is not None else set()))
    at = (max(used) + 1) * 8                            # HL's offset into the fade row so far
    for pal in obj_pals:
        skip = (len(project["palettes"]) + pal) * 8 - at
        if skip:
            lines += [f"    ld de, {skip}", "    add hl, de"]
        lines += [f"    ld a, $80 | {pal * 8}", "    ldh [rOCPS], a", "    ld c, LOW(rOCPD)", "    call PalCopy8"]
        at = (len(project["palettes"]) + pal + 1) * 8
    if (s["menu"] or {}).get("gloves"):                 # (not faded: they're up only once the fade is done)
        lines += [f"    ld hl, Scene{i}GloveColors", f"    ld a, $80 | {GLOVE_PAL * 8}", "    ldh [rOCPS], a", "    ld c, LOW(rOCPD)",
                  "    call PalCopy8"]
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


def _press_target(s, index_of):
    """A press-start screen's way on: its target, or (a loss's screen, Punch-Out!!'s circuits) the career's."""
    return "ld a, [wRecNext]" if s.get("_rec_next") else f"ld a, {index_of[s['press']['target']]}"


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
    press_sound = "    ld a, SFX_PRESS_START\n    call PlaySfx\n"
    if p.get("quiet"):                      # no sound; the NES game's music, if it's playing, stopped (as its screens do)
        press_sound = ("IF DEF(FT_NES_SOUND)\n    ldh a, [hNesSound]\n    and a\n    jr z, .quiet\n    ld a, $80\n"
                       "    ld [wNes + $F2], a\n.quiet:\nENDC\n")
    if p.get("nes_dmc"):                    # the press starts an NES sample instead (the crowd, as Punch-Out!!'s)
        press_sound = (f"IF DEF(FT_NES_SOUND)\n    ld a, {p['nes_dmc']}\n    call NesDmc\nELSE\n" + press_sound + "ENDC\n")
    hold, hold_code = "", ""
    if p.get("hold"):                       # then a while on the screen (the crowd, before the fight)
        hold = f"    ld a, {p['hold']}\n    ldh [hTimer], a\n    SET_UPDATE Scene{i}Hold\n    ret\n"
        hold_code = (f"Scene{i}Hold:\n    ld hl, hTimer\n    dec [hl]\n    ret nz\n"
                     f"    {_press_target(s, index_of)}\n    jp StartTransition\n")
    typed = ""
    if s.get("typed"):                      # its words write themselves first; Start waits for them (as Punch-Out!!'s)
        show = (f"    ld hl, Scene{i}PromptShown  ; then the prompt\n    QUEUE_PATCH Scene{i}PromptPatch\n"
                if blink else "")
        typed = f"""    ld a, [wTyDone]
    and a
    jr nz, .typed
    call TypeStep
    ld a, [wTyDone]
    and a
    ret z
{show}    ret
.typed:
"""
    card_go, card_code = "", ""
    if p.get("card"):                       # Punch-Out!!'s round card comes up from below, then on
        c = p["card"]
        pick = (["    ld a, [wFtRound]        ; (the corner before round 2: the first)", "    sub 2", "    jr nc, .variant",
                 "    xor a", ".variant:", f"    cp {len(c['variants'])}", "    jr c, .variantOk", f"    ld a, {len(c['variants']) - 1}",
                 ".variantOk:"] if c["pick"] == "round" else ["    xor a"])
        card_go = "\n".join(pick + [
            "    ld l, a                 ; its rows", "    ld h, 0", "    add hl, hl", f"    ld de, Scene{i}CardRows", "    add hl, de",
            "    ld a, [hl+]", "    ld [wCardRows], a", "    ld a, [hl]", "    ld [wCardRows + 1], a",
            "    xor a", "    ld [wCardY], a", "    ld [wCardRow], a", f"    ld a, {c['hold']}", "    ld [wCardHold], a",
            "    ld a, 1", "    ld [wCardOn], a",
            f"    SET_UPDATE Scene{i}Card", "    ret"]) + "\n"
        card_code = f"""Scene{i}Card:                ; the screen scrolls up 4 pixels a frame, the card's rows drawn below a row ahead
    ld a, [wCardY]
    cp CARD_TOP
    jr nc, .held
    add 4
    ld [wCardY], a
    ldh [hScrollY], a
    jp CardStep
.held:
    ldh [hScrollY], a       ; (kept there)
    call CardStep
    ld hl, wCardHold
    dec [hl]
    ret nz
    {_press_target(s, index_of)}
    jp StartTransition
"""
    if p.get("auto"):                       # Start ignored: on by itself once its time is up
        ring = (f"""    ld a, [wRingTick]       ; its effect on its frames (the bells)
    and a
    jr z, .quiet
    dec a
    ld [wRingTick], a
    jr nz, .quiet
IF DEF(FT_NES_SOUND)
    ld a, ${p['ring']['sfx']:02X}
    call NesSfx
ENDC
    ld a, [wRingNext]
    ld e, a
    inc a
    ld [wRingNext], a
    ld d, 0
    ld hl, Scene{i}RingGaps
    add hl, de
    ld a, [hl]
    ld [wRingTick], a
.quiet:
""" if p.get("ring") else "")
        ring_data = (f"Scene{i}RingGaps:           ; frames to each (0: done)\n    db " + ", ".join(map(str, p['ring']['gaps'] + [0])) + "\n"
                     if p.get("ring") else "")
        return f"""Scene{i}Update:              ; a screen that goes on by itself
{ring}    ld hl, wAutoLeft
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    dec hl
    ld a, l
    ld [wAutoLeft], a
    ld a, h
    ld [wAutoLeft + 1], a
    or l
    ret nz
    {_press_target(s, index_of)}
    jp StartTransition
{ring_data}"""
    return f"""Scene{i}Update:              ; press-start screen: wait for Start or A
{select}{typed}    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr nz, .press
{idle}
.press:
{press_sound}    ld a, {p['flashes'] * 2 - 1}
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
{card_go}{hold}    {_press_target(s, index_of)}
    jp StartTransition
{hold_code}{card_code}"""


def _typed_data(i, s):
    """Typed text's scripts (TypeStep's): per group its variants, each a run of ops."""
    cell = lambda c: f"${0x9800 + (c // CW) * 32 + c % CW:04X}"
    snd = {None: 0, "type": "SFX_TYPE + 1", "type_alt": "SFX_TYPE_ALT + 1"}
    groups = s["typed_scripts"]
    out = [f"Scene{i}Typed:               ; groups (a round each, or one), each: its variants", f"    db {len(groups)}",
           "    dw " + ", ".join(f"Scene{i}TyG{g}" for g in range(len(groups)))]
    for g, variants in enumerate(groups):
        out += [f"Scene{i}TyG{g}:", f"    db {len(variants)}", "    dw " + ", ".join(f"Scene{i}TyG{g}V{v}" for v in range(len(variants)))]
        for v, ops in enumerate(variants):
            out.append(f"Scene{i}TyG{g}V{v}:")
            for op in ops:
                if op[0] == "clear":
                    out.append(f"    db TY_CLEAR, {len(op[1])}, " + ", ".join(f"LOW({cell(c)}), HIGH({cell(c)}), ${t:02X}" for c, t in op[1]))
                elif op[0] == "letter":
                    out.append(f"    db TY_LETTER, 1, LOW({cell(op[1])}), HIGH({cell(op[1])}), ${op[2]:02X}")
                elif op[0] == "space":
                    out.append("    db TY_SPACE")
                elif op[0] == "pause":
                    out.append(f"    db TY_PAUSE, {op[1]}")
                else:
                    out.append(f"    db TY_SOUND, {snd[op[1]]}")
            out.append("    db TY_END")
    return "\n".join(out)


def _card_data(i, s):
    """A round card's rows per variant: 18 rows of 20 tiles, then their 18 rows of attributes (palettes)."""
    out = [f"Scene{i}CardRows:", "    dw " + ", ".join(f"Scene{i}Card{v}" for v in range(len(s["card_rows"])))]
    for v, rows in enumerate(s["card_rows"]):
        out.append(f"Scene{i}Card{v}:")
        out += ["    db " + ", ".join(f"${t:02X}" for t, _ in row) for row in rows]
        out += ["    db " + ", ".join(f"${g & 7:02X}" for _, g in row) for row in rows]
    return "\n".join(out)


def _press_data(i, s):
    lines = [_typed_data(i, s)] if s.get("typed") else []
    if s.get("card_rows"):
        lines.append(_card_data(i, s))
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
        out.append(_patch_routine(f"Scene{i}PromptPatch", [((pr["y"] + k) * 32 + pr["x"], len(row))
                                                           for k, row in enumerate(pr["label"].split("\n"))], "prompt"))
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


def _all_pics(project):
    """Every fight's rival in pictures, Color's and the original's (FT_ALL_PICS): no poses of his kept at all."""
    fs = [sc for sc in project["scenes"] if sc.get("fight")]
    return bool(fs) and all(sc.get("fight_pics") and sc.get("fight_pics_dmg") for sc in fs)


def _career(scenes, fights, index_of):
    """Punch-Out!!'s circuits, from how the fights link up: per fight scene, (flags, rematch, drop, game over)
    for FtCareerResult. A title bout's win goes somewhere other than the next challenger (the training run);
    the first fight of a circuit follows one; a loss drops him to the challenger before (two before after the
    third circuit's title bout); the last fight's loss, or a third loss, is game over (the title). None: no
    circuits (one fight, or not the NES game's)."""
    if len(fights) < 2 or not all(scenes[f]["fight"].get("nes") for f in fights):
        return None
    press = lambda j: index_of.get((scenes[j].get("press") or {}).get("target"))
    rematch = {f: press(index_of[scenes[f]["fight"]["lose"]]) for f in fights}
    corner = {f: index_of.get(scenes[f]["fight"].get("corner")) for f in fights}
    chal = {}
    for j, s in enumerate(scenes):
        f = press(j) if s.get("press") and not s.get("fight") else None
        if f in fights and j not in (rematch[f], corner[f]) and f not in chal:
            chal[f] = j
    title = {}
    for k, f in enumerate(fights):
        nxt = fights[k + 1] if k + 1 < len(fights) else None
        title[f] = nxt is not None and press(index_of[scenes[f]["fight"]["win"]]) != chal.get(nxt)
    out = {}
    for k, f in enumerate(fights):
        flags = 0x80 | (1 << 0 if title[f] else 0) | (1 << 1 if k == 0 or title[fights[k - 1]] else 0) \
            | (1 << 2 if k == len(fights) - 1 else 0)
        back = 2 if title[f] and sum(title[g] for g in fights[:k]) >= 2 else 1
        drop = chal.get(fights[max(0, k - back)], rematch[f]) if k else rematch[f]
        over = index_of.get(scenes[f]["fight"].get("game_over"), 0)
        win_next = press(index_of[scenes[f]["fight"]["win"]])
        aw = scenes[f]["fight"].get("another_world") or {}
        aw_flags = (0x80 | (2 if aw.get("first") else 0) | (4 if aw.get("final") else 0)) if aw else 0
        out[f] = (flags, rematch[f], drop, over, win_next if win_next is not None else 255, aw_flags,
                  index_of.get(aw.get("next"), 255), index_of.get(aw.get("drop"), 255))
    return out


def _fight_entry(i, s, index_of, suffix, all_pics=False, career=None):
    """A fight's row of FtFights: its scene, then the kit's wFtFight (its banks, its swap area, where it goes)."""
    from . import fight as kit
    ft, sw = s["fight"], s["fight_swap"]
    swap_a = max(0, min(sw["count"], 128 - sw["first"]))
    vram_a = 0x9000 + 16 * sw["first"] if swap_a else 0
    vram_b = 0x8800 + 16 * (max(sw["first"], 128) - 128)
    scene = lambda key: index_of[ft[key]] if ft.get(key) is not None else "$FF"
    poses = f"BANK(RivalPalSlots{suffix}), 0, 0" if all_pics else f"BANK(RivalMaps{suffix}), BANK(RivalMap_idle{suffix}), BANK(FtSwapSet0{suffix})"
    return (f"    db {i}, {poses}, "
            f"{f'BANK(NesFighter{suffix})' if ft.get('nes') else '0'}, {(ft.get('nes') or {}).get('offset', 0)}\n"
            f"    db {sw['count']}, {swap_a}\n    dw ${vram_a:04X}, ${vram_b:04X}\n"
            f"    db {s['fight_flash_tile']}, {scene('win')}, {scene('win_tko')}, {scene('lose')}, {scene('corner')}\n"
            f"    db {f'BANK(CgbMaps{suffix}), BANK(CgbSwap{suffix})' if s.get('fight_cgb') else '0, 0'}\n"
            f"    db {f'BANK(RivalHeads{suffix})' if ft.get('rope_row') and not all_pics else '0'}\n"
            f"    db {f'BANK(PicHeader{suffix})' if s.get('fight_pics') else '0'}\n"
            f"    db {f'BANK(PicHeaderDmg{suffix})' if s.get('fight_pics_dmg') and s.get('fight_pics') else '0'}\n"
            f"    db {', '.join(str(v) for v in (career or (0, 255, 255, 255, 255, 0, 255, 255)))}")


def _heads_data(s, suffix):
    """A rival's top rows as sprites (a rope row: he stands in front of it), per pose: the original's, then
    Color's: count, then (dy, dx, tile, attributes) for each of his tiles there (not the mat's; sprites reach
    tiles 128-255, his top rows' are kept there). Color: his palettes in sprite palettes 5-7, a tile's bank."""
    from . import fight as kit
    ft = s["fight"]
    slot_of = s.get("pal_slots") or {}
    rival = [slot_of.get(g, g) for g in sorted(set(ft["palettes"].values()))]
    obj = {hw: 5 + k for k, hw in enumerate(rival)}
    lists = []
    for pose in kit.RIVAL_POSES:
        m, out = s["fight_maps"][pose], []
        for i in range(kit.head_rows(pose) * kit.REGION_W):
            t = m[i]
            if t != s["fight_blank"] and t >= 128:
                out.append((i // kit.REGION_W * 8, i % kit.REGION_W * 8, t, 0))
        lists.append(out)
    cg = s.get("fight_cgb")
    for pose in kit.RIVAL_POSES:
        if not cg:
            lists.append(lists[kit.RIVAL_POSES.index(pose)])
            continue
        m, b, a = cg["maps"][pose], cg["banks"][pose], cg["attrs"][pose]
        fl = cg.get("flips", {}).get(pose) or [0] * len(m)
        keys = [(t, bb) for p in kit.RIVAL_POSES for t, bb in zip(cg["maps"][p], cg["banks"][p])]
        out = []
        blank = cg.setdefault("_blank", max(set(keys), key=keys.count))
        for i in range(kit.head_rows(pose) * kit.REGION_W):
            if (m[i], b[i]) != blank and m[i] >= 128:
                out.append((i // kit.REGION_W * 8, i % kit.REGION_W * 8, m[i], obj.get(a[i], 5) | b[i] << 3 | fl[i] << 5))
        lists.append(out)
    names = [f"RivalHead{suffix}_{k}" for k in range(len(lists))]
    body = "\n".join(f"{n}:\n    db {len(l)}" + "".join(f"\n    db {dy}, {dx}, {t}, ${at:02X}" for dy, dx, t, at in l)
                     for n, l in zip(names, lists))
    return (f"\nSECTION \"Data: Rival heads{suffix}\", ROMX[$4000]\nRivalHeads{suffix}::        ; per pose (the original's, then "
            f"Color's): his top rows as sprites\n    dw {', '.join(names)}\n{body}\n")


def _suffixed(text, suffix):
    """A later fight's data: every label it defines renamed with the suffix (sections too), and checks that
    each sits where the first fight's does (the kit uses those)."""
    names = re.findall(r"^([A-Za-z_]\w*)::?", text, flags=re.M)
    for n in sorted(set(names), key=len, reverse=True):
        text = re.sub(rf"(?<![\w.]){n}(?!\w)", n + suffix, text)
    text = re.sub(r'SECTION "([^"]+)"', lambda m: f'SECTION "{m.group(1)}{suffix}"', text)
    checks = "\n".join(f'ASSERT {n} == {n}{suffix}, "{n}{suffix}: not where the first fight\'s is"' for n in sorted(set(names)))
    return text, checks


POSES_PER_BANK = 25                 # a pose's map rows: 640 bytes (25 to a 16 KB bank)


def _blank_top(pixels):
    """A rival pose's blank pixel rows on top (at most FT_NES_UP_MAX)."""
    from . import fight as kit
    w = kit.REGION_W * 8
    rows = next((i // w for i, v in enumerate(pixels) if int(v)), len(pixels) // w)
    return min(rows, 48)


def _fight_asm(i, s, index_of, project, banked=False, suffix="", shared=True, pads=None, table=""):
    """Constants, tables and generated HUD code for the fight scene, plus the hand-written kit. A game's first
    fight scene brings the kit and what every fight shares (shared); each fight's own data goes in sections of
    its own at $4000, laid out alike (swap sets padded to `pads`), its labels with `suffix` past the first:
    the kit uses the first's labels and each fight's banks (FtFights, `table`)."""
    from . import fight as kit
    ft = s["fight"]
    nl = "\n"
    tiles = s["cell_tiles"]
    pose_ids = "\n".join(f"DEF RP_{p.upper()} EQU {k}" for k, p in enumerate(kit.RIVAL_POSES)) + f"\nDEF RP_COUNT EQU {len(kit.RIVAL_POSES)}"
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
    twinkle_def = ""
    if s.get("fight_twinkle_tile"):     # (OAM x, y of the NES's place, its home: the pose frame's anchor in his area)
        ax, ay = kit.NES_ANCHOR
        twinkle_def = (f"DEF FT_TWINKLE_TILE EQU {s['fight_twinkle_tile']}\n"
                       f"DEF FT_TWINKLE_X0 EQU {ft['x'] * 8 + ax + 8}\nDEF FT_TWINKLE_Y0 EQU {ft['y'] * 8 + ay + 16}")
    pl_cgb, pl_cgb_def = "", ""
    if s.get("fight_pl_cgb"):           # Color: the player's own poses, unshared (their tiles in bank 1)
        pc = s["fight_pl_cgb"]
        pl_cgb = (f"PlayerCgbShared:            ; per pose: 1 = Color draws the original's (its tiles loaded as needed)\n"
                  f"    db {', '.join('1' if p in kit.PLAYER_CGB_SHARED else '0' for p in kit.PLAYER_POSES)}\n"
                  f"PlayerPosesCgb:\n    dw {', '.join(f'PlayerCgb_{p}' for p in kit.PLAYER_POSES)}\n"
                  + "\n".join(f"PlayerCgb_{p}:\n    db {len(pc['sprites'][p])}\n"
                              + "\n".join(f"    db {dy}, {dx}, {t}, ${a:02X}" for dy, dx, t, a in pc["sprites"][p])
                              for p in kit.PLAYER_POSES)
                  + "\n    ds -@ & 15                  ; (on 16 bytes: DMA'd in as the fight loads)\nPlayerCgbTiles:\n" + _db([b for t in pc["tiles"] for b in encode_tile(list(t))]) + "\n")
        pl_cgb_def = f"DEF FT_PL_CGB EQU 1\nDEF FT_PL_CGB_TILES EQU {len(pc['tiles'])}"
        if s.get("fight_side_tile") is not None:   # (the side ropes' ends: Color's, in the referee's shirt's colors)
            shirt = ft["referee"].get("shirt_palette")
            pl_cgb_def += (f"\nDEF FT_SIDE_TILE EQU {s['fight_side_tile']}\nDEF FT_SIDE_ATTR EQU {(shirt if shirt is not None else ft['referee']['palette']) | 0x08}"
                           f"\nDEF FT_SIDE_Y EQU {(ft['y'] + 1) * 8 + 16}")
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
    nes_defs, nes_data, nes_shared = "", "", ""
    if nes:
        parts = _nes_parts()
        hx, hy = nes["home"]
        off = lambda v, home: max(-127, min(127, round((((v - home + 128) & 0xFF) - 128) * nes["scale"])))
        sound_head, _, sound_code = KIT_NES_SOUND.partition(";;PART sound")
        nes_defs = (f"DEF FT_NES EQU 1\nDEF FT_NES_OFFSET EQU {nes['offset']}   ; the fighter's entry in its bank\n"
                    "DEF FT_NES_DOWN_MAX EQU 8       ; pixels he may move down (his band moves over the floor)\n"
                    "DEF FT_NES_UP_MAX EQU 48        ; and up (his band rises to the HUD; inside it, over the tail rows)\n"
                    "DEF FT_NES_END EQU 72           ; frames from the winner's call to the fade (the NES's is black 90 frames on)\n"
                    )
        set_of = {p: k for k, (name, ps) in enumerate(kit.POSE_SETS.items()) for p in ps}
        gem = (ft.get("nes") or {}).get("jewel") or {}
        order = sorted(set(ft["palettes"].values()))     # (his palettes copied to sprite palettes 5 on, in this order)
        objp = lambda kind: 5 + order.index(ft["palettes"][kind])
        jewel_head = (f"{s['fight_jewel_tile']}, {objp('g')}, {objp('h')}" if gem and ft.get("rope_row") else "0, 0, 0")
        jewel_poses = ", ".join(f"{gem[p][0]}, {gem[p][1]}" if p in gem else "$FF, $FF" for p in kit.RIVAL_POSES)
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
NesPlaceX:                  ; per frame (then mirrored): our pose's offset to sit where the NES draws that frame
{_db([dx & 0xFF for dx, _ in nes["places"]])}
NesPlaceY:
{_db([dy & 0xFF for _, dy in nes["places"]])}
RivalPoseSet:               ; per pose: the set whose tiles it needs ($FF: always in video memory)
{_db([set_of.get(p, 0xFF) for p in kit.RIVAL_POSES])}
{parts["fighter"]}
"""
        nes_shared = f"""
SECTION "NES Mac", ROMX[$4000]
NesMac::                    ; Little Mac: Punch-Out!!'s PRG bank B, as it was at $8000
{_db(list(nes["mac"]))}
MacPoseMap:                 ; NES Mac frame number -> our player pose
{_db(nes["mac_frames"])}
MacPlaceY:                  ; and where it sits: pixels down (bit 7: in his knocked-down colors)
{_db(nes["mac_places"])}
MacOffsetX:                 ; NES $15 -> pixels right of his place ($15 scrolls the NES background, Mac in it: up is left)
{_db([max(-127, min(127, round((((nes["mac_home"] - v + 128) & 0xFF) - 128) * nes["mac_scale"]))) & 0xFF for v in range(256)])}
{parts["mac"]}

{parts["head"]}
SECTION "NES engine: shared", ROM0
{parts["common"]}
{KIT_PASSKEY}
"""
        mp = s.get("fight_mac_pics")
        if mp:                          # Color: Mac's pictures (kit_fight.asm, FT_MAC_PICS): per NES frame of his, his
            nes_defs += "DEF FT_MAC_PICS EQU 1\n"                # picture; per picture its tiles and sprites
            n = len(mp["pics"])
            entries = "\n".join(f"    dw MacPicT_{k}\n    db BANK(MacPicT_{k}), {len(pic['tiles'])}\n    dw MacPicS_{k}"
                                for k, pic in enumerate(mp["pics"]))
            mac_sprites = "\n".join(f"MacPicS_{k}:\n    db {len(pic['sprites'])}" + "".join(
                f"\n    db {dy & 0xFF}, {dx & 0xFF}, {t}, ${a:02X}" for dy, dx, t, a in pic["sprites"])
                for k, pic in enumerate(mp["pics"]))
            mac_tiles = "\n".join(f'SECTION "Data: Mac picture {k}", ROMX, ALIGN[4]\nMacPicT_{k}:\n'
                              + (_db([b for t in pic["tiles"] for b in encode_tile(list(t))]) if pic["tiles"] else "")
                              for k, pic in enumerate(mp["pics"]))
            nes_shared += f"""
SECTION "Data: Mac pictures", ROMX
MacPicFrames:               ; NES Mac frame -> his picture ($FF: the one up stays)
{_db(mp["frames"])}
MacPicIdle:
    db {mp["idle"]}
MacPicTable:                ; per picture ({n}): its tiles (address, bank, count), its sprites
{entries}
{mac_sprites}
{mac_tiles}
"""
        if nes.get("sound"):
            nes_shared += f"""
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
    tail_data = f"""    ds -@ & 15                  ; (16-aligned, these rows: copied by DMA on Color)
FtTailTiles:                ; his band's last rows without him (the scene's own tiles)
{_db(_pad_rows(tail_t, True), 32)}
FtTailAttr:
{_db(_pad_rows(tail_p, True), 32)}"""
    rope = ft.get("rope_row")
    rope_defs, heads_data = "", ""
    rope_flash = ""                     # (his top rows' sprites flash with him: his palettes in sprite palettes 5-7)
    if rope:
        rope_flash = ("    pop hl\n    ld a, $80 | 5 * 8\n    ldh [rOCPS], a\n    ld c, LOW(rOCPD)\n"
                      f"    ld b, {len(set(ft['palettes'].values())) * 8}\n.objPal:\n    ld a, [hl+]\n    ldh [c], a\n"
                      "    dec b\n    jr nz, .objPal\n")
    if rope:                            # Punch-Out!!'s ropes behind him: their row in a map row of its own (the
        slot_of = s.get("pal_slots") or {}   # band's first row shows it), his rows over it sprites
        rope_p = [slot_of.get(g, g) for g in rope["cells"]]
        tail_data += f"""
FtRopeTiles:                ; the bottom rope's row: shown over his area's first row (its own map row)
{_db(_pad_rows(s['fight_rope_tiles'], True), 32)}
FtRopeAttr:
{_db(_pad_rows(rope_p, True), 32)}"""
        rope_defs = (f"DEF FT_ROPE EQU 1\nDEF FT_ROPE_ROW EQU 30                              ; its map row (off screen)\n"
                     f"DEF FT_ROPE_LINE EQU {ft['y'] * 8 - 1}                ; LY where it shows, over his area's first row\n"
                     f"DEF FT_ROPE_SCY EQU ((30 - {ft['y']}) * 8) & $FF\n"
                     f"DEF FT_HEAD_ROOM EQU {ft['y'] * 8 - crowd_y * 8}                ; lines from the crowd's top to his area's\n"
                     f"DEF FT_HEAD_X0 EQU {ft['x'] * 8 + 8}                ; OAM x, y of his area's top left (unscrolled)\n"
                     f"DEF FT_HEAD_Y0 EQU {ft['y'] * 8 + 16}\n"
                     f"DEF FT_HEAD_LIMIT EQU {(ft['y'] + 1) * 8 + 16}             ; OAM y from which his band draws him\n"
                     f"DEF FT_DMA_LINE EQU {(ft['y'] + 3) * 8}                 ; LY where the lower part's sprites come in "
                     "(his top rows' done, the referee's not begun)")
        heads_data = "" if _all_pics(project) else _heads_data(s, suffix)
    lum = lambda c: c[0] * 3 + c[1] * 6 + c[2]
    ink = min((lum(c) for k in rival_pals for c in project["palettes"][k]), default=0)   # his outline: the darkest

    def _outline(pal):                  # color across his palettes; in each, the entry that's it (none: none)
        j = min(range(len(pal)), key=lambda k: lum(pal[k]))
        return j if lum(pal[j]) <= ink + 8 and max(pal[j]) <= 10 else None
    cue_outline = [_outline(project["palettes"][k]) for k in rival_pals]
    cue_build = "    ld hl, RivalPalNormal   ; (2: none here)\n"
    if ft.get("nes"):                   # (2: his dodge cue: FtCueBuild's palettes, built each frame, not in VBlank)
        cue_build = "    ld hl, wFtPalCue        ; (2: his dodge cue, FtCueBuild's)\n"
    pad = lambda data, k: data + [0] * (max(0, (pads or {}).get(k, len(data)) - len(data)))
    code = f"""; ---- Fight: "{s['name']}" ----
{nes_defs}
DEF FT_WIN_SCENE EQU 0                             ; results (the scenes they go to: this fight's, FtFights)
DEF FT_LOSE_SCENE EQU 1
DEF FT_CORNER_RESULT EQU 2
DEF CAREER_TITLE EQU 0                            ; wFtCareer (bit 7: circuits): a title bout,
DEF CAREER_FIRST EQU 1                            ; a circuit's first fight,
DEF CAREER_FINAL EQU 2                            ; the last fight
FtFights:                   ; per fight scene: its number, then the kit's wFtFight
{table}
DEF FT_REGION_X EQU {ft['x']}
DEF FT_REGION_W EQU {kit.REGION_W}
DEF FT_REGION_H EQU {kit.REGION_H}
DEF FT_REGION_ROW EQU $9800 + {ft['y'] * 32}     ; the rival's first map row
DEF FT_CROWD_ROW EQU $9800 + {crowd_y * 32}
DEF FT_CROWD_W EQU {CW}
DEF FT_FLASH_TILE EQU {s['fight_flash_tile']}
DEF FT_BAND_TOP EQU {(ft['y'] + (1 if rope else 0)) * 8 - 1}               ; LY where his band's scroll starts (a line early: the change lands in time)
{rope_defs}
DEF FT_BAND_BOTTOM EQU {(ft['y'] + kit.REGION_H) * 8 - 1}
DEF FT_TAIL_ROWS EQU 6                              ; off-screen map rows: the background of his band's last rows,
DEF FT_TAIL_ROW EQU 24                              ; without him, for when he's shown higher in it
DEF FT_TAIL_SCY EQU (FT_TAIL_ROW - {ft['y'] + kit.REGION_H} + FT_TAIL_ROWS) * 8 & $FF
DEF FT_HEADROOM EQU 0                               ; his band never rises over the crowd and ropes
DEF FT_GAP_SCY EQU ({CH - 1} * 8 - FT_BAND_TOP - 1) & $FF   ; (the lines his band has left: the screen's last row, plain)
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
DEF FT_REF_SLOT EQU {s['fight_slots']['ref']}               ; the referee's poses' own tiles: two areas of FT_REF_TILES
DEF FT_REF_TILES EQU {s['fight_slots']['ref_tiles']}
DEF FT_PL_SLOT EQU {s['fight_slots']['pl']}                ; the player's rare poses' own tiles (one at a time)
DEF FT_COUNT_TILE EQU {s['fight_count_tile']}
DEF FT_PLAYER_W EQU {kit.PLAYER_W}
{pl_cgb_def}
{twinkle_def}
DEF FT_PLAYER_X EQU {kit.PLAYER_X + 8}       ; OAM coordinates of the player's top-left
DEF FT_PLAYER_Y EQU {144 - kit.PLAYER_H + 16}
DEF FT_PLAYER_PAL EQU {ft['player']['palette']}
DEF FT_TIRED_PAL EQU {ft['player']['tired_palette']}
DEF FT_DOWN_PAL EQU {ft['player']['down_palette']}
DEF FT_REF_ATTR EQU {ft['referee']['palette'] | 0x10}
DEF FT_SAY_ATTR EQU {(ft['referee']['shirt_palette'] if ft['referee'].get('shirt_palette') is not None else ft['referee']['palette']) | 0x10}   ; his words' bubble: white and black
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
DEF FT_SAY_Y EQU {kit.REF_Y - 8}                 ; (just above his head: sharing his rows would make 11 sprites a line, the hardware shows 10)
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

FtFlashPalettes:            ; during VBlank, Color only: the rival's palettes, white-flashed or normal, into his
    ldh a, [hIsCGB]         ; slots (RivalPalSlots: this fight's)
    and a
    ret z
    ldh a, [hFtFlashShown]
    and a
    ld hl, RivalPalNormal
    jr z, .upload
    dec a
    ld hl, RivalPalFlash
    jr z, .upload
{cue_build}.upload:
{"    push hl" + nl if ft.get("rope_row") else ""}    ld de, RivalPalSlots
    ld a, [de]
    inc de
    ld b, a
.pal:
    ld a, [de]
    inc de
    ldh [rBCPS], a
    ld c, LOW(rBCPD)
    REPT 8
        ld a, [hl+]
        ldh [c], a
    ENDR
    dec b
    jr nz, .pal
{rope_flash}    ret
"""
    pose_data = "" if _all_pics(project) else f"""
SECTION "Data: Rival poses", {"ROMX[$4000]" if banked else "ROM0"}   ; per pose: 10 full map rows, then their palettes
{nl.join(poses[:POSES_PER_BANK])}

SECTION "Data: Rival poses 2", {"ROMX[$4000]" if banked else "ROM0"}   ; (the rest: a bank holds 25)
{nl.join(poses[POSES_PER_BANK:])}

SECTION "Data: Rival swap", {"ROMX[$4000]" if banked else "ROM0"}
FtSwapSet0:                 ; attack poses (loaded with the scene, and put back)
{_db(pad(swap_sets[0], 0))}
FtSwapSet1:                 ; knockdown
{_db(pad(swap_sets[1], 1))}
FtSwapSet2:                 ; special: the taunt, the arm pop
{_db(pad(swap_sets[2], 2))}
"""          # (every fight in pictures: his poses never shown, none kept)
    data = pose_data + f"""

SECTION "Data: Fight", {"ROMX[$4000]" if banked else "ROM0"}   ; mapped while the fight runs
RivalPalSlots:              ; his palettes' hardware slots, as BCPS writes ($80: auto-increment)
    db {len(rival_pals)}, {", ".join(f"${0x80 | (s.get('pal_slots') or {}).get(k, k) * 8:02X}" for k in rival_pals)}
{tail_data}
{"" if _all_pics(project) else "RivalMaps:" + nl + "    dw " + ", ".join(f"RivalMap_{p}" for p in kit.RIVAL_POSES) + nl + "RivalMapBanks:              ; (each pose's rows' bank)" + nl + "    db " + ", ".join(f"BANK(RivalMap_{p})" for p in kit.RIVAL_POSES)}
RivalPoseRise:              ; per pose: how far it can rise in his band and stay whole (its blank rows on top)
    db {", ".join(str(_blank_top(ft["poses"][p]["pixels"])) for p in kit.RIVAL_POSES)}
CrowdMap:                   ; the crowd row's tiles, put back after each camera flash
    db {", ".join(f"${t:02X}" for t in s['cell_tiles'][crowd_y * CW:(crowd_y + 1) * CW])}
CrowdPulse:                 ; Color, his KO: the crowd's color through the NES's brightnesses (its slot's BCPS, 4 steps)
{_crowd_pulse(s, project)}
RivalPalNormal:
    dw {", ".join(_rgb555(project["palettes"][k]).split(", ")[j] for k in rival_pals for j in range(4))}
RivalPalFlash:              ; a hit flushes him red; the background and outline stay
    dw {", ".join(_rgb555([c if j in (0, 3) else ([31, 16, 12] if j == 1 else [26, 4, 4]) for j, c in enumerate(project["palettes"][k])]).split(", ")[j] for k in rival_pals for j in range(4))}
RivalCueOutline:            ; per palette of his: which color is his outline ($FF: none), for his dodge cue
    db {", ".join("$FF" if o is None else str(o) for o in cue_outline + [None] * (8 - len(cue_outline)))}
NesRgb:                     ; the NES's colors as Color ones: his dodge cue's outline, by its number ($05EC)
    dw {", ".join(f"${(b >> 3) << 10 | (g >> 3) << 5 | (r >> 3):04X}" for r, g, b in NES_RGB)}
RivalJewel:                 ; his turban's gem (Great Tiger's): its tile (0: none), Color palettes (his gloves', in his
    db {jewel_head}         ; tell his white's), then per pose its middle in his area ($FF: not showing)
    db {jewel_poses}
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
{pl_cgb}RefPoses:
    dw {", ".join(f"Ref_{p}" for p in kit.REF_POSES)}
{nl.join(ref_sprites)}
RefTiles:                   ; per pose: its own tiles' address and count, loaded into his area as his pose changes
{nl.join(f"    dw RefTiles_{p}" + nl + f"    db {len(s['fight_ref_tiles'][p])}" for p in kit.REF_POSES)}
{nl.join(f"RefTiles_{p}:" + nl + (_db([b for t in s['fight_ref_tiles'][p] for b in encode_tile(list(t))]) or "") for p in kit.REF_POSES)}
PlayerRare:                 ; per player pose: 1 if it's loaded as it's needed
    db {", ".join("1" if p in kit.PLAYER_RARE else "0" for p in kit.PLAYER_POSES)}
PlayerRareHold:             ; per pose: its sequence (the star punch 1, down and up 2): one held while the next loads
    db {", ".join(str(kit.PLAYER_HOLD.get(p, 0)) for p in kit.PLAYER_POSES)}
RareTiles:                  ; per player pose: its own tiles' address and count (the rare ones)
{nl.join(f"    dw RareTiles_{p}" + nl + f"    db {len(s['fight_rare_tiles'][p])}" if p in kit.PLAYER_RARE else "    dw 0" + nl + "    db 0" for p in kit.PLAYER_POSES)}
{nl.join(f"RareTiles_{p}:" + nl + (_db([b for t in s['fight_rare_tiles'][p] for b in encode_tile(list(t))]) or "") for p in kit.PLAYER_RARE)}
FtObjBytes:                 ; (this fight's: one has a tile more, Great Tiger's gem)
    dw {len(s['fight_obj']) * 16}
    ds -@ & 15                  ; (on 16 bytes: DMA'd in as the fight loads)
FtObjTiles:                 ; the player's {len(s['fight_obj']) - len(kit.COUNT_GLYPHS)} tiles, then the count's glyphs
{_db(obj_bytes)}
{nes_data}
"""
    cgb = s.get("fight_cgb")
    cgb_data = ""
    if cgb:                             # Color's finer poses: their map rows (a bank of their own), then their
        tile_bytes = lambda ts: [b for t in ts for b in encode_tile(list(t))]   # tiles (another): kit_fight.asm
        sets_b = [tile_bytes(t) for t in cgb["sets"]]                            # reads their headers (FtCgb*)
        p0, p1 = tile_bytes(cgb["perm0"]), tile_bytes(cgb["perm1"])
        vram = lambda t: 0x9000 + 16 * t if t < 128 else 0x8800 + 16 * (t - 128)
        runs = []                       # (bank, offset, bytes, where): runs of consecutive slots, split where tile
        slots = [(0, t, n) for n, t in enumerate(cgb["perm0_slots"])] + \
                [(1, cgb["perm1_first"] + n, n) for n in range(len(cgb["perm1"]))]   # 128 moves to $8800
        for b, t, n in slots:
            if runs and runs[-1][0] == b and runs[-1][4] == t and t != 128:
                bank, off, size, where, nxt = runs[-1]
                runs[-1] = (bank, off, size + 16, where, t + 1)
            else:
                runs.append((b, 16 * n, 16, vram(t), t + 1))
        runs = [r[:4] for r in runs]
        cgb_rows = lambda pose: (_db(rows(cgb["maps"][pose], tiles), 32) + "\n"
                                 + _db(rows([a | b << 3 | f << 5 for a, b, f in zip(cgb["attrs"][pose], cgb["banks"][pose], cgb.get("flips", {}).get(pose) or [0] * len(cgb["banks"][pose]))], s["cell_pal"]), 32))
        cgb_data = f"""
SECTION "Data: Rival poses (Color){suffix}", ROMX[$4000]
CgbMaps{suffix}:                ; per pose: its map rows' address, then their bank; each: its rows, their attributes
    dw {", ".join(f"CgbMap{suffix}_{p}" for p in kit.RIVAL_POSES)}
    db {", ".join(f"BANK(CgbMap{suffix}_{p})" for p in kit.RIVAL_POSES)}
    ds {-3 * len(kit.RIVAL_POSES) % 16}                         ; (GDMA copies from 16-byte boundaries)
{nl.join(f"CgbMap{suffix}_{p}:" + nl + cgb_rows(p) for p in kit.RIVAL_POSES[:POSES_PER_BANK - 1])}

SECTION "Data: Rival poses (Color) 2{suffix}", ROMX[$4000]
{nl.join(f"CgbMap{suffix}_{p}:" + nl + cgb_rows(p) for p in kit.RIVAL_POSES[POSES_PER_BANK - 1:])}

SECTION "Data: Rival tiles (Color){suffix}", ROMX[$4000]
CgbSwap{suffix}:                ; each set's tiles; the swap area's runs (tiles, where, bank); the sets; his
    dw {", ".join(str(len(t)) for t in cgb["sets"])}         ; always-there tiles' runs (source, bytes, where, bank)
{nl.join(f"    db {n}" + nl + f"    dw ${vram(t):04X}" + nl + f"    db {b}" for t, n, b in cgb["runs"])}
{nl.join("    db 0, 0, 0, 0" for _ in range(4 - len(cgb["runs"])))}
    dw CgbSwap{suffix}.set0, CgbSwap{suffix}.set1, CgbSwap{suffix}.set2
    db {len(runs)}                    ; then his always-there tiles' runs: source, bytes, where, bank
{nl.join(f"    dw CgbSwap{suffix}.perm{b} + {off}, {n}, ${dest:04X}" + nl + f"    db {b}" for b, off, n, dest in runs)}
    ds {-(29 + 7 * len(runs)) % 16}                         ; (GDMA copies from 16-byte boundaries)
{nl.join(f".set{k}:" + nl + _db(b) for k, b in enumerate(sets_b))}
.perm0:
{_db(p0)}
.perm1:
{_db(p1)}
ASSERT (CgbMap{suffix}_idle | CgbSwap{suffix}.set0) & 15 == 0, "GDMA copies from 16-byte boundaries"
"""
    pics = s.get("fight_pics")
    pics_data = ""
    if pics:                            # Color, an NES fighter: his pictures (kit_fight.asm, FT_PIC_*): a header
        slot_of = s.get("pal_slots") or {}                       # bank, then each picture's tiles and rows
        rival_hw = [slot_of.get(g, g) for g in sorted(set(ft["palettes"].values()))]
        obj = {hw: 5 + k for k, hw in enumerate(rival_hw)}
        n = len(pics["order"])
        assert n <= 128, "a fighter has at most 128 pictures"
        lab = lambda k: f"Pic{suffix}_{k}"
        entries = []
        for k in range(n):
            entries.append(f"    dw {lab(k)}\n    db BANK({lab(k)}), {max(1, len(pics['tiles'][k]))}")
        heads = []
        for k in range(n):
            hl = pics["heads"][k]
            heads.append(f"PicHead{suffix}_{k}:\n    db {len(hl)}" + "".join(
                f"\n    db {dy}, {dx}, {t}, ${obj.get(a, 5) | 1 << 3 | f << 5:02X}" for dy, dx, t, a, f in hl))
        body = []
        for k in range(n):
            tb = [b for t in pics["tiles"][k] for b in encode_tile(list(t))] or [0] * 16
            maprow = rows(pics["maps"][k], tiles)
            attrow = rows([a | 1 << 3 | f << 5 for a, f in zip(pics["attrs"][k], pics["flips"][k])], s["cell_pal"])
            maprow2 = rows([t + 64 for t in pics["maps"][k]], tiles)     # (for its tiles' second copy, 64 on)
            body.append(f'SECTION "Data: Rival picture {pics["order"][k]}{suffix}", ROMX, ALIGN[4]\n{lab(k)}:\n'
                        + _db(tb) + "\n" + _db(maprow, 32) + "\n" + _db(attrow, 32) + "\n" + _db(maprow2, 32))
        pics_data = f"""
SECTION "Data: Rival pictures{suffix}", ROMX[$4000]
PicHeader{suffix}:              ; his NES pictures: count, the idle one's; per NES frame (then mirrored) its picture,
    db {n}, {pics["idle"]}       ; its place's x, y; per picture its tiles (address, bank, count), its top rows' sprites
    ds 14
{_db(pics["frame_map"])}
{_db([dx & 0xFF for dx, _ in pics["places"]])}
{_db([dy & 0xFF for _, dy in pics["places"]])}
{nl.join(entries)}
    ds {4 * (128 - n)}
    dw {", ".join(f"PicHead{suffix}_{k}" for k in range(n))}
    ds {2 * (128 - n)}
{nl.join(heads)}
ASSERT PicHeader{suffix} == $4000
{nl.join(body)}
"""
    dpics = s.get("fight_pics_dmg")
    if dpics and pics:                  # the original: his pictures in greys (FT_DMG_PICS): a header bank, then each
        n = len(dpics["tiles"])         # picture's tiles and his area's rows for each copy of them
        lab = lambda k: f"PicDmg{suffix}_{k}"
        entries = "\n".join(f"    dw {lab(k)}\n    db BANK({lab(k)}), {max(1, len(dpics['tiles'][k]))}\n    dw PicHeadDmg{suffix}_{k}"
                            for k in range(n))
        heads = "\n".join(f"PicHeadDmg{suffix}_{k}:\n    db {len(dpics['heads'][k])}" + "".join(
            f"\n    db {dy}, {dx}, {t}, 0" for dy, dx, t in dpics["heads"][k]) for k in range(n))
        body = []
        for k in range(n):
            tb = [b for t in dpics["tiles"][k] for b in encode_tile(list(t))] or [0] * 16
            body.append(f'SECTION "Data: Rival grey picture {k}{suffix}", ROMX, ALIGN[4]\n{lab(k)}:\n' + _db(tb) + "\n"
                        + _db(dpics["maps"][k], kit.REGION_W) + "\n" + _db([t + 64 for t in dpics["maps"][k]], kit.REGION_W))
        pics_data += f"""
SECTION "Data: Rival grey pictures{suffix}", ROMX[$4000]
PicHeaderDmg{suffix}:           ; his pictures in greys: count; per picture its tiles (address, bank, count), his top rows'
    db {n}                      ; sprites; each picture's tiles, then his area's rows for its tiles' first copy, then second
    ds 15
{entries}
    ds {6 * (128 - n)}
PicNextDmg{suffix}:             ; per picture: the one likely next, then (the picture before it this one) the one then
{_db(_pic_next(s, pics))}
{heads}
ASSERT PicHeaderDmg{suffix} == $4000
ASSERT PicNextDmg{suffix} == $4310
{nl.join(body)}
"""
    if not shared:                      # a later fight: its scene's update, its own data under its own labels
        data, checks = _suffixed(data, suffix)
        return f"""; ---- Fight: "{s['name']}" (its own data; the kit is the first fight's) ----
Scene{i}Update:
    jp FightUpdate
{data}
{cgb_data}
{pics_data}
{heads_data}
{checks}
SECTION "Code: Scenes after fight {i}", ROM0
"""
    return code + data + cgb_data + pics_data + heads_data + nes_shared + """
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


def _pk_menu_code(i, pk, beep=True):
    """Punch-Out!!'s pass key, under its menu item while that's chosen: left/right change the digit (the first
    press shows it, 0), A, B or Start go on to the next (0 again); after the tenth the key is checked: a code
    plays out as a choice does, to its scene, else the key is forgotten (dashes again). Moving off hides it."""
    item = pk["item"]
    return f"""    ldh a, [hSel]           ; the pass key: shown while its item's chosen
    cp {item}
    jp z, .pk
    ld a, [wPkShown]
    and a
    jp z, .menu
    xor a                   ; moved off it: the rows as they were, the key forgotten
    ld [wPkShown], a
    call PkReset
    ld hl, Scene{i}PkHide
    QUEUE_PATCH PkListPatch
    jp .menu
.pk:
    ld a, [wPkShown]
    and a
    jp nz, .pkKeys
    inc a
    ld [wPkShown], a
    call PkReset
    ld hl, Scene{i}PkShow
    QUEUE_PATCH PkListPatch
    jp .menu
.pkKeys:
    ldh a, [hPadNew]
    ld b, a
    and PADF_LEFT | PADF_RIGHT
    jp z, .pkNotLR
    ld a, [wPkEdit]
    and a
    jp z, .pkStart
    call .pkDigit
    bit PAD_RIGHT, b
    jp z, .pkLeft
    inc a
    cp 10
    jp c, .pkSet
    xor a
    jp .pkSet
.pkLeft:
    sub 1
    jp nc, .pkSet
    ld a, 9
.pkSet:
    ld [hl], a
    ld a, SFX_PASS_DIGIT
    call PlaySfx
    jp .pkShow
.pkNotLR:
    ld a, [wPkEdit]         ; (Select while typing: held for a special key, not a move)
    and a
    jr z, .pkAny
    bit 2, b
    jp nz, .cursor
.pkAny:
    ld a, b
    and PADF_A | PADF_B | PADF_START
    jp z, .menu
    ld a, [wPkEdit]
    and a
    jp nz, .pkNext
    bit PAD_START, b        ; (Start before a digit: nothing)
    jp nz, .cursor
.pkStart:                   ; the first digit: 0, its blip
    ld a, 1
    ld [wPkEdit], a
    xor a
    ld [wPkPos], a
    ld [wPkDigits], a
    ld a, SFX_PASS_DIGIT
    call PlaySfx
    jp .pkShow
.pkNext:
    ld a, [wPkPos]
    inc a
    ld [wPkPos], a
    cp 10
    jp z, .pkCheck
    call .pkDigit
    xor a
    ld [hl], a
    ld a, SFX_PASS_NEXT
    call PlaySfx
    jp .pkShow
.pkCheck:                   ; the ten digits against each code
    ld hl, Scene{i}PkCodes
    ld a, [hl+]
    and a
    jp z, .pkWrong
    ld c, a
.pkCode:
    push hl
    ld de, wPkDigits
    ld b, 10
.pkCmp:
    ld a, [de]
    cp [hl]
    jp nz, .pkMiss
    inc de
    inc hl
    dec b
    jp nz, .pkCmp
    ld a, [hl]              ; a match: its scene, the choice played out
    pop hl
    ld [wPkTarget], a
{"    ld a, SFX_MENU_CONFIRM" + chr(10) + "    call PlaySfx" + chr(10) if beep else ""}    jp .choose
.pkMiss:
    pop hl
    ld de, 11
    add hl, de
    dec c
    jp nz, .pkCode
.pkWrong:                   ; no match: forgotten, dashes again
{_pk_nes() if pk.get("_nes") else ""}    call PkReset
    ld hl, Scene{i}PkShow
    QUEUE_PATCH PkListPatch
    jp .cursor
.pkDigit:                   ; HL -> the digit being set, A = it
    ld a, [wPkPos]
    add LOW(wPkDigits)
    ld l, a
    adc HIGH(wPkDigits)
    sub l
    ld h, a
    ld a, [hl]
    ret
.pkShow:                    ; the digit being set, on screen next VBlank
    call .pkDigit
    ld b, a
    ld a, [wPkPos]
    ld e, a
    add a
    add a
    add a
    add e
    add e
    add e                   ; 11 tiles a place (0-9, the dash)
    add b
    add LOW(Scene{i}PkDigits)
    ld l, a
    adc HIGH(Scene{i}PkDigits)
    sub l
    ld h, a
    ld a, [hl]
    ld [wPkPatch + 3], a
    ld a, e
    add a
    add LOW(Scene{i}PkCells)
    ld l, a
    adc HIGH(Scene{i}PkCells)
    sub l
    ld h, a
    ld a, [hl+]
    ld [wPkPatch + 1], a
    ld a, [hl]
    ld [wPkPatch + 2], a
    ld a, 1
    ld [wPkPatch], a
    ld hl, wPkPatch
    QUEUE_PATCH PkListPatch
    jp .cursor
"""


def _pk_data(i, pk):
    """The pass key's tables: its rows shown and hidden (cell address, tile), its places' tiles and cells, the codes."""
    nl = "\n"
    cell = lambda c: f"${0x9800 + (c // CW) * 32 + c % CW:04X}"
    rows = lambda pairs: f"    db {len(pairs)}" + nl + nl.join(f"    db LOW({cell(c)}), HIGH({cell(c)}), ${t:02X}" for c, t in pairs)
    codes = pk["codes"]
    return (f"Scene{i}PkShow:" + nl + rows(pk["show"]) + nl + f"Scene{i}PkHide:" + nl + rows(pk["hide"]) + nl
            + f"Scene{i}PkDigits:            ; per place: its tile showing 0-9, then the dash" + nl
            + nl.join("    db " + ", ".join(f"${t:02X}" for t in tiles) for tiles in pk["digits"]) + nl
            + f"Scene{i}PkCells:" + nl + "    dw " + ", ".join(cell(c) for c in pk["cells"]) + nl
            + f"Scene{i}PkCodes:             ; how many; each: its ten digits, its scene" + nl + f"    db {len(codes)}" + nl
            + nl.join("    db " + ", ".join(str(d) for d in c["key"]) + f", {c['target']}" for c in codes))


PK_CODE = """
SECTION "Pass key, under a menu item", WRAM0
wPkDigits: ds 10            ; 0-9; 10 not set (a dash)
wPkPos: db
wPkEdit: db                 ; a digit set yet
wPkShown: db
wPkTarget: db
wPkPatch: ds 4

SECTION "Code: Pass key, under a menu item", ROM0
PkReset:                    ; every place a dash, none set
    ld hl, wPkDigits
    ld a, 10
    ld b, 10
.dash:
    ld [hl+], a
    dec b
    jr nz, .dash
    xor a
    ld [wPkPos], a
    ld [wPkEdit], a
    ret

PkListPatch:                ; (VBlank) HL -> how many, then each cell's address and tile
    ld a, [hl+]
    ld b, a
.cell:
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld [de], a
    dec b
    jr nz, .cell
    ret
"""


def _cut_oam(s):
    """A cutscene's sprites per frame (every actor's at that frame): (y, x, tile, attributes) as OAM takes them."""
    cs, frames = s["cutscene"], s["cut_frames"]
    n = max(len(a["frames"]) for a in cs["actors"]) if cs["actors"] else 1
    out = []
    for f in range(n):
        spr = []
        for a, per in zip(cs["actors"], frames):
            for dy, dx, t, pal in per[f % len(per)]:
                spr.append((a["y"] + dy + 16, a["x"] + dx + 8, t + 2, (pal & 7) | ((pal & 1) << 4)))
        out.append(spr)
    return out


def _cut_code(i, s, index_of):
    """A cutscene: the picture scrolls (its top rows don't: the box's), the actors cycle, the box comes up and
    writes itself, then Start goes on."""
    cs, box = s["cutscene"], s["cutscene"]["box"]
    every = cs["actors"][0]["every"] if cs["actors"] else 8
    split = (box["y"] + len(box["lines"]) + 2) * 8 if box else 0
    box_rows = len(box["lines"]) + 2 if box else 0
    target = index_of[s["press"]["target"]]
    ck = s.get("cut_key") or {}
    key_patch = f"""    ldh a, [hCutTyped]      ; a pass key's digit (the letter just counted): the one worked out
    sub {ck['first'] + 1}           ; (PwKeyFromRecord)
    cp 10
    jr nc, .notKey
    add LOW(wPw + $10)
    ld l, a
    ld h, HIGH(wPw)
    ld a, [hl]
    ld hl, Scene{i}KeyGlyphs
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
    ld [wCutPatch + 3], a
.notKey:
""" if ck.get("circuit") is not None else ""
    hush = ("IF DEF(FT_NES_SOUND)\n    ldh a, [hNesSound]      ; (quiet: its NES song stopped as it goes on)\n    and a\n"
            "    jr z, .hushed\n    ld a, $80\n    ld [wNes + $F2], a\n.hushed:\nENDC\n") if s["press"].get("quiet") else ""
    box_code = f"""    ldh a, [hCutDone]       ; the box: after its wait, its background, then a letter every few frames
    and a
    jp nz, .start
    ld hl, wCutWait
    ld a, [hl+]
    or [hl]
    jr z, .boxing
    dec hl
    ld a, [hl]
    sub 1
    ld [hl+], a
    jp nc, .split
    dec [hl]
    jp .split
.boxing:
    ldh a, [hCutBox]        ; its background a row a frame (a frame's VBlank holds a row's writes)
    cp {box_rows}
    jr nc, .typing
    inc a
    ldh [hCutBox], a
    dec a
    add a
    ld l, a
    ld h, 0
    ld bc, Scene{i}CutBox
    add hl, bc
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    QUEUE_PATCH PkListPatch
    jp .split
.typing:
    ld hl, hCutTick
    dec [hl]
    jp nz, .split
    ld [hl], {box['every']}
    ldh a, [hCutTyped]
    ld c, a
    inc a
    ldh [hCutTyped], a
    cp {len(s['cut_typed'])}
    jr c, .letter
    ld a, 1
    ldh [hCutDone], a
.letter:
    ld b, 0
    ld h, b
    ld l, c
    add hl, hl
    add hl, bc              ; three bytes a letter
    ld bc, Scene{i}CutTyped
    add hl, bc
    ld de, wCutPatch + 1
    REPT 3
        ld a, [hl+]
        ld [de], a
        inc de
    ENDR
{key_patch}    ld a, 1
    ld [wCutPatch], a
    ld hl, wCutPatch
    QUEUE_PATCH PkListPatch
    ld a, SFX_TYPE          ; its tick, as the NES's
    call PlaySfx
    jp .split
.start:
    ldh a, [hPadNew]
    and PADF_START | PADF_A
    jp z, .split
{hush}    ld a, {target}
    jp StartTransition
""" if box else f"""    ldh a, [hPadNew]
    and PADF_START | PADF_A
    jp z, .split
{hush}    ld a, {target}
    jp StartTransition
"""
    return f"""Scene{i}Update:              ; a cutscene: the picture scrolls by, the actors run, its box writes itself
    ldh a, [hCutBox]        ; the box up: the picture has stopped (as the NES's)
    and a
    jr nz, .moved
    ld hl, Scene{i}CutBands ; each band on by its speed, the picture moving right (as the NES's)
    ld b, [hl]
    inc hl
    ld de, wCutBands
.advance:
    inc hl                  ; (its line)
    ld a, [de]
    sub [hl]
    ld [de], a
    inc hl
    inc de
    ld a, [de]
    sbc [hl]
    ld [de], a
    inc hl
    inc de
    inc hl                  ; (its start)
    inc hl
    dec b
    jr nz, .advance
.moved:
    ld hl, hCutAnim         ; the actors' next frame
    dec [hl]
    jr nz, .still
    ld [hl], {every}
    ldh a, [hCutFrame]
    inc a
    cp {len(_cut_oam(s))}
    jr c, .frame
    xor a
.frame:
    ldh [hCutFrame], a
    ld hl, Scene{i}CutFrames
    call CutFrame
.still:
{box_code}.split:                     ; under the box the picture scrolls, each band from its line its own way
    call SfxUpdate          ; (the sound first: the splits run to the bottom of the screen)
.vblank:
    ldh a, [rLY]            ; (out of VBlank first)
    cp 144
    jp nc, .split
    ld hl, Scene{i}CutBands
    ld b, [hl]
    inc hl
    ld de, wCutBands + 1
.band:
    ld c, [hl]              ; its line
    ld a, l
    add 5
    ld l, a
    adc h
    sub l
    ld h, a
.line:
    ldh a, [rLY]
    cp c
    jr c, .line
    ld a, [de]              ; its scroll (whole pixels)
    inc de
    inc de
    ld c, a
.hblank:
    ldh a, [rSTAT]
    and 3
    jr nz, .hblank
    ld a, c
    ldh [rSCX], a
    dec b
    jr nz, .band
    ret
"""


def _cut_data(i, s):
    """A cutscene's tables: its actors' tiles, its sprites per frame, its box's background and letters."""
    nl = "\n"
    cell = lambda c: f"${0x9800 + (c // 32) * 32 + c % 32:04X}"
    oam = _cut_oam(s)
    tile_bytes = [b for t in s["cut_obj"] for b in encode_tile(list(t))]
    out = [f"Scene{i}CutObj:", _db(tile_bytes) or "", f"Scene{i}CutFrames:            ; per frame: its sprites' count, then each (y, x, tile, attributes)",
           "    dw " + ", ".join(f"Scene{i}CutFrame{f}" for f in range(len(oam)))]
    for f, spr in enumerate(oam):
        out.append(f"Scene{i}CutFrame{f}:")
        out.append(f"    db {len(spr)}")
        out += [f"    db {y}, {x}, {t}, ${a:02X}" for y, x, t, a in spr]
    rows = {}                           # its background by row: a list patch each
    for c, t in s["cut_box"]:
        rows.setdefault(c // 32, []).append((c, t))
    out.append(f"Scene{i}CutBox:")
    out.append("    dw " + ", ".join(f"Scene{i}CutBox{r}" for r in sorted(rows)) if rows else "")
    for r in sorted(rows):
        out.append(f"Scene{i}CutBox{r}:")
        out.append(f"    db {len(rows[r])}")
        out += [f"    db LOW({cell(c)}), HIGH({cell(c)}), ${t:02X}" for c, t in rows[r]]
    cs = s["cutscene"]
    after = cs["box"]["after"] if cs["box"] else 0
    split = (cs["box"]["y"] + len(cs["box"]["lines"]) + 2) * 8 if cs["box"] else 0
    out.append(f"Scene{i}CutBands:             ; per band: its line, speed (8.8, a frame), start (8.8: where it ends up at endX)")
    out.append(f"    db {len(cs['bands'])}")
    for k, b in enumerate(cs["bands"]):
        start = (b["end_x"] * 256 + b["speed"] * after) % 65536 if cs["box"] else b["end_x"] * 256
        out.append(f"    db {max(b['y'], split) if k == 0 else max(b['y'], split + 1)}")
        out.append(f"    dw {b['speed']}, ${start:04X}")
    out.append(f"Scene{i}CutTyped:")
    out += [f"    db LOW({cell(c)}), HIGH({cell(c)}), ${t:02X}" for c, t in s["cut_typed"]]
    if (s.get("cut_key") or {}).get("circuit") is not None:
        out += [f"Scene{i}KeyGlyphs:          ; its pass key's digits 0-9", "    db " + ", ".join(f"${g:02X}" for g in s["cut_key"]["glyphs"])]
    return nl.join(out)


CUT_CODE = """
SECTION "Cutscene", WRAM0
wCutWait: dw                ; frames till the box comes up
wCutBands: ds 2 * 12        ; each band's scroll (8.8)
wCutOAM: ds 4 * {MAX}       ; the actors' sprites (VBlank puts them in OAM from entry 2)
wCutPatch: ds 4

SECTION "Code: Cutscene", ROM0
; HL = the scene's frames table: the first frame's sprites in, the scroll at the start, its VBlank work on.
CutStart::
    xor a
    ldh [hCutX], a
    ldh [hCutSub], a
    ldh [hCutFrame], a
    ldh [hCutDone], a
    ldh [hCutBox], a
    ldh [hCutTyped], a
    inc a
    ldh [hCutTick], a
    ldh [hCutAnim], a
    ld b, 4 * {MAX}         ; (none left over)
    ld de, wCutOAM
.clear:
    xor a
    ld [de], a
    inc de
    dec b
    jr nz, .clear
    call CutFrame
    ld a, 1
    ldh [hCutOn], a
    ret

; HL = the frames table; the frame hCutFrame's sprites into wCutOAM.
CutFrame::
    ldh a, [hCutFrame]
    add a
    ld e, a
    ld d, 0
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [hl+]
    add a
    add a                   ; bytes
    ld b, a
    ld c, a
    ld de, wCutOAM
    and a
    jr z, .rest
.copy:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copy
.rest:                      ; the rest hidden
    ld a, 4 * {MAX}
    sub c
    ret z
    ld b, a
    xor a
.hide:
    ld [de], a
    inc de
    dec b
    jr nz, .hide
    ret

; (VBlank) the box's rows unscrolled; the actors' sprites into OAM.
CutVBlank::
    xor a
    ldh [rSCX], a
    ld hl, wCutOAM
    ld de, $FE08
    ld b, 4 * {MAX}
.oam:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .oam
    ret
"""


CARD_CODE = """
DEF CARD_TOP EQU 144         ; the scroll that shows the card whole

SECTION "Round card", WRAM0
wCardRows: dw               ; the card's rows (tiles, then attributes)
wCardRow: db                ; the next to draw
wCardY: db                  ; the screen's scroll up so far
wCardHold: db
wCardDst: dw
wCardOn: db                 ; up (the slide step leaves the scroll be; cleared as a scene loads)

SECTION "Code: Round card", ROM0
; A frame of the card: its next row, if the scroll has brought it a row from view, into the map rows below the
; screen ((18 + row) & 31: past the bottom, round to the top's, gone by then).
CardStep:
    ld a, [wCardRow]
    cp 18
    ret nc
    ld c, a
    add a
    add a
    add a
    ld b, a                 ; B = 8 x row
    ld a, [wCardY]
    add 8
    cp b
    ret c
    ld a, c
    inc a
    ld [wCardRow], a
    add 18 - 1
    and 31
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld de, $9800
    add hl, de
    ld a, l
    ld [wCardDst], a
    ld a, h
    ld [wCardDst + 1], a
    ld a, [wCardRows]
    ld l, a
    ld a, [wCardRows + 1]
    ld h, a
    ld b, 0
    ld a, c                 ; + 20 x row
    add a
    add a
    ld c, a
    add hl, bc
    add hl, bc
    add hl, bc
    add hl, bc
    add hl, bc
    QUEUE_PATCH CardRowPatch
    ret

; (VBlank) HL = a card row's tiles: into the map at wCardDst; Color: its attributes too (18 rows on).
CardRowPatch:
    ld a, [wCardDst]
    ld e, a
    ld a, [wCardDst + 1]
    ld d, a
    push de
    ld b, 20
.tile:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .tile
    pop de
    ldh a, [hIsCGB]
    and a
    ret z
    ld bc, 340
    add hl, bc
    ld a, 1
    ldh [rVBK], a
    ld b, 20
.attr:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .attr
    xor a
    ldh [rVBK], a
    ret
"""


TYPE_CODE = """
DEF TY_END EQU 0
DEF TY_PAUSE EQU 1          ; frames
DEF TY_LETTER EQU 2         ; a list patch of one (1, address, tile); its sound, then a letter's wait
DEF TY_CLEAR EQU 3          ; a list patch (a row back as it was); on next frame
DEF TY_SPACE EQU 4          ; a letter's wait
DEF TY_SOUND EQU 5          ; the letters' sound from here: an effect + 1 (0 none)

SECTION "Typed text", WRAM0
wTyPtr: dw
wTyWait: db
wTySound: db
wTyEvery: db
wTyDone: db

SECTION "Code: Typed text", ROM0
; HL = a scene's groups, A = the group (past the last: the last); one of its variants at random to type.
TypeStart::
    ld c, a
    ld a, [hl+]
    dec a
    cp c
    jr c, .last
    ld a, c
.last:
    add a
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld b, [hl]              ; its variants: one by the divider's count
    inc hl
    ldh a, [$FF04]          ; (DIV)
.mod:
    sub b
    jr nc, .mod
    add b
    add a
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl+]
    ld [wTyPtr], a
    ld a, [hl]
    ld [wTyPtr + 1], a
    xor a
    ld [wTyWait], a
    ld [wTySound], a
    ld [wTyDone], a
    ret

; A frame of typing: the next op once the wait is over. (One patch a frame: every op that queues one ends it.)
TypeStep::
    ld hl, wTyWait
    ld a, [hl]
    and a
    jr z, .next
    dec [hl]
    ret
.next:
    ld a, [wTyPtr]
    ld l, a
    ld a, [wTyPtr + 1]
    ld h, a
.op:
    ld a, [hl+]
    and a
    jr z, .end
    dec a
    jr z, .pause
    dec a
    jr z, .letter
    dec a
    jr z, .clear
    dec a
    jr z, .space
    ld a, [hl+]             ; TY_SOUND
    ld [wTySound], a
    jr .op
.pause:
    ld a, [hl+]
    ld [wTyWait], a
    jr .save
.letter:
    QUEUE_PATCH PkListPatch
    ld de, 4
    add hl, de
    ld a, [wTySound]
    and a
    jr z, .space
    dec a
    call PlaySfx            ; (keeps HL)
.space:
    ld a, [wTyEvery]
    dec a
    ld [wTyWait], a
    jr .save
.clear:
    QUEUE_PATCH PkListPatch
    ld a, [hl+]
    ld e, a
    add a
    add e
    ld e, a
    ld d, 0
    add hl, de
    jr .save
.end:
    dec hl
    ld a, 1
    ld [wTyDone], a
.save:
    ld a, l
    ld [wTyPtr], a
    ld a, h
    ld [wTyPtr + 1], a
    ret
"""


def _pk_nes():
    """The title's pass key as Punch-Out!!'s: the NES's own (PwContinue), when none of the menu's codes matched."""
    return """    call PwContinueFar
    cp $FE
    jr nz, .pkNotBusy
    ld c, 10                ; a busy signal, as the NES's: its beep ten times, a beat apart; then the key forgotten
.pkBusy:
    push bc
    ld a, SFX_PASS_DIGIT
    call PlaySfx
    ld c, 48
.pkBeat:                    ; (a frame: out of VBlank, then into the next)
    ldh a, [rLY]
    cp 144
    jr nc, .pkBeat
.pkFrame:
    ldh a, [rLY]
    cp 144
    jr c, .pkFrame
    push bc
    call SfxUpdate
    pop bc
    dec c
    jr nz, .pkBeat
    pop bc
    dec c
    jr nz, .pkBusy
    jr .pkNotNes
.pkNotBusy:
    cp $FF
    jr z, .pkNotNes
    ld [wPkTarget], a
    ld a, SFX_MENU_CONFIRM
    call PlaySfx
    jp .choose
.pkNotNes:
"""


def _menu_code(i, s, fade=False, fights=False):
    nl = "\n"
    m = s["menu"]
    n = len(m["items"])
    gl = m.get("gloves")
    gloves_set = f"""    ldh a, [hSel]           ; the gloves either side of the chosen item (they jump, as the NES's)
    add LOW(Scene{i}CursorY)
    ld l, a
    adc HIGH(Scene{i}CursorY)
    sub l
    ld h, a
    ld a, [hl]
    add {gl['dy'] & 0xFF}
    ldh [hGloveY], a
""" if gl else ""
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
{"    bit 1, a                ; the glove out in front: the menu's gloves away (as the NES's)" + nl + "    jr z, .behind" + nl + "    xor a" + nl + "    ldh [hGloveY], a" + nl + ".behind:" + nl if gl else ""}    inc de
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
{"    call ConfirmBuild       ; (its sprites built now, for VBlank's DMA)" + nl if fights else ""}    ld a, 1
    ldh [hConfirmDirty], a
    ret
.done:
    ld a, [wConfirmStep]
    and a
    jr z, .go
    xor a                   ; the sprite away first (next VBlank), then go
    ld [wConfirmStep], a
    ld [wConfirmStep + 9], a
{"    call ConfirmBuild" + nl if fights else ""}    inc a
    ldh [hConfirmDirty], a
    ldh [hTimer], a
    ret
.go:
{"    ld a, FADE_STEPS        ; the steps left the screen faded: on with the fade from there" + nl + "    ldh [hFadeStep], a" + nl if fade and m["confirm"]["faded"] else ""}{("    ldh a, [hSel]           ; (the pass key's item: the scene its code goes to)" + nl + f"    cp {m['pass_key']['item']}" + nl + "    jr nz, .item" + nl + "    ld a, [wPkTarget]" + nl + "    jp StartTransition" + nl + ".item:" + nl) if m.get("pass_key") else ""}    ldh a, [hSel]
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
    pk = m.get("pass_key")
    return f"""Scene{i}Update:              ; menu: up/down{"/Select" if select else ""} to move, A or Start to choose
{_pk_menu_code(i, pk, not any(st["sfx"] for st in (m.get("confirm") or {}).get("steps", []))) + ".menu:" + nl if pk else ""}    ldh a, [hPadRepeat]
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
{"    ldh a, [hSel]           ; (the pass key's item: its keys are the key's)" + nl + f"    cp {pk['item']}" + nl + "    jr z, .cursor" + nl if pk else ""}    ldh a, [hPadNew]
    and PADF_A | PADF_START
    jr z, .cursor
{"" if any(st["sfx"] for st in (m.get("confirm") or {}).get("steps", [])) else "    ld a, SFX_MENU_CONFIRM" + nl + "    call PlaySfx" + nl}{".choose:" + nl if pk else ""}{confirm_start}
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
{bob}{gloves_set}    ret

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
    if m.get("gloves"):
        g = m["gloves"]
        lines += [f"Scene{i}GloveTiles:          ; the left glove's 6 tiles (the right: them mirrored)",
                  _db([b for t in g["tiles"] for b in encode_tile(t)]),
                  f"Scene{i}GloveColors:         ; its sprite palette (Color)",
                  "    dw " + _rgb555([g["colors"][0]] + g["colors"])]
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
    slides = any(s.get("slide") or (s["press"] or {}).get("card") for s in scenes)   # (a round card scrolls too)
    cards = [i for i, s in enumerate(scenes) if (s["press"] or {}).get("card")]
    glove_scenes = [i for i, s in enumerate(scenes) if (s["menu"] or {}).get("gloves")]
    if len(glove_scenes) > 1:
        raise ProjectError(["One menu can have gloves for a cursor for now."])
    gloves = (scenes[glove_scenes[0]]["menu"]["gloves"], glove_scenes[0]) if glove_scenes else None
    if gloves and len((scenes[gloves[1]]["menu"].get("confirm") or {}).get("oam", [])) > 27:
        raise ProjectError(["A menu with gloves has room for 27 sprites in its confirm animation (OAM 2-28)."])
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
    patches = options or menus or passes or any(s["press"] and (s["press"]["area"] or s.get("typed") or s["press"].get("card") or (s["press"]["prompt"] and s["press"]["prompt"]["blink"]))
                           for s in scenes)
    prompt_blink = any(s["press"] and s["press"]["prompt"] and s["press"]["prompt"]["blink"] for s in scenes)
    interactive = menus or presses or options or passes or bool(puzzles) or bool(fights) or slides or \
        any(s["back"] is not None for s in scenes)
    if len(scenes) == 1 and not interactive:
        return _static_asm(project, scenes[0])

    cursor_on = (menus or options) and project["cursor"] is not None
    cutscenes = [i for i, sc in enumerate(scenes) if sc.get("cutscene")]
    typed_scenes = [i for i, sc in enumerate(scenes) if sc.get("typed")]
    sprites = cursor_on or bool(fights) or bool(cutscenes)
    # Past what a plain 32 KB cartridge holds, scene data moves to switchable banks (MBC5).
    data_bytes = sum(len(s["tiles"]) * 16 + MAP_BYTES for s in scenes) + sum(FIGHT_BYTES for s in scenes if s.get("fight")) \
        + sum(0x4800 + (0x4000 if s["fight"]["nes"].get("sound") else 0)
              for s in scenes if (s.get("fight") or {}).get("nes"))
    banked = data_bytes > BANK_THRESHOLD
    fade = project["transition"]
    nes_sound_any = any((s.get("fight") or {}).get("nes", {}).get("sound") for s in scenes)
    nes_any = any((s.get("fight") or {}).get("nes") for s in scenes)
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
        hram += ["hFadeStep: db", "hPalDirty: db", "hLoadOn: db             ; loading with the display on (VWait)"]
    if cutscenes:
        hram += ["hCutOn: db              ; a cutscene's VBlank work", "hCutX: db", "hCutSub: db", "hCutAnim: db",
                 "hCutFrame: db", "hCutDone: db", "hCutBox: db", "hCutTyped: db", "hCutTick: db"]
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
    if gloves:
        hram += ["hGloveY: db             ; the menu's gloves: OAM y (0: away)", "hGloveOn: db"]
    if fights:
        hram += ["hFtActive: db", "hFtHudReady: db", "hFtScx: db", "hFtBandX: db", "hFtBandY: db", "hFtBandTop: db", "hFtBandGap: db", "hFtBandBottom: db", "hFtBandOn: db", "hFtShowX: db", "hFtShowY: db", "hFtShowBottom: db", "hFtOamBuild: db", "hFtOamShown: db", "hFtFlash: db",
                 "hFtFlashShown: db", "hFtHeadN: db            ; (his top rows' sprites to go)",
                 "hFtPlY: db              ; (Mac's sprites: y, x, tiles' copy)", "hFtPlX: db", "hFtPlTile: db",
                 "hOAMDMA: ds 8           ; OAM DMA routine (runs from HRAM)"]
        if any((scenes[i]["fight"].get("nes") or {}).get("sound") for i in fights):
            hram += ["hNesSound: db           ; nonzero: the NES's sound engine has the sound hardware"]
    hram.append("hVarsEnd:")

    vblank_work = []
    if slides:
        vblank_work.append("""    ldh a, [hScrollY]       ; a scene sliding in: this frame's scroll
    ldh [rSCY], a""")
    if cutscenes:
        vblank_work.append("""    ldh a, [hCutOn]         ; a cutscene: its top unscrolled, its actors' sprites
    and a
    call nz, CutVBlank""")
    if fights:
        if fade:                        # (palettes first: a fade's must land in VBlank, before the fight's own work)
            vblank_work.append("    ldh a, [hPalDirty]\n    and a\n    call nz, UploadPalettes")
        vblank_work.append("""    ldh a, [hFtActive]      ; fight: sprites, the rival's pose, the HUD
    and a
    call nz, FtVBlank""" + ("""
    ldh a, [hFtActive]      ; (a fight on the original: what's left of VBlank, his coming picture's tiles)
    and a
    call nz, FtDmgStreamVBlank""" if any((sc.get("fight") or {}).get("nes") for sc in scenes) else ""))
    if confirms and fights:             # (first: its OAM DMA covers all of OAM, the cursor's and gloves' after it)
        vblank_work.append("""    ldh a, [hConfirmDirty]  ; a menu choice's animation: its sprite and colors
    and a
    call nz, ConfirmApply""")
    if cursor_on:
        vblank_work.append(("""    ldh a, [hFtActive]      ; (a fight's sprites are its own: its first is no cursor)
    and a
    jr nz, .noCursor
""" if fights else "") + """    ldh a, [hCursorY]       ; a few sprites: write them straight to OAM (cheaper than DMA)
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""" + ("\n.noCursor:" if fights else ""))
    if gloves:
        vblank_work.append("    call GloveOam           ; the menu's gloves (or them away)")
    if markers:
        vblank_work.append(("""    ldh a, [hFtActive]      ; (nor its second a slider's marker)
    and a
    jr nz, .noMarker
""" if fights else "") + """    ldh a, [hMarkerY]
    ld [OAM_CURSOR + 4], a
    ldh a, [hMarkerX]
    ld [OAM_CURSOR + 5], a""" + ("\n.noMarker:" if fights else ""))
    if confirms and not fights:
        vblank_work.append("""    ldh a, [hConfirmDirty]  ; a menu choice's animation: its sprite and colors
    and a
    call nz, ConfirmApply""")
    if fade and not fights:
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
    if fights:
        boot.append("""    ld hl, OAMDMACode       ; the OAM DMA routine into HRAM, once its variables are cleared (a menu's confirm uses it too, before any fight)
    ld de, hOAMDMA
    ld b, OAMDMACodeEnd - OAMDMACode
.oamDma:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .oamDma""")
    if interactive:
        boot.append("    call SfxInit")
        boot.append("    ld a, $C3               ; JP opcode for the update trampoline\n    ldh [hUpdateJump], a")
    if patches:
        boot.append("    ldh [hPatchJump], a     ; ... and for the patch trampoline")

    # Plain screens (press-start, still) load with the display on behind the faded-out palettes: copies wait for
    # VBlank (VWait) and go in pieces. (Switching the display off flashes white on Game Boy Color.)
    screen_on = [i for i, s in enumerate(scenes) if fade and not (s["menu"] or s["options"] or s.get("puzzle")
                                                                or s.get("fight") or s.get("pass_key"))]
    # Fights on Color load the same way (their copies by DMA, a VBlank's worth at a time): the original's would take
    # too long, its display off.
    fight_on = [i for i, s in enumerate(scenes) if fade and s.get("fight")]
    load_on = screen_on + fight_on
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
        finish.append(("    call VWait" + nl if load_on else "") + """    ldh a, [hCursorY]       ; OAM is writable while the screen is off
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""")

    updates = [f"Scene{i}Update" if s["menu"] or s["press"] or s["options"] or s.get("puzzle") or s.get("fight") or s.get("pass_key")
               or s["back"] is not None else "NoUpdate"
               for i, s in enumerate(scenes)]
    # Fights: each one's swap sets padded alike (their labels sit where the first fight's do), and the table of
    # each one's own values the kit loads (FtFights).
    fight_pads = {k: max(len(scenes[f]["fight_swap"]["sets"][k]) * 16 for f in fights) for k in range(3)} if fights else {}
    career = _career(scenes, fights, index_of) if fights else None
    if career:                          # (a new career on the title: the pass key there can set another)
        scenes[0]["_rec_reset"] = True
        if (scenes[0]["menu"] or {}).get("pass_key"):
            scenes[0]["menu"]["pass_key"]["_nes"] = True
        keyed = [sc for sc in scenes if sc.get("cut_key")]     # the training runs' pass keys: circuit by circuit
        for n, sc in enumerate(keyed[:3]):
            sc["cut_key"]["circuit"] = n
    pw_starts = [255] * 6               # where a pass key starts (PwContinue): the World title bout, the World
    if career:                          # circuit, the Major (by circuit), Tyson, the ending
        ttl = [f for f in fights if career[f][0] & 1]
        chal_of = {f: next((j for j, sc in enumerate(scenes) if sc.get("press") and not sc.get("fight")
                            and index_of.get(sc["press"]["target"]) == f and j != career[f][1]), 255) for f in fights}
        last_win = index_of[scenes[fights[-1]]["fight"]["win"]]
        if len(ttl) == 3:
            aw_first = next((f for f in fights if (scenes[f]["fight"].get("another_world") or {}).get("first")), None)
            pw_starts = [chal_of[fights[fights.index(ttl[0]) + 1]], chal_of[fights[fights.index(ttl[1]) + 1]],
                         chal_of[ttl[2]], chal_of[fights[-1]], index_of.get(scenes[last_win]["press"]["target"], 255),
                         chal_of[aw_first] if aw_first is not None else 255]
    for f in career or ():              # (a loss's screen, a win's, go where FtCareerResult says)
        for key in ("lose", "win", "win_tko"):
            if scenes[f]["fight"].get(key) is not None:
                scenes[index_of[scenes[f]["fight"][key]]]["_rec_next"] = True
    fight_table = "\n".join(_fight_entry(f, scenes[f], index_of, "" if k == 0 else f"_F{k}", _all_pics(project),
                                         (career or {}).get(f)) for k, f in enumerate(fights))
    fight_table += ("\nPwStarts::                  ; a pass key's starts: Major, World, the World title bout, Tyson, the"
                    "\n    db " + ", ".join(map(str, pw_starts)) + "      ; ending, Another World ($FF: none)")
    scene_code = []
    in_bank = {i: [] for i in range(len(scenes))}   # a banked game: a press-start screen's code and patches go in
    for i, s in enumerate(scenes):                  # its own data bank, mapped while it runs (ROM0 stays free)
        if s["menu"]:
            scene_code.append(_menu_code(i, s, bool(fade), bool(fights)))
        elif s.get("cutscene"):
            (in_bank[i] if banked else scene_code).append(_cut_code(i, s, index_of))
        elif s["press"]:
            (in_bank[i] if banked else scene_code).append(_press_code(i, s, index_of, corner=any(
                f.get("fight") and f["fight"]["corner"] is not None and index_of[f["fight"]["corner"]] == i for f in scenes)))
        elif s["options"]:
            scene_code.append(_options_code(i, s, index_of, opt_index))
        elif s.get("pass_key"):
            scene_code.append(_pass_code(i, s, index_of))
        elif s.get("puzzle"):
            scene_code.append(_puzzle_asm(i, s, index_of, opt_rows))
        elif s.get("fight"):
            k = fights.index(i)
            scene_code.append(_fight_asm(i, s, index_of, project, banked, suffix="" if k == 0 else f"_F{k}",
                                         shared=k == 0, pads=fight_pads, table=fight_table))
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
{"DEF FT_LOAD_ON EQU 1           ; fights load with the display on, on Color (VWait)" + nl if fight_on else ""}{"DEF FT_ALL_PICS EQU 1          ; every fight's rival in pictures, Color's and the original's: no pose sets" + nl if fights and all(scenes[i].get("fight_pics") and scenes[i].get("fight_pics_dmg") for i in fights) else ""}{"DEF FT_NES_SOUND EQU 1         ; the fight's NES sound engine plays the game's sounds" + nl if nes_sound_any else ""}; joypad bits in hPad / hPadNew (d-pad in the high nibble)
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
wLoadSrc: dw                ; (a map copied in pieces: where it's got to)

SECTION "Code: Start", ROM0
Start:
    ; The boot ROM leaves A = $11 on Game Boy Color hardware, and interrupts disabled (they stay that way).
    cp $11
    ld a, 0
    jr nz, .notCGB
    inc a
.notCGB:
    ldh [hIsCGB], a
{"    xor a                   ; (not loading with the display on: HRAM is random at power-on)" + nl + "    ldh [hLoadOn], a" + nl if load_on else ""}    ld sp, wStackTop
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
{"    ldh a, [hFtActive]      ; a fight: interrupts on, each clears its own flag (clearing them here could drop" + nl + "    and a                   ; a mid-frame split just raised, leaving its scroll on to the bottom)" + nl + "    jr nz, .sleep" + nl if fights else ""}    xor a
    ldh [rIF], a
{".sleep:" + nl if fights else ""}    halt                    ; sleep until VBlank
    nop                     ; HALT may run the next byte twice if VBlank arrives just before it
{"    ldh a, [rLY]            ; a fight's mid-frame scroll interrupt also wakes HALT: sleep on until VBlank" + nl + "    cp 144" + nl + "    jr c, MainLoop" + nl if fights else ""}{"    cp 147                  ; a frame that ran long: its VBlank work waits for the next VBlank's start (a lag frame," + nl + "    jr c, .onTime           ; never half of it done as the screen draws)" + nl + ".late:" + nl + "    ldh a, [rLY]" + nl + "    cp 144" + nl + "    jr nc, .late" + nl + "    jr MainLoop" + nl + ".onTime:" + nl if fights else ""}{nl.join(vblank_work)}
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
{REPEAT_CODE if repeat else ""}{(CARD_HOLD_CHECK if cards else "") + SLIDE_STEP_CODE if slides else ""}    call hUpdateJump
{"    ldh a, [hCutOn]         ; (a cutscene runs the sound itself, before its mid-frame scroll splits)" + nl + "    and a" + nl + "    jp nz, MainLoop" + nl if cutscenes else ""}    call SfxUpdate
{"    ldh a, [hFtActive]      ; a fight on the original: the CPU's free till VBlank, his coming picture's tiles in it" + nl + "    and a" + nl + "    call nz, FtDmgStream" + nl if nes_any else ""}    jp MainLoop

SECTION "Code: Scenes", ROM0
; Load scene A with the screen off. Tiles, map and palette map go by DMA on Game Boy Color.
LoadScene:
    ldh [hScene], a
{"    xor a                   ; (a cutscene's VBlank work done)" + nl + "    ldh [hCutOn], a" + nl + "    ldh [rSCX], a" + nl if cutscenes else ""}{"    xor a                   ; (not loading with the display on, unless a plain screen turns it so)" + nl + "    ldh [hLoadOn], a" + nl if load_on else ""}{"    ldh a, [hFtActive]      ; leaving a fight: its scroll split ends now (it held through the fade)" + nl + "    and a" + nl + "    call nz, FtStop" + nl if fights else ""}    ldh a, [rLCDC]
    add a                   ; screen already off (at boot)? bit 7 -> carry
    jr nc, .screenOff
{SCREEN_ON_CHECK.replace('{fight_check}', SCREEN_ON_FIGHT if fight_on else '') if load_on else ""}.waitVBlank:
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
{"    xor a                   ; not sliding unless this scene starts one" + nl + "    ldh [hScrollY], a" + nl if slides else ""}{"    xor a                   ; (no gloves till its menu puts them up)" + nl + "    ldh [hGloveY], a" + nl if gloves else ""}{"    ld [wCardOn], a         ; (nor a round card up)" + nl if cards else ""}{_bank_switch() if banked else ""}    call JumpHL
{nl.join(finish)}
{"    call VWait              ; (palettes: written in VBlank when the screen stayed on)" + nl if load_on else ""}    call UploadPalettes
{"    ldh a, [hScrollY]" + nl + "    ldh [rSCY], a" + nl if slides else ""}    ld a, LCDC_ON
    ldh [rLCDC], a
{SCREEN_ON_END if load_on else ""}    ret

JumpHL:
    jp hl

SceneLoads:
    dw {", ".join(f"Scene{i}Load" for i in range(len(scenes)))}
{"SceneBanks:" + nl + "    db " + ", ".join(f"BANK(Scene{i}Tiles)" for i in range(len(scenes))) if banked else ""}
{("SceneScreenOn:              ; 1: loads with the display on" + (" (2: on Color)" if fight_on else "") + nl + "    db " + ", ".join("1" if i in screen_on else "2" if i in fight_on else "0" for i in range(len(scenes))) + nl + VWAIT_CODE) if load_on else ""}

{nl.join(_scene_load(i, s, cursor_on, opt_index, markers) for i, s in enumerate(scenes) if not (banked and not s.get("fight")))}{nl + nl + (SLIDE_FILL_ON if load_on else SLIDE_FILL).rstrip() if slides else ""}

; Copy C tiles (1-128) from HL to DE.
CopyTiles:
{COPY_TILES_CHUNKS if load_on else ""}CopyTilesNow:
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
{"    call VWait" + nl if load_on else ""}    ldh a, [hIsCGB]
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
{COPY_MAP_CHUNKS if load_on else ""}    ld [wSavedSP], sp
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
{"    ld a, BANK(FadeColor)   ; (their own bank: the bank that was mapped (hBank) back after)" + nl + "    ld [$2100], a" + nl + "    call .upload" + nl + "    ldh a, [hBank]" + nl + "    ld [$2100], a" + nl + "    ret" + nl + ".upload:" + nl if banked else ""}{'    xor a' + nl + '    ldh [hPalDirty], a' + nl + '    ldh a, [hFadeStep]' if fade else '    xor a'}
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

{'SECTION "Data: Palettes", ROMX' + nl if banked else ""}ScenePalettes:
    dw {", ".join(f"Scene{i}Palettes" for i in range(len(scenes)))}
PalCopy8:                   ; a palette's 8 bytes from HL to the port C names (BCPD or OCPD)
    REPT 8
        ld a, [hl+]
        ldh [c], a
    ENDR
    ret

{nl.join(_scene_palettes(i, s, project, cursor_on) for i, s in enumerate(scenes))}

{'' if banked else 'SECTION "Data: Palettes", ROM0'}
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
            if s["menu"].get("pass_key"):
                patch_data.append(_pk_data(i, s["menu"]["pass_key"]))
        elif s["options"]:
            for r_i, r in enumerate(s["options"]["rows"]):
                cells = len(s["option_strips"][r_i][0])
                patch_code.append(_patch_routine(f"Scene{i}Row{r_i}Patch", [(r["valueY"] * 32 + r["valueX"], cells)],
                                                 f'option "{r["label"]}"'))
            patch_data.append(_options_data(i, s))
        elif s.get("cutscene"):
            (in_bank[i] if banked else patch_data).append(_cut_data(i, s))
        elif s["press"]:
            code = _press_patches(i, s)
            if code:
                (in_bank[i] if banked else patch_code).append(code)
            data = _press_data(i, s)
            if data:
                (in_bank[i] if banked else patch_data).append(data)
    if any((sc["menu"] or {}).get("pass_key") for sc in scenes) or cutscenes or typed_scenes:
        out.append(PK_CODE)             # (its list patch, for the others too)
    if cutscenes:
        out.append(CUT_CODE.replace("{MAX}", str(max(len(fr) for i in cutscenes for fr in _cut_oam(scenes[i])))))
    if typed_scenes:
        out.append(TYPE_CODE)
    if cards:
        out.append(CARD_CODE)
    if gloves:
        g, gi = gloves
        rows = []
        for k, (side, r, c) in enumerate((side, r, c) for side in (0, 1) for r in (0, 1) for c in range(3)):
            slot = 0 if k == 0 else 28 + k                 # OAM 0 (the plain cursor's) and 29-39 (past the confirm's)
            x = (g["left"] if side == 0 else g["right"]) + 8 * c + 8
            tile = 64 + r * 3 + (c if side == 0 else 2 - c)
            rows.append(f"    db {slot * 4}, {r * 8}, {x}, {tile}, ${GLOVE_PAL | (0x20 if side else 0):02X}")
        out.append(f"""SECTION "Menu gloves", ROM0
; (VBlank) Punch-Out!!'s gloves either side of the chosen item: 12 sprites from hGloveY, or (once) them away.
GloveOam:
    ldh a, [hGloveY]
    and a
    jr nz, .draw
    ldh a, [hGloveOn]
    and a
    ret z
    xor a
    ldh [hGloveOn], a
    ld hl, $FE00 + 29 * 4
    ld b, 11
.hide:
    ld [hl+], a
    inc l
    inc l
    inc l
    dec b
    jr nz, .hide
    ld [OAM_CURSOR + 2], a  ; (the plain cursor's tile and palette back)
    ld a, {project['cursor']['palette']}
    ld [OAM_CURSOR + 3], a
    ret
.draw:
    ld a, 1
    ldh [hGloveOn], a
    ld hl, GloveSprites
    ld c, 12
.sprite:
    ld a, [hl+]
    ld e, a
    ld d, $FE
    ldh a, [hGloveY]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    dec c
    jr nz, .sprite
    ret
GloveSprites:               ; per sprite: its OAM entry, y under hGloveY, x, tile, attributes (the right glove mirrored)
""" + "\n".join(rows) + "\n")
    if any((sc["press"] or {}).get("auto") for sc in scenes):
        out.append('SECTION "Auto screen", WRAM0\nwAutoLeft: dw              ; frames till a screen goes on by itself\nwRingTick: db              ; frames till its effect again (0: done)\nwRingNext: db\n')
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
        out.append('SECTION "Code: OAM", ROM0\nResetOAM:                   ; screen off or VBlank: every sprite hidden\n'
                   + ("    call VWait\n" if load_on else "") + nl.join(reset) + "\n    ret\n")
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
    if confirms and fights:             # (its sprites built outside VBlank, then up by OAM DMA: too many to write in it)
        out.append("""SECTION "Code: Menu confirm build", ROM0
ConfirmBuild:               ; the step's sprites into wFtOAM (free outside a fight): shown or not, in front or behind
    ld hl, wFtOAM
    xor a
    ld b, 160
.clear:
    ld [hl+], a
    dec b
    jr nz, .clear
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
    ld de, wFtOAM + 8
.sprite:
    ld a, [hl+]
    and a
    ret z
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
""" + ("""    ld a, HIGH(wFtOAM)      ; its sprites, built (ConfirmBuild): all of OAM by DMA (the cursor's after this)
    call hOAMDMA
    jr .colors
""" if fights else "") + """    ld a, [wConfirmStep]
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
    kit_sfx = KIT_SFX if nes_sound else re.sub(r"IF DEF\(FT_NES_SOUND\)\n.*?ENDC\n", "", KIT_SFX, flags=re.S)
    if banked:                      # (a banked game: the effects' data in a bank of its own, mapped while they run)
        kit_sfx = re.sub(r"^PlaySfx:", "PlaySfxIn:", kit_sfx, flags=re.M)
        kit_sfx = re.sub(r"^SfxUpdate:", "SfxUpdateIn:", kit_sfx, flags=re.M)
        kit_sfx += "\n".join(f"""
{name}:                  ; ({name}In, the effects' bank mapped, then the one that was: hBank)
    push af
    ld a, BANK(SfxData)
    ld [$2100], a
    pop af
    call {name}In
    push af
    ldh a, [hBank]
    ld [$2100], a
    pop af
    ret""" for name in ("PlaySfx", "SfxUpdate")) + "\n"
    out.append(kit_sfx)
    out.append(f'SECTION "Data: Sound effects", {"ROMX" if banked else "ROM0"}\n{"SfxData:" + chr(10) if banked else ""}' + sfx_data + "\n")
    if nes_sound:                   # each effect's counterpart in the NES game (an SQ1 effect; 0: none)
        out.append("SfxNes:\n" + _db([NES_SFX.get(n, 0) for n in sfx.effects(project.get("sound", "arcade"), sfx_groups(scenes))]) + "\n")
    for i, s in enumerate(scenes):      # (a banked game: a scene's load in its own bank, but a fight's: it maps its own)
        if banked and not s.get("fight"):
            in_bank[i].insert(0, _scene_load_banked(i, s, cursor_on, opt_index, markers))
    out += [_scene_data(i, s, banked) + ("\n".join(in_bank[i]) + "\n" if in_bank[i] else "") for i, s in enumerate(scenes)]
    if banked:                      # every bank switch noted (hBank), for what maps a bank of its own and puts back
        hram.append("hBank: db               ; the ROM bank mapped")    # (UploadPalettes): all of them in ROM0
        out = [re.sub(r"^(\s*)ld \[\$2000\], a", r"\1ldh [hBank], a\n\1ld [$2000], a", o, flags=re.M) for o in out]
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
