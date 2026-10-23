"""A rival's picture from the NES frame by one continuous shrink centered on his head: his head 1:1 (the face a
0.7 shrink can't keep), easing down to 0.75 for the rest of him, across and down each on its own (straight lines
stay straight: his sides don't taper) -- no seam, no cut, in any pose (it follows his head). The same numbers for every frame of his. Each of our pixels takes the NES color
most of its area covers (ink and eyes' whites weighed up so lines and eyes survive); his place on screen is where
the 0.7 picture had it.

  python warp.py RIVAL FRAMES OUT.png   -> NES | as approved | warped, as Color shows them"""
import math, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, fidelity, headswap, touchup

LEGENDS = {                                               # (each fighter's NES colors, a letter each)
    "joe": dict(headswap.LEGEND),
    "honda": {"K": (0, 0, 0), "S": (212, 136, 32), "R": (152, 34, 32), "G": (152, 150, 152), "W": (236, 238, 236)},
    "kaiser": {"K": (60, 24, 0), "S": (236, 180, 176), "B": (0, 0, 0), "R": (152, 34, 32), "W": (236, 238, 236)},
    "don": {"K": (0, 0, 0), "S": (236, 106, 100), "W": (236, 238, 236), "U": (120, 124, 236), "G": (56, 204, 108)},
    "hippo": {"K": (0, 0, 0), "S": (212, 136, 32), "M": (228, 84, 236), "R": (152, 34, 32), "W": (236, 238, 236)},
    "bull": {"K": (0, 0, 0), "S": (212, 136, 32), "C": (160, 214, 228), "R": (152, 34, 32), "W": (236, 238, 236)},
    "tiger": {"K": (0, 0, 0), "S": (120, 60, 0), "N": (0, 30, 116), "R": (236, 106, 100), "W": (236, 238, 236)},
    "tyson": {"K": (0, 0, 0), "S": (120, 60, 0), "R": (152, 34, 32), "G": (0, 64, 0), "W": (236, 238, 236)},
    "soda": {"K": (84, 4, 0), "S": (236, 174, 236), "B": (120, 60, 0), "R": (152, 34, 32), "W": (188, 188, 236)},
    "sandman": {"K": (0, 0, 0), "S": (120, 60, 0), "G": (152, 150, 152), "O": (212, 136, 32), "W": (236, 238, 236)},
    "macho": {"K": (0, 0, 0), "S": (236, 180, 176), "R": (152, 34, 32), "U": (120, 124, 236), "W": (236, 238, 236)},
}
GLOVE = {"don": "U", "hippo": "M", "sandman": "O"}
AS = {"don": {"G": "U"}}                                  # (a capture's flash color: his own instead)                                      # (his gloves' color, where it isn't red)
LEG, GL = LEGENDS["joe"], "R"                             # (the fighter being drawn's: use())


def use(rival):
    global LEG, GL, AS_NOW
    LEG, GL, AS_NOW = LEGENDS[rival], GLOVE.get(rival, "R"), AS.get(rival, {})


def char(c):
    k = min(LEG, key=lambda k: sum((a - b) ** 2 for a, b in zip(c[:3], LEG[k])))
    return AS_NOW.get(k, k)


AS_NOW = {}


SCALE = {"joe": ((12, 1.0), (28, 0.75)), "honda": ((12, 1.0), (28, 0.75)), "kaiser": ((12, 1.0), (28, 0.75)),
         "don": ((12, 1.0), (28, 0.75)), "hippo": ((12, 1.0), (28, 0.75)),
         "bull": ((12, 1.0), (28, 0.75)), "tiger": ((12, 1.0), (28, 0.75)),
         "tyson": ((12, 1.0), (28, 0.75)), "soda": ((12, 1.0), (28, 0.75)),
         "sandman": ((12, 1.0), (28, 0.75)), "macho": ((12, 1.0), (28, 0.75))}               # (then 0.75 on out: straight lines stay straight)   # (distance from his head's middle in NES pixels, scale there)
WEIGHT = {"K": 2.2, "W": 3.0, ".": 1.0}
SUB = 5                                                   # (each of our pixels: SUB x SUB points)


def scale_at(pts, r):
    if r <= pts[0][0]:
        return pts[0][1]
    for (r0, s0), (r1, s1) in zip(pts, pts[1:]):
        if r <= r1:
            return s0 + (s1 - s0) * (r - r0) / (r1 - r0)
    return pts[-1][1]


