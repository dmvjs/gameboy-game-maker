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

import contextlib
import re
import threading
from pathlib import Path

W, H, CELL = 160, 144, 8
CW, CH = W // CELL, H // CELL
MAX_BG_PALETTES = 24                 # in a project; each scene uses 8 at most (the hardware holds 8)
SCENE_BG_PALETTES = 8
MAX_OBJ_PALETTES = 8
MAX_TILES = 256
MAX_MENU_ITEMS = 6
MAX_FLASH_TILES = 80          # the flash area must flip within one VBlank
MAX_OPTION_ROWS = 6
FADE_STEPS = 4
FORMAT_VERSION = 2

FONT_FILES = {"classic": Path(__file__).with_name("font.txt"), "bold": Path(__file__).with_name("font-bold.txt")}
FONT_FILE = FONT_FILES["classic"]


class ProjectError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def load_font(path=FONT_FILE):
    """{char: 8x8 list of 0/1}. 5-wide glyphs sit one column in from the left; 7-wide ones at the left edge."""
    font, char, rows = {}, None, []
    for line in path.read_text().splitlines():
        if line.startswith("# ") or not line.strip():
            continue
        if line.startswith("= "):
            if char is not None:
                font[char] = rows
            char, rows = line[2], []
        else:
            rows.append(line)
    font[char] = rows
    width = len(next(iter(font.values()))[0])
    for ch, art in font.items():
        if len(art) != 7 or any(len(row) != width or set(row) - {"#", "."} for row in art):
            raise ValueError(f"{path.name}: glyph {ch!r} must be 7 rows of {width} '#'/'.' characters")
    left = 1 if width == 5 else 0
    glyphs = {" ": [[0] * 8 for _ in range(8)]}
    for ch, art in font.items():
        g = [[0] * 8 for _ in range(8)]
        for y, row in enumerate(art):
            for x, c in enumerate(row):
                g[y][x + left] = 1 if c == "#" else 0
        glyphs[ch] = g
    return glyphs


FONTS = {name: load_font(path) for name, path in FONT_FILES.items()}
FONT = FONTS["classic"]
assert set(FONTS["bold"]) == set(FONT), "every font needs the same characters"
_active = threading.local()


def active_font():
    return getattr(_active, "font", FONT)


