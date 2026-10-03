"""Project files: validation, upgrading old versions, and turning scenes into tiles.

Format version 2:
  palettes:   {"bg": [...], "obj": [...]}     4 colors each, channels 0-31; obj slot 0 is transparent
  cursor:     {"palette": n, "pixels": "64 slots"}            8x8 menu cursor sprite (optional)
  scenes:     [{"name", "background": {...}, "menu": {...} or null, "pressStart": {...} or null,
                "pressed": "pixels of the flash area's pressed frame" or null, "back": scene index or null}]
  start:      index of the first scene
  transition: {"color": "white" | "black", "frames": frames per fade step}   (optional)

A menu draws its labels with the built-in font in one palette slot of whatever palette each tile
already uses, so text can never break the one-palette-per-tile rule.
"""

import re
from pathlib import Path

W, H, CELL = 160, 144, 8
CW, CH = W // CELL, H // CELL
MAX_BG_PALETTES = 8
MAX_OBJ_PALETTES = 8
MAX_TILES = 256
MAX_MENU_ITEMS = 6
MAX_FLASH_TILES = 80          # the flash area must flip within one VBlank
MAX_OPTION_ROWS = 6
FADE_STEPS = 4
FORMAT_VERSION = 2

FONT_FILE = Path(__file__).with_name("font.txt")


class ProjectError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def load_font():
    """{char: 8x8 list of 0/1}, glyphs placed one column in from the left."""
    font, char, rows = {}, None, []
    for line in FONT_FILE.read_text().splitlines():
        if line.startswith("# ") or not line.strip():
            continue
        if line.startswith("= "):
            if char is not None:
                font[char] = rows
            char, rows = line[2], []
        else:
            rows.append(line)
    font[char] = rows
    for ch, art in font.items():
        if len(art) != 7 or any(len(row) != 5 or set(row) - {"#", "."} for row in art):
            raise ValueError(f"font.txt: glyph {ch!r} must be 7 rows of 5 '#'/'.' characters")
    glyphs = {" ": [[0] * 8 for _ in range(8)]}
    for ch, art in font.items():
        g = [[0] * 8 for _ in range(8)]
        for y, row in enumerate(art):
            for x, c in enumerate(row):
                g[y][x + 1] = 1 if c == "#" else 0
        glyphs[ch] = g
    return glyphs


FONT = load_font()


def _colors_ok(colors):
    return (isinstance(colors, list) and len(colors) == 4 and all(
        isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 31 for v in c) for c in colors))


def _background(bg, n_palettes, where, errors):
    pixels, cell_pal = (bg or {}).get("pixels"), (bg or {}).get("cellPalettes")
    if (bg or {}).get("width") != CW or (bg or {}).get("height") != CH:
        errors.append(f"{where}: background must be {CW}x{CH} tiles.")
    if not isinstance(pixels, str) or len(pixels) != W * H or not re.fullmatch(r"[0-3]*", pixels):
        errors.append(f"{where}: background pixel data is damaged.")
        return None, None
    if (not isinstance(cell_pal, list) or len(cell_pal) != CW * CH
            or not all(isinstance(v, int) and 0 <= v < max(1, n_palettes) for v in cell_pal)):
        errors.append(f"{where}: tile palettes are damaged or point at a palette that doesn't exist.")
        return None, None
    return [ord(c) - 48 for c in pixels], list(cell_pal)


def upgrade(data):
    """Bring an older project file up to the current format."""
    if data.get("version", 0) == 1:
        data = dict(data, version=2,
                    palettes={"bg": data.get("palettes", {}).get("bg"), "obj": []},
                    scenes=[{"name": "Main", "background": data.get("background"), "menu": None, "back": None}],
                    start=0, cursor=None, transition=None)
        data.pop("background", None)
    return data


