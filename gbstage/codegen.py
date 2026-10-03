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
        if s.get("puzzle"):
            todo += [s["puzzle"]["win"], s["puzzle"]["lose"]]
    return sorted(seen)


def _db(values, per_line=16):
    return "\n".join("    db " + ", ".join(f"${v:02X}" for v in values[i:i + per_line])
                     for i in range(0, len(values), per_line))


def _rgb555(colors):
    return ", ".join(f"${r | g << 5 | b << 10:04X}" for r, g, b in colors)


def _pad_rows(values):
    """CW-wide rows -> 32-wide rows (the padding is off screen) so DMA can copy whole rows."""
    out = []
    for i in range(0, len(values), CW):
        out += list(values[i:i + CW]) + [0] * (32 - CW)
    return out


def _runs(indexes):
    """[0, 1, 3] -> [(0, 2), (3, 1)]: (first, count) runs of consecutive numbers."""
    runs = []
    for i in indexes:
        if runs and runs[-1][0] + runs[-1][1] == i:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((i, 1))
    return runs


def _upload_runs(indexes, spec, data_reg, at_label=None):
    """Code uploading the given palette indexes through BCPS/BCPD or OCPS/OCPD, 16 cycles per byte.

    HL walks a table holding every palette in order; runs of consecutive palettes share one index
    write and one loop, and palettes the scene doesn't use are skipped."""
    lines, pos = [f"    ld c, LOW({data_reg})"], 0
    if at_label:
        lines.insert(0, f"    ld hl, {at_label}")
    for first, count in _runs(indexes):
        skip = (first - pos) * 8
        if skip:
            lines += [f"    ld de, {skip}", "    add hl, de"]
        lines += [f"    ld a, $80 | {first * 8}", f"    ldh [{spec}], a"]
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


def _scene_data(i, s):
    tile_bytes = [b for t in s["tiles"] for b in encode_tile(t)]
    return f"""SECTION "Data: Scene {i} tiles", ROM0, ALIGN[4]   ; DMA needs 16-byte alignment
Scene{i}Tiles:              ; "{s['name']}": {len(s['tiles'])} unique tiles
{_db(tile_bytes)}

SECTION "Data: Scene {i} maps", ROM0, ALIGN[4]    ; rows padded to 32 tiles so DMA can copy them whole
Scene{i}Map:
{_db(_pad_rows(s['cell_tiles']), 32)}
Scene{i}Attr:               ; palette number per tile (Game Boy Color only)
{_db(_pad_rows(s['cell_pal']), 32)}
"""


# ---- one still screen: straight-line code ------------------------------------

def _static_asm(project, s):
    n = len(s["tiles"])
    used = sorted(set(s["cell_pal"]))
    tiles_color = _gdma("Scene0Tiles", 0x9000, min(n, 128) * 16)
    tiles_cpu = ["    ld sp, Scene0Tiles", "    ld hl, $9000            ; tiles 0-127", f"    ld b, {min(n, 128)}",
                 ".tiles:", POP_TILES, "    dec b", "    jr nz, .tiles"]
    if n > 128:
        tiles_color += "\n" + _gdma("Scene0Tiles + 128 * 16", 0x8800, (n - 128) * 16)
        tiles_cpu += ["    ld hl, $8800            ; tiles 128-255 (SP has moved on to them)", f"    ld b, {n - 128}",
                      ".tilesHigh:", POP_TILES, "    dec b", "    jr nz, .tilesHigh"]
    palettes = "\n".join(_upload_runs(used, "rBCPS", "rBCPD", at_label="BgPalettes"))
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

def _scene_load(i, s, sprites, opt_index=None, markers=False):
    n = len(s["tiles"])
    lines = [f"Scene{i}Load:", f"    ld hl, Scene{i}Tiles", "    ld de, $9000            ; tiles 0-127",
             f"    ld c, {min(n, 128)}", "    call CopyTiles"]
    if n > 128:
        lines += [f"    ld hl, Scene{i}Tiles + 128 * 16", "    ld de, $8800            ; tiles 128-255",
                  f"    ld c, {n - 128}", "    call CopyTiles"]
    lines += [f"    ld hl, Scene{i}Map", "    call CopyMap", f"    ld hl, Scene{i}Attr", "    call CopyAttr"]
    if s.get("puzzle"):
        lines.append("    call PuzzleLoad")
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
    lines += _upload_runs(sorted(set(s["cell_pal"])), "rBCPS", "rBCPD")
    if sprites and (s["menu"] or s["options"]):
        pal = project["cursor"]["palette"]
        skip = (len(project["palettes"]) - (max(s["cell_pal"]) + 1) + pal) * 8
        if skip:
            lines += [f"    ld de, {skip}", "    add hl, de"]
        lines += [f"    ld a, $80 | {pal * 8}", "    ldh [rOCPS], a", "    ld c, LOW(rOCPD)",
                  "    REPT 8", "        ld a, [hl+]", "        ldh [c], a", "    ENDR"]
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


