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
MAX_BG_PALETTES = 128                # in a project; each scene uses 8 at most (the hardware holds 8)
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
    if not 1 <= len(scenes_in) <= 120:            # (scene tables are indexed by its number doubled: under 128)
        errors.append("A project needs between 1 and 120 scenes.")
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
        cutscene = _cutscene((s or {}).get("cutscene"), where, len(bg), len(obj), errors)
        typed = _typed((s or {}).get("typed"), where, errors)
        if typed and not press:
            errors.append(f"{where}: typed text is for a press-start screen (Start goes on once it's written)."); typed = None
        if cutscene and not press:
            errors.append(f"{where}: a cutscene is a press-start screen (Start goes on, once its box is written)."); cutscene = None
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
        if puzzle and max(used, default=0) >= SCENE_BG_PALETTES:   # (a fight's are moved into hardware slots)
            errors.append(f"{where}: a puzzle grid scene uses palettes 1-{SCENE_BG_PALETTES} only.")
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
        music = (s or {}).get("nesMusic", 0)             # an NES song to start with the scene (Punch-Out!!'s numbers)
        if not (isinstance(music, int) and 0 <= music <= 255):
            errors.append(f"{where}: nesMusic is an NES song number, 0-255."); music = 0
        scenes.append({"name": name, "pixels": pixels, "cell_pal": cell_pal, "menu": menu, "press": press, "nes_dmc": dmc,
                       **({"nes_music": music} if music else {}),
                       "options": options, "puzzle": puzzle, "fight": fight, "back": back, "texts": texts,
                       "slide": slide, **({"pass_key": pass_key} if pass_key else {}),
                       **({"cutscene": cutscene} if cutscene else {}), **({"typed": typed} if typed else {})})

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
                n = s["fight_slots"]["used"]
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
    pk = menu.get("passKey")                # Punch-Out!!'s: the key shown under its item while it's chosen
    if pk is not None and ok:
        item, label = pk.get("item"), str(pk.get("label", "PASS KEY")).upper()
        ly, ky, pslot = pk.get("labelY"), pk.get("y"), pk.get("textSlot", slot)
        codes = pk.get("codes") or []
        if not (isinstance(item, int) and 0 <= item < len(out)):
            errors.append(f"{where}: the pass key's item doesn't exist."); ok = False
        elif not (isinstance(ly, int) and isinstance(ky, int) and 0 <= ly < CH and 0 <= ky < CH and ly != ky
                  and len(label) <= CW and set(label) <= set(FONT)):
            errors.append(f"{where}: the pass key's rows must be on screen (its label in the font, {CW} at most)."); ok = False
        elif not all(isinstance(c, dict) and re.fullmatch(r"[0-9]{10}", str(c.get("key", "")))
                     and isinstance(c.get("target"), int) and 0 <= c["target"] < scene_count for c in codes):
            errors.append(f"{where}: each pass key code is ten digits and a scene."); ok = False
        else:
            pk = {"item": item, "label": label, "label_y": ly, "y": ky, "text_slot": pslot,
                  "codes": [{"key": [int(d) for d in c["key"]], "target": c["target"]} for c in codes]}
    gloves = menu.get("gloves")             # Punch-Out!!'s: a glove either side of the chosen item, for the cursor
    if gloves is not None:
        g = gloves if isinstance(gloves, dict) else {}
        px, cols, lx, rx, dy = (g.get(k) for k in ("pixels", "colors", "left", "right", "dy"))
        good = lambda c: isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 31 for v in c)
        if not (isinstance(px, str) and len(px) == 24 * 16 and set(px) <= set("0123") and isinstance(cols, list)
                and len(cols) == 3 and all(good(c) for c in cols) and all(isinstance(v, int) for v in (lx, rx, dy))
                and 0 <= lx <= W - 24 and 0 <= rx <= W - 24 and -8 <= dy <= 8):
            errors.append(f"{where}: the menu's gloves are 24x16 pixels of slots 0-3, 3 colors, and their places."); ok = False
        else:
            gloves = {"tiles": [tuple(int(px[(r * 8 + y) * 24 + c * 8 + x]) for y in range(8) for x in range(8))
                                for r in range(2) for c in range(3)], "colors": cols, "left": lx, "right": rx, "dy": dy}
    if not ok:
        return None
    blinks = menu.get("blinks", 3)
    return {"x": x, "y": y, "spacing": spacing, "text_slot": slot, "items": out,
            "cursor_bob": menu.get("cursorAnimation", "bob") == "bob",
            "blinks": blinks if isinstance(blinks, int) and 0 <= blinks <= 8 else 3,
            "select_moves": menu.get("selectMoves") is True, **({"pass_key": pk} if pk else {}),
            **({"gloves": gloves} if gloves else {})}


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