def validate(data):
    """Check a project against the hardware rules. Returns a normalized project or raises ProjectError."""
    if not isinstance(data, dict) or data.get("format") != "gbstage":
        raise ProjectError(["Not a gbstage project."])
    if data.get("version", 0) > FORMAT_VERSION:
        raise ProjectError([f"Project was made by a newer gbstage (format {data['version']})."])
    data = upgrade(data)
    errors = []

    pals = data.get("palettes") or {}
    bg, obj = pals.get("bg") or [], pals.get("obj") or []
    if not 1 <= len(bg) <= MAX_BG_PALETTES:
        errors.append(f"Use between 1 and {MAX_BG_PALETTES} background palettes (found {len(bg)}).")
    if len(obj) > MAX_OBJ_PALETTES:
        errors.append(f"Use at most {MAX_OBJ_PALETTES} sprite palettes (found {len(obj)}).")
    for kind, group in (("Palette", bg), ("Sprite palette", obj)):
        for n, p in enumerate(group):
            if not isinstance(p, dict) or not _colors_ok(p.get("colors")):
                errors.append(f"{kind} {n + 1} needs exactly 4 colors with channels 0-31.")

    scenes_in = data.get("scenes") or []
    if not 1 <= len(scenes_in) <= 32:
        errors.append("A project needs between 1 and 32 scenes.")
    scene_count = len(scenes_in)
    scenes = []
    for i, s in enumerate(scenes_in):
        name = str((s or {}).get("name") or f"Scene {i + 1}")
        where = f'Scene "{name}"'
        pixels, cell_pal = _background((s or {}).get("background"), len(bg), where, errors)
        menu = _menu((s or {}).get("menu"), where, i, scene_count, errors)
        press = _press_start((s or {}).get("pressStart"), (s or {}).get("pressed"), where, i, scene_count, errors)
        options = _options((s or {}).get("options"), where, i, scene_count, errors)
        puzzle = _puzzle((s or {}).get("puzzle"), where, i, scene_count, len(bg), cell_pal, errors)
        if sum(bool(x) for x in (menu, press, options, puzzle)) > 1:
            errors.append(f"{where}: a scene can be a menu, a press-start screen, an options screen or a puzzle grid, only one.")
            press = options = puzzle = None
        back = (s or {}).get("back")
        if back is not None and not (isinstance(back, int) and 0 <= back < scene_count and back != i):
            errors.append(f"{where}: the B button goes to a scene that doesn't exist.")
            back = None
        if puzzle and back is not None:
            errors.append(f"{where}: B rotates the capsule on a puzzle grid, so it can't also go back.")
        scenes.append({"name": name, "pixels": pixels, "cell_pal": cell_pal, "menu": menu, "press": press,
                       "options": options, "puzzle": puzzle, "back": back})

    start = data.get("start", 0)
    if not (isinstance(start, int) and 0 <= start < max(1, scene_count)):
        errors.append("The start scene doesn't exist.")

    cursor = data.get("cursor")
    if cursor is not None:
        px = cursor.get("pixels") if isinstance(cursor, dict) else None
        if not isinstance(px, str) or len(px) != 64 or not re.fullmatch(r"[0-3]*", px):
            errors.append("The cursor sprite's pixel data is damaged.")
        elif not (isinstance(cursor.get("palette"), int) and 0 <= cursor["palette"] < len(obj)):
            errors.append("The cursor uses a sprite palette that doesn't exist.")
        else:
            cursor = {"palette": cursor["palette"], "pixels": [ord(c) - 48 for c in px]}
    uses_menus = any(s["menu"] or s["options"] for s in scenes)
    if uses_menus and cursor is None and not errors:
        errors.append("Menus and options screens need a cursor sprite.")

    transition = data.get("transition")
    if transition is not None:
        if (not isinstance(transition, dict) or transition.get("color") not in ("white", "black")
                or not (isinstance(transition.get("frames"), int) and 1 <= transition["frames"] <= 30)):
            errors.append("Transitions need a color (white or black) and 1-30 frames per fade step.")
    elif uses_menus or any(s["back"] is not None or s["press"] for s in scenes):
        transition = {"color": "white", "frames": 3}

    option_rows = {r["symbol"]: r for sc in scenes if sc["options"] for r in sc["options"]["rows"]}
    for sc in scenes:
        pz = sc["puzzle"]
        if not pz:
            continue
        for key in ("speed_option", "level_option"):
            name = pz[key]
            if name and name not in option_rows:
                errors.append(f'Scene "{sc["name"]}": the puzzle reads {name}, but no options screen has that option.')
        if pz["level_option"] in option_rows and option_rows[pz["level_option"]]["kind"] != "number":
            errors.append(f'Scene "{sc["name"]}": the level comes from {pz["level_option"]}, which must be a number option.')

    if errors:
        raise ProjectError(errors)

    project = {
        "name": str(data.get("name") or "Untitled"),
        "palettes": [p["colors"] for p in bg],
        "palette_names": [str(p.get("name") or f"Palette {i + 1}") for i, p in enumerate(bg)],
        "obj_palettes": [p["colors"] for p in obj],
        "obj_palette_names": [str(p.get("name") or f"Sprite palette {i + 1}") for i, p in enumerate(obj)],
        "cursor": cursor if uses_menus else None,
        "scenes": scenes,
        "start": start,
        "transition": transition,
    }
    for s in project["scenes"]:
        compose(s)
        if len(s["tiles"]) > MAX_TILES:
            raise ProjectError([f'Scene "{s["name"]}" uses {len(s["tiles"])} different 8x8 tiles; the limit is '
                                f"{MAX_TILES}. Reuse repeated patterns to bring it down."])
    return project