def _press_code(i, s, index_of):
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
    return f"""Scene{i}Update:              ; press-start screen: wait for Start or A
    ldh a, [hPadNew]
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


def _menu_code(i, s):
    m = s["menu"]
    n = len(m["items"])
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
    return f"""Scene{i}Update:              ; menu: up/down to move, A or Start to choose
    ldh a, [hPadRepeat]
    and a
    jr z, .cursor           ; nothing pressed: just animate
    ld b, a
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
    ld a, {m['blinks'] * 2 + 1}
    ldh [hCounter], a
    ld a, 1
    ldh [hTimer], a
    SET_UPDATE Scene{i}Blink
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
"""


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
    scenes = [project["scenes"][i] for i in keep]
    menus = any(s["menu"] for s in scenes)
    presses = any(s["press"] for s in scenes)
    options = any(s["options"] for s in scenes)
    markers = any(r.get("slider") for s in scenes if s["options"] for r in s["options"]["rows"])
    puzzles = [i for i, sc in enumerate(scenes) if sc.get("puzzle")]
    if len(puzzles) > 1:
        raise ProjectError(["A project can have one puzzle grid scene for now."])
    repeat = menus or options or bool(puzzles)
    opt_index, opt_rows = {}, []
    for i, sc in enumerate(scenes):
        for r_i, r in enumerate((sc["options"] or {}).get("rows", [])):
            opt_index[(i, r_i)] = len(opt_rows)
            opt_rows.append(r)
    names = [r["symbol"] for r in opt_rows]
    if len(set(names)) != len(names):
        dup = sorted({n for n in names if names.count(n) > 1})
        raise ProjectError([f"Two options screens use the same option name ({', '.join(dup)}); rename one."])
    patches = options or menus or any(s["press"] and (s["press"]["area"] or (s["press"]["prompt"] and s["press"]["prompt"]["blink"]))
                           for s in scenes)
    prompt_blink = any(s["press"] and s["press"]["prompt"] and s["press"]["prompt"]["blink"] for s in scenes)
    interactive = menus or presses or options or bool(puzzles) or any(s["back"] is not None for s in scenes)
    if len(scenes) == 1 and not interactive:
        return _static_asm(project, scenes[0])

    sprites = (menus or options) and project["cursor"] is not None
    fade = project["transition"]
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
    if sprites:
        hram += ["hCursorY: db", "hCursorX: db"]
    hram.append("hVarsEnd:")

    vblank_work = []
    if sprites:
        vblank_work.append("""    ldh a, [hCursorY]       ; a few sprites: write them straight to OAM (cheaper than DMA)
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""")
    if markers:
        vblank_work.append("""    ldh a, [hMarkerY]
    ld [OAM_CURSOR + 4], a
    ldh a, [hMarkerX]
    ld [OAM_CURSOR + 5], a""")
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
        boot.append(f"""    ld hl, $FE00            ; clear OAM (it's random at power-on); A = 0
    ld b, 160
.clearOAM:
    ld [hl+], a
    dec b
    jr nz, .clearOAM
    ld a, {project['cursor']['palette']}
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
    if sprites:
        finish.append("""    ldh a, [hCursorY]       ; OAM is writable while the screen is off
    ld [OAM_CURSOR], a
    ldh a, [hCursorX]
    ld [OAM_CURSOR + 1], a""")

    updates = [f"Scene{i}Update" if s["menu"] or s["press"] or s["options"] or s.get("puzzle") or s["back"] is not None else "NoUpdate"
               for i, s in enumerate(scenes)]
    scene_code = []
    for i, s in enumerate(scenes):
        if s["menu"]:
            scene_code.append(_menu_code(i, s))
        elif s["press"]:
            scene_code.append(_press_code(i, s, index_of))
        elif s["options"]:
            scene_code.append(_options_code(i, s, index_of, opt_index))
        elif s.get("puzzle"):
            scene_code.append(_puzzle_asm(i, s, index_of, opt_rows))
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

    sfx_defs, sfx_data = sfx.asm_data()
    option_defs = "\n".join([f"DEF OPTION_COUNT EQU {len(opt_rows)}"] + [f"DEF {r['symbol']} EQU {k}   ; {r['label']}" for k, r in enumerate(opt_rows)]) if options else ""
    out = [f"""; Generated by gbstage from "{project['name']}". Changes here are overwritten on the next build.

{HW_DEFS}
DEF MAP_W EQU {CW}
DEF MAP_H EQU {CH}
DEF FADE_STEPS EQU {steps}
DEF FADE_FRAMES EQU {fade['frames'] if fade else 1}
DEF BLINK_FRAMES EQU {BLINK_FRAMES}
DEF LCDC_ON EQU %{lcdc:08b}

; joypad bits in hPad / hPadNew (d-pad in the high nibble)
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

SECTION "Header", ROM0[$100]
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
{nl.join(vblank_work)}
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
{REPEAT_CODE if repeat else ""}    call hUpdateJump
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
    ldh a, [hScene]
    add a
    add LOW(SceneLoads)
    ld l, a
    adc HIGH(SceneLoads)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    call JumpHL
{nl.join(finish)}
    call UploadPalettes
    ld a, LCDC_ON
    ldh [rLCDC], a
    ret

JumpHL:
    jp hl

SceneLoads:
    dw {", ".join(f"Scene{i}Load" for i in range(len(scenes)))}

{nl.join(_scene_load(i, s, sprites, opt_index, markers) for i, s in enumerate(scenes))}

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
{'    ldh [rOBP0], a' + nl if sprites else ''}    ret

ScenePalettes:
    dw {", ".join(f"Scene{i}Palettes" for i in range(len(scenes)))}

{nl.join(_scene_palettes(i, s, project, sprites) for i, s in enumerate(scenes))}

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
    if options:
        out.append(f"""SECTION "Options", WRAM0
wOptions: ds OPTION_COUNT   ; current value of each option (0 = first choice / minimum)

SECTION "Data: Option defaults", ROM0
OptionDefaults:
    db {", ".join(str(r["default"]) for r in opt_rows)}
""")
    out.append(KIT_SFX)
    out.append('SECTION "Data: Sound effects", ROM0\n' + sfx_data + "\n")
    out += [_scene_data(i, s) for i, s in enumerate(scenes)]
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