def radial(pts):
    """g(r): how far from the middle a point r NES pixels out lands (the scale summed along the way), and back."""
    pts = SCALE[pts] if isinstance(pts, str) else pts
    step, table = 0.25, [(0.0, 0.0)]
    r = g = 0.0
    while r < 200:
        g += scale_at(pts, r + step / 2) * step
        r += step
        table.append((r, g))
    def fwd(x):
        i = min(int(x / step), len(table) - 2)
        (r0, g0), (r1, g1) = table[i], table[i + 1]
        return g0 + (g1 - g0) * (x - r0) / step
    def back(y):
        lo, hi = 0, len(table) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if table[m][1] <= y:
                lo = m
            else:
                hi = m
        (r0, g0), (r1, g1) = table[lo], table[hi]
        return r0 + (r1 - r0) * ((y - g0) / (g1 - g0) if g1 > g0 else 0)
    return fwd, back


def head_middle(nes):
    """His head's middle: his hair's, a little down to his face (his eyes' when they show); a fighter whose hair is
    his outline's black: the top of him (his gloves aside), down to his eyes."""
    hair = [(x, y) for (x, y), c in nes.items() if c == "H"]
    if not hair:
        body = [(x, y) for (x, y), c in nes.items() if c != GL and not any(
            nes.get((x + i, y + j)) == GL for i in (-1, 0, 1) for j in (-1, 0, 1))]
        top = min(y for _, y in body)
        tx = sorted(x for x, y in body if y <= top + 2)
        tx = tx[len(tx) // 2]
        hair = [(x, y) for x, y in body if y <= top + 12 and abs(x - tx) <= 12]
    eyes = [(x, y) for (x, y), c in nes.items() if c == "W" and not any(nes.get((x + i, y + j)) == GL
                                                                         for i in (-1, 0, 1) for j in (-1, 0, 1))]
    hx = sum(x for x, _ in hair) / len(hair)
    hy = sum(y for _, y in hair) / len(hair)
    if eyes:
        ey = min(y for _, y in eyes)
        top = min(y for _, y in hair)
        return hx, (top + ey + 6) / 2 + 2
    return hx, hy


HEAD_FROM = {"joe": {"3A": ("C4", 3)}}                    # (and rows down from eye to eye: his neck's foot on his)
FIXES = {"joe": {                                         # (pixels by hand, after all that: row, column, color)
    "C6!macho": [(48, 32, 'S'), (48, 33, 'S'), (48, 34, 'S'), (48, 35, 'S'), (48, 36, 'S'), (48, 37, 'S'), (48, 38, 'S'), (48, 39, 'S'), (48, 40, 'S'), (48, 41, 'S'), (48, 42, 'S'), (48, 43, 'S'), (48, 44, 'S'), (48, 45, 'K'), (48, 46, '.'), (49, 32, 'S'), (49, 33, 'S'), (49, 34, 'S'), (49, 35, 'S'), (49, 36, 'S'), (49, 37, 'S'), (49, 38, 'S'), (49, 39, 'S'), (49, 40, 'S'), (49, 41, 'S'), (49, 42, 'S'), (49, 43, 'S'), (49, 44, 'S'), (49, 45, 'K'), (49, 46, '.'), (50, 32, 'S'), (50, 33, 'S'), (50, 34, 'S'), (50, 35, 'S'), (50, 36, 'S'), (50, 37, 'S'), (50, 38, 'S'), (50, 39, 'S'), (50, 40, 'S'), (50, 41, 'S'), (50, 42, 'S'), (50, 43, 'S'), (50, 44, 'S'), (50, 45, 'K'), (50, 46, '.'), (51, 32, 'S'), (51, 33, 'S'), (51, 34, 'S'), (51, 35, 'S'), (51, 36, 'S'), (51, 37, 'S'), (51, 38, 'S'), (51, 39, 'S'), (51, 40, 'S'), (51, 41, 'S'), (51, 42, 'S'), (51, 43, 'S'), (51, 44, 'S'), (51, 45, 'K'), (51, 46, '.'), (52, 32, 'S'), (52, 33, 'S'), (52, 34, 'S'), (52, 35, 'S'), (52, 36, 'S'), (52, 37, 'S'), (52, 38, 'S'), (52, 39, 'S'), (52, 40, 'S'), (52, 41, 'S'), (52, 42, 'S'), (52, 43, 'S'), (52, 44, 'S'), (52, 45, 'K'), (52, 46, '.'), (53, 32, 'S'), (53, 33, 'S'), (53, 34, 'S'), (53, 35, 'S'), (53, 36, 'S'), (53, 37, 'S'), (53, 38, 'S'), (53, 39, 'S'), (53, 40, 'S'), (53, 41, 'S'), (53, 42, 'S'), (53, 43, 'S'), (53, 44, 'K'), (53, 45, '.'), (53, 46, '.'), (54, 32, 'S'), (54, 33, 'S'), (54, 34, 'S'), (54, 35, 'S'), (54, 36, 'S'), (54, 37, 'S'), (54, 38, 'S'), (54, 39, 'S'), (54, 40, 'S'), (54, 41, 'S'), (54, 42, 'S'), (54, 43, 'S'), (54, 44, 'K'), (54, 45, '.'), (54, 46, '.'), (55, 32, 'S'), (55, 33, 'S'), (55, 34, 'S'), (55, 35, 'S'), (55, 36, 'S'), (55, 37, 'S'), (55, 38, 'S'), (55, 39, 'S'), (55, 40, 'S'), (55, 41, 'S'), (55, 42, 'S'), (55, 43, 'S'), (55, 44, 'K'), (55, 45, '.'), (55, 46, '.'), (56, 32, 'S'), (56, 33, 'S'), (56, 34, 'S'), (56, 35, 'S'), (56, 36, 'S'), (56, 37, 'S'), (56, 38, 'S'), (56, 39, 'S'), (56, 40, 'S'), (56, 41, 'S'), (56, 42, 'S'), (56, 43, 'S'), (56, 44, 'K'), (56, 45, '.'), (56, 46, '.'), (57, 32, 'S'), (57, 33, 'S'), (57, 34, 'S'), (57, 35, 'S'), (57, 36, 'S'), (57, 37, 'S'), (57, 38, 'S'), (57, 39, 'S'), (57, 40, 'S'), (57, 41, 'S'), (57, 42, 'S'), (57, 43, 'S'), (57, 44, 'K'), (57, 45, '.'), (57, 46, '.'), (47, 44, 'K'), (47, 45, '.'), (47, 46, '.'), (47, 47, '.'), (48, 47, '.'), (49, 47, '.'), (50, 47, '.'), (51, 47, '.'), (52, 47, '.'), (53, 47, '.'), (54, 47, '.'), (55, 47, '.'), (56, 47, '.')],   # (Super Macho Man's windup: the game's own frame has a block of wrong tiles in his side)
    "34": [("checker", 59, 66, 9, 15), ("checker", 60, 69, 33, 43), (39, 60, "R"), (40, 61, "R"), (41, 61, "R"), (39, 61, "K"), (40, 62, "K"), (41, 62, "K"), (42, 61, "K")],
                                                          # (his glove's end the NES's capture cut off, rounded)
    "34|": [(39, 3, "R"), (40, 2, "R"), (41, 2, "R"), (39, 2, "K"), (40, 1, "K"), (41, 1, "K"), (42, 2, "K")],
    "3A": [(31, 39, 'K'), (31, 40, 'K'), (31, 41, 'K'), (32, 39, 'S'), (32, 40, 'S'), (32, 41, 'S'), (33, 39, 'S'), (33, 40, 'S'), (33, 41, 'S'), (34, 39, 'S'), (34, 40, 'S'), (34, 41, 'S'), (35, 39, 'S'), (35, 40, 'S'), (35, 41, 'S'), (36, 40, 'S'), (36, 41, 'S'), (37, 41, 'S'), (42, 24, 'S')],   # (his shoulder under his raised arm up to the neck, not a gap; his other's corner rounded)
}}                         # (a frame whose own face is rough: another's, his best)


def nes_of(rival, key):
    every = build.joe_shapes(build.NES_RIVALS[rival]["opp"], everything=True)
    shape = every.get(build._key(key))
    if shape is None:
        other = every[build._key(key[:-1]) if key.endswith("|") else build._key(key + "|")]
        shape = {(-x, y): c for (x, y), c in other.items()}
    return {p: char(c) for p, c in shape.items()}


def head_of(nes, chin_rows=27):
    """His head in an NES frame: what's joined to his hair from its top down chin_rows rows, gloves and an arm
    beside it (past his face's width) left out; and his eyes' top-left."""
    hair = [(x, y) for (x, y), c in nes.items() if c == "H"]
    top = min(y for _, y in hair)
    eyes = [(x, y) for (x, y), c in nes.items() if c == "W" and top <= y <= top + 16
            and not any(nes.get((x + i, y + j)) == "R" for i in (-1, 0, 1) for j in (-1, 0, 1))]
    hx = [x for x, _ in hair]
    lo, hi = min(hx) - 1, max(hx) + 1
    grid = {}
    seen, st = set(hair), list(hair)
    while st:
        x, y = st.pop()
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                q = (x + i, y + j)
                c = nes.get(q, ".")
                if q not in seen and c not in ".R" and top <= q[1] <= top + chin_rows and lo <= q[0] <= hi:
                    seen.add(q); st.append(q)
    return seen, (min(x for x, _ in eyes), min(y for _, y in eyes)) if eyes else None


def borrow_head(rival, nes, other, down=0):
    """This frame with another frame's head in place of its own, laid by their eyes (and down rows more)."""
    mine, my_eyes = head_of(nes)
    theirs, their_eyes = head_of(nes_of(rival, other))
    src = nes_of(rival, other)
    dx, dy = my_eyes[0] - their_eyes[0], my_eyes[1] - their_eyes[1] + down
    placed = {(x + dx, y + dy): src[(x, y)] for (x, y) in theirs}
    foot = max(y for _, y in placed)
    out = {p: c for p, c in nes.items() if not (p in mine and p[1] <= foot)}   # (his own neck under it kept)
    out.update(placed)
    return out


PAD_Y, PAD_X = 24, 12                                     # (room round the frame while he's drawn: then fitted in)


def warp(rival, key):
    """The warped picture fitted in his frame: RH rows of RW characters (headswap's), the NES frame, and how far
    it was moved from where the 0.7 picture's place puts him (to undo on screen, as a touch-up's 'moved').
    Too tall or wide for the frame (an arm up, him down), the scale past his head eased down till he fits; then moved (up to 7 pixels) to
    where his tiles keep the most of his colors (each 8x8 three: his hair's and gloves', not skin's pink)."""
    use(rival)
    fit.rival = auto_placement.rival = rival
    pts = list(SCALE[rival])
    while True:
        rows, nes, C = draw(rival, key, pts)
        ys = [y for y, r in enumerate(rows) for c in r if c != "."]
        xs = [x for r in rows for x, c in enumerate(r) if c != "."]
        if (max(ys) - min(ys) + 1 <= build.RH and max(xs) - min(xs) + 1 <= build.RW) or pts[-1][1] < 0.65:
            break
        pts = pts[:1] + [(r, s * 0.97) for r, s in pts[1:]]
    g, nes, mv = fit(rows, nes, NUDGE.get(rival, {}).get(key, (0, 0)))
    while tiles(g) > TILE_ROOM and pts[-1][1] >= 0.6:   # (more tiles than a picture can have, the original's
        pts = pts[:1] + [(r, s * 0.97) for r, s in pts[1:]]   #  greys counted: smaller past his head, till it fits)
        rows, nes, C = draw(rival, key, pts)
        g, nes, mv = fit(rows, nes, NUDGE.get(rival, {}).get(key, (0, 0)))
    for f in FIXES.get(rival, {}).get(key, ()) or FIXES["joe"].get(f"{key}!{rival}", ()):   # (the hand's last pixels)
        if f[0] == "checker":                           # (a strict checkerboard, black and white, in a box: each
            _, y0, y1, x0, x1 = f                       #  row's outermost pixels kept as its outline)
            for y in range(y0, y1 + 1):
                xs = [x for x in range(x0, x1 + 1) if g[y][x] != "."]
                for x in xs[1:-1] if len(xs) > 2 else []:
                    g[y][x] = "K" if (x + y) % 2 else "W"
        else:
            y, x, c = f
            g[y][x] = c
    return g, nes, mv


NUDGE = {"joe": {"34": (-3, 0), "34|": (3, 0)}}          # (room in his frame for what the NES's capture cut off)


TILE_ROOM = 60                                            # (a picture's tiles: 64, the whites' sprites some of them)


def tiles(g):
    """His frame's different 8x8 tiles, unflipped (the original Game Boy's can't flip a background tile)."""
    return len({t for ty in range(build.RH // 8) for tx in range(build.RW // 8)
                for t in [tuple(g[y][x] for y in range(ty * 8, ty * 8 + 8) for x in range(tx * 8, tx * 8 + 8))]
                if any(c != "." for c in t)})


def shows(pals):
    """What each tile kind can show: the letters of his colors nearest its palette's three."""
    to8 = lambda c: tuple((v << 3) | (v >> 2) for v in c)
    return {k: {char(to8(pals[i][j])) for j in (1, 2, 3)} for i, k in enumerate(build.KINDS)}


def lost(grid, pals, weight):
    """Pixels his tiles can't show (as import_pictures picks each tile's palette), each its weight."""
    fr = [[(LEG[c] + (255,)) if c != "." else None for c in r] for r in grid]
    cells = build.import_pictures({"x": fr}, pals)["x"]["cells"]
    sh = shows(pals)
    return sum(weight(y, x) for y, r in enumerate(grid) for x, c in enumerate(r)
               if c != "." and c not in sh[cells[(y // 8) * build.FIGHT_W + x // 8]])


def fit(rows, nes, nudge=(0, 0)):
    pals = touchup.auto_pictures(fit.rival)[1]
    H, W = len(rows), len(rows[0])
    ys = [y for y in range(H) for c in rows[y] if c != "."]
    xs = [x for r in rows for x, c in enumerate(r) if c != "."]
    top, bot, left, right = min(ys), max(ys), min(xs), max(xs)
    if right - left + 1 > build.RW:                     # (still too wide at the least scale -- his arms flung out:
        cut = (right - left + 1 - build.RW + 1) // 2    #  as much off each side)
        left, right = left + cut, left + cut + build.RW - 1
        rows = [[c if left <= x <= right else "." for x, c in enumerate(r)] for r in rows]
    if bot - top + 1 > build.RH:                        # (still too tall at the least scale -- a glove high over his
        bot = top + build.RH - 1                        #  head, as the NES's own frame can't fit either: his feet off
        rows = [r if y <= bot else ["."] * W for y, r in enumerate(rows)]   # the bottom, where Mac stands over them)
    trials = {}
    for dy in range(-top, build.RH - bot):          # (row y of the drawing lands at y + dy)
        for dx in range(-left, build.RW - right):
            ph = ((top + dy) % 8, (left + dx) % 8)
            mv = abs(dx + PAD_X) + abs(dy + PAD_Y)
            if ph not in trials or mv < trials[ph][0]:
                trials[ph] = (mv, dx, dy)
    best = None
    for mv, dx, dy in sorted(trials.values()):
        g = [["."] * build.RW for _ in range(build.RH)]
        for y in range(top, bot + 1):
            for x in range(left, right + 1):
                if rows[y][x] != ".":
                    g[y + dy][x + dx] = rows[y][x]
        n = lost(g, pals, lambda y, x: 0 if g[y][x] == "W" else (3 if g[y][x] in "HG" + GL else 1))   # (hair, gloves:
                                                                                                      #  dear)
        if best is None or (n, mv) < best[0]:
            best = ((n, mv), dx, dy, g)
    (_, _), dx, dy, g = best
    fr = [[(LEG[c] + (255,)) if c != "." else None for c in r] for r in g]
    cells = build.import_pictures({"x": fr}, pals)["x"]["cells"]
    sh = shows(pals)
    for ty in range(build.RH // 8):                 # (a tile that can't hold his glove's color with the rest: the
        for tx in range(build.RW // 8):             #  glove's kept, the rest it can't hold black -- a shadow by
            px = [(y, x) for y in range(ty * 8, ty * 8 + 8) for x in range(tx * 8, tx * 8 + 8) if g[y][x] != "."]
            can = sh[cells[ty * build.FIGHT_W + tx]]               #  it, not a block of skin in his glove)
            if any(g[y][x] == GL and GL not in can for y, x in px):
                for y, x in px:
                    if g[y][x] not in (GL, "K", "S", "."):
                        g[y][x] = "K"
            else:                                   # (any other color it can't show: black too, a shadow, not
                for y, x in px:                     #  the nearest color's block -- an eye's white aside: a sprite's)
                    if g[y][x] not in can and g[y][x] not in ".W":
                        g[y][x] = "K"
    if nudge != (0, 0):                             # (moved on by hand, the colors' phase kept: a tile's width)
        ndx, ndy = nudge
        h = [["."] * build.RW for _ in range(build.RH)]
        for y in range(build.RH):
            for x in range(build.RW):
                if g[y][x] != "." and 0 <= y + ndy < build.RH and 0 <= x + ndx < build.RW:
                    h[y + ndy][x + ndx] = g[y][x]
        g, dx, dy = h, dx + ndx, dy + ndy
    return g, nes, (dx + PAD_X, dy + PAD_Y)


def auto_placement(rival, key):
    """Where the NES frame lies over his auto picture (the 0.7 one build.py makes, before any touch-up): the
    frame, and the phase and offset the silhouettes agree best at (fidelity.register's)."""
    import numpy as np
    if getattr(auto_placement, "of", None) != rival:
        auto_placement.frames, auto_placement.of = touchup.auto_pictures(rival)[0], rival
    mask = np.array([[c is not None for c in row] for row in auto_placement.frames[key]])
    rgb, a = fidelity.nes_frame(rival, key)
    px, py, ox, oy = fidelity.register(mask, rgb, a)
    return rgb, a, px, py, ox, oy


def draw(rival, key, pts):
    """The warped drawing on a canvas PAD round his frame: rows, the NES frame, his head's middle on it."""
    r = build.NES_RIVALS[rival]
    every = build.joe_shapes(r["opp"], everything=True)
    shape = every.get(build._key(key))
    if shape is None:
        other = every[build._key(key[:-1]) if key.endswith("|") else build._key(key + "|")]
        shape = {(-x, y): c for (x, y), c in other.items()}
    nes = {p: char(c) for p, c in shape.items()}
    if key in HEAD_FROM.get(rival, {}):
        nes = borrow_head(rival, nes, *HEAD_FROM[rival][key])
    cx, cy = (round(v) for v in head_middle(nes))      # (on the NES's grid: his head 1:1 pixel for pixel, no half)
    fwd, back = radial(pts)
    rgb, a, px, py, ox, oy = auto_placement(rival, key)
    xs = [x for x, _ in shape]; ys = [y for _, y in shape]
    x0, y0 = min(xs), min(ys)
    A = (((0 - x0) * fidelity.UP + px) / fidelity.DOWN + ox, ((0 - y0) * fidelity.UP + py) / fidelity.DOWN + oy)
    gs = lambda v: fwd(abs(v)) * (1 if v >= 0 else -1)
    C = (round(A[0] + gs(cx)) + PAD_X, round(A[1] + gs(cy)) + PAD_Y)   # (his place where the 0.7 picture has it; his
                                                                        #  head's middle whole pixels, 1:1 exact)
    H, W = build.RH + 2 * PAD_Y, build.RW + 2 * PAD_X
    sg = lambda f, v: f(abs(v)) * (1 if v >= 0 else -1)   # (each axis on its own: across, then down)
    def to(x, y):                                       # (an NES pixel's middle, on ours)
        return math.floor(C[0] + sg(fwd, x + 0.5 - cx)), math.floor(C[1] + sg(fwd, y + 0.5 - cy))
    out = []
    for Y in range(H):                                  # the fills: his colors by area, ink left out of the vote
        row = []
        for X in range(W):
            votes = {}
            for j in range(SUB):
                for i in range(SUB):
                    qx, qy = X + (i + 0.5) / SUB - C[0], Y + (j + 0.5) / SUB - C[1]
                    c = nes.get((math.floor(cx + sg(back, qx)), math.floor(cy + sg(back, qy))), ".")
                    if c == "K":
                        c = "S*"                        # (under ink: whatever fill is around it)
                    votes[c] = votes.get(c, 0) + WEIGHT.get(c, 0.5 if c == "S*" else 1.0)
            best = max(votes, key=votes.get)
            if votes.get("S*", 0) / 0.5 >= 0.6 * SUB * SUB:   # (mostly ink: a boot, a belt -- solid, not lines)
                best = "K"
            elif best == "S*":
                best = max((c for c in votes if c != "S*"), key=votes.get, default="S")
            row.append(best)
        out.append(row)
    ink = {p for p, c in nes.items() if c == "K"}        # the ink: each touching pair of the NES's, a line on ours
    def line(a, b):
        (x0, y0), (x1, y1) = a, b
        n = max(abs(x1 - x0), abs(y1 - y0))
        for t in range(n + 1):
            yield (round(x0 + (x1 - x0) * t / n), round(y0 + (y1 - y0) * t / n)) if n else a
    for (x, y) in ink:
        a = to(x, y)
        for q in ((x + 1, y), (x, y + 1), (x + 1, y + 1), (x - 1, y + 1)):
            if q in ink:
                for X, Y in line(a, to(*q)):
                    if 0 <= X < W and 0 <= Y < H:
                        out[Y][X] = "K"
        X, Y = a
        if 0 <= X < W and 0 <= Y < H:
            out[Y][X] = "K"
    for Y in range(1, H - 1):                           # a lone speck of a fill: its neighbors' (not an eye's white)
        for X in range(1, W - 1):
            c = out[Y][X]
            if c in "K.W":
                continue
            nb = [out[Y - 1][X], out[Y + 1][X], out[Y][X - 1], out[Y][X + 1]]
            if c not in nb:
                out[Y][X] = max(set(nb), key=nb.count)
    warp.last = (C, cx, cy, back)
    checker(out, nes, C, cx, cy, sg, back)
    for _ in range(3):                                  # the sweep: ink where the NES has none under it, that no line
        changed = 0                                     # needs to stay whole, the NES's color instead
        for X, Y, ours, theirs in scan(rival, key, out, nes):
            if ours == "K" and theirs != "K" and not needed(out, X, Y):
                out[Y][X] = theirs if theirs != "K" else "S"
                changed += 1
        if not changed:
            break
    return out, nes, C


EYE = 0.8                                               # (the eye's blur, NES pixels)
LONE = 0.6                                              # (a lone dot's cost, against a blurred pixel's error of 1)


def refine(rival, out, nes):
    """The whole picture seen as the eye sees it: ours blown up to the NES's size (each NES pixel the color of the
    pixel of ours it lands in), both blurred an NES pixel or so, compared in color; each of our pixels (his head
    aside, 1:1 already) tried in each color beside it, kept if the whole looks nearer the NES's, till none is."""
    C, cx, cy, back = warp.last
    fwd, _ = radial(rival)
    R1 = SCALE[rival][0][0]
    xs = [x for x, _ in nes]; ys = [y for _, y in nes]
    bx0, bx1, by0, by1 = min(xs) - 3, max(xs) + 3, min(ys) - 3, max(ys) + 3
    lum = {c: (sum(v * w for v, w in zip(LEG[c], (0.299, 0.587, 0.114))) / 255 if c != "." else 0.35,
               (LEG[c][0] - LEG[c][2]) / 510 if c != "." else -0.3) for c in list(LEG) + ["."]}
    lands, pre = {}, {}
    for y in range(by0, by1 + 1):
        for x in range(bx0, bx1 + 1):
            qx, qy = x + 0.5 - cx, y + 0.5 - cy
            rr = math.hypot(qx, qy)
            k = fwd(rr) / rr if rr else 1
            X, Y = math.floor(C[0] + qx * k), math.floor(C[1] + qy * k)
            lands[(x, y)] = (X, Y)
            pre.setdefault((X, Y), []).append((x, y))
    r = int(2 * EYE + 0.5)
    ker = {(i, j): math.exp(-(i * i + j * j) / (2 * EYE * EYE)) for i in range(-r, r + 1) for j in range(-r, r + 1)}
    tot = sum(ker.values()); ker = {k: v / tot for k, v in ker.items()}
    col = lambda X, Y: out[Y][X] if 0 <= X < build.RW and 0 <= Y < build.RH else "."
    def blurred(x, y, src):
        a = b = 0.0
        for (i, j), w in ker.items():
            c = src(x + i, y + j)
            a += w * lum[c][0]; b += w * lum[c][1]
        return a, b
    target = {p: blurred(*p, lambda x, y: nes.get((x, y), ".")) for p in lands}
    ours = lambda x, y: col(*lands[(x, y)]) if (x, y) in lands else "."
    def err(pts):
        e = 0.0
        for p in pts:
            a, b = blurred(*p, ours); t = target[p]
            e += (a - t[0]) ** 2 + 0.5 * (b - t[1]) ** 2
        return e
    def lone(X, Y):
        c = col(X, Y)
        return c not in ".W" and all(col(X + i, Y + j) != c for i in (-1, 0, 1) for j in (-1, 0, 1) if i or j)
    for sweep in range(6):
        changed = 0
        for Y in range(build.RH):
            for X in range(build.RW):
                if (X, Y) not in pre:
                    continue
                if math.hypot(X + 0.5 - C[0], Y + 0.5 - C[1]) < R1 - 1:
                    continue                            # (his head: the NES's own pixels)
                cur = out[Y][X]
                if cur == "W":
                    continue
                near = {col(X + 1, Y), col(X - 1, Y), col(X, Y + 1), col(X, Y - 1)} - {cur, "W"}
                if not near:
                    continue
                area = {(x + i, y + j) for x, y in pre[(X, Y)] for (i, j) in ker} & set(lands)
                ring = [(X + i, Y + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
                base = err(area) + LONE * sum(lone(*q) for q in ring)
                best, bv = None, base - 1e-9
                for c in near:
                    out[Y][X] = c
                    v = err(area) + LONE * sum(lone(*q) for q in ring)
                    if v < bv:
                        best, bv = c, v
                out[Y][X] = cur
                if best:
                    out[Y][X] = best; changed += 1
        if not changed:
            break


def checker(out, nes, C, cx, cy, sg, back):
    """The NES's checkerboard shading (two colors, each pixel unlike its neighbors across and down and like the
    one corner to corner) kept a strict checkerboard on ours: where most of a pixel's area is the NES's
    checkerboard, the pair's color its square's parity gives -- the parity agreeing most with the NES's."""
    def chk(x, y):
        a, b = nes.get((x, y), "."), nes.get((x + 1, y), ".")
        if a == b or "." in (a, b):
            return None
        for j in (-1, 0, 1):                            # (a whole 3x3 of it alternating: not a line's diagonal)
            for i in (-1, 0, 1):
                if nes.get((x + i, y + j), ".") != (a if (i + j) % 2 == 0 else b):
                    return None
        return (a, b)
    R1 = 10
    mark = {}
    H, W = len(out), len(out[0])
    for Y in range(H):
        for X in range(W):
            if abs(X + 0.5 - C[0]) < R1 and abs(Y + 0.5 - C[1]) < R1:
                continue                                # (his head: the NES's own pixels already)
            pairs = []
            for j in range(3):
                for i in range(3):
                    qx, qy = X + (i + 0.5) / 3 - C[0], Y + (j + 0.5) / 3 - C[1]
                    p = (math.floor(cx + sg(back, qx)), math.floor(cy + sg(back, qy)))
                    k = chk(*p)
                    if k:
                        pairs.append(frozenset(k))
            if len(pairs) >= 4:
                mark[(X, Y)] = max(set(pairs), key=pairs.count)
    for pair in set(mark.values()):                   # (each pair's own area, its own parity)
        pts = [p for p, v in mark.items() if v == pair]
        a, b = sorted(pair)
        agree = sum(1 for X, Y in pts if out[Y][X] == (a if (X + Y) % 2 == 0 else b))
        even, odd = (a, b) if agree * 2 >= len(pts) else (b, a)
        for X, Y in pts:
            out[Y][X] = even if (X + Y) % 2 == 0 else odd


def needed(rows, X, Y):
    """Whether an ink pixel holds a line together: its inky neighbors in more than one piece without it (or it
    ends a line of two or more)."""
    ring = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
    ink = [0 <= Y + dy < len(rows) and 0 <= X + dx < len(rows[0]) and rows[Y + dy][X + dx] == "K" for dx, dy in ring]
    if sum(ink) == 1:
        return True
    runs = sum(1 for i in range(8) if ink[i] and not ink[i - 1])
    return runs > 1


def scan(rival, key, rows, nes):
    """Each of our rows swept against the NES's: the NES color under each pixel's middle, and where ours differs
    (a line drawn through, or a speck): [(x, y, ours, NES's)]."""
    C, cx, cy, back = warp.last
    diff = []
    for Y in range(len(rows)):
        for X in range(len(rows[0])):
            qx, qy = X + 0.5 - C[0], Y + 0.5 - C[1]
            sb = lambda v: back(abs(v)) * (1 if v >= 0 else -1)
            n = nes.get((math.floor(cx + sb(qx)), math.floor(cy + sb(qy))), ".")
            if n != rows[Y][X]:
                diff.append((X, Y, rows[Y][X], n))
    return diff


def shown(rows, pals):
    fr = [[(LEG[c] + (255,)) if c != "." else None for c in r] for r in rows]
    p = build.import_pictures({"x": fr}, pals)["x"]
    rgb = lambda c: tuple((v << 3) | (v >> 2) for v in c)
    from PIL import Image
    im = Image.new("RGB", (build.RW, build.RH), (8, 76, 196))
    for i, ch in enumerate(p["pixels"]):
        if ch != "0":
            im.putpixel((i % build.RW, i // build.RW),
                        rgb(pals[build.KINDS.index(p["cells"][(i // build.RW // 8) * build.FIGHT_W + (i % build.RW) // 8])][int(ch)]))
    for i in p.get("whites", []):
        im.putpixel((i % build.RW, i // build.RW), (236, 238, 236))
    return im


def main():
    from PIL import Image, ImageDraw
    rival, keys, out = sys.argv[1], [k.replace("m", "|") for k in sys.argv[2].split(",")], sys.argv[3]
    frames, pals = touchup.auto_pictures(rival)
    frames = build.apply_touchups(rival, frames)
    Z, tiles = 4, []
    for k in keys:
        rows, nes, _ = warp(rival, k)
        xs = [x for x, _ in nes]; ys = [y for _, y in nes]
        n = Image.new("RGB", (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1), (8, 76, 196))
        for (x, y), c in nes.items():
            if c != ".":
                n.putpixel((x - min(xs), y - min(ys)), LEG[c])
        appr = shown([[char(c) if c else "." for c in r] for r in frames[k]], pals)
        tiles.append((k, n, appr, shown(rows, pals)))
    W = sum(max(t[1].width, 64) * Z + 2 * 64 * Z + 60 for t in tiles[:1])
    H = sum(max(t[1].height, 80) * Z + 20 for t in tiles)
    sheet = Image.new("RGB", (W, H), (24, 24, 24)); d = ImageDraw.Draw(sheet); y = 0
    for k, n, appr, wp in tiles:
        x = 0
        for label, im in (("NES", n), ("approved", appr), ("warped", wp)):
            sheet.paste(im.resize((im.width * Z, im.height * Z), Image.NEAREST), (x, y + 16))
            d.text((x + 2, y + 2), f"{k} {label}", fill=(255, 255, 0))
            x += im.width * Z + 20
        y += max(n.height, 80) * Z + 20
    sheet.save(out); print(out)


if __name__ == "__main__":
    main()