def _menu(menu, where, index, scene_count, errors):
    if menu is None:
        return None
    if not isinstance(menu, dict):
        errors.append(f"{where}: the menu is damaged.")
        return None
    x, y, spacing, slot = menu.get("x"), menu.get("y"), menu.get("spacing"), menu.get("textSlot")
    items = menu.get("items") or []
    ok = True
    if not (isinstance(x, int) and 2 <= x < CW):
        errors.append(f"{where}: menu column must be 2-{CW - 1} (the cursor needs room on the left)."); ok = False
    if not (isinstance(spacing, int) and 1 <= spacing <= 4):
        errors.append(f"{where}: menu spacing must be 1-4 rows."); ok = False
    if not (isinstance(slot, int) and 0 <= slot <= 3):
        errors.append(f"{where}: menu text slot must be 1-4."); ok = False
    if not 1 <= len(items) <= MAX_MENU_ITEMS:
        errors.append(f"{where}: a menu needs 1-{MAX_MENU_ITEMS} items."); ok = False
    if not (isinstance(y, int) and 0 <= y and ok and y + (len(items) - 1) * spacing < CH):
        if ok:
            errors.append(f"{where}: the menu runs off the bottom of the screen.")
        ok = False
    out = []
    for n, item in enumerate(items):
        label = str((item or {}).get("label") or "").upper()
        target = (item or {}).get("target")
        if not label or (ok and x + len(label) > CW):
            errors.append(f"{where}: menu item {n + 1} needs a label that fits on screen ({CW - (x or 0)} characters)."); ok = False
        bad = sorted({c for c in label if c not in FONT})
        if bad:
            errors.append(f"{where}: menu item {n + 1} uses characters the font doesn't have: {' '.join(bad)}"); ok = False
        if not (isinstance(target, int) and 0 <= target < scene_count and target != index):
            errors.append(f"{where}: menu item {n + 1} goes to a scene that doesn't exist."); ok = False
        out.append({"label": label, "target": target})
    if not ok:
        return None
    blinks = menu.get("blinks", 3)
    return {"x": x, "y": y, "spacing": spacing, "text_slot": slot, "items": out,
            "cursor_bob": menu.get("cursorAnimation", "bob") == "bob",
            "blinks": blinks if isinstance(blinks, int) and 0 <= blinks <= 8 else 3}