@contextlib.contextmanager
def using_font(name):
    """Draw text in this project's font (per thread, so parallel builds don't mix fonts)."""
    old = active_font()
    _active.font = FONTS[name]
    try:
        yield
    finally:
        _active.font = old


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
        if menu and (s.get("menu") or {}).get("confirm") is not None:
            menu["confirm"] = _menu_confirm(s["menu"]["confirm"], where, len(bg), errors)
        press = _press_start((s or {}).get("pressStart"), (s or {}).get("pressed"), where, i, scene_count, errors)
        options = _options((s or {}).get("options"), where, i, scene_count, errors)
        puzzle = _puzzle((s or {}).get("puzzle"), where, i, scene_count, len(bg), cell_pal, errors)
        fight = _fight((s or {}).get("fight"), where, i, scene_count, len(bg), len(obj), errors)
        pass_key = _pass_key((s or {}).get("passKey"), where, i, scene_count, errors)
        if sum(bool(x) for x in (menu, press, options, puzzle, fight, pass_key)) > 1:
            errors.append(f"{where}: a scene can be a menu, a press-start screen, an options screen, a puzzle grid, "
                          "a fight or a pass key, only one.")
            press = options = puzzle = fight = pass_key = None
        back = (s or {}).get("back")
        if back is not None and not (isinstance(back, int) and 0 <= back < scene_count and back != i):
            errors.append(f"{where}: the B button goes to a scene that doesn't exist.")
            back = None
        if puzzle and back is not None:
            errors.append(f"{where}: B rotates the capsule on a puzzle grid, so it can't also go back.")
        if fight and back is not None:
            errors.append(f"{where}: B punches in a fight, so it can't also go back.")
        texts = _texts((s or {}).get("texts"), where, errors)
        used = set(cell_pal)
        if len(used) > SCENE_BG_PALETTES:
            errors.append(f"{where} uses {len(used)} background palettes; a scene can use {SCENE_BG_PALETTES}.")
        if (fight or puzzle) and max(used, default=0) >= SCENE_BG_PALETTES:
            errors.append(f"{where}: a {'fight' if fight else 'puzzle grid'} scene uses palettes 1-{SCENE_BG_PALETTES} only.")
        slide = (s or {}).get("slideIn", False)
        if not isinstance(slide, bool):
            errors.append(f"{where}: slideIn is true or false.")
            slide = False
        if slide and fight:
            errors.append(f"{where}: a fight scrolls its own rows, so it can't slide in.")
            slide = False
        dmc = (s or {}).get("nesDmc", 0)                 # an NES sample (1 the crowd) to start with the scene
        if not (isinstance(dmc, int) and 0 <= dmc <= 7):
            errors.append(f"{where}: nesDmc is an NES sample number, 0-7."); dmc = 0
        scenes.append({"name": name, "pixels": pixels, "cell_pal": cell_pal, "menu": menu, "press": press, "nes_dmc": dmc,
                       "options": options, "puzzle": puzzle, "fight": fight, "back": back, "texts": texts,
                       "slide": slide, **({"pass_key": pass_key} if pass_key else {})})

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
    for s in scenes:
        if s["fight"] and not obj_ok(s["fight"]["player"]["palette"], len(obj)):
            errors.append(f'Scene "{s["name"]}": the player uses a sprite palette that doesn\'t exist.')
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

    from .sfx import STYLES
    font = data.get("font", "classic")
    if font not in FONTS:
        errors.append(f"Unknown font {font!r}; use one of: {', '.join(FONTS)}.")
    sound = data.get("sound", "arcade")
    if sound not in STYLES:
        errors.append(f"Unknown sound style {sound!r}; use one of: {', '.join(STYLES)}.")

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
        "sound": sound,
        "font": font,
    }
    with using_font(font):
        for s in project["scenes"]:
            compose(s)
            if len(s["tiles"]) > MAX_TILES:
                extra = (" (the rival's always-there poses, plus room for his largest pose set, and the HUD's digits "
                         f"and bars; sets: {s['fight_swap']['sizes']})") if s.get("fight") else ""
                raise ProjectError([f'Scene "{s["name"]}" uses {len(s["tiles"])} different 8x8 tiles{extra}; the limit is '
                                    f"{MAX_TILES}. Reuse repeated patterns to bring it down."])
            if s.get("fight"):
                from . import fight as kit
                n = kit.OBJ_FIRST_TILE + len(s["fight_obj"])
                if n > kit.OBJ_TILE_LIMIT:
                    raise ProjectError([f'Scene "{s["name"]}": the player\'s poses need {n} sprite tiles; the limit is '
                                        f"{kit.OBJ_TILE_LIMIT}. Repeated and mirrored 8x8 pieces are free."])
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
            "blinks": blinks if isinstance(blinks, int) and 0 <= blinks <= 8 else 3,
            "select_moves": menu.get("selectMoves") is True}


MAX_CONFIRM_SPRITES = 30                          # OAM entries 2-31 (the cursor and slider marker take 0 and 1)