def _cutscene(cs, where, n_bg, n_obj, errors):
    """A press-start screen that plays a scene (Punch-Out!!'s training run): a picture 256 wide (the whole map:
    it scrolls round), scrolling at speed pixels every 4 frames (evenly: 3 is 1, 1, 1, 0) until its box comes up,
    stopping where endX puts it then (or in bands, each from its line down: its speed in 256ths of a pixel a
    frame and its endX, Punch-Out!!'s parallax); sprite actors each cycling frames (on after the stop); the box comes up
    after some frames and writes its lines a letter at a time (Start goes on once it's done); NES music."""
    if cs is None:
        return None
    try:
        px, cells = cs["pixels"], cs["cells"]
        assert isinstance(px, str) and len(px) == 256 * H and set(px) <= set("0123")
        assert isinstance(cells, list) and len(cells) == 32 * CH and all(isinstance(c, int) and 0 <= c < n_bg for c in cells)
        actors = []
        for a in cs.get("actors") or []:
            w, h = a["w"], a["h"]
            assert w % 8 == 0 and h % 8 == 0 and 0 < w <= 32 and 0 < h <= 32
            frames = []
            for f in a["frames"]:
                assert len(f["pixels"]) == w * h and set(f["pixels"]) <= set("0123")
                assert len(f["cells"]) == (w // 8) * (h // 8) and all(0 <= c < n_obj for c in f["cells"])
                frames.append({"pixels": [int(v) for v in f["pixels"]], "cells": list(f["cells"])})
            assert 1 <= len(frames) <= 16
            actors.append({"x": int(a["x"]), "y": int(a["y"]), "w": w, "h": h, "every": int(a.get("every", 6)), "frames": frames})
        box = cs.get("box")
        if box:
            lines = [str(l).upper() for l in box["lines"]]
            assert all(set(l) <= set(FONT) for l in lines) and 1 <= len(lines) <= 4
            width = max(len(l) for l in lines) + 2
            assert 0 <= box["x"] and box["x"] + width <= CW and 0 <= box["y"] and box["y"] + len(lines) + 2 <= CH
            assert isinstance(box["palette"], int) and 0 <= box["palette"] < n_bg
            box = {"x": box["x"], "y": box["y"], "lines": lines, "width": width, "palette": box["palette"],
                   "text_slot": int(box.get("textSlot", 1)), "bg_slot": int(box.get("bgSlot", 3)),
                   "after": int(box.get("after", 300)), "every": int(box.get("every", 2))}
        speed = int(cs.get("speed", 3))
        music = int(cs.get("music", 0))
        end_x = int(cs.get("endX", 0))
        assert 0 <= speed <= 8 and 0 <= music <= 0x3F and 0 <= end_x < 256
        bands = [{"y": int(b["y"]), "speed": int(b["speed"]), "end_x": int(b.get("endX", 0))} for b in cs.get("bands") or []]
        assert len(bands) <= 12 and all(0 <= b["y"] < H and 0 <= b["speed"] <= 1024 and 0 <= b["end_x"] < 256 for b in bands)
        assert all(a["y"] < b["y"] for a, b in zip(bands, bands[1:]))
    except (KeyError, TypeError, ValueError, AssertionError):
        errors.append(f"{where}: the cutscene is damaged (a 256x{H} picture, its cells' palettes, actors, its box).")
        return None
    return {"pixels": [int(v) for v in px], "cells": cells, "actors": actors, "box": box, "speed": speed, "music": music, "end_x": end_x,
            "bands": bands or [{"y": 0, "speed": speed * 64, "end_x": end_x}]}


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
        rows = label.split("\n")                    # (a line each: Punch-Out!!'s PUSH / START!)
        bad = sorted({c for c in label if c not in FONT and c != "\n"})
        if not all(rows) or bad:
            errors.append(f"{where}: the prompt needs a label using the font's characters."); ok = False
        elif not (isinstance(px, int) and isinstance(py, int) and 0 <= px and px + max(map(len, rows)) <= CW
                  and 0 <= py and py + len(rows) <= CH):
            errors.append(f"{where}: the prompt runs off screen."); ok = False
        elif not (isinstance(slot, int) and 0 <= slot <= 3):
            errors.append(f"{where}: the prompt text slot must be 1-4."); ok = False
        elif area is not None and ok and (area["y"] <= py + len(rows) - 1 and py < area["y"] + area["h"]) and (
                px < area["x"] + area["w"] and area["x"] < px + max(map(len, rows))):
            errors.append(f"{where}: the prompt and the flash area overlap; move one of them."); ok = False
        if ok:
            prompt = {"label": label, "x": px, "y": py, "text_slot": slot, "blink": bool(prompt.get("blink", True))}
    dmc = press.get("nesDmc", 0)           # an NES sample (1 the crowd) on the press, in place of its sound
    if not (isinstance(dmc, int) and 0 <= dmc <= 7):
        errors.append(f"{where}: the press's nesDmc is an NES sample number, 0-7."); ok = False
    hold = press.get("hold", 0)             # frames on the screen after the flashes (Punch-Out!!'s challenger, its crowd)
    if not (isinstance(hold, int) and 0 <= hold <= 255):
        errors.append(f"{where}: the press's hold is 0-255 frames."); ok = False
    auto = press.get("auto", 0)             # frames till it goes on by itself, Start ignored (Punch-Out!!'s first screen)
    if not (isinstance(auto, int) and 0 <= auto <= 65535):
        errors.append(f"{where}: the press's auto is 0-65535 frames."); ok = False
    ring = press.get("ring")                # while it waits: an NES effect on these frames (Punch-Out!!'s bells at power-on)
    at = (ring or {}).get("at") if isinstance(ring, dict) else None
    if ring is not None and not (isinstance(ring.get("nesSfx"), int) and 1 <= ring["nesSfx"] <= 255 and auto
                                 and isinstance(at, list) and 1 <= len(at) <= 32 and all(isinstance(f, int) for f in at)
                                 and at[0] >= 0 and all(a < b for a, b in zip(at, at[1:])) and all(b - a <= 255 for a, b in zip([-1] + at, at))):
        errors.append(f"{where}: the press's ring is an NES effect (1-255) on rising frames (up to 32, at most 255 apart), "
                      "on a screen that goes on by itself."); ok = False
    quiet = press.get("quiet", False)       # no sound on the press (the NES game's own music stopped, as its screens do)
    if not isinstance(quiet, bool):
        errors.append(f"{where}: the press's quiet is true or false."); ok = False
    card = _round_card(press.get("card"), where, errors)
    if press.get("card") is not None and card is None:
        ok = False
    if not ok:
        return None
    return {"target": target, "flashes": flashes, "prompt": prompt, "nes_dmc": dmc, "hold": hold, "quiet": quiet,
            **({"auto": auto} if auto else {}),
            **({"ring": {"sfx": ring["nesSfx"], "gaps": [b - a for a, b in zip([-1] + at, at)]}} if ring else {}),
            **({"card": card} if card else {}),
            "area": dict(area) if area else None,
            "pressed": [ord(c) - 48 for c in pressed] if area else None}


def _round_card(card, where, errors):
    """Punch-Out!!'s round card, under a press-start screen: after Start the screen scrolls up (4 pixels a frame)
    and it comes up from below, then holds before the next scene. Its variants (pick "first", or "round": the
    corner before round 2 the first) each a label (its top row, centred) and a 12x16 dot matrix ("#" lit) under it
    past a row's gap; the grid's palette (slot 0 the lit dot, 2 the unlit cell, 3 black), the label's palette and
    slot; hold frames."""
    if card is None:
        return None
    bad = lambda msg: errors.append(f"{where}: the round card: {msg}")
    if not isinstance(card, dict):
        bad("its settings are damaged."); return None
    variants, pick = card.get("variants"), card.get("pick", "first")
    if pick not in ("first", "round") or not (isinstance(variants, list) and 1 <= len(variants) <= 4):
        bad('it needs 1-4 variants, picked "first" or by "round".'); return None
    out = []
    for v in variants:
        label = str((v or {}).get("label") or "").upper()
        dots = (v or {}).get("dots")
        if not label or len(label) > CW or any(c not in FONT for c in label):
            bad("a label is 1-20 of the font's characters."); return None
        if not (isinstance(dots, list) and len(dots) == 16 and all(isinstance(r, str) and len(r) == 12 for r in dots)):
            bad("a digit is 16 rows of 12 dots."); return None
        out.append({"label": label, "dots": [[ch == "#" for ch in r] for r in dots]})
    pal, tpal, slot, hold = card.get("palette"), card.get("textPalette"), card.get("textSlot", 1), card.get("hold", 100)
    if not all(isinstance(v, int) for v in (pal, tpal, slot, hold)) or slot not in (0, 1, 2, 3) or not 1 <= hold <= 255:
        bad("its palettes, text slot (1-4) and hold (1-255 frames) are needed."); return None
    return {"pick": pick, "variants": out, "palette": pal, "text_palette": tpal, "text_slot": slot, "hold": hold}


CARD_UNLIT = tuple(3 if x == 0 or y == 0 else 2 for y in range(8) for x in range(8))     # a dark cell, its grid
CARD_LIT = tuple(3 if x == 0 or y == 0 or (x in (1, 7) and y in (1, 7)) else 0          # a lit dot, rounded
                 for y in range(8) for x in range(8))


def _compose_card(scene, tile_of):
    """The round card's rows per variant: 18 rows of (tile, palette) for the screen's 20 cells: the label on the
    top row, a row's gap, the 12x16 grid centred under it."""
    card = scene["press"]["card"]
    blank = tile_of(tuple([3] * 64))
    unlit, lit = tile_of(CARD_UNLIT), tile_of(CARD_LIT)
    glyph = {}
    out = []
    for v in card["variants"]:
        rows = [[(blank, card["text_palette"])] * CW for _ in range(CH)]
        x0 = (CW - len(v["label"])) // 2
        for k, ch in enumerate(v["label"]):
            if ch not in glyph:
                key = [3] * 64
                for x, y in text_ink(ch, 0, 0):
                    key[y * CELL + x] = card["text_slot"]
                glyph[ch] = tile_of(tuple(key))
            rows[0][x0 + k] = (glyph[ch], card["text_palette"])
        gx = (CW - 12) // 2
        for r, line in enumerate(v["dots"]):
            for c, on in enumerate(line):
                rows[2 + r][gx + c] = (lit if on else unlit, card["palette"])
        out.append(rows)
    scene["card_rows"] = out


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
    def rival_poses(given, which):
        poses = {}
        given = dict(given)
        for name, stand_in in kit.POSE_FALLBACK.items():  # older projects: newer poses borrow an older one
            if name not in given and stand_in in given:
                given[name] = given[stand_in]
        for name in kit.RIVAL_POSES:
            pose = given.get(name)
            px, cells = (pose or {}).get("pixels"), (pose or {}).get("cells")
            if not (isinstance(px, str) and len(px) == kit.REGION_W * kit.REGION_H * 64 and set(px) <= set("0123")
                    and isinstance(cells, str) and len(cells) == kit.REGION_W * kit.REGION_H and set(cells) <= set(kit.CELL_KINDS)):
                errors.append(f'{where}: the rival\'s "{name}" {which}pose is missing or damaged.')
                continue
            poses[name] = {"pixels": [ord(c) - 48 for c in px], "cells": cells}
        return poses
    poses = rival_poses(rv.get("poses") or {}, "")
    cgb_poses = rival_poses(rv["cgbPoses"], "Game Boy Color ") if rv.get("cgbPoses") else None   # (finer: Color has
                                                                                                  # a second tile bank)
    pl = ft.get("player") or {}
    pposes = {}
    for name in kit.PLAYER_POSES:
        px = (pl.get("poses") or {}).get(name)
        if not (isinstance(px, str) and len(px) == kit.PLAYER_W * kit.PLAYER_H and set(px) <= set("0123")):
            errors.append(f'{where}: the player\'s "{name}" pose is missing or damaged.')
            continue
        pposes[name] = [ord(c) - 48 for c in px]
    pcgb = {}                                   # (optional) Color's own, unshared: in its second tile bank
    for name in kit.PLAYER_POSES if pl.get("cgbPoses") else ():
        px = (pl.get("cgbPoses") or {}).get(name)
        if not (isinstance(px, str) and len(px) == kit.PLAYER_W * kit.PLAYER_H and set(px) <= set("0123")):
            errors.append(f'{where}: the player\'s Game Boy Color "{name}" pose is missing or damaged.')
            continue
        pcgb[name] = [ord(c) - 48 for c in px]
    ref = ft.get("referee") or {}
    rposes_ref = {}
    shirt = ref.get("shirtPalette")             # (optional) a second palette: pixels 4 are drawn in it
    if shirt is not None and not (isinstance(shirt, int) and 0 <= shirt < n_obj):
        errors.append(f"{where}: the referee's shirt palette doesn't exist."); shirt = None
    for name in kit.REF_POSES:
        px = (ref.get("poses") or {}).get(name)
        if not (isinstance(px, str) and len(px) == kit.REF_W * kit.REF_H and set(px) <= set("01234" if shirt is not None else "0123")):
            errors.append(f'{where}: the referee\'s "{name}" pose is missing or damaged.')
            continue
        rposes_ref[name] = [ord(c) - 48 for c in px]
    if not (isinstance(pl.get("tiredPalette", pl.get("palette")), int) and 0 <= pl.get("tiredPalette", pl.get("palette")) < n_obj):
        errors.append(f"{where}: the player's tired palette doesn't exist.")
    if not (isinstance(pl.get("downPalette", pl.get("palette")), int) and 0 <= pl.get("downPalette", pl.get("palette")) < n_obj):
        errors.append(f"{where}: the player's knocked-down palette doesn't exist.")
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
    rope = ft.get("ropeRow")                    # (optional) Punch-Out!!'s bottom rope, behind his head: the row his
    if rope is not None:                        # area starts at shows it; his rows over it are sprites
        px, cells = (rope.get("pixels"), rope.get("cells")) if isinstance(rope, dict) else (None, None)
        if not (isinstance(px, str) and len(px) == W * CELL and set(px) <= set("0123")
                and isinstance(cells, list) and len(cells) == CW and all(isinstance(c, int) and 0 <= c < n_bg for c in cells)):
            errors.append(f"{where}: the rope row is a 160x8 strip and its 20 cells' palettes."); rope = None
        else:
            rope = {"pixels": [ord(c) - 48 for c in px], "cells": list(cells)}
    side = ft.get("sideRope")                   # (optional, Color) the ring's side ropes' ends below the crowd's
    if side is not None and not (isinstance(side, str) and len(side) == 8 * 16 and set(side) <= set("0123")):   # rows:
        errors.append(f"{where}: the side rope is an 8x16 sprite."); side = None              # 8x16, left (mirrored right)
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
    win_tko = ft.get("winTko")                  # (optional) the win scene when he's out on a TKO
    if win_tko is not None and not (isinstance(win_tko, int) and 0 <= win_tko < scene_count and win_tko != index):
        errors.append(f"{where}: the TKO win scene doesn't exist."); win_tko = None
    nes = _nes_fighter(ft.get("nes"), where, errors)
    fx = ft.get("effects") or {}
    if not (isinstance(fx, dict) and set(fx) <= set(kit.EFFECTS) and all(isinstance(v, bool) for v in fx.values())):
        errors.append(f"{where}: effects are on (true) or off (false): {', '.join(kit.EFFECTS)}.")
    if len(errors) > n:
        return None
    return {"x": region["x"], "y": region["y"], "palettes": {k: pals[k] for k in kit.CELL_KINDS}, "poses": poses,
            **({"cgb_poses": cgb_poses} if cgb_poses else {}),
            "player": {"palette": pl.get("palette"), "tired_palette": pl.get("tiredPalette", pl.get("palette")),
                       "down_palette": pl.get("downPalette", pl.get("palette")),
                       "poses": pposes, **({"cgb_poses": pcgb} if pcgb else {})}, "hud": hud,
            "referee": {"palette": ref.get("palette"), "shirt_palette": shirt, "poses": rposes_ref},
            "text_slot": slots[0], "bar_slot": slots[1], "crowd_row": crowd, "opening": opening, "loop": loop, "timed": timed,
            **({"rope_row": rope} if rope else {}), **({"side_rope": [ord(c) - 48 for c in side]} if side else {}),
            "win": ft["win"], "lose": ft["lose"], "corner": corner, "win_tko": win_tko,
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
    places = [(0, 0)] * 512                             # per frame (then mirrored): pixels right, down
    for mirrored in (False, True):
        for k, v in (nes.get("places") or {}).items():
            k = str(k)
            if k.endswith("|") != mirrored:
                continue
            try:
                n = int(k.rstrip("|"), 16)
            except (TypeError, ValueError):
                n = -1
            if not (0 <= n < 256 and isinstance(v, list) and len(v) == 2
                    and all(isinstance(d, int) and -32 <= d <= 32 for d in v)):
                errors.append(f"{where}: NES frame {k!r}'s place: a frame number (hex, | for mirrored) and [right, down], -32 to 32.")
                return None
            if not mirrored:
                places[n] = places[256 + n] = tuple(v)
            else:
                places[256 + n] = tuple(v)
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
    mac_places = [0] * 256              # per Mac frame: pixels down (0-63), bit 7: in his knocked-down colors
    for k, v in (nes.get("macPlaces") or {}).items():
        try:
            n = int(k, 16)
        except (TypeError, ValueError):
            n = -1
        if not (0 <= n < 256 and isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) and 0 <= v[0] < 64
                and v[1] in (0, 1)):
            errors.append(f"{where}: NES Mac frame {k!r}'s place: a frame number (hex) and [pixels down 0-63, knocked-down colors 0/1].")
            return None
        mac_places[n] = v[0] | (0x80 if v[1] else 0)
    return {"bank": bank, "offset": offset, "frames": frames, "places": places, "home": home, "scale": float(scale),
            "mac": mac, "mac_frames": mac_frames, "mac_places": mac_places, "mac_home": nes.get("macHome", 176),
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


TYPED_SOUNDS = (None, "type", "type_alt")   # (Punch-Out!!'s: Doc's letters, the rival's)


def _typed(typed, where, errors):
    """Text that writes itself a letter at a time, as Punch-Out!!'s corner: groups of variants (pick "round": a
    group per round, the corner after round 1 the first; "random": the one group), one of a group's at random.
    A variant is steps: its box (x, y, w, h) cleared if asked, its lines typed in from its corner (leading spaces
    skipped), each letter with its sound, then a pause in frames. The prompt shows once it's all written."""
    if typed is None:
        return None
    bad = lambda msg: errors.append(f"{where}: typed text: {msg}")
    if not isinstance(typed, dict):
        bad("the settings are damaged."); return None
    every, pick, groups = typed.get("every", 4), typed.get("pick", "random"), typed.get("groups")
    if not (isinstance(every, int) and 1 <= every <= 30):
        bad("every is 1-30 frames a letter."); return None
    if pick not in ("random", "round"):
        bad('pick is "random" or "round".'); return None
    if not (isinstance(groups, list) and 1 <= len(groups) <= 8 and all(isinstance(g, list) and 1 <= len(g) <= 16 for g in groups)):
        bad("it needs 1-8 groups of 1-16 variants."); return None
    out = []
    for group in groups:
        variants = []
        for variant in group:
            if not (isinstance(variant, list) and 1 <= len(variant) <= 8):
                bad("a variant is 1-8 steps."); return None
            steps = []
            for st in variant:
                st = st if isinstance(st, dict) else {}
                x, y, w, h = (st.get(k) for k in ("x", "y", "w", "h"))
                lines = st.get("lines") or []
                if not all(isinstance(v, int) for v in (x, y, w, h)) or not (0 <= x and 0 <= y and w >= 1 and h >= 1
                                                                            and x + w <= CW and y + h <= CH):
                    bad("a step's box is off screen."); return None
                lines = [str(l).upper() for l in lines]
                if len(lines) > h or any(len(l) > w for l in lines):
                    bad(f"{lines} doesn't fit its {w}x{h} box."); return None
                if any(c not in FONT for l in lines for c in l):
                    bad(f"{lines} uses characters the font doesn't have."); return None
                slot, sound, pause = st.get("textSlot", 0), st.get("sound"), st.get("pause", 0)
                if slot not in (0, 1, 2, 3) or sound not in TYPED_SOUNDS or not (isinstance(pause, int) and 0 <= pause <= 255):
                    bad("a step's textSlot is 1-4, its sound type or type_alt, its pause 0-255 frames."); return None
                steps.append({"x": x, "y": y, "w": w, "h": h, "lines": lines, "text_slot": slot, "sound": sound,
                              "pause": pause, "clear": bool(st.get("clear", False))})
            variants.append(steps)
        out.append(variants)
    return {"every": every, "pick": pick, "groups": out}


def _compose_typed(scene, composed, tile_of):
    """Typed text's scripts: per group, per variant, its ops: ("clear", [(cell, tile)]) a row back to the scene's,
    ("sound", name), ("letter", cell, tile), ("space",), ("pause", frames). The prompt starts hidden."""
    ty = scene["typed"]
    scripts = []
    for group in ty["groups"]:
        per = []
        for variant in group:
            ops = []
            for st in variant:
                if st["clear"]:
                    for r in range(st["h"]):
                        cells = [(st["y"] + r) * CW + st["x"] + k for k in range(st["w"])]
                        ops.append(("clear", [(c, scene["cell_tiles"][c]) for c in cells]))
                ops.append(("sound", st["sound"]))
                for n, line in enumerate(st["lines"]):
                    lead = len(line) - len(line.lstrip(" "))
                    for k, ch in enumerate(line):
                        if k < lead:
                            continue
                        if ch == " ":
                            ops.append(("space",))
                            continue
                        c = (st["y"] + n) * CW + st["x"] + k
                        img = list(composed)
                        for x, y in text_ink(ch, st["x"] + k, st["y"] + n):
                            img[y * W + x] = st["text_slot"]
                        ops.append(("letter", c, tile_of(cell_key(img, c))))
                if st["pause"]:
                    ops.append(("pause", st["pause"]))
            per.append(ops)
        scripts.append(per)
    scene["typed_scripts"] = scripts
    for c, _, hidden in scene["prompt_cells"]:
        scene["cell_tiles"][c] = hidden


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


def _compose_cutscene(scene):
    """A cutscene's tiles: its picture's (32 cells across), its box (each cell blank as the sky behind it, its
    background, its letters), its actors' sprite tiles (each frame's, shared) and per frame their sprites."""
    cs = scene["cutscene"]
    tiles, index = [], {}
    def tile_of(key):
        if key not in index:
            index[key] = len(tiles)
            tiles.append(key)
        return index[key]
    px = cs["pixels"]
    cell_key32 = lambda c: tuple(px[((c // 32) * CELL + y) * 256 + (c % 32) * CELL + x] for y in range(CELL) for x in range(CELL))
    scene["cell_tiles"] = [tile_of(cell_key32(c)) for c in range(32 * CH)]
    scene["cell_pal"] = list(cs["cells"])
    box = cs["box"]
    scene["cut_box"], scene["cut_typed"] = [], []
    if box:
        blank = tile_of(tuple([0] * 64))
        fill = tile_of(tuple([box["bg_slot"]] * 64))
        for r in range(len(box["lines"]) + 2):
            for k in range(box["width"]):
                c = (box["y"] + r) * 32 + box["x"] + k
                scene["cell_tiles"][c] = blank          # (the box's palette: its slot 0 the sky's color)
                scene["cell_pal"][c] = box["palette"]
                scene["cut_box"].append((c, fill))
        for n, line in enumerate(box["lines"]):
            for k, ch in enumerate(line):
                if ch == " ":
                    continue
                img = [box["bg_slot"]] * (CELL * CELL * CW * 2)
                key = [box["bg_slot"]] * 64
                for x, y in text_ink(ch, 0, 0):
                    key[y * CELL + x] = box["text_slot"]
                c = (box["y"] + 1 + n) * 32 + box["x"] + 1 + k
                scene["cut_typed"].append((c, tile_of(tuple(key))))
    obj, oindex, frames = [], {}, []
    for a in cs["actors"]:
        per = []
        for f in a["frames"]:
            sprites = []
            for ty in range(a["h"] // 8):
                for tx in range(a["w"] // 8):
                    key = tuple(f["pixels"][(ty * 8 + y) * a["w"] + tx * 8 + x] for y in range(8) for x in range(8))
                    if not any(key):
                        continue
                    if key not in oindex:
                        oindex[key] = len(obj)
                        obj.append(key)
                    sprites.append((ty * 8, tx * 8, oindex[key], f["cells"][ty * (a["w"] // 8) + tx]))
            per.append(sprites)
        frames.append(per)
    scene["cut_obj"], scene["cut_frames"] = obj, frames
    scene["tiles"] = tiles
    scene["composed"] = list(scene["pixels"])
    for key in ("prompt_cells", "area_cells", "option_strips", "item_cells"):
        scene[key] = []
    return scene


def compose(scene):
    """Bake menu text into the scene and build its tile set (with blink variants).

    Adds: composed (pixels with text), tiles (unique 64-slot tuples), cell_tiles (tile per cell),
    item_cells (per item: [(cell, shown tile, hidden tile)])."""
    if scene.get("cutscene"):
        return _compose_cutscene(scene)
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
        for k, row in enumerate(pr["label"].split("\n")):
            for x, y in text_ink(row, pr["x"], pr["y"] + k):
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
        cells = [(pr["y"] + k) * CW + pr["x"] + i for k, row in enumerate(pr["label"].split("\n")) for i in range(len(row))]
        scene["prompt_cells"] = [(c, scene["cell_tiles"][c], tile_of(cell_key(scene["pixels"], c))) for c in cells]
    if scene.get("typed"):
        _compose_typed(scene, composed, tile_of)
    if press and press.get("card"):
        _compose_card(scene, tile_of)
    if press and press["area"]:
        a = press["area"]
        for row in range(a["y"], a["y"] + a["h"]):
            cells = [row * CW + x for x in range(a["x"], a["x"] + a["w"])]
            scene["area_cells"].append([(c, scene["cell_tiles"][c], tile_of(cell_key(press["pressed"], c))) for c in cells])
    if ft:
        _fight_compose_tiles(scene, tile_of)
    if menu and menu.get("pass_key"):     # its key's tiles: the label, a dash or digit per place (3-3-4), and
        pk = menu["pass_key"]               # what's there without it
        def drawn(text, cx, cy):
            img = list(scene["pixels"])
            for x, y in text_ink(text, cx, cy):
                img[y * W + x] = pk["text_slot"]
            return img
        lx = (CW - len(pk["label"])) // 2
        label_cells = [pk["label_y"] * CW + lx + k for k in range(len(pk["label"]))]
        kx = (CW - 12) // 2
        places = [kx + k for k in (0, 1, 2, 4, 5, 6, 8, 9, 10, 11)]
        row = [pk["y"] * CW + kx + k for k in range(12)]
        shown = drawn(pk["label"], lx, pk["label_y"])
        dashes = drawn("--- --- ----", kx, pk["y"])
        rows = [pk["label_y"] * CW + x for x in range(CW)] + [pk["y"] * CW + x for x in range(CW)]   # (whole rows: the
                                                                                                    # credit goes)
        pk["show"] = [(c, tile_of(cell_key(shown if c // CW == pk["label_y"] else dashes, c))) for c in rows]
        pk["hide"] = [(c, scene["cell_tiles"][c]) for c in rows]
        pk["cells"] = [pk["y"] * CW + x for x in places]
        pk["digits"] = [[tile_of(cell_key(drawn("0123456789-"[v], x, pk["y"]), pk["y"] * CW + x)) for v in range(11)]
                        for x in places]
    scene["item_cells"] = []
    if menu:
        for n, item in enumerate(menu["items"]):
            row = menu["y"] + n * menu["spacing"]
            cells = [row * CW + menu["x"] + i for i in range(len(item["label"]))]
            scene["item_cells"].append([(c, scene["cell_tiles"][c], tile_of(cell_key(scene["pixels"], c))) for c in cells])
    scene["tiles"] = tiles
    if ft:
        _fight_swap(scene)
        if scene["fight"].get("cgb_poses"):
            _fight_cgb(scene)
    return scene


def _rival_pixels(scene, pose, which="poses"):
    """The rival's area painted with one pose: (pixel index, slot) and (cell, palette) pairs."""
    from . import fight as kit
    ft = scene["fight"]
    p = ft[which][pose]
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
    sprites = {pose: sprite_list(ft["player"]["poses"][pose], kit.PLAYER_W, kit.PLAYER_H, pal)
               for pose in kit.PLAYER_POSES if pose not in kit.PLAYER_RARE}
    # Tiles loaded as they're needed (two areas past the rest, sized to what they hold): the player's rare poses
    # (one at a time) and the referee's (two areas: the next pose loads into the one not shown). A tile already
    # kept for good, or (the referee's) used by more than one of his poses, is kept for good instead.
    def slot_list(px, w, h, attr_of, map_of, shared, area):
        out, slot = [], {}
        for by in range(h // 8):
            for bx in range(w // 8):
                key = tuple(px[(by * 8 + y) * w + bx * 8 + x] for y in range(8) for x in range(8))
                if not any(key):
                    continue
                attr, key = attr_of(key), map_of(key)
                flipped = tuple(key[y * 8 + 7 - x] for y in range(8) for x in range(8))
                if key in index or flipped in index or key in shared:
                    t, flip = obj_tile(key)
                    out.append((by * 8, bx * 8, kit.OBJ_FIRST_TILE + t, attr | flip))
                else:
                    k = slot.setdefault(key, len(slot))
                    out.append((by * 8, bx * 8, (area, k), attr))
        return out, list(slot)
    rare = {pose: slot_list(ft["player"]["poses"][pose], kit.PLAYER_W, kit.PLAYER_H, lambda k: pal, lambda k: k, (), "pl")
            for pose in kit.PLAYER_RARE}
    ref_attr = ft["referee"]["palette"] | 0x10          # Color: its palette; original: OBP1
    shirt = ft["referee"].get("shirt_palette")
    in_shirt = lambda key: shirt is not None and key.count(4) > key.count(2)     # (the palette its colors need
    ref_ink = lambda key: tuple((2 if in_shirt(key) else 1) if v == 4 else (1 if in_shirt(key) and v == 2 else v)
                                for v in key)   # most: in the cap's, a speck of white is skin; in the shirt's, red)
    def ref_tiles(px):
        return [ref_ink(k) for k in (tuple(px[(by * 8 + y) * kit.REF_W + bx * 8 + x] for y in range(8) for x in range(8))
                for by in range(kit.REF_H // 8) for bx in range(kit.REF_W // 8)) if any(k)]
    seen_in = {}
    for pose in kit.REF_POSES:
        for k in set(ref_tiles(ft["referee"]["poses"][pose])):
            seen_in[k] = seen_in.get(k, 0) + 1
    shared = {k for k, n in seen_in.items() if n > 1}
    refs = {pose: slot_list(ft["referee"]["poses"][pose], kit.REF_W, kit.REF_H,
                            lambda k: shirt | 0x10 if in_shirt(k) else ref_attr, ref_ink, shared, "ref")
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
    if ft.get("nes"):                                   # Punch-Out!!'s star just earned, twinkling by the HUD's
        obj.append(tuple(int(ch) if ch != "." else 0 for row in kit.TWINKLE_TILE for ch in row))
        scene["fight_twinkle_tile"] = kit.OBJ_FIRST_TILE + len(obj) - 1
    # the loaded areas, at the top of the sprite tiles: the referee's two, the player's rare poses' below them
    ref_n = max([len(t) for _, t in refs.values()] + [0])
    pl_n = max([len(t) for _, t in rare.values()] + [0])
    ref_at = kit.OBJ_TILE_LIMIT - 2 * ref_n
    pl_at = ref_at - pl_n
    base = {"ref": ref_at, "pl": pl_at}
    fix = lambda sp: [(dy, dx, base[t[0]] + t[1] if isinstance(t, tuple) else t, a) for dy, dx, t, a in sp]
    for pose, (sp, _) in rare.items():
        sprites[pose] = fix(sp)
    scene["fight_sprites"] = {pose: sprites[pose] for pose in kit.PLAYER_POSES}
    scene["fight_ref_sprites"] = {pose: fix(refs[pose][0]) for pose in kit.REF_POSES}
    scene["fight_ref_tiles"] = {pose: refs[pose][1] for pose in kit.REF_POSES}
    scene["fight_rare_tiles"] = {pose: rare[pose][1] for pose in kit.PLAYER_RARE}
    pc = ft["player"].get("cgb_poses")
    if pc:                                      # Color: the player's own poses, unshared, all in its second bank's
        ctiles, cindex = [], {}                 # sprite-only tiles ($8000: Color's bank 1, attribute bit 3)
        def cgb_tile(key):
            flipped = tuple(key[y * 8 + 7 - x] for y in range(8) for x in range(8))
            if key in cindex:
                return cindex[key], 0
            if flipped in cindex:
                return cindex[flipped], 0x20
            cindex[key] = len(ctiles)
            ctiles.append(key)
            return cindex[key], 0
        csprites = {}
        for pose in kit.PLAYER_POSES:
            out = []
            for by in range(kit.PLAYER_H // 8):
                for bx in range(kit.PLAYER_W // 8):
                    key = tuple(pc[pose][(by * 8 + y) * kit.PLAYER_W + bx * 8 + x] for y in range(8) for x in range(8))
                    if any(key):
                        t, flip = cgb_tile(key)
                        out.append((by * 8, bx * 8, t, pal | flip | 0x08))
            csprites[pose] = out
        side = ft.get("side_rope")              # (and the side ropes' ends: their two tiles with his)
        if side:
            scene["fight_side_tile"] = len(ctiles)
            for half in (0, 1):
                ctiles.append(tuple(side[(half * 8 + y) * 8 + x] for y in range(8) for x in range(8)))
        if len(ctiles) > 128:
            raise ProjectError([f'Scene "{scene["name"]}": the player\'s Game Boy Color poses need {len(ctiles)} tiles; '
                                'the limit is 128. Share more of their tiles.'])
        scene["fight_pl_cgb"] = {"tiles": ctiles, "sprites": csprites}
    scene["fight_slots"] = {"ref": ref_at, "ref_tiles": ref_n, "pl": pl_at, "pl_tiles": pl_n,
                            "used": kit.OBJ_FIRST_TILE + len(obj) + pl_n + 2 * ref_n}
    # a camera flash in the crowd: a white burst (slot 1) on the darkest slot
    burst = ["...#....", ".#.#.#..", "..###...", "#######.", "..###...", ".#.#.#..", "...#....", "........"]
    scene["fight_flash_tile"] = tile_of(tuple(0 if ch == "#" else 3 for row in burst for ch in row))
    rope = ft.get("rope_row")
    if rope:                                    # the rope row's tiles, always in video memory (its own map row)
        scene["fight_rope_tiles"] = [tile_of(tuple(rope["pixels"][y * W + c * CELL + x] for y in range(CELL) for x in range(CELL)))
                                     for c in range(CW)]


def _head_keys(keys, pose, blank):
    """A pose's tiles in its top rows (kit.head_rows: the ones that can show over the ropes, as sprites), but the
    mat's."""
    from . import fight as kit
    return [k for k in keys[pose][:kit.head_rows(pose) * kit.REGION_W] if k != blank]


def _fight_swap(scene):
    """Lay out video memory: tiles every frame may need first, then one shared area that holds one pose set at
    a time (attack, knockdown or special). The ROM swaps sets into that area as the fight needs them. With a rope
    row, his top rows' tiles go where sprites can reach them too (slots 128-255): each set's at the end of its part
    of the area, the always-there poses' just past it."""
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
    rope = scene["fight"].get("rope_row")
    region = {(scene["fight"]["y"] + r) * CW + scene["fight"]["x"] + c for r in range(kit.REGION_H) for c in range(kit.REGION_W)}
    blank = tiles[scene["cell_tiles"][min(region)]] if rope else None   # (his area's background: the mat)
    scene_keys = [tiles[t] for t in scene["cell_tiles"]] + [tiles[t] for t in scene["fight_lut"]] + [tiles[scene["fight_flash_tile"]]]
    scene_keys += [tiles[t] for t in scene.get("fight_rope_tiles", [])]
    always = list(scene_keys)
    for pose, k in keys.items():
        if pose not in in_set:
            always += k
    high = []                                           # the always-there poses' top rows (sprites reach them)
    if rope:                                            # (the screen's own tiles: his area's aside, his pose's)
        sk = {tiles[t] for c, t in enumerate(scene["cell_tiles"]) if c not in region}
        sk |= {tiles[t] for t in scene["fight_lut"]} | {tiles[scene["fight_flash_tile"]]}
        sk |= {tiles[t] for t in scene.get("fight_rope_tiles", [])}
        for pose in keys:
            if pose not in in_set:
                high += [k for k in _head_keys(keys, pose, blank) if k not in sk and k not in high]
    base, base_index = [], {}
    for key in always:
        if key not in base_index and key not in high:
            base_index[key] = len(base)
            base.append(key)
    first = len(base)
    sets, heads = {}, {}
    for name, poses in kit.POSE_SETS.items():
        own = []
        for pose in poses:
            for key in keys[pose]:
                if key not in base_index and key not in high and key not in own:
                    own.append(key)
        hk = []
        if rope:
            for pose in poses:
                hk += [k for k in _head_keys(keys, pose, blank) if k in own and k not in hk]
        rest = [k for k in own if k not in hk]
        reach = max(0, 128 - first)                     # (positions past it are at slot 128 on)
        own = rest[:reach] + [tuple([0] * 64)] * max(0, reach - len(rest)) + hk + rest[reach:] if hk else own
        sets[name] = own
        heads[name] = hk
    size = max(len(own) for own in sets.values())
    if rope and first + size + len(high) > 256:
        raise ProjectError([f'Scene "{scene["name"]}" uses {first + size + len(high)} different 8x8 tiles (his top rows '
                            "where sprites can reach them); the limit is 256. Share more of his tiles."])
    high_index = {key: first + size + n for n, key in enumerate(high)}
    for name, poses in kit.POSE_SETS.items():
        slot = {}
        for n, key in enumerate(sets[name]):
            slot.setdefault(key, first + n)
        for pose in poses:
            maps[pose] = [base_index.get(key, high_index.get(key, slot.get(key))) for key in keys[pose]]
    for pose in maps:
        if pose not in in_set:
            maps[pose] = [base_index.get(key, high_index.get(key)) for key in keys[pose]]
    empty = tuple([0] * 64)
    padded = {name: own + [empty] * (size - len(own)) for name, own in sets.items()}
    scene["tiles"] = base + padded["attack"] + high       # the attack set is loaded with the scene
    scene["cell_tiles"] = [base_index.get(tiles[t], high_index.get(tiles[t])) for t in scene["cell_tiles"]]
    scene["fight_lut"] = [base_index[tiles[t]] for t in scene["fight_lut"]]
    scene["fight_flash_tile"] = base_index[tiles[scene["fight_flash_tile"]]]
    if rope:
        scene["fight_rope_tiles"] = [base_index[tiles[t]] for t in scene["fight_rope_tiles"]]
        scene["fight_blank"] = base_index[blank]
    scene["fight_swap"] = {"first": first, "count": size, "sets": [padded[n] for n in ("attack", "knockdown", "special")],
                           "sizes": {n: len(own) for n, own in sets.items()}}


def _fight_cgb(scene):
    """Game Boy Color: the rival's finer poses (cgb_poses) in tiles of their own. Bank 0 keeps the scene's (the
    original's layout, so the screen as loaded is the same); his always-there tiles take its slots past them
    (the original's swap area: Color swaps in bank 1), then bank 1's past his swap area there."""
    from . import fight as kit
    sw = scene["fight_swap"]
    in_set = {p for poses in kit.POSE_SETS.values() for p in poses}
    keys, attrs = {}, {}
    for pose in kit.RIVAL_POSES:
        img = list(scene["composed"])
        px, cells = _rival_pixels(scene, pose, "cgb_poses")
        for i, v in px:
            img[i] = v
        keys[pose] = [cell_key(img, c) for c, _ in cells]
        attrs[pose] = [pal for _, pal in cells]
    perm = []
    for pose in kit.RIVAL_POSES:
        if pose not in in_set:
            for k in keys[pose]:
                if k not in perm:
                    perm.append(k)
    sets = {}
    for name, poses in kit.POSE_SETS.items():
        own = []
        for pose in poses:
            for k in keys[pose]:
                if k not in perm and k not in own:
                    own.append(k)
        sets[name] = own
    size = max(len(own) for own in sets.values())
    ft = scene["fight"]                 # bank 0's slots the screen itself needs: the cells outside his area (and
    region = {(ft["y"] + r) * CW + ft["x"] + c for r in range(kit.REGION_H) for c in range(kit.REGION_W)}
    keep = {0} | {t for c, t in enumerate(scene["cell_tiles"]) if c not in region}   # tile 0, the rows' padding),
    keep |= set(scene["fight_lut"]) | {scene["fight_flash_tile"]} | set(scene.get("fight_rope_tiles", []))   # the
    free0 = [t for t in range(256) if t not in keep]  # HUD's, the camera flash's, the rope row's; the rest his: the
    rope = ft.get("rope_row")                          # original's poses go (Color draws its own)
    blank = cell_key(scene["composed"], min(region)) if rope else None
    head = set()                        # (with a rope row: his top rows' tiles, where sprites reach: slots 128-255)
    if rope:
        for pose in kit.RIVAL_POSES:
            head |= set(_head_keys(keys, pose, blank))
    if rope:                            # his always-there ones: their top rows' in bank 0's upper half, then the rest
        hp = [k for k in perm if k in head]
        lp = [k for k in perm if k not in head]
        up0, low0 = [t for t in free0 if t >= 128], [t for t in free0 if t < 128]
        n1 = max(0, len(hp) - len(up0)) + max(0, len(lp) - len(low0) - max(0, len(up0) - len(hp)))
        perm0, slots0 = [], []          # (bank 1's top takes what bank 0 can't: always reachable)
        for k, t in zip(hp, up0):
            perm0.append(k); slots0.append(t)
        rest0 = low0 + up0[len(hp):]
        for k, t in zip(lp, rest0):
            perm0.append(k); slots0.append(t)
        perm1 = [k for k in perm if k not in perm0]
        used0 = set(slots0)
        left0 = [t for t in free0 if t not in used0]
    else:
        perm0, perm1 = perm[:len(free0)], perm[len(free0):]
        slots0 = free0[:len(perm0)]
        left0 = free0[len(perm0):]      # the swap area: bank 1 (past any always-there overflow at its end), then
    blocks = []                         # bank 0's two longest runs of slots still free (split where 128 moves)
    for t in left0:
        if blocks and blocks[-1][-1] == t - 1 and t != 128:
            blocks[-1].append(t)
        else:
            blocks.append([t])
    blocks = sorted(blocks, key=len, reverse=True)[:2]
    set_slots = [(t, 1) for t in range(256 - len(perm1))] + [(t, 0) for blk in blocks for t in blk]
    if rope:                            # (the slots sprites reach first: a set's top rows' tiles at its start, so a
        set_slots = ([st for st in set_slots if st[0] >= 128 and st[1] == 1]      # small set copies short)
                     + [st for st in set_slots if st[0] < 128 and st[1] == 1] + [st for st in set_slots if st[1] == 0])
    if size > len(set_slots):
        raise ProjectError([f'Scene "{scene["name"]}": the rival\'s Game Boy Color poses need {len(perm) + size} tiles '
                            f"of their own; there's room for {len(perm) + len(set_slots)}. Share more of their tiles."])
    if rope:                            # each set: its top rows' tiles in the area's slots sprites reach, the rest
        for name in sets:               # in the others (its copy as short as that allows)
            own = sets[name]
            hk, rk = [k for k in own if k in head], [k for k in own if k not in head]
            reach = [n for n, (t, _) in enumerate(set_slots) if t >= 128]
            other = [n for n, (t, _) in enumerate(set_slots) if t < 128]
            if len(hk) > len(reach):
                raise ProjectError([f'Scene "{scene["name"]}": the rival\'s Game Boy Color top rows need {len(hk)} tiles '
                                    f"sprites can reach; there's room for {len(reach)}. Share more of their tiles."])
            at = dict(zip(reach, hk))
            spare = other + reach[len(hk):]
            spare.sort()
            at.update(zip(spare, rk))
            length = max(at) + 1 if at else 0
            sets[name] = [at.get(n, tuple([0] * 64)) for n in range(length)]
        size = max(len(own) for own in sets.values())
    set_slots = set_slots[:size]
    runs = []                           # the swap area's runs: (first slot, count, bank)
    for t, b in set_slots:
        if runs and runs[-1][2] == b and runs[-1][0] + runs[-1][1] == t and t != 128:
            runs[-1][1] += 1
        else:
            runs.append([t, 1, b])
    slot = {k: (slots0[n], 0) for n, k in enumerate(perm0)}
    slot.update({k: (256 - len(perm1) + n, 1) for n, k in enumerate(perm1)})
    maps, battrs = {}, {}
    set_of = {pose: name for name, poses in kit.POSE_SETS.items() for pose in poses}
    for pose in kit.RIVAL_POSES:
        own = {}
        if pose in set_of:
            for n, k in enumerate(sets[set_of[pose]]):
                own.setdefault(k, set_slots[n])
        at = [slot.get(k) or own[k] for k in keys[pose]]
        maps[pose] = [t for t, _ in at]
        battrs[pose] = [b for _, b in at]
    empty = tuple([0] * 64)
    scene["fight_cgb"] = {"maps": maps, "attrs": attrs, "banks": battrs, "size": size,
                          "sets": [sets[n] for n in ("attack", "knockdown", "special")],   # (each copies only its own)
                          "perm0": perm0, "perm0_slots": slots0, "perm1": perm1, "perm1_first": 256 - len(perm1),
                          "runs": [tuple(r) for r in runs],
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