def _press_start(press, pressed, where, index, scene_count, errors):
    if press is None:
        return None
    if not isinstance(press, dict):
        errors.append(f"{where}: the press-start settings are damaged.")
        return None
    ok = True
    target = press.get("target")
    if not (isinstance(target, int) and 0 <= target < scene_count and target != index):
        errors.append(f"{where}: Start goes to a scene that doesn't exist."); ok = False
    flashes = press.get("flashes", 3)
    if not (isinstance(flashes, int) and 1 <= flashes <= 8):
        errors.append(f"{where}: flashes must be 1-8."); ok = False
    area = press.get("area")
    if area is not None:
        x, y, w, h = (area.get(k) for k in ("x", "y", "w", "h")) if isinstance(area, dict) else (None,) * 4
        if not all(isinstance(v, int) for v in (x, y, w, h)) or not (0 <= x and 0 <= y and w >= 1 and h >= 1
                                                                    and x + w <= CW and y + h <= CH):
            errors.append(f"{where}: the flash area is off screen."); ok = False
        elif w * h > MAX_FLASH_TILES:
            errors.append(f"{where}: the flash area is {w * h} tiles; at most {MAX_FLASH_TILES} can change in one frame."); ok = False
        if not isinstance(pressed, str) or len(pressed) != W * H or not re.fullmatch(r"[0-3]*", pressed):
            errors.append(f"{where}: the pressed frame is damaged."); ok = False
    prompt = press.get("prompt")
    if prompt is not None:
        label = str(prompt.get("label") or "").upper() if isinstance(prompt, dict) else ""
        px, py, slot = (prompt.get(k) for k in ("x", "y", "textSlot")) if isinstance(prompt, dict) else (None,) * 3
        bad = sorted({c for c in label if c not in FONT})
        if not label or bad:
            errors.append(f"{where}: the prompt needs a label using the font's characters."); ok = False
        elif not (isinstance(px, int) and isinstance(py, int) and 0 <= px and px + len(label) <= CW and 0 <= py < CH):
            errors.append(f"{where}: the prompt runs off screen."); ok = False
        elif not (isinstance(slot, int) and 0 <= slot <= 3):
            errors.append(f"{where}: the prompt text slot must be 1-4."); ok = False
        elif area is not None and ok and (area["y"] <= py < area["y"] + area["h"]) and (
                px < area["x"] + area["w"] and area["x"] < px + len(label)):
            errors.append(f"{where}: the prompt and the flash area overlap; move one of them."); ok = False
        if ok:
            prompt = {"label": label, "x": px, "y": py, "text_slot": slot, "blink": bool(prompt.get("blink", True))}
    if not ok:
        return None
    return {"target": target, "flashes": flashes, "prompt": prompt,
            "area": dict(area) if area else None,
            "pressed": [ord(c) - 48 for c in pressed] if area else None}