def _menu_confirm(c, where, n_bg, errors):
    """A menu's choice played out before its scene comes: a sprite (w x h pixels of slots 0-3 at x, y) and
    steps, each `frames` long: the sprite's colors 1-3 (or null: hidden), in front of the background or
    behind it (showing only where the background has color 0), and background palettes recolored. faded: the
    steps end in the transition's color, so the fade to the next scene starts there."""
    if c is None:
        return None
    spr, steps = (c or {}).get("sprite"), (c or {}).get("steps")
    if not isinstance(spr, dict) or not isinstance(steps, list) or not 1 <= len(steps) <= 64:
        errors.append(f"{where}: the menu's confirm animation is damaged (a sprite and 1-64 steps)."); return None
    w, h, x, y, px = (spr.get(k) for k in ("w", "h", "x", "y", "pixels"))
    if not (all(isinstance(v, int) for v in (w, h, x, y)) and w % 8 == 0 and h % 8 == 0 and 0 < w <= 64 and 0 < h <= 64
            and isinstance(px, str) and len(px) == w * h and set(px) <= set("0123")
            and 0 <= x and x + w <= W and 0 <= y and y + h <= H):
        errors.append(f"{where}: the confirm sprite must be up to 64x64 pixels (multiples of 8) of slots 0-3, on screen."); return None
    tiles, oam = [], []
    for by in range(h // 8):
        for bx in range(w // 8):
            key = tuple(int(px[(by * 8 + yy) * w + bx * 8 + xx]) for yy in range(8) for xx in range(8))
            if any(key):
                oam.append((y + by * 8, x + bx * 8, len(tiles)))
                tiles.append(key)
    if len(oam) > MAX_CONFIRM_SPRITES:
        errors.append(f"{where}: the confirm sprite needs {len(oam)} 8x8 sprites; {MAX_CONFIRM_SPRITES} at most."); return None
    good = lambda col: isinstance(col, list) and len(col) == 3 and all(isinstance(v, int) and 0 <= v <= 31 for v in col)
    out = []
    for st in steps:
        st = st if isinstance(st, dict) else {}
        frames, colors, bg = st.get("frames"), st.get("colors"), st.get("bg") or {}
        if not (isinstance(frames, int) and 1 <= frames <= 255) or not (colors is None or (isinstance(colors, list)
                and len(colors) == 3 and all(good(col) for col in colors))) or not isinstance(bg, dict):
            errors.append(f"{where}: a confirm step needs 1-255 frames and 3 colors (or none)."); return None
        recolor = {}
        for k, cols in bg.items():
            if not (str(k).isdigit() and int(k) < n_bg and isinstance(cols, list) and len(cols) == 4 and all(good(col) for col in cols)):
                errors.append(f"{where}: a confirm step recolors a palette that doesn't exist."); return None
            recolor[int(k)] = cols
        sfx = st.get("nesSfx", 0)
        out.append({"frames": frames, "colors": colors, "front": st.get("front") is True, "bg": recolor,
                    "sfx": sfx if isinstance(sfx, int) and 0 <= sfx < 256 else 0})
    return {"tiles": tiles, "oam": oam, "steps": out, "faded": c.get("faded") is True}


PASS_GROUPS = (3, 4, 3)                          # a pass key's digits, as Punch-Out!!'s: 3, 4, 3
PASS_OFFSETS = [k + g for g, n in enumerate(PASS_GROUPS) for k in range(sum(PASS_GROUPS[:g]), sum(PASS_GROUPS[:g + 1]))]
PASS_WIDTH = sum(PASS_GROUPS) + len(PASS_GROUPS) - 1


def _pass_key(pk, where, index, scene_count, errors):
    """A pass key entry: digits in groups at (x, y) cells; left/right picks one, up/down changes it, Start goes on."""
    if pk is None:
        return None
    if not isinstance(pk, dict):
        errors.append(f"{where}: the pass key settings are damaged."); return None
    x, y, slot, target = pk.get("x"), pk.get("y"), pk.get("textSlot", 0), pk.get("target")
    if not (isinstance(x, int) and isinstance(y, int) and 0 <= x and x + PASS_WIDTH <= CW and 0 <= y < CH):
        errors.append(f"{where}: the pass key is off screen ({PASS_WIDTH} cells wide)."); return None
    if not (isinstance(slot, int) and 0 <= slot <= 3):
        errors.append(f"{where}: the pass key's text slot must be 1-4."); return None
    if not (isinstance(target, int) and 0 <= target < scene_count and target != index):
        errors.append(f"{where}: Start goes to a scene that doesn't exist."); return None
    return {"x": x, "y": y, "text_slot": slot, "target": target, "cells": [y * CW + x + k for k in PASS_OFFSETS]}


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


def obj_ok(index, n_obj):
    return isinstance(index, int) and 0 <= index < n_obj


def _spot(spot, width, height=1):
    if not (isinstance(spot, dict) and isinstance(spot.get("x"), int) and isinstance(spot.get("y"), int)):
        return None
    if not (0 <= spot["x"] and spot["x"] + width <= CW and 0 <= spot["y"] and spot["y"] + height <= CH):
        return None
    return {"x": spot["x"], "y": spot["y"]}


def _fight(ft, where, index, scene_count, n_bg, n_obj, errors):
    """A boxing match: the rival's poses, the player's sprite poses, the HUD and the rival's script."""
    from . import fight as kit
    if ft is None:
        return None
    if not isinstance(ft, dict):
        errors.append(f"{where}: the fight settings are damaged."); return None
    n = len(errors)
    rv = ft.get("rival") or {}
    region = _spot(rv, kit.REGION_W, kit.REGION_H)
    if not region:
        errors.append(f"{where}: the rival's {kit.REGION_W}x{kit.REGION_H}-tile area must be on screen.")
    pals = rv.get("palettes") or {}
    if not all(isinstance(pals.get(k), int) and 0 <= pals[k] < n_bg for k in kit.CELL_KINDS):
        errors.append(f"{where}: the rival needs a skin, gloves and hair palette that exist.")
    poses = {}
    given = dict(rv.get("poses") or {})
    for name, stand_in in kit.POSE_FALLBACK.items():      # older projects: newer poses borrow an older one
        if name not in given and stand_in in given:
            given[name] = given[stand_in]
    for name in kit.RIVAL_POSES:
        pose = given.get(name)
        px, cells = (pose or {}).get("pixels"), (pose or {}).get("cells")
        if not (isinstance(px, str) and len(px) == kit.REGION_W * kit.REGION_H * 64 and set(px) <= set("0123")
                and isinstance(cells, str) and len(cells) == kit.REGION_W * kit.REGION_H and set(cells) <= set(kit.CELL_KINDS)):
            errors.append(f'{where}: the rival\'s "{name}" pose is missing or damaged.')
            continue
        poses[name] = {"pixels": [ord(c) - 48 for c in px], "cells": cells}
    pl = ft.get("player") or {}
    pposes = {}
    for name in kit.PLAYER_POSES:
        px = (pl.get("poses") or {}).get(name)
        if not (isinstance(px, str) and len(px) == kit.PLAYER_W * kit.PLAYER_H and set(px) <= set("0123")):
            errors.append(f'{where}: the player\'s "{name}" pose is missing or damaged.')
            continue
        pposes[name] = [ord(c) - 48 for c in px]
    ref = ft.get("referee") or {}
    rposes_ref = {}
    for name in kit.REF_POSES:
        px = (ref.get("poses") or {}).get(name)
        if not (isinstance(px, str) and len(px) == kit.REF_W * kit.REF_H and set(px) <= set("0123")):
            errors.append(f'{where}: the referee\'s "{name}" pose is missing or damaged.')
            continue
        rposes_ref[name] = [ord(c) - 48 for c in px]
    if not (isinstance(pl.get("tiredPalette", pl.get("palette")), int) and 0 <= pl.get("tiredPalette", pl.get("palette")) < n_obj):
        errors.append(f"{where}: the player's tired palette doesn't exist.")
    if not (isinstance(ref.get("palette"), int) and 0 <= ref["palette"] < n_obj):
        errors.append(f"{where}: the referee uses a sprite palette that doesn't exist.")
    hud_in = ft.get("hud") or {}
    hud = {}
    widths = {"stars": 1, "hearts": 2, "points": 6, "clock": 4, "round": 1, "playerBar": kit.BAR_CELLS, "rivalBar": kit.BAR_CELLS}
    for key, width in widths.items():
        spot = _spot(hud_in.get(key), width)
        if not spot:
            errors.append(f"{where}: the HUD's {key} must be on screen."); continue
        hud[key] = spot
    if region and len(hud) == len(widths):
        rcells = {(region["y"] + r) * CW + region["x"] + c for r in range(kit.REGION_H) for c in range(kit.REGION_W)}
        for key, spot in hud.items():
            if any(spot["y"] * CW + spot["x"] + k in rcells for k in range(widths[key])):
                errors.append(f"{where}: the HUD's {key} overlaps the rival's area.")
    crowd = ft.get("crowdRow", 0)
    if not (isinstance(crowd, int) and 0 <= crowd < CH):
        errors.append(f"{where}: the crowd row (where cameras flash) must be on screen.")
    slots = [ft.get("textSlot", 3), ft.get("barSlot", 3)]
    if not all(isinstance(v, int) and 0 <= v <= 3 for v in slots):
        errors.append(f"{where}: the HUD text and bar slots must be 1-4.")

    def script(items, what):
        out = []
        for it in items if isinstance(items, list) else []:
            op, arg = (it or [None, None])[:2] if isinstance(it, list) else (None, None)
            if op not in kit.OPS or not (isinstance(arg, int) and 0 <= arg <= 255):
                errors.append(f"{where}: the rival's {what} has a bad step ({it})."); return []
            out.append((op, arg))
        return out
    opening = script(ft.get("opening", []), "opening")
    loop = script(ft.get("loop"), "loop")
    if not loop:
        errors.append(f"{where}: the rival needs at least one move in his loop.")
    timed = []
    for t in ft.get("timed") or []:
        m = re.fullmatch(r"(\d):([0-5]\d)", str((t or {}).get("time", "")))
        rnd = (t or {}).get("round")
        if not (m and isinstance(rnd, int) and 1 <= rnd <= kit.TUNING["ROUNDS"] and t.get("op") in kit.OPS
                and isinstance(t.get("arg", 0), int) and int(m.group(1)) < kit.TUNING["ROUND_MINUTES"]):
            errors.append(f"{where}: a timed move is damaged ({t})."); continue
        timed.append((rnd, int(m.group(1)), int(m.group(2)), t["op"], t.get("arg", 0)))
    timed.sort()
    for key in ("win", "lose"):
        t = ft.get(key)
        if not (isinstance(t, int) and 0 <= t < scene_count and t != index):
            errors.append(f"{where}: the {'win' if key == 'win' else 'lose'} scene doesn't exist.")
    corner = ft.get("corner")
    if corner is not None and not (isinstance(corner, int) and 0 <= corner < scene_count and corner != index):
        errors.append(f"{where}: the between-rounds scene doesn't exist."); corner = None
    nes = _nes_fighter(ft.get("nes"), where, errors)
    fx = ft.get("effects") or {}
    if not (isinstance(fx, dict) and set(fx) <= set(kit.EFFECTS) and all(isinstance(v, bool) for v in fx.values())):
        errors.append(f"{where}: effects are on (true) or off (false): {', '.join(kit.EFFECTS)}.")
    if len(errors) > n:
        return None
    return {"x": region["x"], "y": region["y"], "palettes": {k: pals[k] for k in kit.CELL_KINDS}, "poses": poses,
            "player": {"palette": pl.get("palette"), "tired_palette": pl.get("tiredPalette", pl.get("palette")),
                       "poses": pposes}, "hud": hud,
            "referee": {"palette": ref.get("palette"), "poses": rposes_ref},
            "text_slot": slots[0], "bar_slot": slots[1], "crowd_row": crowd, "opening": opening, "loop": loop, "timed": timed,
            "win": ft["win"], "lose": ft["lose"], "corner": corner,
            "effects": {k: fx.get(k, True) for k in kit.EFFECTS}, "nes": nes}


def _nes_fighter(nes, where, errors):
    """A rival driven by Punch-Out!!'s own fighter data (see kit_nes.asm): the NES bank holding it (8 KB,
    base64), the fighter's offset in that bank, which of our poses shows each of its frames, and where its
    standing position is and how its coordinates scale to ours."""
    from . import fight as kit
    import base64
    if nes is None:
        return None
    try:
        bank = base64.b64decode(nes.get("bank", ""), validate=True)
    except Exception:
        bank = b""
    if len(bank) != 0x2000:
        errors.append(f"{where}: the NES fighter bank must be 8 KB."); return None
    try:
        mac = base64.b64decode(nes.get("mac", ""), validate=True)
    except Exception:
        mac = b""
    if len(mac) != 0x2000:
        errors.append(f"{where}: the NES Little Mac bank (PRG bank B) must be 8 KB."); return None
    sound = sound_fixed = samples = None
    if nes.get("sound") is not None:             # its sound engine: PRG bank 8 and the fixed bank's $F400-$F8FF
        try:
            sound = base64.b64decode(nes.get("sound", ""), validate=True)
            sound_fixed = base64.b64decode(nes.get("soundFixed", ""), validate=True)
            samples = base64.b64decode(nes.get("samples", ""), validate=True)
        except Exception:
            sound = b""
        if len(sound) != 0x2000 or len(sound_fixed or b"") != 0x500 or len(samples or b"") != 0x1400:
            errors.append(f"{where}: the NES sound engine must be PRG bank 8 (8 KB), the fixed bank's $F400-$F8FF and its"
                          " samples ($E000-$F3FF)."); return None
    offset = nes.get("offset", 0)
    if not (isinstance(offset, int) and 0 <= offset < 0x80 and offset % 16 == 0):
        errors.append(f"{where}: the NES fighter's offset must be 0-112, a multiple of 16."); return None
    frames = [kit.RIVAL_POSES.index("idle")] * 512      # per frame, then per frame drawn mirrored ($A2 set)
    given = (nes.get("frames") or {}).items()
    for mirrored in (False, True):
        for k, pose in given:
            k = str(k)
            if k.endswith("|") != mirrored:
                continue
            try:
                n = int(k.rstrip("|"), 16)
            except (TypeError, ValueError):
                n = -1
            if not 0 <= n < 256 or pose not in kit.RIVAL_POSES:
                errors.append(f"{where}: NES frame {k!r} -> {pose!r}: a frame number (hex, | for mirrored) and one of the rival's poses.")
                return None
            if not mirrored:
                frames[n] = frames[256 + n] = kit.RIVAL_POSES.index(pose)    # mirrored: the same, unless given
            else:
                frames[256 + n] = kit.RIVAL_POSES.index(pose)
    home = nes.get("home", [135, 182])
    scale = nes.get("scale", 0.7)
    if not (isinstance(home, list) and len(home) == 2 and all(isinstance(v, int) for v in home)
            and isinstance(scale, (int, float)) and 0.25 <= scale <= 1.5):
        errors.append(f"{where}: the NES fighter's home position or scale is damaged."); return None
    # Mac's frames: our pose (bit 7: mirrored); $80 and up are the NES's other pictures in his place (the
    # referee close up, the "Fight!" bubble): he keeps the pose he has ($FF), unless given one.
    mac_frames = [kit.PLAYER_POSES.index("idle")] * 128 + [0xFF] * 128
    for k, pose in (nes.get("macFrames") or {}).items():
        try:
            n = int(k, 16)
        except (TypeError, ValueError):
            n = -1
        if pose == "-" and 0 <= n < 256:
            mac_frames[n] = 0xFF
            continue
        mirrored = isinstance(pose, str) and pose.endswith("|")
        pose = pose[:-1] if mirrored else pose
        if not 0 <= n < 256 or pose not in kit.PLAYER_POSES:
            errors.append(f"{where}: NES Mac frame {k!r} -> {pose!r}: a frame number (hex) and one of the player's poses.")
            return None
        mac_frames[n] = kit.PLAYER_POSES.index(pose) | (0x80 if mirrored else 0)
    return {"bank": bank, "offset": offset, "frames": frames, "home": home, "scale": float(scale),
            "mac": mac, "mac_frames": mac_frames, "mac_home": nes.get("macHome", 176),
            "mac_scale": float(nes.get("macScale", scale)), "sound": sound, "sound_fixed": sound_fixed,
            "samples": samples}


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


def _texts(texts, where, errors):
    """Free text labels: [{label, x, y, textSlot}] in tiles, baked into the scene's tiles."""
    out = []
    for t in texts or []:
        t = t if isinstance(t, dict) else {}
        label = str(t.get("label") or "").upper()
        x, y, slot = t.get("x"), t.get("y"), t.get("textSlot")
        bad = sorted({c for c in label if c not in FONT})
        if not label or bad:
            errors.append(f"{where}: a text label needs characters from the font" + (f" (not {''.join(bad)})." if bad else "."))
        elif not (isinstance(x, int) and isinstance(y, int) and 0 <= x and x + len(label) <= CW and 0 <= y < CH):
            errors.append(f'{where}: the text "{label}" runs off screen.')
        elif slot not in (0, 1, 2, 3):
            errors.append(f'{where}: the text "{label}" needs a color slot 1-4.')
        else:
            out.append({"label": label, "x": x, "y": y, "text_slot": slot})
    return out


def text_ink(label, x, y):
    """Pixel positions covered by a label drawn with the built-in font at tile (x, y)."""
    ink = []
    for ci, ch in enumerate(label):
        g = active_font()[ch]
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
            g = active_font()[ch]
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
    for t in scene.get("texts") or []:
        for x, y in text_ink(t["label"], t["x"], t["y"]):
            composed[y * W + x] = t["text_slot"]
    ft = scene.get("fight")
    if ft:
        _fight_compose_base(scene, composed)
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
    pk = scene.get("pass_key")
    if pk:
        for c in pk["cells"]:
            for x, y in text_ink("0", c % CW, c // CW):
                composed[y * W + x] = pk["text_slot"]
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
    if pk:                          # per digit: its tile for 0-9, then without it (the blink)
        per_cell = []
        for c in pk["cells"]:
            tiles_c = []
            for d in range(10):
                img = list(scene["pixels"])
                for x, y in text_ink(str(d), c % CW, c // CW):
                    img[y * W + x] = pk["text_slot"]
                tiles_c.append(tile_of(cell_key(img, c)))
            per_cell.append(tiles_c + [tile_of(cell_key(scene["pixels"], c))])
        scene["pass_tiles"] = per_cell
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
    if ft:
        _fight_compose_tiles(scene, tile_of)
    scene["item_cells"] = []
    if menu:
        for n, item in enumerate(menu["items"]):
            row = menu["y"] + n * menu["spacing"]
            cells = [row * CW + menu["x"] + i for i in range(len(item["label"]))]
            scene["item_cells"].append([(c, scene["cell_tiles"][c], tile_of(cell_key(scene["pixels"], c))) for c in cells])
    scene["tiles"] = tiles
    if ft:
        _fight_swap(scene)
    return scene


def _rival_pixels(scene, pose):
    """The rival's area painted with one pose: (pixel index, slot) and (cell, palette) pairs."""
    from . import fight as kit
    ft = scene["fight"]
    p = ft["poses"][pose]
    pw = kit.REGION_W * CELL
    px = [((ft["y"] * CELL + i // pw) * W + ft["x"] * CELL + i % pw, v) for i, v in enumerate(p["pixels"])]
    cells = [((ft["y"] + k // kit.REGION_W) * CW + ft["x"] + k % kit.REGION_W, ft["palettes"][kind])
             for k, kind in enumerate(p["cells"])]
    return px, cells


def _fight_compose_base(scene, composed):
    """Bake the idle pose and the clock's colon into the scene."""
    ft = scene["fight"]
    px, cells = _rival_pixels(scene, "idle")
    for i, v in px:
        composed[i] = v
    for c, pal in cells:
        scene["cell_pal"][c] = pal
    clock = ft["hud"]["clock"]
    for x, y in text_ink(":", clock["x"] + 1, clock["y"]):
        composed[y * W + x] = ft["text_slot"]


def bar_tile(pixels, c, level, slot):
    """A health bar cell filled `level` pixels (0-8) from the left, rows 2-5, over what's painted."""
    key = list(cell_key(pixels, c))
    for y in range(2, 6):
        for x in range(level):
            key[y * CELL + x] = slot
    return tuple(key)


def _fight_compose_tiles(scene, tile_of):
    """Tiles for every rival pose, the HUD's digits and bars, and the sprite tiles."""
    from . import fight as kit
    ft = scene["fight"]
    maps, attrs = {}, {}
    for pose in [p for p in kit.RIVAL_POSES if p not in kit.POSE_SETS["knockdown"]]:
        img = list(scene["composed"])
        px, cells = _rival_pixels(scene, pose)
        for i, v in px:
            img[i] = v
        maps[pose] = [tile_of(cell_key(img, c)) for c, _ in cells]
        attrs[pose] = [pal for _, pal in cells]
    scene["fight_maps"], scene["fight_attrs"] = maps, attrs
    # HUD: each cell's tile for every value, drawn over that cell's painting
    hud, lut, cells = ft["hud"], [], []
    def digit_cells(key, offsets):
        for k in offsets:
            c = hud[key]["y"] * CW + hud[key]["x"] + k
            row = []
            for d in range(10):
                img = list(scene["pixels"])
                for x, y in text_ink(str(d), hud[key]["x"] + k, hud[key]["y"]):
                    img[y * W + x] = ft["text_slot"]
                row.append(tile_of(cell_key(img, c)))
            lut.extend(row); cells.append(c)
    def bar_cells(key):
        for k in range(kit.BAR_CELLS):
            c = hud[key]["y"] * CW + hud[key]["x"] + k
            row = [tile_of(bar_tile(scene["pixels"], c, lv, ft["bar_slot"])) for lv in range(9)]
            lut.extend(row + [row[0]]); cells.append(c)
    digit_cells("stars", [0]); digit_cells("hearts", [0, 1]); digit_cells("points", range(6))
    digit_cells("clock", [0, 2, 3]); digit_cells("round", [0])
    bar_cells("playerBar"); bar_cells("rivalBar")
    scene["fight_lut"], scene["fight_hud_cells"] = lut, cells
    # sprite tiles: the player's poses (mirrored copies shared) and the count's glyphs
    obj, index = [], {}
    def obj_tile(key):
        if key in index:
            return index[key], 0
        flipped = tuple(key[y * 8 + 7 - x] for y in range(8) for x in range(8))
        if flipped in index:
            return index[flipped], 0x20
        index[key] = len(obj)
        obj.append(key)
        return index[key], 0
    def sprite_list(px, w, h, attr):
        out = []
        for by in range(h // 8):
            for bx in range(w // 8):
                key = tuple(px[(by * 8 + y) * w + bx * 8 + x] for y in range(8) for x in range(8))
                if any(key):
                    t, flip = obj_tile(key)
                    out.append((by * 8, bx * 8, kit.OBJ_FIRST_TILE + t, attr | flip))
        return out
    pal = ft["player"]["palette"]
    sprites = {pose: sprite_list(ft["player"]["poses"][pose], kit.PLAYER_W, kit.PLAYER_H, pal) for pose in kit.PLAYER_POSES}
    ref_attr = ft["referee"]["palette"] | 0x10          # Color: its palette; original: OBP1
    scene["fight_ref_sprites"] = {pose: sprite_list(ft["referee"]["poses"][pose], kit.REF_W, kit.REF_H, ref_attr)
                                  for pose in kit.REF_POSES}
    count_first = len(obj)
    for ch in kit.COUNT_GLYPHS:                 # the referee's words, each letter on a piece of speech bubble
        g = active_font()[ch]
        key = tuple(3 if y == 7 else (3 if g[y][x] else 2) for y in range(8) for x in range(8))
        index.pop(key, None)
        obj.append(key)
    for art in kit.BUBBLE_ENDS:
        obj.append(tuple(int(ch) if ch != "." else 0 for row in art for ch in row))
    scene["fight_bubble"] = [kit.OBJ_FIRST_TILE + len(obj) - 2, kit.OBJ_FIRST_TILE + len(obj) - 1]
    scene["fight_sprites"], scene["fight_obj"] = sprites, obj
    scene["fight_count_tile"] = kit.OBJ_FIRST_TILE + count_first
    for effect, art, key in (("stars", kit.STAR_TILE, "fight_star_tile"),        # the dazed star
                             ("sweat", kit.DROP_TILE, "fight_drop_tile"),        # a sweat bead
                             ("spark", kit.SPARK_TILE, "fight_spark_tile")):     # a quarter of the impact burst
        if ft["effects"][effect]:                       # effects that are off take no sprite tile
            obj.append(tuple(int(ch) if ch != "." else 0 for row in art for ch in row))
            scene[key] = kit.OBJ_FIRST_TILE + len(obj) - 1
        else:
            scene[key] = 0
    # a camera flash in the crowd: a white burst (slot 1) on the darkest slot
    burst = ["...#....", ".#.#.#..", "..###...", "#######.", "..###...", ".#.#.#..", "...#....", "........"]
    scene["fight_flash_tile"] = tile_of(tuple(0 if ch == "#" else 3 for row in burst for ch in row))


def _fight_swap(scene):
    """Lay out video memory: tiles every frame may need first, then one shared area that holds one pose set at
    a time (attack, knockdown or special). The ROM swaps sets into that area as the fight needs them."""
    from . import fight as kit
    tiles, maps = scene["tiles"], scene["fight_maps"]
    in_set = {p for poses in kit.POSE_SETS.values() for p in poses}
    keys = {pose: [tiles[t] for t in m] for pose, m in maps.items()}
    for pose in kit.POSE_SETS["knockdown"]:            # knockdown poses weren't in the tile set yet
        img = list(scene["composed"])
        px, cells = _rival_pixels(scene, pose)
        for i, v in px:
            img[i] = v
        keys[pose] = [cell_key(img, c) for c, _ in cells]
        scene["fight_attrs"][pose] = [pal for _, pal in cells]
    always = [tiles[t] for t in scene["cell_tiles"]] + [tiles[t] for t in scene["fight_lut"]] + [tiles[scene["fight_flash_tile"]]]
    for pose, k in keys.items():
        if pose not in in_set:
            always += k
    base, base_index = [], {}
    for key in always:
        if key not in base_index:
            base_index[key] = len(base)
            base.append(key)
    first = len(base)
    sets = {}
    for name, poses in kit.POSE_SETS.items():
        own = []
        for pose in poses:
            for key in keys[pose]:
                if key not in base_index and key not in own:
                    own.append(key)
        sets[name] = own
    size = max(len(own) for own in sets.values())
    for name, poses in kit.POSE_SETS.items():
        slot = {key: first + n for n, key in enumerate(sets[name])}
        for pose in poses:
            maps[pose] = [base_index.get(key, slot.get(key)) for key in keys[pose]]
    for pose in maps:
        if pose not in in_set:
            maps[pose] = [base_index[key] for key in keys[pose]]
    empty = tuple([0] * 64)
    padded = {name: own + [empty] * (size - len(own)) for name, own in sets.items()}
    scene["tiles"] = base + padded["attack"]              # the attack set is loaded with the scene
    scene["cell_tiles"] = [base_index[tiles[t]] for t in scene["cell_tiles"]]
    scene["fight_lut"] = [base_index[tiles[t]] for t in scene["fight_lut"]]
    scene["fight_flash_tile"] = base_index[tiles[scene["fight_flash_tile"]]]
    scene["fight_swap"] = {"first": first, "count": size, "sets": [padded[n] for n in ("attack", "knockdown", "special")],
                           "sizes": {n: len(own) for n, own in sets.items()}}


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