def _puzzle(pz, where, index, scene_count, n_palettes, cell_pal, errors):
    from . import puzzle as kit
    if pz is None:
        return None
    if not isinstance(pz, dict):
        errors.append(f"{where}: the puzzle grid settings are damaged.")
        return None
    ok = True
    g = pz.get("grid") or {}
    gx, gy, gw, gh = (g.get(k) for k in ("x", "y", "w", "h"))
    if not all(isinstance(v, int) for v in (gx, gy, gw, gh)) or not (
            kit.MIN_W <= gw <= kit.MAX_W and kit.MIN_H <= gh <= kit.MAX_H and gx >= 0 and gy >= 0 and gx + gw <= CW and gy + gh <= CH):
        errors.append(f"{where}: the puzzle grid must be {kit.MIN_W}-{kit.MAX_W} wide and {kit.MIN_H}-{kit.MAX_H} tall, on screen.")
        return None
    pal = pz.get("palette")
    if not (isinstance(pal, int) and 0 <= pal < n_palettes):
        errors.append(f"{where}: the puzzle's piece palette doesn't exist."); return None
    grid_cells = {(gy + r) * CW + gx + c for r in range(gh) for c in range(gw)}
    taken = {c: "the grid" for c in grid_cells}

    def place(key, width, what):
        nonlocal ok
        spot = pz.get(key)
        if spot is None:
            return None
        if not (isinstance(spot, dict) and isinstance(spot.get("x"), int) and isinstance(spot.get("y"), int)
                and 0 <= spot["x"] and spot["x"] + width <= CW and 0 <= spot["y"] < CH):
            errors.append(f"{where}: the {what} is off screen."); ok = False
            return None
        cells = [spot["y"] * CW + spot["x"] + k for k in range(width)]
        clash = next((taken[c] for c in cells if c in taken), None)
        if clash:
            errors.append(f"{where}: the {what} overlaps {clash}."); ok = False
            return None
        for c in cells:
            taken[c] = f"the {what}"
        return {"x": spot["x"], "y": spot["y"], "cells": cells}

    nxt = place("next", 2, "next capsule")
    score = place("score", 6, "score")
    viruses = place("virusCount", 2, "virus count")
    level = place("level", 2, "level")
    if cell_pal is not None:
        wrong = [c for c in grid_cells | set(nxt["cells"] if nxt else []) if cell_pal[c] != pal]
        if wrong:
            errors.append(f"{where}: every grid and next-capsule tile must use the piece palette "
                          f"({len(wrong)} don't). The editor sets this when you place the grid."); ok = False
    for key in ("win", "lose"):
        t = pz.get(key)
        if not (isinstance(t, int) and 0 <= t < scene_count and t != index):
            errors.append(f"{where}: the {'win' if key == 'win' else 'game over'} scene doesn't exist."); ok = False
    slot = pz.get("textSlot", 3)
    if not (isinstance(slot, int) and 0 <= slot <= 3):
        errors.append(f"{where}: the puzzle text slot must be 1-4."); ok = False
    shapes = {}
    for name in kit.SHAPES:
        m = (pz.get("shapes") or {}).get(name, kit.DEFAULT_MASKS[name])
        if not (isinstance(m, str) and len(m) == 64 and set(m) <= {"0", "1"}):
            errors.append(f"{where}: the {name} shape is damaged."); ok = False
        shapes[name] = m
    if not ok:
        return None
    return {"grid": {"x": gx, "y": gy, "w": gw, "h": gh}, "palette": pal, "next": nxt, "score": score,
            "virus_count": viruses, "level": level, "text_slot": slot, "win": pz["win"], "lose": pz["lose"],
            "speed_option": pz.get("speedOption") or None, "level_option": pz.get("levelOption") or None,
            "shapes": shapes}


def option_symbol(label):
    """'VIRUS LEVEL' -> 'OPT_VIRUS_LEVEL': the constant gameplay code uses to read this option."""
    return "OPT_" + (re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_") or "VALUE")


def _options(opts, where, index, scene_count, errors):
    if opts is None:
        return None
    if not isinstance(opts, dict):
        errors.append(f"{where}: the options settings are damaged.")
        return None
    ok = True
    target = opts.get("target")
    if not (isinstance(target, int) and 0 <= target < scene_count and target != index):
        errors.append(f"{where}: Start goes to a scene that doesn't exist."); ok = False
    slot = opts.get("textSlot", 3)
    if not (isinstance(slot, int) and 0 <= slot <= 3):
        errors.append(f"{where}: the options text slot must be 1-4."); ok = False
    rows_in = opts.get("rows") or []
    if not 1 <= len(rows_in) <= MAX_OPTION_ROWS:
        errors.append(f"{where}: an options screen needs 1-{MAX_OPTION_ROWS} rows."); ok = False
    rows, used = [], {}
    for n, r in enumerate(rows_in if isinstance(rows_in, list) else []):
        r = r if isinstance(r, dict) else {}
        label = str(r.get("label") or "").upper()
        name = f'{where} option "{label or n + 1}"'
        kind = r.get("kind")
        ints = {k: r.get(k) for k in ("labelX", "labelY", "valueX", "valueY", "value")}
        if not label or any(c not in FONT for c in label):
            errors.append(f"{name}: the label needs the font's characters."); ok = False; continue
        if not all(isinstance(v, int) for v in ints.values()):
            errors.append(f"{name}: positions and value must be whole numbers."); ok = False; continue
        if not (0 <= ints["labelY"] < CH and 0 <= ints["valueY"] < CH and 2 <= ints["labelX"] and ints["labelX"] + len(label) <= CW):
            errors.append(f"{name}: the label is off screen (the cursor needs column 2 or more)."); ok = False; continue
        row = {"label": label, "symbol": option_symbol(label), "kind": kind, **{k: ints[k] for k in ("labelX", "labelY", "valueX", "valueY")}}
        if kind == "choice":
            choices = [str(c).upper() for c in (r.get("choices") or [])]
            if not 2 <= len(choices) <= 6 or any(not c or any(ch not in FONT for ch in c) for c in choices):
                errors.append(f"{name}: needs 2-6 choices using the font's characters."); ok = False; continue
            width = sum(len(c) for c in choices) + len(choices) - 1
            if ints["valueX"] < 0 or ints["valueX"] + width > CW:
                errors.append(f"{name}: the choices run off screen."); ok = False; continue
            if not 0 <= ints["value"] < len(choices):
                errors.append(f"{name}: the starting choice doesn't exist."); ok = False; continue
            row.update(choices=choices, count=len(choices), default=ints["value"])
        elif kind == "number":
            lo, hi, digits = r.get("min"), r.get("max"), r.get("digits", 2)
            if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= lo < hi <= 99 and digits in (1, 2) and hi < 10 ** digits):
                errors.append(f"{name}: numbers go from a minimum to a larger maximum, 0-99."); ok = False; continue
            if not (lo <= ints["value"] <= hi) or ints["valueX"] < 0 or ints["valueX"] + digits > CW:
                errors.append(f"{name}: the starting number or its position is out of range."); ok = False; continue
            row.update(min=lo, max=hi, digits=digits, count=hi - lo + 1, default=ints["value"] - lo)
            bar = r.get("slider")
            if bar is not None:
                if not (isinstance(bar, dict) and all(isinstance(bar.get(k), int) for k in ("x0", "x1", "y"))
                        and 0 <= bar["x0"] < bar["x1"] <= W - 8 and 0 <= bar["y"] <= H - 8):
                    errors.append(f"{name}: the slider is off screen."); ok = False; continue
                row["slider"] = dict(bar)
        else:
            errors.append(f"{name}: kind must be choice or number."); ok = False; continue
        if row["symbol"] in used:
            errors.append(f"{name}: two options have the same name."); ok = False; continue
        used[row["symbol"]] = True
        rows.append(row)
    taken = {}
    for r in rows:
        areas = ((f'"{r["label"]}"', [r["labelY"] * CW + r["labelX"] + k for k in range(len(r["label"]))]),
                 (f'the values of "{r["label"]}"', option_value_cells(r)))
        for what, cells in areas:
            clash = next((taken[c] for c in cells if c in taken), None)
            if clash:
                errors.append(f"{where}: {what} and {clash} overlap; move one of them."); ok = False
            for c in cells:
                taken[c] = what
    sliders = [r for r in rows if r.get("slider")]
    if len(sliders) > 1:
        errors.append(f"{where}: only one slider per options screen (it's a sprite)."); ok = False
    if not ok:
        return None
    return {"target": target, "text_slot": slot, "rows": rows}


def option_strings(row, value):
    """The text written in a row's value area for one value (choices are all shown; the chosen one
    is highlighted separately)."""
    if row["kind"] == "number":
        return [str(row["min"] + value).zfill(row["digits"])]
    return row["choices"]


def option_value_cells(row):
    """Cells of a row's value area, left to right."""
    width = sum(len(c) for c in row["choices"]) + len(row["choices"]) - 1 if row["kind"] == "choice" else row["digits"]
    return [row["valueY"] * CW + row["valueX"] + k for k in range(width)]


def draw_option_value(pixels, base, row, value, slot):
    """Draw a row's value area for one value into pixels (base: the background without text)."""
    cells = option_value_cells(row)
    for c in cells:
        x0, y0 = (c % CW) * CELL, (c // CW) * CELL
        for y in range(CELL):
            for x in range(CELL):
                pixels[(y0 + y) * W + x0 + x] = base[(y0 + y) * W + x0 + x]
    x = row["valueX"]
    if row["kind"] == "number":
        for px, py in text_ink(option_strings(row, value)[0], x, row["valueY"]):
            pixels[py * W + px] = slot
        return
    for k, choice in enumerate(row["choices"]):
        for px, py in text_ink(choice, x, row["valueY"]):
            pixels[py * W + px] = slot
        if k == value:          # the chosen one: inverted, like a lit button
            for cx in range(x, x + len(choice)):
                c = row["valueY"] * CW + cx
                x0, y0 = cx * CELL, row["valueY"] * CELL
                for yy in range(CELL):
                    for xx in range(CELL):
                        i = (y0 + yy) * W + x0 + xx
                        pixels[i] = 3 - pixels[i]
        x += len(choice) + 1


def text_ink(label, x, y):
    """Pixel positions covered by a label drawn with the built-in font at tile (x, y)."""
    ink = []
    for ci, ch in enumerate(label):
        g = FONT[ch]
        for gy in range(8):
            for gx in range(8):
                if g[gy][gx]:
                    ink.append(((x + ci) * 8 + gx, y * 8 + gy))
    return ink


def menu_text_pixels(menu):
    """Pixel positions covered by each menu label's glyph ink: list (per item) of (x, y) lists."""
    out = []
    for n, item in enumerate(menu["items"]):
        row = menu["y"] + n * menu["spacing"]
        ink = []
        for ci, ch in enumerate(item["label"]):
            g = FONT[ch]
            for gy in range(8):
                for gx in range(8):
                    if g[gy][gx]:
                        ink.append(((menu["x"] + ci) * 8 + gx, row * 8 + gy))
        out.append(ink)
    return out


def cell_key(pixels, c):
    x0, y0 = (c % CW) * CELL, (c // CW) * CELL
    return tuple(pixels[(y0 + y) * W + x0 + x] for y in range(CELL) for x in range(CELL))


def compose(scene):
    """Bake menu text into the scene and build its tile set (with blink variants).

    Adds: composed (pixels with text), tiles (unique 64-slot tuples), cell_tiles (tile per cell),
    item_cells (per item: [(cell, shown tile, hidden tile)])."""
    composed = list(scene["pixels"])
    menu = scene["menu"]
    if menu:
        for ink in menu_text_pixels(menu):
            for x, y in ink:
                composed[y * W + x] = menu["text_slot"]
    tiles, index = [], {}

    def tile_of(key):
        if key not in index:
            index[key] = len(tiles)
            tiles.append(key)
        return index[key]

    opts = scene.get("options")
    if opts:
        for r in opts["rows"]:
            for x, y in text_ink(r["label"], r["labelX"], r["labelY"]):
                composed[y * W + x] = opts["text_slot"]
        for r in opts["rows"]:
            draw_option_value(composed, list(composed), r, r["default"], opts["text_slot"])
    pz = scene.get("puzzle")
    if pz:
        from . import puzzle as kit
        empty_cells = [(pz["grid"]["y"] + r) * CW + pz["grid"]["x"] + c for r in range(pz["grid"]["h"]) for c in range(pz["grid"]["w"])]
        empty_cells += pz["next"]["cells"] if pz["next"] else []
        for c in empty_cells:
            x0, y0 = (c % CW) * CELL, (c // CW) * CELL
            for y in range(CELL):
                for x in range(CELL):
                    composed[(y0 + y) * W + x0 + x] = kit.BG_SLOT
        for spot, text in ((pz["score"], "000000"), (pz["virus_count"], "00"), (pz["level"], "00")):
            if spot:
                for x, y in text_ink(text, spot["x"], spot["y"]):
                    composed[y * W + x] = pz["text_slot"]
    press = scene.get("press")
    if press and press["prompt"]:
        pr = press["prompt"]
        for x, y in text_ink(pr["label"], pr["x"], pr["y"]):
            composed[y * W + x] = pr["text_slot"]
    scene["composed"] = composed
    scene["cell_tiles"] = [tile_of(cell_key(composed, c)) for c in range(CW * CH)]
    scene["prompt_cells"] = []
    scene["area_cells"] = []
    scene["option_strips"] = []      # per row: list (per value) of tile numbers for the value area
    if pz:
        from . import puzzle as kit
        # Kit tiles: index (shape << 2 | color) -> tile number. Shape 0 is the empty cell.
        empty = tile_of(kit.empty_tile())
        lut = [empty] * 32
        for shape, name in enumerate(kit.SHAPES, start=1):
            for color in range(kit.COLORS):
                lut[shape << 2 | color] = tile_of(kit.tile_slots(pz["shapes"][name], color))
        scene["kit_lut"] = lut
        # Digit tiles for each HUD cell, drawn over whatever is painted there.
        hud = {}
        for key in ("score", "virus_count", "level"):
            spot = pz[key]
            if not spot:
                continue
            per_cell = []
            for k, c in enumerate(spot["cells"]):
                digits = []
                for d in range(10):
                    img = list(scene["pixels"])
                    for x, y in text_ink(str(d), spot["x"] + k, spot["y"]):
                        img[y * W + x] = pz["text_slot"]
                    digits.append(tile_of(cell_key(img, c)))
                per_cell.append(digits)
            hud[key] = per_cell
        scene["hud"] = hud
    if opts:
        base = list(composed)
        for r in opts["rows"]:
            for c in option_value_cells(r):
                x0, y0 = (c % CW) * CELL, (c // CW) * CELL
                for y in range(CELL):
                    for x in range(CELL):
                        base[(y0 + y) * W + x0 + x] = scene["pixels"][(y0 + y) * W + x0 + x]
        strips = []
        for r in opts["rows"]:
            per_value = []
            for v in range(r["count"]):
                img = list(base)
                draw_option_value(img, base, r, v, opts["text_slot"])
                per_value.append([tile_of(cell_key(img, c)) for c in option_value_cells(r)])
            strips.append(per_value)
        scene["option_strips"] = strips
    if press and press["prompt"]:
        pr = press["prompt"]
        cells = [pr["y"] * CW + pr["x"] + i for i in range(len(pr["label"]))]
        scene["prompt_cells"] = [(c, scene["cell_tiles"][c], tile_of(cell_key(scene["pixels"], c))) for c in cells]
    if press and press["area"]:
        a = press["area"]
        for row in range(a["y"], a["y"] + a["h"]):
            cells = [row * CW + x for x in range(a["x"], a["x"] + a["w"])]
            scene["area_cells"].append([(c, scene["cell_tiles"][c], tile_of(cell_key(press["pressed"], c))) for c in cells])
    scene["item_cells"] = []
    if menu:
        for n, item in enumerate(menu["items"]):
            row = menu["y"] + n * menu["spacing"]
            cells = [row * CW + menu["x"] + i for i in range(len(item["label"]))]
            scene["item_cells"].append([(c, scene["cell_tiles"][c], tile_of(cell_key(scene["pixels"], c))) for c in cells])
    scene["tiles"] = tiles
    return scene


def fade_palettes(colors, step, to):
    """Blend RGB555 colors step/FADE_STEPS of the way to white or black."""
    out = []
    for c in colors:
        if to == "white":
            out.append([v + ((31 - v) * step + FADE_STEPS // 2) // FADE_STEPS for v in c])
        else:
            out.append([(v * (FADE_STEPS - step) + FADE_STEPS // 2) // FADE_STEPS for v in c])
    return out


def dmg_fade(step, to):
    """BGP/OBP value at a fade step: every shade moves `step` levels toward white or black."""
    shades = [0, 1, 2, 3]
    if to == "white":
        shades = [max(0, s - step) for s in shades]
    else:
        shades = [min(3, s + step) for s in shades]
    return sum(s << (2 * i) for i, s in enumerate(shades))
