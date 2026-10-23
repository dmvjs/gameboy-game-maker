"""Little Mac and Glass Joe from Punch-Out!! (NES) for the Mac vs Joe test sample. Local only: git ignores
this folder and editor/art/mac-vs-joe.js (.git/info/exclude).

    python3 tools/punchout_art/build.py                    # rebuild from the NES rips at the default scales
    python3 tools/punchout_art/build.py --joe 0.7 --mac 0.75
    python3 tools/punchout_art/build.py --mac-sheet my-mac.png      # a hand-edited sheet

From the rips it writes out/joe-from-rip.png (64x80 frames) and out/mac-from-rip.png (24x48 frames); copy one
to edit in any pixel editor (these two are rewritten on every run). Then, only if everything fits, it writes
editor/art/mac-vs-joe.js, and prints the fight scene's tile budget on the original Game Boy.
Colors go through the same rules as the editor's importer (editor/importer.js), ported below. Shrinking keeps
outlines (they're what make faces read at this size), and near-duplicate 8x8 tiles are shared only as much as
it takes to fit; out/preview.png shows exactly what the game will draw.
"""
import argparse, copy, json, re, sys
from pathlib import Path
import png

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
OUT_JS = ROOT / "editor" / "art" / "mac-vs-joe.js"
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
BLUE = (13, 77, 196)                    # the rips' frame background
# The Glass Joe sheet's colors -> the game's own (sampled from the NES game: orange hair, red gloves, a royal
# blue portrait background), so he looks as he does in the ring.
RECOLOR = {"glass-joe.png": {(250, 195, 231): (242, 183, 203),     # skin
                             (75, 36, 222): (28, 48, 218),         # portrait background
                             (33, 53, 12): (31, 33, 37),           # outline
                             (146, 52, 4): (200, 41, 21),          # gloves
                             (204, 158, 34): (241, 138, 62),       # hair
                             (255, 255, 255): (244, 244, 244)}}

# Pose -> frame number in the source sheet (frames found left to right, top to bottom; see --contact).
JOE = dict(idle=0, idle2=1, guard=28, hit_l=37, hit_r=36, hit_body=41, dazed=35, jab_tell=7, jab_mid=8, jab=15,
           hook_tell=16, hook_mid=17, hook=11, slip=43, idle3=2, hit_back=42, kd_stagger=47, kd_fall=44,
           kd_down=49, kd_kneel=45, taunt=6, arm_pop=10, guard_low=31, tell1=7, tell2=7, tell3=7, tell4=7, tell5=7,
           kd2_stagger=47, kd2_fall=44, kd2_down=49, kd2_kneel=45)
MAC = dict(idle=0, jab=2, jab_high=7, dodge=5, block=38, hit=34, star=30, down=37, win=24)
KD = {"kd_fall", "kd_down", "kd_kneel", "kd_stagger", "kd2_fall", "kd2_down", "kd2_kneel", "kd2_stagger"}   # sit on the floor of the frame
JOE_ROWS, MAC_ROWS = (9, 114, 100), (25, 98, 95)  # source rows' top lines, and the y where the second row starts:
                                                 # standing poses keep their offset from their row's top


# ---- frames out of the rips ----

def components(px, maxh):
    h, w = len(px), len(px[0]); seen = [[0] * w for _ in range(h)]; out = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or px[y][x][3] == 0: continue
            st = [(x, y)]; seen[y][x] = 1; x0 = x1 = x; y0 = y1 = y; n = 0
            while st:
                a, b = st.pop(); n += 1; x0, x1, y0, y1 = min(x0, a), max(x1, a), min(y0, b), max(y1, b)
                for c, d in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if 0 <= c < w and 0 <= d < h and not seen[d][c] and px[d][c][3]:
                        seen[d][c] = 1; st.append((c, d))
            if n > 200 and y1 - y0 + 1 <= maxh: out.append((x0, y0, x1 - x0 + 1, y1 - y0 + 1))
    return sorted(out, key=lambda r: (r[1] // 40, r[0]))

def load(name):
    """A source sheet's pixels, in the game's colors."""
    _, _, px = png.read(HERE / "sources" / name)
    m = RECOLOR.get(name, {})
    return [[m[c[:3]] + (c[3],) if c[:3] in m else c for c in row] for row in px] if m else px

def cut(px, box):
    x0, y0, cw, ch = box
    return [[None if (px[y0 + y][x0 + x][3] == 0 or px[y0 + y][x0 + x][:3] == BLUE) else px[y0 + y][x0 + x]
             for x in range(cw)] for y in range(ch)]

def scale(f, s, outline_weight=1.8):
    """Shrink pixel art: each new pixel takes the color covering most of its area, with the outline (the darkest
    color) counted extra so outlines, eyes and mouths survive instead of dropping out as they do with nearest
    neighbour."""
    h, w = len(f), len(f[0]); H, W = max(1, round(h * s)), max(1, round(w * s))
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    seen = {c[:3] for row in f for c in row if c}
    dark = min(seen, key=lum) if seen else None
    def spans(n, N):                    # per new pixel: [(old index, overlap)]
        out = []
        for X in range(N):
            a, b = X / s, (X + 1) / s; row = []
            for i in range(int(a), min(n, int(b) + 1)):
                o = min(b, i + 1) - max(a, i)
                if o > 1e-9: row.append((i, o))
            out.append(row)
        return out
    ys, xs = spans(h, H), spans(w, W)
    out = []
    for Y in range(H):
        row = []
        for X in range(W):
            score = {}
            for y, oy in ys[Y]:
                for x, ox in xs[X]:
                    c = f[y][x]; k = c[:3] if c else None
                    weight = outline_weight if k == dark else (0.85 if k is None else      # (the background gives
                             1.6 if lum(k) > 200 else 1)                                      # way at his edges; eyes'
                    score[k] = score.get(k, 0) + oy * ox * weight                             # and teeth's whites stay)
            k = max(score, key=score.get)
            row.append(k + (255,) if k else None)
        out.append(row)
    return out

FEATURE = 40                            # (shrink_lines: a thin bright feature's line, this much costlier to drop)


MAC_LETTERS = "KGS"                      # (Mac's baked frames: his 3 colors, MAC_INK's order)


def mac_baked(name, make):
    """Mac's frame `name` as baked (touchups/mac/NAME.txt, 'final'): its rows of his colors; not baked, make()'s."""
    path = TOUCHUPS / "mac" / f"{name}.txt"
    if path.exists():
        rows = [l for l in path.read_text().splitlines() if l and not l.startswith(("#", "final"))]
        return [[MAC_INK[MAC_LETTERS.index(c)] + (255,) if c != "." else None for c in r] for r in rows]
    return make()


def bake_mac(name, rows):
    path = TOUCHUPS / "mac" / f"{name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Little Mac, {name}: from the NES frame by treat_lines (0.7), baked", "final"]
    lines += ["".join(MAC_LETTERS[MAC_INK.index(tuple(c[:3]))] if c else "." for c in r) for r in rows]
    path.write_text("\n".join(lines) + "\n")


def treat_lines(f, s, ink_color):
    """Shrink pixel art the way warp.py draws a fighter (uniform here: no head kept larger): each pixel the color
    most of its area covers, the ink left out of that vote; the ink drawn as lines (each touching pair of the
    original's inked pixels joined), so outlines stay whole and a pixel thin; lone specks of a color taken by
    their neighbors'; then swept against the original row by row, ink no line needs given back the color under
    it. Closer to the original than shrink_lines (a third of the pixels wrong there, an eighth here)."""
    import math
    SUB = 5
    H, W = len(f), len(f[0])
    key = lambda c: tuple(c[:3]) if c else None
    ink = tuple(ink_color[:3])
    src = {(x, y): key(c) for y, row in enumerate(f) for x, c in enumerate(row) if c}
    full = {key(c): c for row in f for c in row if c}
    oh, ow = math.ceil(H * s) + 1, math.ceil(W * s) + 1
    out = [[None] * ow for _ in range(oh)]
    for Y in range(oh):
        for X in range(ow):
            v = {}
            for j in range(SUB):
                for i in range(SUB):
                    c = src.get((math.floor((X + (i + .5) / SUB) / s), math.floor((Y + (j + .5) / SUB) / s)))
                    k = "ink" if c == ink else c
                    v[k] = v.get(k, 0) + (0.5 if k == "ink" else 1)
            if v.get("ink", 0) / 0.5 >= 0.85 * SUB * SUB:      # (solid: a tank top, a boot -- not a lined leg)
                out[Y][X] = ink
                continue
            b = max(v, key=v.get)
            if b == "ink":
                b = max((k for k in v if k != "ink"), key=v.get, default=None)
            out[Y][X] = b
    to = lambda x, y: (math.floor((x + .5) * s), math.floor((y + .5) * s))
    def line(a, b):
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        for t in range(n + 1):
            yield (round(a[0] + (b[0] - a[0]) * t / n), round(a[1] + (b[1] - a[1]) * t / n)) if n else a
    inks = {p for p, c in src.items() if c == ink}
    for (x, y) in inks:
        a = to(x, y)
        out[a[1]][a[0]] = ink
        for q in ((x + 1, y), (x, y + 1), (x + 1, y + 1), (x - 1, y + 1)):
            if q in inks:
                for X, Y in line(a, to(*q)):
                    if 0 <= X < ow and 0 <= Y < oh:
                        out[Y][X] = ink
    for Y in range(1, oh - 1):
        for X in range(1, ow - 1):
            c = out[Y][X]
            if c in (ink, None):
                continue
            nb = [out[Y - 1][X], out[Y + 1][X], out[Y][X - 1], out[Y][X + 1]]
            fill = [n for n in nb if n not in (ink, None)]
            if c not in nb and fill:            # (a speck of a color: its neighbors' -- never ink: skin between
                out[Y][X] = max(set(fill), key=fill.count)   #  two lines is the art, not a speck)
    def needed(X, Y):
        ring = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
        k = [0 <= Y + dy < oh and 0 <= X + dx < ow and out[Y + dy][X + dx] == ink for dx, dy in ring]
        return sum(k) == 1 or sum(1 for i in range(8) if k[i] and not k[i - 1]) > 1
    for _ in range(3):
        for Y in range(oh):
            for X in range(ow):
                if out[Y][X] == ink:
                    n = src.get((math.floor((X + .5) / s), math.floor((Y + .5) / s)))
                    if n not in (ink, None) and not needed(X, Y):
                        out[Y][X] = n
    rows = [[full[c] if c else None for c in r] for r in out]
    while rows and not any(rows[-1]):
        rows.pop()
    while rows and not any(rows[0]):
        rows.pop(0)
    cols = [x for r in rows for x, c in enumerate(r) if c]
    lo, hi = (min(cols), max(cols)) if cols else (0, 0)
    return [r[lo:hi + 1] for r in rows]


def shrink_lines(f, s):
    """Shrink pixel art by dropping whole rows and columns (3 in every 10 at 0.7): in each block the ones that
    most repeat a neighbour, never two side by side, the blocks' phase the one losing least. What's kept is the
    art's own pixels, so thin lines (hair, straps, outlines) stay crisp instead of being voted away."""
    def same(a, b):
        return sum(1 for x, y in zip(a, b) if (x[:3] if x else None) != (y[:3] if y else None))
    lum = lambda c: c[0] * 3 + c[1] * 6 + c[2] if c else -1
    def thin(rows, i):                  # its thin bright features: a light pixel with darker ones either side across
        n = len(rows)                   # (eyes' whites, teeth, a glint), which dropping its line would wipe out
        if not 0 < i < n - 1:
            return 0
        return sum(1 for x, c in enumerate(rows[i])
                   if c and lum(c) >= 1400 and lum(rows[i - 1][x]) < lum(c) - 600 and lum(rows[i + 1][x]) < lum(c) - 600)
    def keep(rows):
        n = len(rows)
        cost = [min(same(rows[i], rows[i - 1]) if i else 99, same(rows[i], rows[i + 1]) if i + 1 < n else 99)
                + FEATURE * thin(rows, i) for i in range(n)]
        best = None
        for phase in range(10):
            drop = set()
            for b0 in range(-phase, n, 10):
                block = [i for i in range(b0, b0 + 10) if 0 <= i < n]
                want, got = round(len(block) * (1 - s)), []
                for i in sorted(block, key=lambda i: cost[i]):
                    if len(got) == want:
                        break
                    if all(abs(i - j) > 1 for j in got):
                        got.append(i)
                drop |= set(got)
            total = sum(cost[i] for i in drop)
            if best is None or total < best[0]:
                best = (total, drop)
        return [i for i in range(n) if i not in best[1]]
    f = [f[y] for y in keep(f)]
    xs = keep([[r[x] for r in f] for x in range(len(f[0]))])
    return [[r[x] for x in xs] for r in f]

def place(f, FW, FH, dy):               # centred, or slid to keep the most pixels when wider than the frame
    h, w = len(f), len(f[0]); best, ox = -1, 0
    for o in range(min(0, FW - w), max(0, FW - w) + 1):
        n = sum(1 for y in range(h) for x in range(w) if f[y][x] and 0 <= x + o < FW and 0 <= y + dy < FH)
        if n > best or (n == best and abs(o - (FW - w) / 2) < abs(ox - (FW - w) / 2)): best, ox = n, o
    out = [[None] * FW for _ in range(FH)]
    for y in range(h):
        for x in range(w):
            if f[y][x] and 0 <= x + ox < FW and 0 <= y + dy < FH: out[y + dy][x + ox] = f[y][x]
    return out

def frames_from_rip(path, poses, s, FW, FH, natural_h, rows, maxh):
    px = load(path.name); boxes = components(px, maxh); out = []
    for name, i in poses.items():
        box = boxes[i]; f = scale(cut(px, box), s)
        if name in KD: dy = FH - len(f)
        else:
            top = rows[1] if box[1] >= rows[2] else rows[0]
            dy = round((box[1] - top) * s) + max(0, FH - round(natural_h * s))
        out.append(place(f, FW, FH, dy))
    return out

def write_sheet(path, frames, FW, FH, cols=4):
    rows = (len(frames) + cols - 1) // cols; img = [[(0, 0, 0, 0)] * (cols * FW) for _ in range(rows * FH)]
    for n, f in enumerate(frames):
        for y in range(FH):
            for x in range(FW):
                if f[y][x]: img[(n // cols) * FH + y][(n % cols) * FW + x] = tuple(f[y][x])
    path.parent.mkdir(exist_ok=True); png.write(path, cols * FW, rows * FH, img)


# ---- editor/importer.js, ported ----

FIGHT_W, FIGHT_H = 8, 10
FIGHT_POSES = ['idle','idle2','guard','hit_l','hit_r','hit_body','dazed','jab_tell','jab_mid','jab','hook_tell','hook_mid','hook','slip','idle3','hit_back','kd_stagger','kd_fall','kd_down','kd_kneel','kd_rise','taunt','arm_pop','guard_low','tell1','tell2','tell3','tell4','tell5','extra1','extra2','extra3','extra4','kd2_stagger','kd2_fall','kd2_down','kd2_kneel','kd2_rise']
TELL_FALLBACK = {**{f'tell{k}': 'jab_tell' for k in range(1, 6)}, **{f'kd2_{p}': f'kd_{p}' for p in ('stagger', 'fall', 'down', 'kneel')},
                 **{f'extra{k}': 'jab' for k in range(1, 5)}, 'kd_rise': 'kd_kneel', 'kd2_rise': 'kd2_kneel'}   # (a fighter without his own)
PLAYER_POSES = ['idle','jab','jab_high','dodge','block','hit','star','down','win','star2','star3','star4','jab_tell','high_tell','knocked','duck']
RW, RH, PW, PH = 64, 80, 24, 48
KINDS = 'sgh'
expand = lambda v: (v << 3) | (v >> 2)
def snap(v): x = min(255, max(0, v)) * 31 / 255; return int(x + 0.5)  # Math.round for non-negatives
from8 = lambda c: [snap(v) for v in c]
to8 = lambda c: [expand(v) for v in c]
def lum(c): r, g, b = to8(c); return 0.299*r + 0.587*g + 0.114*b
key = lambda c: ','.join(map(str, c))
dist = lambda a, b: (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2

def frames(path, fw, fh, count):
    w, h, px = png.read(path)
    assert w % fw == 0 and h % fh == 0
    cols = w // fw; out = []
    for n in range(min(count, cols * (h // fh))):   # (an older sheet: fewer poses, the rest borrow one)
        fx, fy = (n % cols)*fw, (n // cols)*fh
        out.append([None if px[fy+y][fx+x][3] < 128 else from8(px[fy+y][fx+x][:3]) for y in range(fh) for x in range(fw)])
    return out

def import_rival(path, mat):
    allf = frames(path, RW, RH, len(FIGHT_POSES))
    bg = [px[0] and key(px[0]) for px in allf]
    isBg = lambda n, c: not c or key(c) == bg[n]
    black = None
    for n, px in enumerate(allf):
        for c in px:
            if not isBg(n, c) and (black is None or lum(c) < lum(black)): black = c
    black = black or [0, 0, 0]
    tiles = []
    for n, px in enumerate(allf):
        for cy in range(FIGHT_H):
            for cx in range(FIGHT_W):
                colors = {}
                for y in range(8):
                    for x in range(8):
                        c = px[(cy*8+y)*RW + cx*8+x]
                        if not isBg(n, c) and key(c) != key(black): colors[key(c)] = colors.get(key(c), 0) + 1
                tiles.append(colors)
    pairs = {}
    for t in tiles:
        if not t or len(t) > 2: continue
        k = '|'.join(sorted(t)); pairs[k] = pairs.get(k, 0) + 1
    chosen = []
    covers = lambda pair, t: all(c in pair for c in t)
    while len(chosen) < 3 and pairs:
        best, bestScore = None, -1
        for k in pairs:
            pair = k.split('|')
            score = sum(1 for t in tiles if t and covers(pair, t) and not any(covers(p, t) for p in chosen))
            if score > bestScore: best, bestScore = pair, score
        if bestScore <= 0: break
        chosen.append(best); del pairs['|'.join(sorted(best))]
    parse = lambda k: list(map(int, k.split(',')))
    palettes = []
    for pair in chosen:
        cs = sorted(map(parse, pair), key=lambda c: -lum(c))
        if len(cs) == 1: cs.append([max(0, v-6) for v in cs[0]])
        palettes.append([mat, cs[0], cs[1], black])
    while len(palettes) < 3: palettes.append(list(palettes[0]) if palettes else [mat, [31,24,18], [23,14,10], black])
    changed = 0; poses = {}
    for n, px in enumerate(allf):
        out = [0]*(RW*RH); kinds = []
        for cy in range(FIGHT_H):
            for cx in range(FIGHT_W):
                cell = [(cy*8+y)*RW + cx*8+x for y in range(8) for x in range(8)]
                bestP, bestErr = 0, float('inf')
                for pi, pal in enumerate(palettes):
                    err = sum(min(dist(px[i], pal[s]) for s in (1,2,3)) for i in cell if not isBg(n, px[i]))
                    if err < bestErr: bestErr, bestP = err, pi
                if bestErr > 0: changed += 1
                pal = palettes[bestP]
                for i in cell:
                    c = px[i]
                    if isBg(n, c): continue
                    s, e = 1, float('inf')
                    for k in (1,2,3):
                        d = dist(c, pal[k])
                        if d < e: e, s = d, k
                    out[i] = s
                kinds.append(KINDS[bestP])
        poses[FIGHT_POSES[n]] = {'pixels': ''.join(map(str, out)), 'cells': ''.join(kinds)}
    return poses, palettes, changed

def import_player(path):
    allf = frames(path, PW, PH, len(PLAYER_POSES))
    bg = [px[0] and key(px[0]) for px in allf]
    isBg = lambda n, c: not c or key(c) == bg[n]
    count = {}
    for n, px in enumerate(allf):
        for c in px:
            if not isBg(n, c): count[key(c)] = count.get(key(c), 0) + 1
    top = sorted(count.items(), key=lambda kv: -kv[1])[:3]
    colors = sorted((list(map(int, k.split(','))) for k, _ in top), key=lambda c: -lum(c))
    while len(colors) < 3: colors.append([0,0,0])
    changed = 0; poses = {}
    for n, px in enumerate(allf):
        s_out = []
        for c in px:
            if isBg(n, c): s_out.append('0'); continue
            s, e = 1, float('inf')
            for k, pc in enumerate(colors):
                d = dist(c, pc)
                if d < e: e, s = d, k+1
            if e > 0: changed += 1
            s_out.append(str(s))
        poses[PLAYER_POSES[n]] = ''.join(s_out)
    return poses, colors, changed



# ---- sharing tiles ----
# Video memory holds every pose's 8x8 tiles at once on the original Game Boy, so a near-duplicate tile costs as much
# as a new drawing. Here a tile that differs from one already kept by at most `limit` pixels is replaced by it
# (the NES game shares tiles between poses the same way). Poses go most-seen first, so they keep their own tiles.

def _planes(key):
    a = b = 0
    for i, ch in enumerate(key):
        v = ord(ch) - 48
        if v & 1: a |= 1 << i
        if v & 2: b |= 1 << i
    return a, b

def _nearest(key, pool, limit):
    if key in pool: return key
    a, b = _planes(key); best, bd = None, limit + 1
    for k, (c, d) in pool.items():
        n = bin((a ^ c) | (b ^ d)).count("1")
        if n < bd: best, bd = k, n
    return best

def share_rival_tiles(poses, limit):
    from gbstage import fight as kit
    in_set = {p for ps in kit.POSE_SETS.values() for p in ps}
    order = [("base", [p for p in kit.RIVAL_POSES if p not in in_set])] + list(kit.POSE_SETS.items())
    base, out = {}, {}
    for group, names in order:
        pool = dict(base) if group != "base" else base
        for name in names:
            px = list(poses[name]["pixels"])
            for cy in range(FIGHT_H):
                for cx in range(FIGHT_W):
                    idx = [(cy * 8 + y) * RW + cx * 8 + x for y in range(8) for x in range(8)]
                    key = "".join(px[i] for i in idx)
                    got = _nearest(key, pool, limit) if limit else (key if key in pool else None)
                    if got is None: pool[key] = _planes(key); got = key
                    for i, ch in zip(idx, got): px[i] = ch
            out[name] = {"pixels": "".join(px), "cells": poses[name]["cells"]}
    return out

def merge_closest(poses, count):
    """After share_rival_tiles: share `count` more tiles in his largest pose set, the closest pairs first (so a
    level of sharing that just misses needs only a few tiles of the next, not all of them)."""
    from gbstage import fight as kit
    in_set = {p for ps in kit.POSE_SETS.values() for p in ps}
    base = [p for p in kit.RIVAL_POSES if p not in in_set]
    cells = [(cy, cx) for cy in range(FIGHT_H) for cx in range(FIGHT_W)]
    tile = lambda name, cy, cx: "".join(poses[name]["pixels"][(cy * 8 + y) * RW + cx * 8 + x] for y in range(8) for x in range(8))
    tiles_of = lambda names: {tile(n, cy, cx) for n in names for cy, cx in cells}
    base_t = tiles_of(base)
    group = max(kit.POSE_SETS.values(), key=lambda ps: len(tiles_of(ps) - base_t))
    others = tiles_of([p for p in in_set if p not in group])
    mine = tiles_of(group)
    tells = tiles_of([p for p in group if "tell" in p])   # (a tell's tiles stay exact: the calls must read)
    movable = mine - base_t - others - tells    # (a tile another set uses too stays: it's no saving there)
    dist = lambda k1, k2: bin((lambda a, b, c, d: (a ^ c) | (b ^ d))(*_planes(k1), *_planes(k2))).count("1")
    pairs = sorted((dist(k, j), k, j) for k in movable for j in mine | base_t if j != k)
    into, n = {}, 0
    for d, k, j in pairs:
        if n == count: break
        if k in into or j in into or any(v == k for v in into.values()): continue
        into[k] = j; n += 1
    out = dict(poses)
    for name in group:
        px = list(poses[name]["pixels"])
        for cy, cx in cells:
            k = tile(name, cy, cx)
            if k in into:
                for i, ch in enumerate(into[k]): px[(cy * 8 + i // 8) * RW + cx * 8 + i % 8] = ch
        out[name] = {"pixels": "".join(px), "cells": poses[name]["cells"]}
    return out, (max(d for d, k, j in pairs if into.get(k) == j) if into else 0)

PLAYER_ORDER = ["idle", "jab", "block", "dodge", "hit", "jab_high", "star", "down", "win", "star2", "star3", "star4",
                "jab_tell", "high_tell", "knocked", "duck"]   # most seen first

STAR_POSES = ("star", "star2", "star3", "star4", "jab_tell", "high_tell", "knocked", "duck")   # (up a moment,
                                                                                    # loaded as needed: shared more loosely)

def share_player_tiles(poses, limit, star_extra=10):
    flip = lambda k: "".join(k[y * 8 + 7 - x] for y in range(8) for x in range(8))
    empty = "0" * 64
    pool = {empty: _planes(empty)}       # empty tiles are free; a stray pixel or two can become one
    out = {}
    for name in PLAYER_ORDER:
        px = list(poses[name])
        for by in range(PH // 8):
            for bx in range(PW // 8):
                idx = [(by * 8 + y) * PW + bx * 8 + x for y in range(8) for x in range(8)]
                key = "".join(px[i] for i in idx)
                best = None
                lim = limit + star_extra if name in STAR_POSES else limit + 3 if name == "win" else limit   # (his win:
                                                                    # loaded as needed, its area sized by it)
                for k, unflip in ((key, lambda t: t), (flip(key), flip)):    # a mirrored tile is free too
                    got = _nearest(k, pool, lim) if lim else (k if k in pool else None)
                    if got is not None:
                        a, b = _planes(k); c, d = pool[got]; n = bin((a ^ c) | (b ^ d)).count("1")
                        if best is None or n < best[0]: best = (n, unflip(got))
                if best is None: pool[key] = _planes(key); got = key
                else: got = best[1]
                for i, ch in zip(idx, got): px[i] = ch
        out[name] = "".join(px)
    return {n: out[n] for n in PLAYER_POSES}


# ---- portraits ----
# The challenger screen's and corner's close-ups: 56x56 (7x7 tiles), the NES portraits' own pixels at 1:1 (pixel
# art doesn't survive scaling) cropped around the face, inside a 1-pixel white frame. Each fighter's portraits get
# palettes of their own, picked from the art (a scene can use 8, and the project 24): one palette per tile, as
# the hardware wants, chosen so every tile is drawn as closely as 4 colors allow.

TEXT_PALETTE = [[31, 31, 31], [31, 15, 7], [11, 27, 9], [0, 0, 0]]     # white, orange, green, black (the background)
PORTRAIT = 56
CROP = PORTRAIT - 2                                                      # inside the frame
PORTRAITS = {"joe": ("glass-joe.png", (938 + 22, 16 + 18)),            # top-left of the crop in the sheet
             "joe_hurt": ("glass-joe.png", (938 + 22, 97 + 18)),
             "mac": ("little-mac.png", (782 + 26, 1 + 8))}
PORTRAIT_PALETTES = {"joe": 5, "mac": 1, "kaiser": 5, "honda": 5, "don": 5, "hippo": 5, "tiger": 5, "bull": 5, "soda": 5, "sandman": 5, "macho": 5, "tyson": 4}      # palettes per fighter's portraits (joe_hurt shares Joe's)
FRAME = [31, 31, 31]

VS_BOX = (161, 52, 238, 126)                  # the portrait's box on the NES challenger screen (inside the frame)

def nes_portrait(opponent):
    """An opponent's close-up from the game's challenger screen: the middle of its box, inside a frame."""
    import nes_play
    img = nes_play.vs_screen(opponent)
    x0, y0, x1, y1 = VS_BOX
    inner = PORTRAIT - 2                # at the game's own size, as Joe's: the box's middle, from just under its top
    cx = x0 + (x1 - x0 + 1 - inner) // 2
    cy = y0 + 4
    out = [[FRAME] * PORTRAIT for _ in range(PORTRAIT)]
    for y in range(inner):
        for x in range(inner):
            out[1 + y][1 + x] = from8(tuple(img[cy + y][cx + x])[:3])
    return out

def portrait(name):
    if name in NES_RIVALS and name not in PORTRAITS:    # (Joe's close-ups: their own, his hurt one too)
        return nes_portrait(NES_RIVALS[name]["opp"])
    src, (x0, y0) = PORTRAITS[name]
    px = load(src)
    return [[FRAME if not (0 < x < PORTRAIT - 1 and 0 < y < PORTRAIT - 1) else from8(px[y0 + y - 1][x0 + x - 1][:3])
             for x in range(PORTRAIT)] for y in range(PORTRAIT)]

def _tiles(px):
    return [[px[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)]
            for cy in range(PORTRAIT // 8) for cx in range(PORTRAIT // 8)]

def _weight(c):
    """Whites and blacks (eyes, teeth, outlines) cost far more to lose than a shade of skin."""
    v = c[0] + c[1] + c[2]
    return 24 if v >= 84 or v <= 12 else 1

def _tile_err(tile, pal):
    return sum(_weight(c) * min(dist(c, q) for q in pal) for c in tile)

def _palette_for(tiles):
    """4 of these tiles' own colors that draw them best: the commonest first, then whichever cuts the error most."""
    count = {}
    for t in tiles:
        for c in t: count[key(c)] = count.get(key(c), 0) + 1
    colors = [list(map(int, k.split(","))) for k in sorted(count, key=lambda k: -count[k])]
    pal = colors[:1]
    while len(pal) < 4 and len(pal) < len(colors):
        pal.append(min((c for c in colors if c not in pal), key=lambda c: sum(_tile_err(t, pal + [c]) for t in tiles)))
    return pal + [pal[-1]] * (4 - len(pal))

def choose_palettes(tiles, n, rounds=8):
    """n palettes for these tiles: seeded on the worst-drawn tile in turn, then refined (each tile to its best
    palette, each palette remade from its tiles) until nothing changes."""
    pals = [_palette_for(tiles)]
    while len(pals) < n:
        worst = max(tiles, key=lambda t: min(_tile_err(t, p) for p in pals))
        pals.append(_palette_for([worst]))
    for _ in range(rounds):
        groups = [[] for _ in pals]
        for t in tiles:
            groups[min(range(len(pals)), key=lambda k: _tile_err(t, pals[k]))].append(t)
        new = [_palette_for(g) if g else p for g, p in zip(groups, pals)]
        if new == pals: break
        pals = new
    return [sorted(p, key=lambda c: -lum(c)) for p in pals]    # lightest first: the original Game Boy's grays

def _draw(px, pals):
    slots, cells = [0] * (PORTRAIT * PORTRAIT), []
    for k, tile in enumerate(_tiles(px)):
        best = min(range(len(pals)), key=lambda p: _tile_err(tile, pals[p]))
        cy, cx = divmod(k, PORTRAIT // 8)
        for n, c in enumerate(tile):
            y, x = cy * 8 + n // 8, cx * 8 + n % 8
            slots[y * PORTRAIT + x] = min(range(4), key=lambda q: dist(c, pals[best][q]))
        cells.append(best)
    return slots, cells

# The NES's own close-ups at their full size (Punch-Out!!'s challenger and corner screens): 80x72, 10x9 tiles, its
# boxes and frames as the game draws them. The rival's from his challenger screen; Doc and Mac from the corner, in
# its four states (Doc's mouth shut or open, his hand down or up on Mac's shoulder), the challenger's being the first.
FULL_W, FULL_H = 80, 72
FULL_RIVAL = (160, 48)                          # their boxes' top-left on the NES screen (tile-aligned)
FULL_MAC = (16, 120)
DOC_MOUTH = [(4, 1), (4, 2), (5, 1), (5, 2)]    # (row, column) of the tiles each changes
DOC_HAND = [(6, 2), (6, 3), (7, 1), (7, 2), (7, 3), (7, 4), (8, 1), (8, 2), (8, 3), (8, 4)]


def _crop(img, x0, y0):
    return [[from8(tuple(img[y0 + y][x0 + x])[:3]) for x in range(FULL_W)] for y in range(FULL_H)]


def full_rival(opponent):
    import nes_play
    return _crop(nes_play.vs_screen(opponent), *FULL_RIVAL)


def doc_states():
    """Doc and Mac in the corner's four states: shut/hand down, open/down, shut/up, open/up (cynes, the real game)."""
    import pickle
    cache = HERE / "out" / "nes-doc-states.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    import cynes_frames as C
    from cynes import NES
    nes = NES(C.rom_path())

    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):
        run(4, C.START); nes[0x01] = 3; run(86)
        if nes[0x00] == 1:
            break
    run(300)
    nes[0x302], nes[0x304], nes[0x305] = 2, 5, 8      # (the round's end, soon: the corner)
    seen = []
    for _ in range(2400):
        f = run(1)
        if nes[0x00] in (1, 0x40):
            continue
        rows = [[tuple(int(v) for v in f[FULL_MAC[1] + y][FULL_MAC[0] + x][:3]) for x in range(FULL_W)] for y in range(FULL_H)]
        if rows not in seen:
            seen.append(rows)
        if len(seen) >= 7:
            break
    tile = lambda img, cells: [img[r * 8 + y][c * 8 + x] for r, c in cells for y in range(8) for x in range(8)]
    base = seen[-4]                                     # (the first three: the screen coming up)
    states = [None] * 4
    for img in seen[-4:]:
        m = tile(img, DOC_MOUTH) != tile(base, DOC_MOUTH)
        h = tile(img, DOC_HAND) != tile(base, DOC_HAND)
        states[m + 2 * h] = img
    assert all(states), "the corner's four states"
    states = [[[from8(c) for c in row] for row in img] for img in states]
    cache.parent.mkdir(exist_ok=True)
    pickle.dump(states, open(cache, "wb"))
    return states


def rival_talk(opponent):
    """The rival in the corner, talking (cynes, the real game): his two states and their frames, (first, other, back)
    -- his first state as the screen comes up, then the two in turn -- or None (Mike Tyson's stays still)."""
    import pickle, statistics
    cache = HERE / "out" / f"nes-talk{opponent}.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    import cynes_frames as C
    from cynes import NES
    nes = NES(C.rom_path())

    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):
        run(4, C.START); nes[0x01] = opponent; run(86)
        if nes[0x00] == 1:
            break
    run(300)
    nes[0x302], nes[0x304], nes[0x305] = 2, 5, 8      # (the round's end, soon: the corner)
    seq = []
    for _ in range(3000):
        f = run(1)
        if nes[0x00] != 0xFF:
            if seq:
                break
            continue
        seq.append([[tuple(int(v) for v in f[FULL_RIVAL[1] + y][FULL_RIVAL[0] + x][:3]) for x in range(FULL_W)] for y in range(FULL_H)])
    runs = []
    for img in seq:
        if runs and runs[-1][0] == img:
            runs[-1][1] += 1
        else:
            runs.append([img, 1])
    up = max(k for k, (img, _) in enumerate(runs) if not any(c != (0, 0, 0) for row in img for c in row)) + 1   # (black, then up)
    runs = runs[up:]
    talk = None
    if len(runs) > 4:
        a, b = runs[0][0], runs[1][0]
        assert all(img in (a, b) for img, _ in runs), "two states"
        talk = ([[from8(c) for c in row] for row in a], [[from8(c) for c in row] for row in b],
                (runs[0][1], round(statistics.median(n for _, n in runs[1:-1:2])), round(statistics.median(n for _, n in runs[2:-1:2]))))
    cache.parent.mkdir(exist_ok=True)
    pickle.dump(talk, open(cache, "wb"))
    return talk


def _tiles_wh(px, w, h):
    return [[px[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)] for cy in range(h // 8) for cx in range(w // 8)]


def exact_palettes(tiles, limit):
    """The fewest palettes (4 colors each) holding every tile's colors exactly (the NES's: each tile inside one of
    its 16x16 palette areas), merged greedily; past the limit, the nearest (choose_palettes)."""
    sets = sorted({frozenset(key(c) for c in t) for t in tiles}, key=lambda s: (-len(s), sorted(s)))   # (ties: by color,
    if any(len(s) > 4 for s in sets):                                                                 # the same each run)
        return choose_palettes(tiles, limit)
    pals = []
    for s in sets:
        fit = [p for p in pals if s <= p] or [p for p in pals if len(p | s) <= 4]
        if fit:
            best = min(fit, key=lambda p: len(p | s))
            pals[pals.index(best)] = best | s
        else:
            pals.append(set(s))
    if len(pals) > limit:
        return choose_palettes(tiles, limit)
    out = []
    for p in pals:
        cols = sorted((list(map(int, k.split(","))) for k in p), key=lambda c: (-sum(c), c))
        out.append(cols + [cols[-1]] * (4 - len(cols)))
    return out


FULL_GREYS = {}


def _grey_levels(pals, tiles):
    """Each palette's slots as greys (0 white to 3 black) for the original Game Boy: the picture's colors split into
    4 by brightness (k-means, by use), each color the grey of its group."""
    lum = lambda c: 2 * c[0] + 4 * c[1] + c[2]
    use = {}
    for tl in tiles:
        for c in tl:
            use[tuple(c)] = use.get(tuple(c), 0) + 1
    vals = sorted({lum(v) for v in use})
    centers = [vals[int((len(vals) - 1) * q)] for q in (0, 1 / 3, 2 / 3, 1)]
    for _ in range(20):
        groups = [[] for _ in range(4)]
        for c, n in use.items():
            groups[min(range(4), key=lambda k: abs(lum(c) - centers[k]))].append((lum(c), n))
        centers = sorted(sum(l * n for l, n in g) / sum(n for _, n in g) if g else centers[k] for k, g in enumerate(groups))
    return [[3 - min(range(4), key=lambda k: abs(lum(c) - centers[k])) for c in p] for p in pals]


def _grey_slots(pals, tiles):
    """Palettes reordered so a color's slot is its grey on the original Game Boy (one map for every palette): the
    picture's colors split by brightness into 4 levels (by use, k-means), each palette's colors put at their
    level's slot (a clash moved to the nearest free one), a palette's unused slots its neighbors' colors."""
    lum = lambda c: 2 * c[0] + 4 * c[1] + c[2]
    use = {}
    for tl in tiles:
        for c in tl:
            use[tuple(c)] = use.get(tuple(c), 0) + 1
    vals = sorted(use, key=lum)
    cuts = [lum(vals[int(len(vals) * q)]) for q in (0.25, 0.5, 0.75)] if len(vals) >= 4 else [0, 0, 0]
    centers = sorted({lum(v) for v in vals})
    centers = [centers[int((len(centers) - 1) * q)] for q in (0, 1 / 3, 2 / 3, 1)]
    for _ in range(20):                                   # (k-means on brightness, weighted by use)
        groups = [[] for _ in range(4)]
        for c, n in use.items():
            groups[min(range(4), key=lambda k: abs(lum(c) - centers[k]))].append((lum(c), n))
        centers = [sum(l * n for l, n in g) / sum(n for _, n in g) if g else centers[k] for k, g in enumerate(groups)]
        centers.sort()
    level = lambda c: 3 - min(range(4), key=lambda k: abs(lum(c) - centers[k]))   # (0 lightest: slot 0 white)
    sets = [{tuple(c) for c in p} for p in pals]
    gslot = {}                                            # (each color one slot in every palette: the commonest
    mid = (centers[0] + centers[3]) / 2                   # first: the darkest and lightest, then the rest by use)
    for c in sorted({c for s in sets for c in s}, key=lambda c: (-abs(lum(c) - mid) // 40, -use.get(c, 0), c)):
        for d in (0, 1, -1, 2, -2, 3, -3):
            s = level(c) + d
            if 0 <= s < 4 and all(gslot.get(o) != s for st in sets if c in st for o in st if o != c):
                gslot[c] = s
                break
    out = []
    for p in pals:
        cols = sorted({tuple(c) for c in p}, key=lambda c: (lum(c), c), reverse=True)
        slots = [None] * 4
        for c in cols:
            want = gslot.get(c, level(c))
            for d in (0, 1, -1, 2, -2, 3, -3):
                s = want + d
                if 0 <= s < 4 and slots[s] is None:
                    slots[s] = c
                    break
        for s in range(4):                                # (unused: the nearest filled slot's color)
            if slots[s] is None:
                slots[s] = next(slots[s + d] for d in (1, -1, 2, -2, 3, -3) if 0 <= s + d < 4 and slots[s + d] is not None)
        out.append([list(c) for c in slots])
    return out


def _draw_wh(px, pals, w, h, cells_given=None):
    slots, cells = [0] * (w * h), []
    for k, tile in enumerate(_tiles_wh(px, w, h)):
        best = cells_given[k] if cells_given else min(range(len(pals)), key=lambda p: _tile_err(tile, pals[p]))
        cy, cx = divmod(k, w // 8)
        for n, c in enumerate(tile):
            y, x = cy * 8 + n // 8, cx * 8 + n % 8
            slots[y * w + x] = min(range(4), key=lambda q: dist(c, pals[best][q]))
        cells.append(best)
    return slots, cells


def full_portraits(palettes):
    """{name: {w, h, pixels, cells}} at the NES's size (each rival; "docmac": Doc and Mac, with its four "states"'
    pixels), their palettes added to the list given (cells index it)."""
    global _weight
    weight, _weight = _weight, lambda c: 1      # (at this size every color counts alike: skin as much as outlines)
    try:
        return _full_portraits(palettes)
    finally:
        _weight = weight


def _best_bg(imgs, k=3):
    """The k background palettes, and each tile's (one through every state), that leave the fewest tiles needing a
    sprite over them (then the fewest pixels): every choice of k from all 4-color sets, searched (a close-up has
    5-7 colors)."""
    import itertools
    cols = sorted({key(c) for img in imgs for row in img for c in row})
    at = {c: n for n, c in enumerate(cols)}
    per = [[[at[key(c)] for c in t] for t in _tiles_wh(img, FULL_W, FULL_H)] for img in imgs]
    subs = list(itertools.combinations(range(len(cols)), min(4, len(cols))))
    wrong = [[[sum(1 for c in t if c not in p) for t in ts] for ts in per] for p in subs]   # pal, state, tile
    score = [[sum((w[st][t] > 0) * 10000 + w[st][t] for st in range(len(per))) for t in range(len(per[0]))] for w in wrong]
    best = min(itertools.combinations(range(len(subs)), min(k, len(subs))),
               key=lambda ch: sum(min(score[p][t] for p in ch) for t in range(len(per[0]))))
    cells = [min(range(len(best)), key=lambda j: score[best[j]][t]) for t in range(len(per[0]))]
    lum = lambda c: -(2 * c[0] + 4 * c[1] + c[2])
    pals = [sorted((list(map(int, cols[n].split(","))) for n in subs[j]), key=lum) for j in best]
    return [p + [p[-1]] * (4 - len(p)) for p in pals], cells


def _overlay(imgs, pals, cells):
    """What the background can't show (a tile's colors past its palette's: the NES puts them in sprites), as 8x8
    sprites over those tiles, for each state: {"pals": their 3-color palettes, "states": [[x, y, pixels, pal]]}."""
    per = [_tiles_wh(img, FULL_W, FULL_H) for img in imgs]
    want = []                                           # (state, tile, {pixel: color}) for each sprite
    for st, ts in enumerate(per):
        for t, tl in enumerate(ts):
            have = {key(c) for c in pals[cells[t]]}
            px = {n: key(c) for n, c in enumerate(tl) if key(c) not in have}
            if px:
                want.append((st, t, px))
    sets = []                                           # (their palettes: each sprite's colors, merged to 3s)
    for cs in sorted({frozenset(px.values()) for _, _, px in want}, key=lambda q: (-len(q), sorted(q))):
        fit = [q for q in sets if cs <= q] or [q for q in sets if len(q | cs) <= 3]
        if fit:
            q = min(fit, key=len)
            sets[sets.index(q)] = q | cs
        else:
            sets.append(set(cs))
    order = [sorted(q) for q in sets]
    states = [[] for _ in imgs]
    for st, t, px in want:
        j = next(n for n, q in enumerate(order) if set(px.values()) <= set(q))
        pixels = "".join(str(order[j].index(px[n]) + 1) if n in px else "0" for n in range(64))
        states[st].append([t % (FULL_W // 8) * 8, t // (FULL_W // 8) * 8, pixels, j])
    return {"pals": [[list(map(int, c.split(","))) for c in q] for q in order], "states": states}


def _grey_of(pals, tiles):
    """Each color's grey on the original (0 white to 3 black): its group in _grey_levels's split by brightness."""
    lum = lambda c: 2 * c[0] + 4 * c[1] + c[2]
    use = {}
    for tl in tiles:
        for c in tl:
            use[tuple(c)] = use.get(tuple(c), 0) + 1
    vals = sorted({lum(v) for v in use})
    centers = [vals[int((len(vals) - 1) * q)] for q in (0, 1 / 3, 2 / 3, 1)]
    for _ in range(20):
        groups = [[] for _ in range(4)]
        for c, n in use.items():
            groups[min(range(4), key=lambda k: abs(lum(c) - centers[k]))].append((lum(c), n))
        centers = sorted(sum(l * n for l, n in g) / sum(n for _, n in g) if g else centers[k] for k, g in enumerate(groups))
    return lambda c: 3 - min(range(4), key=lambda k: abs(lum(c) - centers[k]))


def _overlay_dmg(imgs, pals, cells):
    """The original's: where its greys of the background differ from each color's own, as 8x8 sprites for each
    state: [[x, y, pixels, palette]] -- palette 0 the background's greys (1-3), 1 with white for 1 (and 2, 3)."""
    tiles = [t for img in imgs for t in _tiles_wh(img, FULL_W, FULL_H)]
    grey = _grey_of(pals, tiles)
    near = lambda p, c: min(p, key=lambda q: sum((a - b) ** 2 for a, b in zip(q, c)))
    states = []
    for img in imgs:
        out = []
        for t, tl in enumerate(_tiles_wh(img, FULL_W, FULL_H)):
            want = [grey(c) if grey(near(pals[cells[t]], c)) != grey(c) else None for c in tl]
            x, y = t % (FULL_W // 8) * 8, t // (FULL_W // 8) * 8
            if any(w == 0 for w in want) and not any(w == 1 for w in want):     # (white with 2s and 3s: one sprite)
                out.append([x, y, "".join("1" if w == 0 else str(w) if w else "0" for w in want), 1])
                continue
            if any(w for w in want):
                out.append([x, y, "".join(str(w) if w else "0" for w in want), 0])
            if any(w == 0 for w in want):
                out.append([x, y, "".join("1" if w == 0 else "0" for w in want), 1])
        states.append(out)
    return states


def _full_portraits(palettes):
    out = {}
    docs = doc_states()
    talks = {r: rival_talk(NES_RIVALS[r]["opp"]) for r in NES_RIVALS}
    groups = [("docmac", docs)] + [(r, [full_rival(NES_RIVALS[r]["opp"])] + list(talks[r][:2] if talks[r] else ())) for r in NES_RIVALS]
    for name, imgs in groups:
        pals, cells = _best_bg(imgs, 3)     # (3 each: with the text's and the round card's, a screen's 8)
        tiles = [t for img in imgs for t in _tiles_wh(img, FULL_W, FULL_H)]
        for k, g in enumerate(_grey_levels(pals, tiles)):    # (each slot's grey on the original, this picture's:
            FULL_GREYS[len(palettes) + k] = g                #  the scene's tiles put in them as it loads there)
        drawn = [_draw_wh(img, pals, FULL_W, FULL_H, cells) for img in imgs]
        entry = {"w": FULL_W, "h": FULL_H, "pixels": "".join(map(str, drawn[0][0])),
                 "cells": "".join(_cell(len(palettes) + c) for c in cells)}
        if name == "docmac":
            entry["states"] = ["".join(map(str, s)) for s, _ in drawn]
        elif talks[name]:                   # (his corner: talking, his two states and their frames)
            entry["talk"] = {"states": ["".join(map(str, s)) for s, _ in drawn[1:]], "time": list(talks[name][2])}
        entry["overlay"] = _overlay(imgs, pals, cells)   # (Color: the rest of his colors, as sprites)
        entry["overlay"]["dmg"] = _overlay_dmg(imgs, pals, cells)     # (the original: the rest of his greys)
        out[name] = entry
        palettes += pals
    return out


_cell = lambda k: str(k) if k < 10 else chr(65 + k - 10) if k < 36 else chr(0xC0 + k - 36)   # a tile's palette: 0-9,
                                                                                          # A-Z, then À on

def portraits():
    """({name: {pixels, cells}}, palettes): cells are digits, each tile's palette in the returned list."""
    faces = {name: portrait(name) for name in list(PORTRAITS) + [r for r in NES_RIVALS if r not in PORTRAITS]}
    out, palettes = {}, []
    for fighter, names in (("joe", ["joe", "joe_hurt"]), ("mac", ["mac"]), *((r, [r]) for r in NES_RIVALS if r != "joe")):
        pals = choose_palettes([t for n in names for t in _tiles(faces[n])], PORTRAIT_PALETTES[fighter])
        for n in names:
            slots, cells = _draw(faces[n], pals)
            out[n] = {"pixels": "".join(map(str, slots)), "cells": "".join(_cell(len(palettes) + c) for c in cells)}
        palettes += pals
    full = full_portraits(palettes)
    return out, palettes, full


# ---- output ----

def write_preview(path, poses, pals, colors, pposes, zoom=3):
    """What the game will show: every rival pose, then every player pose, in Game Boy Color colors."""
    rgb = lambda c: tuple((v << 3) | (v >> 2) for v in c) + (255,)
    mat = rgb(pals[0][0]); n = len(poses); cols = 6
    cw, chh = RW + 4, RH + 4
    W = max(cols * cw, len(PLAYER_POSES) * (PW + 4)); H = ((n + cols - 1) // cols) * chh + PH + 8
    img = [[(255, 255, 255, 255)] * W for _ in range(H)]
    for k, (name, p) in enumerate(poses.items()):
        ox, oy = (k % cols) * cw, (k // cols) * chh
        for y in range(RH):
            for x in range(RW):
                kind = "sgh".index(p["cells"][(y // 8) * FIGHT_W + x // 8]); v = ord(p["pixels"][y * RW + x]) - 48
                img[oy + y][ox + x] = rgb(pals[kind][v]) if v else mat
    oy = ((n + cols - 1) // cols) * chh + 4
    for k, name in enumerate(PLAYER_POSES):
        for y in range(PH):
            for x in range(PW):
                v = ord(pposes[name][y * PW + x]) - 48
                img[oy + y][k * (PW + 4) + x] = rgb(colors[v - 1]) if v else mat
    big = [[c for c in row for _ in range(zoom)] for row in img for _ in range(zoom)]
    png.write(path, W * zoom, H * zoom, big)

# Glass Joe's brain: the NES game's own fighter bank (state scripts, AI, round timeline; see gbstage/kit_nes.asm),
# from the disassembly clone, and which of our poses shows each of its frame numbers (by what the scripts use
# them for: $C0-$C4 the idle bob, $08/$0A guard high/low, $0E the jab, $16-$1A the hook, $1C-$24 hits...).
import gamefiles
DISASM_BANK = gamefiles.banks() / "PRG_Bank000.bin"      # your copy of the game (gamefiles.py)
# Audited against the game's own drawing (nes_frames.py renders each frame from the real fight; audit_sheet.py
# sets them beside these): 06 and 82 stand, 80 guards high, 3A is his glove raised (his intro, and taunting).
# Down: 28 the fall (the spin, legs up), 2A on the mat for the count, 2C/2E up on his hands, 30/32 bent over after.
NES_FRAMES = {
    "00": "idle", "C0": "idle", "02": "idle2", "C2": "idle2", "04": "idle3", "C4": "idle3", "06": "idle",
    "08": "guard", "0A": "guard_low", "0C": "dazed", "0E": "jab", "10": "guard_low", "12": "guard", "14": "guard",
    "C6": "guard", "16": "hook_tell", "18": "hook", "1A": "hook_mid", "1C": "hit_body", "1E": "hit_r",
    "20": "hit_r", "22": "hit_l", "24": "hit_back", "C8": "guard", "CA": "guard", "CC": "jab_tell",   # (0C: his
                                                                   # stunned face, just before he goes down)
    "80": "tell2", "82": "tell1", "84": "slip", "86": "jab_mid", "26": "kd_stagger", "28": "kd_fall",
    "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel", "3A": "taunt",   # (82, 80: his taunting bob, state $19)
    "30": "kd2_stagger", "32": "kd2_fall", "34": "kd2_down", "36": "kd2_kneel", "38": "kd2_kneel",   # his other way
    "30|": "kd2_stagger", "32|": "kd2_fall", "34|": "kd2_down", "36|": "kd2_kneel", "38|": "kd2_kneel",   # down
    "1E|": "hit_l", "20|": "hit_l", "22|": "hit_r",      # mirrored ($A2): the hit from the other side
}

# Little Mac's NES frames (recorded by running his own scripts, PRG bank B) -> our player poses; "|" marks
# the mirrored (right-hand / rightward) ones. Left punches and leftward dodges are the poses as drawn.
DISASM_MAC = DISASM_BANK.with_name("PRG_Bank00B.bin")
MAC_FRAMES = {
    **{k: "idle" for k in ("00", "01", "58", "54", "12", "13", "1C")}, "05": "duck",     # (05: his duck)
    **{k: "dodge" for k in ("08", "09", "0A", "60", "07")}, **{k: "dodge|" for k in ("0B", "0C", "61", "0D")},  # (the art is 0A)
    **{k: "block" for k in ("5F", "5E", "06", "23", "24")},
    **{k: "jab_tell" for k in ("0E", "0F")}, "14": "jab_tell|",                        # (his jab wound up, then out:
    **{k: "jab" for k in ("10", "11")}, **{k: "jab|" for k in ("15", "16")},           # 11, 16 its full reach)
    **{k: "high_tell" for k in ("17", "18")}, **{k: "high_tell|" for k in ("1D", "1E")},   # (to the face: wound up,
    "19": "jab_high", "1F": "jab_high|",                                               # then up)
    **{k: "star" for k in ("25", "26", "27", "28")}, "29": "star2", "2A": "star3",     # the star punch: wound up,
    **{k: "star4" for k in ("2B", "2C", "2D", "2E")},                                  # rising, the uppercut, after
    **{k: "hit" for k in ("2F", "30", "33")}, **{k: "hit|" for k in ("31", "32", "34")},
    "3B": "knocked", "3A": "down",                          # his knockdown: knocked back, facing us (3A: the count's
                                                            # sliver of him at the screen's edge: out of view),
    **{f"{k:02X}": "down" for k in range(0x3C, 0x44)},     # then sinking below the screen's edge (40-43: gone),
    **{f"{k:02X}": "idle" for k in range(0x44, 0x48)},     # and back up from behind, rising into view
    "48": "idle",                                           # (its top, $48, is him standing: the intro, and up)
    "55": "win", "56": "win", "57": "win",                  # he's won: turned to the camera, gloves up
    "19": "jab_high", "1A": "jab_high", "1B": "jab_high", "1F": "jab_high|", "20": "jab_high|", "21": "jab_high|",   # his punch to the face, all the way up
    "35": "knocked|", **{f"{k:02X}": "down" for k in range(0x36, 0x3A)},      # his other knockdown: back, then sinking
    **{f"{k:02X}": "idle" for k in range(0x49, 0x54)},     # the round's start: up into view from below
    "04": "duck",                                           # (his duck: crouched, head down)
}
# ... where those frames sit (pixels down: the NES draws them lower each frame, cut off at the screen's
# bottom; 48 is all the way under) and in his knockdown colors, pink (NES $25), green ($2A), dark ($08):
# the colors he flashes whenever he's hit.
MAC_PLACES = {**{f"{k:02X}": 0 for k in range(0x2F, 0x35)},          # (hit, he shows the same colors)
              "3A": 48, "3B": 0, "3C": 0, "3D": 6, "3E": 11, "3F": 17, "40": 48, "41": 48, "42": 48, "43": 48,
              "44": 33, "45": 30, "46": 25, "47": 19,
              "35": 0, "36": 0, "37": 6, "38": 11, "39": 17}
MAC_LIFTS = {"49": 13, "4A": 10, "4B": 8, "4C": 5, "4D": 2,          # rising into view, in his own colors
             "04": 8}                                              # (ducked)
MAC_DOWN_INK = [(32, 42, 0), (76, 208, 32), (236, 88, 180)]  # for MAC_INK's black, greens and skin
MAC_TIRED_INK = [(0, 0, 0), (90, 205, 78), (136, 20, 176)]  # worn out: his skin NES $14 (the game's $048E)

# ---- the title: Punch-Out!!'s logo from the game's own title screen ----

NES_TITLE = HERE / "out" / "nes-title.png"
LOGO_W, LOGO_H = 160, 48                # a full-width band, 6 tiles
LOGO_MESH, LOGO_HOLE = (48, 50, 236), (0, 0, 0)
LOGO_TOP, LOGO_BOTTOM = (212, 136, 32), (152, 34, 32)

LOGO_FIT = {}                           # how title_logo() placed the NES letters: their corner, scale, offset

def title_logo():
    """The "PUNCH-OUT!!" letters off the NES title screen (booted in cpu6502, nes_boot.py), shrunk to fit the
    GB's width, over the title's blue mesh redrawn at GB pixels (a 3-pixel grid would smear if scaled).
    Slots: 0 the holes (black), 1 the mesh, 2 the letters' orange tops, 3 their red bottoms."""
    if not NES_TITLE.exists():
        import nes_boot
        b = nes_boot.Boot()
        b.run(700)
        nes_boot.save(b.render(sprites=False), str(NES_TITLE))
    _, _, px = png.read(NES_TITLE)
    letters = {LOGO_TOP, LOGO_BOTTOM}
    pts = [(x, y) for y in range(40, 132) for x in range(230) if px[y][x][:3] in letters]   # (not the ®)
    x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
    y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
    f = [[px[y][x] if px[y][x][:3] in letters and x < 230 else None for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)]
    s = (LOGO_W - 8) / len(f[0])
    small = scale(f, s, outline_weight=1.0)
    h, w = len(small), len(small[0])
    ox, oy = (LOGO_W - w) // 2, (LOGO_H - h) // 2
    LOGO_FIT.update(x0=x0, y0=y0, s=s, ox=ox, oy=oy)
    out = []
    for y in range(LOGO_H):
        for x in range(LOGO_W):
            c = small[y - oy][x - ox] if 0 <= y - oy < h and 0 <= x - ox < w else None
            if c:
                out.append(2 if c[:3] == LOGO_TOP else 3)
            else:
                edge = y == 0 or y == LOGO_H - 1        # (the mesh 46 rows, every cell whole, a dark row over and under)
                out.append(0 if edge else 1 if x % 3 == 0 or (y - 1) % 3 == 0 else 0)
    to5 = lambda c: [round(v * 31 / 255) for v in c]
    return {"w": LOGO_W, "h": LOGO_H, "pixels": "".join(map(str, out)),
            "colors": [to5(LOGO_HOLE), to5(LOGO_MESH), to5(LOGO_TOP), to5(LOGO_BOTTOM)]}


# ---- the first screen ----
# Punch-Out!!'s power-on screen, MIKE IS WAITING FOR YOUR CHALLENGE!!, from the game's own pixels at 1:1: its
# MIKE TYSON pattern (8 tiles, a tile further left each row), his framed portrait centered (just 8 rows of its
# blue padding over his head left out, to fit 144 lines), and its black box under it, as the game has it, with
# the big green MIKE TYSON and the two lines (spaced by the pixel inside the box: one palette there). His face
# gets 6 of the scene's 8 palettes, the pattern and the box one each.

SPLASH_W, SPLASH_H = 160, 144
SPLASH_FRAME = (88, 48, 167, 127)             # the portrait's 1-pixel white frame on the NES screen
SPLASH_TRIM = (6, 2)                          # rows of its inside left out: over his head (blue), under (chest)
SPLASH_FACE_PALETTES = 6
SPLASH_FRAMES = 390                           # up, as the game holds it (frame 138 to its fade at 528)
SPLASH_MUSIC = 0x02                           # the song the game starts with it (on into the title)
SPLASH_BELLS = {"sfx": 0x0C, "at": [0, 13, 26, 40, 82, 96, 109, 123], "frames": 132}   # before it, over black: its
                                              # bell, twice four rings (the frames the game rings them, from the first)

def splash():
    import nes_play
    img = [[tuple(px)[:3] for px in row] for row in nes_play.splash_screen()]
    NAVY, BLUE, BLACK = img[16][0], None, (0, 0, 0)
    out = [[NAVY] * SPLASH_W for _ in range(SPLASH_H)]
    kind = [[None] * (SPLASH_W // 8) for _ in range(SPLASH_H // 8)]      # per tile: 'p'attern, 'f'ace, 'b'ox
    # the pattern: the NES tile with the same place in its 8-tile run (rows 1-5 there are all pattern)
    src = {}
    for R in range(1, 6):
        for C in range(1, 32):
            src.setdefault((C - R) % 8, (R, C))
    for r in range(SPLASH_H // 8):
        for c in range(SPLASH_W // 8):
            R, C = src[(c - r + 3) % 8]                # (its phase: MIKE TYSON whole beside his portrait)
            for y in range(8):
                for x in range(8):
                    out[r * 8 + y][c * 8 + x] = img[R * 8 + y][C * 8 + x]
            kind[r][c] = "p"
    # his portrait: frame, inside less the trim, frame; centered, from line 8
    x0, y0, x1, y1 = SPLASH_FRAME
    top, bottom = SPLASH_TRIM
    rows = [y0] + list(range(y0 + 1 + top, y1 - bottom)) + [y1]
    fx, fy = (SPLASH_W - (x1 - x0 + 1)) // 2, 8
    for k, y in enumerate(rows):
        for x in range(x0, x1 + 1):
            out[fy + k][fx + x - x0] = img[y][x]
    for r in range(fy // 8, (fy + len(rows)) // 8):
        for c in range(fx // 8, (fx + x1 - x0 + 1) // 8):
            kind[r][c] = "f"
    # the box: black, the rest of the screen under him
    by = fy + len(rows)
    for y in range(by, SPLASH_H):
        out[y] = [BLACK] * SPLASH_W
        for c in range(SPLASH_W // 8): kind[y // 8][c] = "b"
    def ink(y0, y1, xa, xb):                       # a run of the NES's lines: its inked columns' extent
        cols = [x for x in range(xa, xb) if any(img[y][x] != BLACK for y in range(y0, y1))]
        return cols[0], cols[-1] + 1
    def put(y0, y1, at_y, tighten=0):               # centered by its ink; its word gaps narrowed by `tighten`
        a, b = ink(y0, y1, 40, 216)
        blank = [all(img[y][x] == BLACK for y in range(y0, y1)) for x in range(a, b)]
        cols, run = [], []
        for k, x in enumerate(range(a, b)):
            if blank[k]:
                run.append(x); continue
            cols += run[tighten:] if len(run) >= 5 else run      # (a word's gap: 5 blank columns or more)
            run = []
            cols.append(x)
        ox = (SPLASH_W - len(cols)) // 2
        assert len(cols) <= SPLASH_W, "a line wider than the screen"
        for y in range(y0, y1):
            for k, x in enumerate(cols):
                out[at_y + y - y0][ox + k] = img[y][x]
        return len(cols)
    big = (136, 168)                                # MIKE / TYSON, then the two lines (NES rows 22, 24)
    gap = (SPLASH_H - by - 32 - 16) // 4            # the box's space, even: over, between, between, under
    put(*big, by + gap)
    put(176, 184, by + gap + 32 + gap, 3)
    w2 = put(192, 200, by + gap + 32 + gap + 8 + gap, 3)
    head = next(y for y in range(y0 + 1, y1) if any(img[y][x] not in (img[y0 + 2][x0 + 2],) for x in range(x0 + 1, x1)))
    print(f"    splash: his head {head - y0 - 1 - top} lines under the frame, the box's spacing {gap}, its last line {w2} wide")
    # palettes: the pattern's (letters slot 2, its navy 3: dark on the original), the box's, his face's
    pc = lambda c: from8(c)
    letters = next(c for row in out[:8] for c in row if c != NAVY)
    pat = [pc(letters), pc(letters), pc(letters), pc(NAVY)]
    box_colors = sorted({c for row in out[by:] for c in row} - {BLACK}, key=lambda c: -lum(pc(c)))
    assert len(box_colors) <= 3, box_colors
    box = [pc(c) for c in box_colors] + [pc(BLACK)] * (4 - len(box_colors))
    box = box[:3] + [pc(BLACK)] if len(box_colors) == 3 else box
    face_tiles = [[pc(out[r * 8 + y][c * 8 + x]) for y in range(8) for x in range(8)]
                  for r in range(SPLASH_H // 8) for c in range(SPLASH_W // 8) if kind[r][c] == "f"]
    faces = choose_palettes(face_tiles, SPLASH_FACE_PALETTES)
    # each color a slot of its own across his palettes, so the original's grays agree from tile to tile: the blue
    # behind him (and the frame and his teeth, where there's room) lightest, then his brown, dark brown, black
    shade = {key(pc(c)): t for c, t in ((img[y0 + 2][x0 + 2], 0), ((236, 238, 236), 0), ((120, 60, 0), 1), ((60, 24, 0), 2), (BLACK, 3))}
    count = {}
    for t in face_tiles:
        for col in t: count[key(col)] = count.get(key(col), 0) + 1
    import itertools
    def order(pal):
        cs = list({key(c): c for c in pal}.values())
        cs += [None] * (4 - len(cs))
        best = min(itertools.permutations(cs), key=lambda perm: sum(count.get(key(c), 0) * (n - shade.get(key(c), n)) ** 2
                                                                    for n, c in enumerate(perm) if c))
        return [list(c) if c else [31, 0, 31] for c in best]     # (a slot none of his pixels use)
    faces = [order(f) for f in faces]
    palettes = [pat, box] + faces
    pixels, cells = [0] * (SPLASH_W * SPLASH_H), []
    for r in range(SPLASH_H // 8):
        for c in range(SPLASH_W // 8):
            tile = [pc(out[r * 8 + y][c * 8 + x]) for y in range(8) for x in range(8)]
            k = kind[r][c]
            best = 0 if k == "p" else 1 if k == "b" else 2 + min(range(len(faces)), key=lambda p: _tile_err(tile, faces[p]))
            pal = palettes[best]
            for n, col in enumerate(tile):
                v = (2 if col != pal[3] else 3) if k == "p" else min(range(4), key=lambda q: dist(col, pal[q]))
                pixels[(r * 8 + n // 8) * SPLASH_W + c * 8 + n % 8] = v
            cells.append(best)
    return {"pixels": "".join(map(str, pixels)), "cells": "".join(map(str, cells)), "palettes": palettes,
            "frames": SPLASH_FRAMES, "music": SPLASH_MUSIC, "bells": SPLASH_BELLS}


# ---- the ending ----
# After Mike Tyson, as the game has it: his word to Mac under his portrait, then each fighter's portrait and name
# in turn (the ten of them, no rematches), then Mac standing on blue (the game's own picture, 1:1) with his record
# and THE END typed under him. Its song plays from the first.
ENDING_BOX = (108, 50, 156, 154)              # Mac on the game's last screen (a tile-whole crop around him)
ENDING_MUSIC = 0x1F

def ending():
    import nes_play
    img = [[tuple(px)[:3] for px in row] for row in nes_play.ending_screen()]
    navy = img[5][5]
    x0, y0, x1, y1 = ENDING_BOX
    w, h = x1 - x0, y1 - y0
    pc = lambda c: from8(c)
    tiles = []
    for ty in range(h // 8):
        for tx in range(w // 8):
            px = [img[y0 + ty * 8 + y][x0 + tx * 8 + x] for y in range(8) for x in range(8)]
            count = {c: px.count(c) for c in set(px) - {navy}}
            tiles.append(set(sorted(count, key=lambda c: -count[c])[:3]))   # (a fourth: its nearest, below)
    pals = []                                   # each: navy, then up to 3 colors (dark to light, for the original)
    for cs in sorted(tiles, key=len, reverse=True):
        if not cs or any(cs <= set(p) for p in pals):
            continue
        fit = next((p for p in pals if len(set(p) | cs) <= 3), None)
        if fit is not None:
            pals[pals.index(fit)] = sorted(set(fit) | cs, key=lambda c: -lum(pc(c)))
        else:
            pals.append(sorted(cs, key=lambda c: -lum(pc(c))))
    assert len(pals) <= 4, len(pals)
    pixels, cells = [], []
    for ty in range(h // 8):
        for tx in range(w // 8):
            cs = tiles[ty * (w // 8) + tx]
            k = next((i for i, p in enumerate(pals) if cs <= set(p)), 0)
            cells.append(k)
    for y in range(h):
        for x in range(w):
            c = img[y0 + y][x0 + x]
            p = pals[cells[(y // 8) * (w // 8) + x // 8]]
            pixels.append(0 if c == navy else 1 + min(range(len(p)), key=lambda i: dist(pc(c), pc(p[i]))))
    palettes = [[pc(navy)] + [pc(c) for c in p] + [pc(navy)] * (3 - len(p)) for p in pals]
    return {"mac": {"w": w, "h": h, "pixels": "".join(map(str, pixels)), "cells": "".join(map(str, cells)),
                    "palettes": palettes}, "navy": pc(navy), "music": ENDING_MUSIC,
            "tyson": ["MIKE TYSON:", '"GREAT FIGHTING!!', "YOU WERE TOUGH, MAC!", "I'VE NEVER SEEN", "SUCH FINGER SPEED",
                      'BEFORE."'],
            "frames": {"word": 480, "portrait": 280}}


# ---- game over ----
# The third loss, as the game has it: Mac on his stool, head down, a line across behind him, "GIVE UP?" and "RETIRE?"
# either side, then GAME OVER and Doc's "START TRAINING / MAKE A COMEBACK!". Mac 1:1 from the game's own screen
# (cynes, losing three times), his tile-whole crop.
GAME_OVER_BOX = (110, 44, 150, 140)           # Mac and his stool (x0, y0, x1, y1), 5x12 tiles
GAME_OVER_LINE = 114                          # the line's row on the NES screen
GAME_OVER_CACHE = HERE / "out" / "game-over.pkl"

def game_over_screen():
    import pickle
    if GAME_OVER_CACHE.exists():
        return pickle.load(open(GAME_OVER_CACHE, "rb"))
    import cynes_frames as C
    from cynes import NES
    nes = NES(C.rom_path())
    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):
        run(4, C.START); run(86)
        if nes[0x00] == 1:
            break
    for n in range(40000):              # three losses (his health gone each fight), then his screen
        if nes[0x00] == 1:
            nes[0x391] = 0
        losses = nes[0x173]
        run(1, C.START if nes[0x00] != 1 and n % 120 < 3 and losses < 3 else 0)
        if losses == 3 and nes[0x173] == 3:
            break
    f = run(400)
    img = [[tuple(int(v) for v in f[y][x]) for x in range(256)] for y in range(240)]
    pickle.dump(img, open(GAME_OVER_CACHE, "wb"))
    return img

def game_over():
    img = game_over_screen()
    bg = img[5][5]
    x0, y0, x1, y1 = GAME_OVER_BOX
    w, h = x1 - x0, y1 - y0
    pc = lambda c: from8(c)
    tiles = []
    for ty in range(h // 8):
        for tx in range(w // 8):
            px = [img[y0 + ty * 8 + y][x0 + tx * 8 + x] for y in range(8) for x in range(8)]
            count = {c: px.count(c) for c in set(px) - {bg}}
            tiles.append(set(sorted(count, key=lambda c: -count[c])[:3]))
    pals = []                                   # as the ending's: the background, then up to 3 colors
    for cs in sorted(tiles, key=len, reverse=True):
        if not cs or any(cs <= set(p) for p in pals):
            continue
        fit = next((p for p in pals if len(set(p) | cs) <= 3), None)
        if fit is not None:
            pals[pals.index(fit)] = sorted(set(fit) | cs, key=lambda c: -lum(pc(c)))
        else:
            pals.append(sorted(cs, key=lambda c: -lum(pc(c))))
    assert len(pals) <= 6, len(pals)             # (the scene's text takes a seventh)
    pixels, cells = [], []
    for ty in range(h // 8):
        for tx in range(w // 8):
            cs = tiles[ty * (w // 8) + tx]
            cells.append(next((i for i, p in enumerate(pals) if cs <= set(p)), 0))
    for y in range(h):
        for x in range(w):
            c = img[y0 + y][x0 + x]
            p = pals[cells[(y // 8) * (w // 8) + x // 8]]
            pixels.append(0 if c == bg else 1 + min(range(len(p)), key=lambda i: dist(pc(c), pc(p[i]))))
    palettes = [[pc(bg)] + [pc(c) for c in p] + [pc(bg)] * (3 - len(p)) for p in pals]
    return {"mac": {"w": w, "h": h, "pixels": "".join(map(str, pixels)), "cells": "".join(map(str, cells)),
                    "palettes": palettes}, "bg": pc(bg), "line": GAME_OVER_LINE - y0,
            "left": "GIVE UP?", "right": "RETIRE?", "over": "GAME OVER",
            "doc": ['"START TRAINING', 'MAKE A COMEBACK!"'], "music": None}


NES_TITLE_START = HERE / "out" / "title-start.pkl"

def title_punch(logo_y):
    """The title's answer to Start, as the NES game plays it (booted in cpu6502 with Start pressed): its glove,
    behind the logo (seen through the mesh's holes) flashing red, then punching out in front while the screen
    lights up, then everything fading to black. Steps: per run of identical frames, the glove's colors (or
    hidden), in front or not, the logo's 4 colors and the backdrop's."""
    import pickle, nes_boot
    if not NES_TITLE_START.exists():
        b = nes_boot.Boot()
        b.run(600)
        frames = []
        for _ in range(240):
            b.run(1, lambda fr: 0x10 if 605 <= fr < 609 else 0)
            frames.append({'f': b._booted, 'spr': [tuple(b.oam[i * 4:i * 4 + 4]) for i in range(64) if b.oam[i * 4] < 0xEF],
                           'pal': bytes(b.pal), 'chr': dict(b.chr)})
        pickle.dump(frames, open(NES_TITLE_START, "wb"))
    frames = pickle.load(open(NES_TITLE_START, "rb"))
    glove = lambda fr: [s for s in fr['spr'] if 88 <= s[3] < 152 and s[0] < 110]     # (not the menu's gloves)
    # the glove: drawn from its in-front frame, slots as the NES's colors 1-3
    fr = next(fr for fr in frames if any(not s[2] & 0x20 for s in glove(fr)))
    data = nes_boot.CHR[fr['chr'][0xC000]]
    sp = glove(fr)
    gx0, gy0 = min(s[3] for s in sp), min(s[0] for s in sp) + 1
    gw, gh = max(s[3] for s in sp) + 8 - gx0, max(s[0] for s in sp) + 9 - gy0
    SLOT = [None, (255, 0, 0, 255), (255, 255, 255, 255), (0, 0, 0, 255)]
    img = [[None] * gw for _ in range(gh)]
    for sy, t, a, sx in sp:
        d = data[t * 16:t * 16 + 16]
        for y in range(8):
            for x in range(8):
                yy, xx = (7 - y if a & 0x80 else y), (7 - x if a & 0x40 else x)
                v = ((d[yy] >> (7 - xx)) & 1) | (((d[yy + 8] >> (7 - xx)) & 1) << 1)
                if v: img[sy + 1 - gy0 + y][sx - gx0 + x] = SLOT[v]
    fit = LOGO_FIT
    small = scale(img, fit['s'])
    w8, h8 = (len(small[0]) + 7) // 8 * 8, (len(small) + 7) // 8 * 8
    px = "".join(str(SLOT.index(small[y][x]) if y < len(small) and x < len(small[0]) and small[y][x] else 0)
                 for y in range(h8) for x in range(w8))
    sprite = {"w": w8, "h": h8, "pixels": px,
              "x": round(fit['ox'] + (gx0 - fit['x0']) * fit['s']), "y": round(logo_y + fit['oy'] + (gy0 - fit['y0']) * fit['s'])}
    # the steps, from the press to black
    rgb5 = lambda v: [round(c * 31 / 255) for c in nes_boot.NES_RGB[v & 0x3F]]
    def state(fr):
        p, g = fr['pal'], glove(fr)
        shown = any(v & 0x3F != 0x0F for v in p[17:20])
        return (tuple(tuple(rgb5(v)) for v in p[17:20]) if shown else None,
                any(not s[2] & 0x20 for s in g),
                tuple(tuple(rgb5(v)) for v in (p[0], p[1], p[13], p[14])))
    run = [fr for fr in frames if fr['f'] >= 609]
    black = lambda p: all(p[k] & 0x3F == 0x0F for k in (0, 1, 13, 14, 17, 18, 19))
    end = next(k for k, fr in enumerate(run) if black(fr['pal'])) + 1
    steps = []
    for fr in run[:end]:
        st = state(fr)
        if steps and steps[-1][0] == st and steps[-1][1] < 255:
            steps[-1][1] += 1
        else:
            steps.append([st, 1])
    out = [{"frames": n, "colors": [list(c) for c in st[0]] if st[0] else None, "front": st[1],
            "logo": [list(c) for c in st[2]], "backdrop": list(st[2][0])} for st, n in steps]
    # its sounds, as the game asks for them after Start: the intro punch twice, the glove through the logo
    at = 4                                  # (the press began 4 frames before the first step)
    for st in out:
        for when, sfx in ((8, 0x01), (44, 0x01), (76, 0x18)):
            if at <= when < at + st["frames"]:
                st["nesSfx"] = sfx
        at += st["frames"]
    return {"sprite": sprite, "steps": out}


def lose_glove(s=40 / 56):
    """The big glove on the NES's "YOU LOST!" screen: the title's, as it first shows behind the logo (it's the
    same picture), whole, scaled by s (to 5 tiles wide). Slots: the NES's colors 1-3 (dark red, light red, black)."""
    import pickle, nes_boot
    title_punch(24)                         # (records the title's frames, the first time)
    frames = pickle.load(open(NES_TITLE_START, "rb"))
    glove = lambda fr: [s_ for s_ in fr['spr'] if 88 <= s_[3] < 152 and s_[0] < 110]
    fr = next(fr for fr in frames if glove(fr))
    data = nes_boot.CHR[fr['chr'][0xC000]]
    sp = glove(fr)
    gx0, gy0 = min(t[3] for t in sp), min(t[0] for t in sp) + 1
    gw, gh = max(t[3] for t in sp) + 8 - gx0, max(t[0] for t in sp) + 9 - gy0
    SLOT = [None, (255, 0, 0, 255), (255, 255, 255, 255), (0, 0, 0, 255)]
    img = [[None] * gw for _ in range(gh)]
    for sy, t, a, sx in sp:
        d = data[t * 16:t * 16 + 16]
        for y in range(8):
            for x in range(8):
                yy, xx = (7 - y if a & 0x80 else y), (7 - x if a & 0x40 else x)
                v = ((d[yy] >> (7 - xx)) & 1) | (((d[yy + 8] >> (7 - xx)) & 1) << 1)
                if v: img[sy + 1 - gy0 + y][sx - gx0 + x] = SLOT[v]
    small = scale(img, s)
    w, h = len(small[0]), len(small)
    return {"w": w, "h": h, "pixels": "".join(str(SLOT.index(c) if c else 0) for row in small for c in row)}


def title_gloves():
    """The title's gloves, a pair either side of the chosen item (the NES game's sprites $EC-$F1, its palette
    1), as they're up before Start: the left one, 24x16 (the right is it mirrored). Slots: 1 white, 2 red, 3 black
    (light to dark, for the original's grays). gap: from CONTINUE's letters; dy: over the item's row."""
    import pickle, nes_boot
    frames = pickle.load(open(NES_TITLE_START, "rb"))      # (title_punch records them)
    left = lambda fr: [t for t in fr['spr'] if 236 <= t[1] <= 241 and not t[2] & 0x40 and t[2] & 3 == 1]
    fr = next(fr for fr in frames if left(fr))
    data, sp = nes_boot.CHR[fr['chr'][0xC000]], left(fr)
    x0, y0 = min(t[3] for t in sp), min(t[0] for t in sp)
    px = [[0] * 24 for _ in range(16)]
    for sy, t, a, sx in sp:
        d = data[t * 16:t * 16 + 16]
        for y in range(8):
            for x in range(8):
                v = ((d[y] >> (7 - x)) & 1) | (((d[y + 8] >> (7 - x)) & 1) << 1)
                px[sy - y0 + y][sx - x0 + x] = (0, 2, 1, 3)[v]
    rgb5 = lambda v: [round(c * 31 / 255) for c in nes_boot.NES_RGB[v & 0x3F]]
    pal = fr['pal'][16 + 4:16 + 8]
    return {"w": 24, "h": 16, "pixels": "".join(str(v) for row in px for v in row),
            "colors": [rgb5(pal[2]), rgb5(pal[1]), rgb5(0x0F)], "gap": 96 - (x0 + 24), "dy": -4}


# Little Mac's poses from the NES game's own frames (mac_nes.py draws them as bank B does); the rest from the rip.
MAC_NES = dict(idle=0x00, jab=0x10, jab_high=0x1A, dodge=0x0A, block=0x5F, hit=0x2F, down=0x3C, win=0x55,
               star=0x25, star2=0x29, star3=0x2A, star4=0x2B,   # (the star punch: wound up, rising, the uppercut, after)
               jab_tell=0x0E, high_tell=0x18, knocked=0x3B, duck=0x04)   # (wind-ups, knocked back, ducking)
# ($18 draws as $10, his body jab; his punch to the face is $19-$1B, arm straight up: taller than the 24x48
# frame at his scale, so its forearm is shortened, a few rows of it, to fit.)
MAC_INK = [(0, 0, 0), (90, 205, 78), (247, 206, 195)]       # black, his greens, skin (the rip's, as the palette)

def mac_from_nes(s):
    """Each pose: his NES frame, whole, scaled by s and set at the bottom of the 24x48 frame, in his 3 colors."""
    import mac_nes
    rip = load("little-mac.png"); boxes = components(rip, 70)
    def ink(c):
        r, g, b = c[:3]
        if r + g + b < 90: return MAC_INK[0] + (255,)
        if r > g > b and r - b > 40: return MAC_INK[2] + (255,)
        return MAC_INK[1] + (255,)
    out = []
    for pose in PLAYER_POSES:
        if pose in MAC_NES:
            f = [[ink(c) if c else None for c in row] for row in mac_nes.mac_frame(MAC_NES[pose])]
            extra = len(f) - int(PH / s)        # too tall: rows out of the arm alone above his head (the
            if extra > 0:                       # narrow rows at the top), evenly, the glove kept whole
                top = next(y for y, row in enumerate(f) if any(row))
                glove = top + 8                 # (below the glove, above his shoulders: the arm)
                arm = [y for y in range(glove, len(f) // 2) if sum(1 for c in f[y] if c) <= 12]
                drop = set(arm[k * len(arm) // extra] for k in range(extra)) if len(arm) >= extra else set()
                f = [row for y, row in enumerate(f) if y not in drop]
            if pose == "duck":                  # (the render leaves a slit down his back: his tank top's black)
                for row in f:
                    on = [x for x, c in enumerate(row) if c]
                    for x in range(on[0], on[-1] + 1) if on else ():
                        if not row[x]: row[x] = MAC_INK[0] + (255,)
            small = mac_baked(f"pose-{pose}", lambda f=f: treat_lines(f, s, MAC_INK[0]))   # (warp.py's way)
        else:
            small = scale(cut(rip, boxes[MAC[pose]]), s, outline_weight=1.0)
        out.append(place(small, PW, PH, PH - len(small)))
    return out


def mac_pictures(s, colors):
    """Little Mac on Color: every NES frame of his, exact (no pose standing in for another), each where the NES
    draws it: {key: {"pixels": slots, "w", "h", "x", "y"}}, x, y its top-left in the original's 24x48 pose box
    (his idle frame bottom-centred in it, as there), scaled by s; slots 1-3 his palette's (colors: MAC_COLORS, in
    its order). A frame of nothing: no pixels."""
    pal = [tuple(v * 255 // 31 for v in c) for c in colors]
    import mac_nes
    def ink(c):
        r, g, b = c[:3]
        if r + g + b < 90: return MAC_INK[0] + (255,)
        if r > g > b and r - b > 40: return MAC_INK[2] + (255,)
        return MAC_INK[1] + (255,)
    raw = {k: mac_nes.mac_frame_at(int(k, 16)) for k in sorted(MAC_FRAMES, key=lambda k: int(k, 16))}
    i0, (x0, y0) = raw["00"]
    w0 = len(mac_baked("00", lambda: treat_lines([[ink(c) if c else None for c in row] for row in i0], s, MAC_INK[0]))[0])
    bx, by = (PW - w0) // 2, y0 + len(i0)       # (his idle frame's left in the box; its bottom, the box's)
    out = {}
    for k, r in raw.items():
        if r is None:                   # nothing drawn: sunk out of view (none of him), or no new picture (the one
            if MAC_PLACES.get(k) == 48:     # up stays: $48, him standing)
                out[k] = {"pixels": "", "w": 0, "h": 0, "x": 0, "y": 0}
            continue
        img, (x, y) = r
        f = [[ink(c) if c else None for c in row] for row in img]
        if MAC_FRAMES[k] == "duck":         # (the render leaves a slit down his back: his tank top's black)
            for row in f:
                on = [i for i, c in enumerate(row) if c]
                for i in range(on[0], on[-1] + 1) if on else ():
                    if not row[i]: row[i] = MAC_INK[0] + (255,)
        small = mac_baked(k, lambda f=f: treat_lines(f, s, MAC_INK[0]))
        h, w = len(small), len(small[0])
        left = bx + round((x - x0) * s)
        top = PH + round((y + len(img) - by) * s) - h
        px = "".join(str(1 + min(range(3), key=lambda i: dist(c[:3], pal[i]))) if c else "0" for row in small for c in row)
        out[k] = {"pixels": px, "w": w, "h": h, "x": left, "y": top}
    return out


# Where each of Joe's NES frames sits: the NES draws every frame at its own offset from his place (leaning into
# a hit, stepping into a hook, down on the mat), and each pose of ours is cut and centred on its own. Each frame,
# as the game draws it at his home, is matched by shape to the pose that shows it; the offsets put the pose
# where the frame is, his idle frame $00 the reference.

# Joe's poses from the game itself: his frames as the NES game draws them in a fight (nes_play: played in
# the emulator, cached), one per pose, the frame that pose stands for. Poses no frame of his calls for in the
# NES game share a picture (and its tiles) with the nearest one.
JOE_FROM_NES = dict(idle="00", idle2="02", idle3="04", guard="08", guard_low="0A", jab_tell="CC", jab_mid="CC",
                    jab="0E", hook_tell="16", hook_mid="1A", hook="18", slip="C6", hit_l="22", hit_r="1E",
                    hit_body="1C", hit_back="24", dazed="0C", kd_stagger="26", kd_fall="28", kd_down="2A",
                    kd_kneel="2C", taunt="3A", arm_pop="3A", tell1="82", tell2="80",
                    kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
JOE_ANCHOR = (35, 77)                       # his place (the NES's $B0, $B1) in each 64x80 frame: at 0.7, whole
                                            # NES pixels (50, 110), so every frame scales on the same grid and
                                            # what frames share (legs, trunks) comes out as the same tiles
_key = lambda k: (int(k.rstrip("|"), 16), 1 if k.endswith("|") else 0)

# Von Kaiser (opponent 1): his NES frames to our poses, by what each is for in his scripts (logged per AI state),
# and the frame each pose's picture is drawn from.
KAISER_FRAMES = {
    "00": "idle", "C4": "idle", "C0": "idle2", "C6": "idle2", "C2": "idle3",
    "82": "tell1", "CA": "tell2", "80": "tell3",                  # his gloves bouncing before the jab (state $16)
    "08": "guard", "0A": "guard_low", "10": "jab_tell", "12": "jab_mid", "0E": "jab",
    "16": "hook_tell", "18": "hook_mid", "1A": "hook", "44": "slip",                 # his uppercut; his duck
    "1C": "hit_body", "1E": "hit_r", "20": "hit_r", "22": "hit_l", "22|": "hit_r", "24": "hit_back",
    "0C": "dazed", "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "32": "kd2_fall", "34": "kd2_down", "36": "kd2_kneel", "38": "kd2_kneel",   # his other way
    "3A": "guard", "46": "hook", "3C": "arm_pop",                  # (46: his uppercut's end, state $17)
}
KAISER_FROM_NES = dict(idle="00", idle2="C0", idle3="C2", guard="08", guard_low="0A", jab_tell="10", jab_mid="12",
                       jab="0E", hook_tell="16", hook_mid="18", hook="1A", slip="44|", hit_l="22", hit_r="1E",
                       hit_body="1C", hit_back="24", dazed="0C", kd_stagger="26", kd_fall="26", kd_down="2A",
                       kd_kneel="2C", taunt="46", arm_pop="3C|", tell1="82", tell2="CA", tell3="80",
                       kd2_stagger="30", kd2_fall="30", kd2_down="34", kd2_kneel="36|")
# Piston Honda (opponent 2): the same, from his fight's logged frames (his jab 40-16-18, his straight 54-3E, his
# uppercut 4A-44-46-48, his celebration 3A-3C).
HONDA_FRAMES = {
    "C0": "idle", "C4": "idle", "00": "idle", "00|": "idle", "C2": "idle2", "02": "idle2", "C6": "idle2",
    "04": "idle3", "06": "idle3", "08": "guard", "10": "guard", "12": "guard", "42": "guard_low", "42|": "guard_low",
    "0A": "tell1", "D0": "tell2", "CE": "tell3",                   # his gloves rolling (state $16), then the jab 0E
    "80": "tell4", "82": "tell5",                                  # his bob before the rush (state $19)
    "40": "jab_tell", "16": "jab_mid", "18": "jab", "0E": "hook",
    "54": "hook_tell", "54|": "hook_tell", "3E": "hook", "3E|": "hook", "48": "hook_mid",
    "4A": "slip", "44": "slip", "46": "slip", "1A": "hit_back", "20": "hit_back", "24": "hit_back", "1E": "hit_r",
    "22": "hit_l", "22|": "hit_r", "1C": "hit_body", "C8": "dazed", "CA": "dazed", "C8|": "dazed", "CA|": "dazed",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel", "0C": "kd_down",
    "30": "kd2_stagger", "30|": "kd2_stagger", "32": "kd2_fall", "32|": "kd2_fall", "34": "kd2_down", "34|": "kd2_down",
    "36": "kd2_kneel", "36|": "kd2_kneel", "38": "kd2_kneel", "38|": "kd2_kneel",              # (his other way down)
    "3A": "taunt", "3C": "arm_pop", "52": "extra1", "52|": "extra1",   # (52|: his rematch's bounce, the other
                                                                       # side's: 4A and 52| in turn)
}
HONDA_FROM_NES = dict(idle="C0", idle2="C2", idle3="04", guard="08", guard_low="42|", jab_tell="40", jab_mid="16",
                      jab="18", hook_tell="54|", hook_mid="48", hook="3E|", slip="4A", hit_l="22", hit_r="1E",
                      hit_body="1C", hit_back="1A", dazed="C8", kd_stagger="26", kd_fall="28", kd_down="2A",
                      kd_kneel="2C", taunt="3A", arm_pop="3C", tell1="0A", tell2="D0", tell3="CE", tell4="80",
                      tell5="82", extra1="52|", kd2_stagger="30|", kd2_fall="32|", kd2_down="34|", kd2_kneel="36|")
# Don Flamenco (opponent 3, in Joe's bank): his uppercut 10-12-3C-CC-16-18-40 (states 05, 07, 08: the arm raised
# high is his tell), his hook 0A-16-18-1A (state 15), his bob 82-86 (state 18), his "Ole!" 3A, 3E.
DON_FRAMES = {
    "C0": "idle", "C4": "idle2", "C2": "idle3", "00": "idle", "02": "idle2", "04": "idle3", "06": "idle", "0C": "idle",
    "08": "guard", "12": "guard", "14": "guard", "80": "guard", "0A": "guard_low",
    "10": "jab_tell", "3C": "tell1", "CC": "tell2", "40": "jab", "82": "tell4", "86": "tell5",
    "16": "hook_tell", "18": "hook_mid", "1A": "hook", "C6": "slip",
    "1C": "hit_body", "1E": "hit_r", "20": "hit_r", "22|": "hit_l", "24": "hit_back", "C8": "dazed", "CA": "dazed",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "30|": "kd2_stagger", "32": "kd2_fall", "32|": "kd2_fall", "34": "kd2_down", "34|": "kd2_down",
    "36": "kd2_kneel", "36|": "kd2_kneel", "38": "kd2_kneel", "38|": "kd2_kneel",              # (his other way down)
    "3A": "taunt", "3E": "tell3", "0E": "extra1",                       # (his jab's punch: the rematch's)
}
DON_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="10", jab_mid="18",
                    jab="40", hook_tell="16", hook_mid="18", hook="1A", slip="C6", hit_l="22|", hit_r="1E",
                    hit_body="1C", hit_back="24", dazed="C8", kd_stagger="26", kd_fall="28", kd_down="2A",
                    kd_kneel="2C", taunt="3A", arm_pop="3E", tell1="3C", tell2="CC", tell3="3E", tell4="82",
                    tell5="86", extra1="0E", kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
# King Hippo (opponent 4, bank 1): his jab 12-C6-16 (states 05, 15), his big swing 14|-C6-3C|-3C (state 16), his
# mouth open as he winds up (24, 3A; both arms 20, 22: the opening), his shout CC (19); down, he sits (28, 80-88).
HIPPO_FRAMES = {
    "C0": "idle", "C4": "idle2", "C8": "idle3", "CA": "idle2", "00": "idle", "10": "guard",
    "12": "jab_tell", "C6": "jab_mid", "16": "jab", "14|": "hook_tell", "3C|": "hook_mid", "3C": "hook",
    "24": "tell1", "24|": "tell2", "3A": "tell3", "20": "tell4", "22": "tell5", "CC": "taunt",
    "26": "hit_r", "30|": "hit_l", "30": "hit_r",
    "28": "kd_fall", "80": "kd_down", "82": "kd2_down", "86": "kd_kneel", "88": "kd2_kneel",   # (down, his eyes
                                                                                                  # rolling: 80-82)
    # punched in the open mouth: holding it, his trunks falling, gut-punched, pulling them up (all in the always-there
    # and attack sets: nothing swaps in while it plays)
    "0C": "dazed", "84": "hit_body", "1E": "hit_back", "1A": "slip", "1C": "guard_low",
    "CE": "extra1",                                                     # (his punch's last before it comes)
}
HIPPO_FROM_NES = dict(idle="C0", idle2="C4", idle3="C8", guard="10", guard_low="1C", jab_tell="12", jab_mid="C6",
                      jab="16", hook_tell="14|", hook_mid="3C|", hook="3C", slip="1A", hit_l="30|", hit_r="26",
                      hit_body="84", hit_back="1E", dazed="0C", kd_stagger="26", kd_fall="28", kd_down="80",
                      kd_kneel="86", taunt="CC", arm_pop="20", tell1="24", tell2="24|", tell3="3A", tell4="20",
                      tell5="22", extra1="CE", kd2_stagger="26", kd2_fall="28", kd2_down="82", kd2_kneel="88")
# Mr. Sandman (opponent 11, bank 3 at $10): his bob C0-C4-C2, two attacks after the tells 82-80 (16-18-1A, and
# 40|-40-3C|-3C-3E|-3E), the uppercut 0E|-52|-52 (and 0C-4A), the counter 54|-54 off a block, the Dreamland
# Express 46-44-46-48-4A; a lookalike shares a pose where his frames outnumber them (0E 0C's, 4A and 52| 52's,
# 14 and 54| 54's, 48 the lunge 1A's, 44 and 46 the crouch 16's), down either way 26-28-2A-2C or 30-32-34-36|.
SANDMAN_FRAMES = {
    "C0": "idle", "00": "idle", "C4": "idle2", "02": "idle2", "06": "idle2", "C6": "idle2", "C2": "idle3", "04": "idle3",
    "08": "guard", "10": "guard", "12": "guard", "0A": "guard_low",
    "82": "tell1", "80": "tell2", "16": "jab_tell", "44": "jab_tell", "46": "jab_tell", "18": "jab_mid",
    "1A": "jab", "48": "jab", "40|": "hook_tell", "40": "tell3", "3C|": "hook_mid", "3C": "hook_mid",
    "3E|": "hook", "3E": "hit_back", "0C": "slip", "0E": "slip", "0E|": "slip",
    "52": "tell5", "52|": "tell5", "4A": "tell5", "54": "tell4", "54|": "tell4", "14": "tell4",
    "24": "hit_l", "24|": "hit_r", "20": "hit_r", "1C": "hit_body", "1E": "dazed", "22": "dazed", "22|": "dazed",
    "3A": "taunt", "CC": "arm_pop",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "32": "kd2_fall", "34": "kd2_down", "34|": "kd2_down", "36|": "kd2_kneel", "38|": "kd2_kneel",
}
SANDMAN_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="16", jab_mid="18",
                        jab="1A", hook_tell="40|", hook_mid="3C|", hook="3E|", slip="0C", hit_l="24", hit_r="20",
                        hit_body="1C", hit_back="3E", dazed="1E", kd_stagger="26", kd_fall="28", kd_down="2A",
                        kd_kneel="2C", taunt="3A", arm_pop="CC", tell1="82", tell2="80", tell3="40", tell4="54",
                        tell5="52", kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
# Super Macho Man (opponent 12, bank 4 at $30): his bob C0-C4-C2, the jab 16-18-1A, the spin punch 4C|-4E|-50|-50,
# the uppercut 44-46-48, the super spin punch 52-54-56-5A (the extra poses), his flex 3A-CC; hit 22/22|, 12-14,
# turned 24/20/1E, dazed 42; down 26-28-2A-2C or 30-32-34-36|. Some frames come only from cynes (bank latches
# exact), Mac's pixels taken out; the ones it catches Mac in instead (0E, 3E, C6, 1C, 86, 26, 50|) share a lookalike.
MACHO_FRAMES = {
    "C0": "idle", "04": "idle", "06": "idle", "80": "idle", "C6": "idle", "C4": "idle2", "C2": "idle3",
    "08": "guard", "10": "guard", "0E": "guard", "0A": "guard_low",
    "16": "jab_tell", "18": "jab_mid", "1A": "jab",
    "4C|": "hook_tell", "4C": "hook_tell", "4E|": "tell3", "50|": "hook", "50": "hook",
    "44": "tell4", "82": "tell4", "86": "tell4", "46": "tell5", "48": "hit_back", "0C": "slip", "4A": "slip",
    "52": "extra1", "54": "extra2", "56": "extra3", "58": "hook_mid", "5A": "extra4",
    "22": "hit_l", "22|": "hit_r", "12": "hit_body", "14": "hit_body", "1C": "hit_body", "42": "dazed", "42|": "dazed",
    "24": "tell1", "1E": "tell1", "20": "tell2",
    "3A": "taunt", "3E": "taunt", "CC": "arm_pop",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "32": "kd2_fall", "34": "kd2_down", "34|": "kd2_down", "36|": "kd2_kneel", "38|": "kd2_kneel",
}
MACHO_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="16", jab_mid="18",
                      jab="1A", hook_tell="4C|", hook_mid="58", hook="50", slip="0C", hit_l="22", hit_r="22|",
                      hit_body="12", hit_back="48", dazed="42", kd_stagger="1E", kd_fall="28", kd_down="2A",
                      kd_kneel="2C", taunt="3A", arm_pop="CC", tell1="24", tell2="20", tell3="4E|", tell4="44",
                      tell5="46", extra1="52", extra2="54", extra3="56", extra4="5A",
                      kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
# Mike Tyson (opponent 13, bank 5 at $40): his bob C0-C4-C2, the jab 16-18-1A, the uppercut 44-46-48, the dynamite
# punch 4C|-4E|-50|-50 then 54/54|, his wink 82-80 (state 19), 3A/3C/CC; hit 24/24|/22|, 1E-20, 12-14-C6, down
# 26-28-2A-2C. Frames never caught whole (18, 1A, 1C, 20, 2E, his other way down 30-38, ...) share a lookalike.
TYSON_FRAMES = {
    "C0": "idle", "C4": "idle2", "C2": "idle3", "04": "idle3", "C8": "dazed", "CA": "dazed",   # (C8/CA: hit in
                                                                       # his crouch, turned away dizzy)
    "00": "extra3", "D2": "extra3", "02": "extra4", "06": "extra4",    # (his crouch and bounce, state 19: low, up)
    "08": "guard", "10": "guard", "0E": "guard", "0A": "guard_low", "0C": "guard_low",
    "16": "jab_tell", "1A": "jab", "54": "jab", "54|": "jab",
    "CE": "tell2", "D0": "tell2", "40": "jab_mid", "18": "tell1",        # (his straight jab: the blink, back,
    "56": "extra1", "56|": "extra1", "3E": "extra2", "3E|": "extra2",    # out; and the other hand's, 56|-3E|)
    "44": "tell4", "46": "tell5", "48": "hit_back",
    "4C|": "hook_tell", "4C": "hook_tell", "4E|": "tell3", "4E": "tell3", "50|": "hook_mid", "50": "hook",
    "82": "idle2", "80": "idle", "3A": "taunt", "CC": "arm_pop", "3C": "taunt", "C6": "idle2",
    "24": "hit_l", "24|": "hit_r", "22|": "hit_r", "22": "hit_l", "1E": "dazed", "20": "dazed",
    "12": "slip", "14": "slip", "1C": "hit_body", "42": "hit_body", "42|": "hit_body",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "30|": "kd2_stagger", "32": "kd2_fall", "32|": "kd2_fall", "34": "kd2_down", "34|": "kd2_down",
    "36|": "kd2_kneel", "38|": "kd2_kneel",
    "26|": "kd2_stagger", "28|": "kd2_fall", "2A|": "kd2_down", "2C|": "kd2_kneel",   # (his other way down: the first
}                                                                                    # flipped, its frames never caught whole)
TYSON_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="16", jab_mid="40",
                      jab="54", hook_tell="4C|", hook_mid="50|", hook="50", slip="12", hit_l="24", hit_r="24|",
                      hit_body="1C", hit_back="48", dazed="1E", kd_stagger="26", kd_fall="28", kd_down="2A",
                      kd_kneel="2C", taunt="3A", arm_pop="CC", tell1="18", tell2="CE", tell3="4E|", tell4="44",
                      tell5="46", extra1="56|", extra2="3E|", extra3="00", extra4="02",
                      kd2_stagger="26|", kd2_fall="28|", kd2_down="2A|", kd2_kneel="2C|")   # (fewer pictures: his face whole)
# Great Tiger (opponent 5, bank 2): his bob CA-82-80 then the jab 0E (states 05, 16), his uppercut 16-18-46 (17),
# the Tiger punch spinning 44|-44-3C|-3C-48|-48 (18: all in the attack set's spare slots, no swap mid-spin), dazed
# 42/32, down either way 26-2A-2C-2E or 30-34-36-38.
TIGER_FRAMES = {
    "C0": "idle", "00": "idle", "CC": "idle", "C4": "idle2", "C2": "idle2", "C6": "idle2",
    "08": "guard", "10": "guard", "3A": "guard", "0A": "guard_low", "12": "jab_tell", "40|": "jab_tell", "0E": "jab",
    "CA": "tell1", "82": "tell2", "80": "tell3", "16": "hook_tell", "18": "hook_mid", "46": "hook", "1A": "hook",
    "3E": "hook", "3E|": "hook", "4A": "hook", "4C|": "hook",
    "44": "slip", "44|": "tell4", "3C": "tell5", "3C|": "jab_mid", "48": "hit_back", "48|": "idle3",
    "1C": "hit_body", "1E": "hit_r", "22": "hit_l", "22|": "hit_r", "42|": "dazed", "42": "dazed", "32": "dazed", "32|": "dazed",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "30|": "kd2_fall", "34": "kd2_down", "34|": "kd2_down", "36|": "kd2_kneel", "38|": "kd2_kneel",
}
TIGER_FROM_NES = dict(idle="C0", idle2="C4", idle3="48|", guard="08", guard_low="0A", jab_tell="12", jab_mid="3C|",
                      jab="0E", hook_tell="16", hook_mid="18", hook="46", slip="44", hit_l="22", hit_r="1E",
                      hit_body="1C", hit_back="48", dazed="42|", kd_stagger="26", kd_fall="26", kd_down="2A",
                      kd_kneel="2C", taunt="00", arm_pop="00", tell1="CA", tell2="82", tell3="80", tell4="44|",
                      tell5="3C", kd2_stagger="30", kd2_fall="30|", kd2_down="34", kd2_kneel="36|")
# Bald Bull (opponent 6, bank 3): his bob 02/00 then the jab 0E|-0E (state 16), his uppercut 82-80-16-18-1A (15),
# the Bull Charge: hops back 46-44, charges 48, uppercuts 4A (17); down either way 26-2A-2C or 30-32-34-36-38.
BULL_FRAMES = {
    "C0": "idle", "00": "idle", "C6": "idle", "C8": "dazed", "C4": "idle2", "04": "idle2", "06": "idle2", "C2": "idle3",
    "08": "guard", "10": "guard", "12": "guard", "3A": "guard", "CA": "dazed", "0A": "guard_low",   # (C8/CA: dazed, up
    "02": "tell1", "82": "tell2", "80": "tell3", "46": "tell4", "44": "tell5", "48": "slip", "4A": "jab_tell",
    "0E|": "jab_mid", "0E": "jab", "16": "hook_tell", "18": "hook_mid", "1A": "hook",
    "1C": "hit_body", "42|": "hit_body", "20": "extra1", "1E": "extra2",
    "22": "hit_l", "22|": "hit_r", "24": "hit_back", "24|": "hit_back", "CC": "taunt", "CE": "arm_pop",
    "26": "kd_stagger", "28": "kd_fall", "2A": "kd_down", "2C": "kd_kneel", "2E": "kd_kneel",
    "30": "kd2_stagger", "32": "kd2_fall", "34": "kd2_down", "34|": "kd2_down", "36|": "kd2_kneel", "38|": "kd2_kneel",
}
BULL_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="4A", jab_mid="0E|",
                     jab="0E", hook_tell="16", hook_mid="18", hook="1A", slip="48", hit_l="22", hit_r="22|",
                     hit_body="1C", hit_back="24", dazed="C8", kd_stagger="26", kd_fall="28", kd_down="2A",
                     kd_kneel="2C", taunt="CC", arm_pop="CE", tell1="02", tell2="82", tell3="80", tell4="46",
                     tell5="44", extra1="20", extra2="1E",
                     kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
# Soda Popinski (opponent 8, bank 4): his bob C6-80 then the jab 0E|-0E (state 16), his combo 40-3C-3E either way
# (15), his rush 4C-4E-50 (18), his drink and laugh 3A, CC, 0C; down 30-32-34-36-38 (the one way captured).
SODA_FRAMES = {
    "C0": "idle", "00": "idle", "C4": "idle2", "02": "idle2", "06": "idle2", "C2": "idle3", "04": "idle3",
    "08": "guard", "10": "guard", "10|": "guard", "12": "guard", "12|": "guard", "C8": "guard", "CA": "guard",
    "CE": "guard", "4A": "guard", "0A": "guard_low",
    "C6": "tell1", "80": "tell2", "0E|": "jab_mid", "0E": "jab", "D0": "jab",
    "40|": "hook_tell", "40": "jab_tell", "3C|": "hook_mid", "3C": "tell3", "3E|": "hook", "3E": "hit_back",
    "4C|": "tell4", "4E|": "tell5", "50": "slip", "50|": "slip",
    "22|": "hit_r", "24": "hit_l", "42|": "dazed", "42": "dazed", "3A": "taunt", "CC": "taunt", "0C": "arm_pop",
    "30": "kd_stagger", "30|": "kd2_stagger", "32": "kd_fall", "32|": "kd2_fall", "34": "kd_down", "34|": "kd2_down",
    "36|": "kd_kneel", "38|": "kd2_kneel",
    "44": "extra1", "46": "extra2", "48": "extra3",                    # (his uppercut: down, the punch, up)
}
SODA_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="40", jab_mid="0E|",
                     jab="0E", hook_tell="40", hook_mid="3C|", hook="3E|", slip="50", hit_l="24", hit_r="22|",
                     hit_body="24", hit_back="3E", dazed="42|", kd_stagger="30", kd_fall="32", kd_down="34",
                     kd_kneel="36|", taunt="3A", arm_pop="0C", tell1="C6", tell2="80", tell3="3C|", tell4="4C|",
                     tell5="4E|", extra1="44", extra2="46", extra3="48",
                     kd2_stagger="30", kd2_fall="32", kd2_down="34|", kd2_kneel="38|")
# The rivals after Joe, from their NES fights: opponent number, fighter bank (and offset), frames, and the game's
# nth fight (where their tiles are measured).
NES_RIVALS = {
    "joe": dict(name="Glass Joe", opp=0, bank=0, offset=0x00, frames=NES_FRAMES, canon=JOE_FROM_NES, nth=0, pictures=True,
                lines=False, eyes=True),   # (his face's fine strokes voted down, not lines dropped through his eyes;
                                           #  the original: his eyes' whites white)
    "kaiser": dict(name="Von Kaiser", opp=1, bank=2, offset=0x00, frames=KAISER_FRAMES, canon=KAISER_FROM_NES, nth=1, pictures=True),
    "honda": dict(name="Piston Honda", opp=2, bank=5, offset=0x30, frames=HONDA_FRAMES, canon=HONDA_FROM_NES, nth=2, pictures=True),
    "don": dict(name="Don Flamenco", opp=3, bank=0, offset=0x10, frames=DON_FRAMES, canon=DON_FROM_NES, nth=3, pictures=True),
    "hippo": dict(name="King Hippo", opp=4, bank=1, offset=0x00, frames=HIPPO_FRAMES, canon=HIPPO_FROM_NES, nth=4, pictures=True),
    "tiger": dict(name="Great Tiger", opp=5, bank=2, offset=0x10, frames=TIGER_FRAMES, canon=TIGER_FROM_NES, nth=5, jewel=True, pictures=True),
    "bull": dict(name="Bald Bull", opp=6, bank=3, offset=0x30, frames=BULL_FRAMES, canon=BULL_FROM_NES, nth=6, pictures=True),
    "soda": dict(name="Soda Popinski", opp=8, bank=4, offset=0x10, frames=SODA_FRAMES, canon=SODA_FROM_NES, nth=8, pictures=True),
    "sandman": dict(name="Mr. Sandman", opp=11, bank=3, offset=0x10, frames=SANDMAN_FRAMES, canon=SANDMAN_FROM_NES, nth=11, pictures=True),
    "macho": dict(name="Super Macho Man", opp=12, bank=4, offset=0x30, frames=MACHO_FRAMES, canon=MACHO_FROM_NES, nth=12, cynes=True, pictures=True),
    "tyson": dict(name="Mike Tyson", opp=13, bank=5, offset=0x40, frames=TYSON_FRAMES, canon=TYSON_FROM_NES, nth=13, lines=True,
                  pictures=True),
}
FIGHTERS = {0: (NES_FRAMES, JOE_FROM_NES), **{r["opp"]: (r["frames"], r["canon"]) for r in NES_RIVALS.values()}}
for _fm, _canon in FIGHTERS.values():          # up off the knee (2E, his other way 38|): a pose of its own, not
    for _f, _was, _rise in (("2E", "kd_kneel", "kd_rise"), ("38|", "kd2_kneel", "kd2_rise")):   # the kneel again
        if _fm.get(_f) == _was:
            _fm[_f] = _rise
            _canon.setdefault(_rise, _f)


MIRROR_OF = {                           # frames caught with another fighter's tiles in them, their mirror right
    11: {"3C": "3C|"},                  # (Sandman's hook: white trunks)
}
NOT_HIS = {                             # frames the plain emulator caught that the real game never shows him in (its
    2: {"14|", "2E", "30", "32", "38", "38|", "3C|", "40|", "44|", "48|", "4C", "4C|", "84", "86", "88", "CC", "0C"},
}                                       # bank switched wrong: another fighter's tiles; cynes, 120000 frames: never)


def joe_shapes(opponent=0, everything=False):
    """{(frame, mirrored): {(x, y) from his place: color}}: each frame of his from a fight, his biggest piece
    (not a speck of another sprite, nor the referee)."""
    import nes_play
    frames_map, canon = FIGHTERS[opponent]
    wanted = {_key(k) for k in list(frames_map) + list(canon.values())} if opponent == 0 and not everything else None
    out = {}
    found = nes_play.fighter_frames(opponent, wanted)
    if any(r["opp"] == opponent and r.get("cynes") for r in NES_RIVALS.values()):
        import cynes_frames                 # the accurate emulator's, where it has them: its banks are right, but
        exact = cynes_frames.cynes_frames(opponent)     # what Mac (the background, over him) hides is missing;
        for key, (img, place) in exact.items():         # filled from ours where the two agree on the rest
            ours = found.get(key)
            if ours and ours[1] == place:
                both = [(a, b) for ra, rb in zip(img, ours[0]) for a, b in zip(ra, rb) if a and b]
                if both and sum(1 for a, b in both if tuple(a) == tuple(b)) >= 0.9 * len(both):
                    img = [[a if a else b for a, b in zip(ra, rb)] for ra, rb in zip(img, ours[0])]
            found[key] = (img, place)
    for key, (img, (px, py)) in found.items():
        on = {(x, y) for y in range(len(img)) for x in range(len(img[0])) if img[y][x]}
        pieces, seen = [], set()
        for p0 in sorted(on):
            if p0 in seen:
                continue
            g, st = {p0}, [p0]
            while st:
                x, y = st.pop()
                for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
                    if q in on and q not in g:
                        g.add(q); st.append(q)
            seen |= g
            pieces.append(g)
        if not pieces:                      # (a capture with nothing in it)
            continue
        near = [g for g in pieces if any(abs(x - px) <= 12 for x, _ in g)]
        him = set(max(near or pieces, key=len))
        x0, x1 = min(x for x, _ in him) - 8, max(x for x, _ in him) + 8
        y0, y1 = min(y for _, y in him) - 8, max(y for _, y in him) + 8
        for g in pieces:                # (and parts of him drawn apart: Macho's boots as he goes down; not specks,
            if g is not him and len(g) >= 40 and any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in g) \
                    and any(abs(x - a) <= 8 and abs(y - b) <= 8 for x, y in g for a, b in him):   # a star's twinkle)
                him |= g
        out[key] = {(x - px, y - py): img[y][x] for x, y in him}
    for k in frames_map:                               # a mirrored frame never caught whole: its plain one flipped
        f, mi = _key(k)
        if mi and (f, 1) not in out and (f, 0) in out:
            out[(f, 1)] = {(-x, y): c for (x, y), c in out[(f, 0)].items()}
    for (f, mirrored), shape in list(out.items()):     # a mirrored frame caught the same as its plain one (the
        if mirrored and out.get((f, 0)) == shape:      # capture's mirror flag set, the picture taken unflipped):
            out[(f, 1)] = {(-x, y): c for (x, y), c in shape.items()}   # flipped about his place, as the NES's
    for k in NOT_HIS.get(opponent, ()):
        out.pop(_key(k), None)
    for k, other in MIRROR_OF.get(opponent, {}).items():   # (a frame caught wrong whose mirror was caught right:
        o = out.get(_key(other))                            #  the NES draws one as the other flipped)
        if o:
            out[_key(k)] = {(-x, y): c for (x, y), c in o.items()}
    return out

def joe_from_nes(s, shapes=None, opponent=0):
    """His 64x80 frames, one per pose (FIGHT_POSES order), from JOE_FROM_NES, and how far each was moved over
    to fit ({pose: (dx, dy)}, whole grid steps; joe_places takes it back out). Each scales by s on one grid:
    his place at JOE_ANCHOR."""
    shapes = shapes or joe_shapes(opponent)
    canon = FIGHTERS[opponent][1]
    step = 10 if abs(s - 0.7) < 1e-9 else 1     # NES pixels to a whole number of ours (7 at 0.7)
    ax, ay = round(JOE_ANCHOR[0] / s), round(JOE_ANCHOR[1] / s)
    W, H = round(RW / s), round(RH / s)
    frames, moved, jewels = [], {}, {}
    def canon_key(name):                    # (a frame never caught: the pose it stands in for's)
        k = canon.get(name) or canon[TELL_FALLBACK[name]]
        return k if _key(k) in shapes or name not in TELL_FALLBACK else canon_key(TELL_FALLBACK[name])
    for name in FIGHT_POSES:
        shape = shapes[_key(canon_key(name))]
        xs, ys = [x for x, _ in shape], [y for _, y in shape]
        mx = my = 0                         # moved over (in steps) if he reaches past an edge
        while min(xs) + ax + mx < 0 and max(xs) + ax + mx + step < W: mx += step
        while max(xs) + ax + mx >= W and min(xs) + ax + mx - step >= 0: mx -= step
        while max(ys) + ay + my >= H and min(ys) + ay + my - step >= 0: my -= step
        while min(ys) + ay + my < 0 and max(ys) + ay + my + step < H: my += step
        img = [[None] * W for _ in range(H)]
        for (x, y), c in shape.items():
            X, Y = x + ax + mx, y + ay + my
            if 0 <= X < W and 0 <= Y < H:
                img[Y][X] = tuple(c) + (255,)
        lines = not any(r["opp"] == opponent and r.get("lines") is False for r in NES_RIVALS.values())   # (everyone:
                                                                    # whole rows of the game's pixels, crisp)
        small = shrink_lines(img, s) if lines else scale(img, s)   # (lines: whole rows and columns kept, hair crisp)
        frame = [[small[y][x] if y < len(small) and x < len(small[0]) else None for x in range(RW)] for y in range(RH)]
        frames.append(frame)
        moved[name] = (round(mx * s), round(my * s))
        if any(r["opp"] == opponent and r.get("jewel") for r in NES_RIVALS.values()):
            gem = _jewel(shape)                 # (Great Tiger's: his turban's gem, where it lands in the pose)
            if gem:
                jewels[name] = [round((gem[0] + ax + mx) * s), round((gem[1] + ay + my) * s)]
    key_of = {name: canon_key(name) for name in FIGHT_POSES}
    plain = {}
    for name in FIGHT_POSES:
        plain.setdefault(key_of[name], name)
    for k, name in enumerate(FIGHT_POSES):             # a mirrored frame whose plain one is a pose too: that pose
        key = key_of[name]                              # flipped whole (the frame's middle: its tiles each another's
        if key.endswith("|") and key[:-1] in plain:     # mirror, so Color stores them once); its place found as
            other = FIGHT_POSES.index(plain[key[:-1]])  # every frame's is
            frames[k] = [list(reversed(row)) for row in frames[other]]
            moved[name] = moved[plain[key[:-1]]]
            if plain[key[:-1]] in jewels:
                jewels[name] = [RW - 1 - jewels[plain[key[:-1]]][0], jewels[plain[key[:-1]]][1]]
    joe_from_nes.moved = moved
    joe_from_nes.jewels = jewels
    return frames


def pictures_from_nes(s, shapes, opponent, blank=()):
    """Every picture of his the NES game draws, each its own 64x80 frame (Game Boy Color shows exactly these:
    no pose standing in for another): {key: frame}, scaled as joe_from_nes scales poses; a mirrored one from its
    own capture (the NES's mirrored frames are often drawings of their own; one never caught: joe_shapes gives
    its plain one flipped). Keys as the frame maps' ("C0", "56|"). A mirrored picture caught alone gives its plain
    one too, flipped back."""
    step = 10 if abs(s - 0.7) < 1e-9 else 1
    ax, ay = round(JOE_ANCHOR[0] / s), round(JOE_ANCHOR[1] / s)
    W, H = round(RW / s), round(RH / s)
    lines = not any(r["opp"] == opponent and r.get("lines") is False for r in NES_RIVALS.values())
    shapes = dict(shapes)
    for (f, mi), shape in list(shapes.items()):
        if mi and (f, 0) not in shapes:
            shapes[(f, 0)] = {(-x, y): c for (x, y), c in shape.items()}
    def make(shape):
        xs, ys = [x for x, _ in shape], [y for _, y in shape]
        mx = my = 0
        while min(xs) + ax + mx < 0 and max(xs) + ax + mx + step < W: mx += step
        while max(xs) + ax + mx >= W and min(xs) + ax + mx - step >= 0: mx -= step
        while max(ys) + ay + my >= H and min(ys) + ay + my - step >= 0: my -= step
        while min(ys) + ay + my < 0 and max(ys) + ay + my + step < H: my += step
        img = [[None] * W for _ in range(H)]
        for (x, y), c in shape.items():
            X, Y = x + ax + mx, y + ay + my
            if 0 <= X < W and 0 <= Y < H:
                img[Y][X] = tuple(c) + (255,)
        small = shrink_lines(img, s) if lines else scale(img, s)
        if opponent in LINE_REDRAW and not getattr(pictures_from_nes, "plain", False):
            small = redraw_lines(img, small, s)
        return [[small[y][x] if y < len(small) and x < len(small[0]) else None for x in range(RW)] for y in range(RH)]
    out = {}
    for (f, mi) in sorted(shapes):
        if not mi:
            out["%02X" % f] = make(shapes[(f, 0)])
    for (f, mi) in blank:               # (frames the NES draws him in as nothing: Tiger gone in his dash)
        out["%02X%s" % (f, "|" if mi else "")] = [[None] * RW for _ in range(RH)]
    for (f, mi) in sorted(shapes):       # a mirrored one: as the NES draws it (often its own drawing: Tyson's head
        if mi and "%02X|" % f not in out:    # snapped back, not his fist-up 22 turned round), from its own capture
            out["%02X|" % f] = make(shapes[(f, 1)])
    return out


def blank_frames(opponent):
    """The frames a fight showed him as nothing at all (his crop empty): {(frame, mirrored)}."""
    import nes_play
    return {k for k, (crop, _) in nes_play.fighter_frames(opponent).items() if not any(any(row) for row in crop)}


def picture_places(frames, s, shapes):
    """Where each picture sits: the NES draws each frame at its own place; each picture's NES shape is laid
    over the picture to find his place in it, given (as joe_places' offsets) from the idle picture's: {key:
    [dx, dy]}, nonzero ones."""
    ax, ay = round(JOE_ANCHOR[0] / s), round(JOE_ANCHOR[1] / s)
    W, H = round(RW / s) + 40, round(RH / s) + 40
    pad = round(20 * s)
    def scaled_rows(shape):
        img = [[None] * W for _ in range(H)]
        for (x, y), c in shape.items():
            X, Y = x + ax + 20, y + ay + 20
            if 0 <= X < W and 0 <= Y < H:
                img[Y][X] = (255, 255, 255, 255)
        return [sum(1 << x for x, c in enumerate(r) if c) for r in scale(img, s, outline_weight=1.0)]
    def own_rows(frame):
        return [sum(1 << x for x in range(RW) if frame[y][x]) for y in range(RH)]
    found = {}
    for key, frame in frames.items():
        if not any(any(row) for row in frame):
            continue                        # (a blank one: nothing to place)
        shape = shapes.get(_key(key))
        if shape is None:                   # (a picture only caught the other way round: that one flipped)
            other = shapes.get(_key(key[:-1])) if key.endswith("|") else shapes.get(_key(key + "|"))
            shape = {(-x, y): c for (x, y), c in other.items()}
        a, b = scaled_rows(shape), own_rows(frame)
        best = (-1, 0, 0)
        for dy in range(-24, 25):
            for dx in range(-24, 25):
                n = 0
                for y, bits in enumerate(a):
                    Y = y - pad + dy
                    if bits and 0 <= Y < RH:
                        sh = dx - pad
                        n += bin((bits << sh if sh >= 0 else bits >> -sh) & b[Y]).count("1")
                if n > best[0]:
                    best = (n, dx, dy)
        found[key] = (JOE_ANCHOR[0] + best[1], JOE_ANCHOR[1] + best[2])
    rx, ry = found.get("C0") or found.get("00") or next(iter(found.values()))
    return {k: [rx - x, ry - y] for k, (x, y) in found.items() if (rx - x, ry - y) != (0, 0)}


TOUCHUPS = HERE / "touchups"            # hand touch-ups of a rival's pictures (touchup.py writes and checks them)


def frame_hash(fr):
    """A picture's pixels' hash: what a touch-up was drawn over (it's applied only over that same picture)."""
    import hashlib
    return hashlib.sha1("".join(",".join(map(str, c[:3])) if c else "-" for row in fr for c in row).encode()).hexdigest()[:16]


def touchup_name(key):
    return key.replace("|", "m")


def read_touchup(path):
    """(the auto picture's hash, the touched-up picture) from a touch-up file: '#' comments, 'auto HASH', 'legend
    .=- K=r,g,b ...', then the picture's rows, a character a pixel."""
    auto, legend, rows = None, {}, []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("auto "):
            auto = line.split()[1]
        elif line.startswith("moved ") or line == "final":
            pass                            # (touchup_moved's; touchup_final's)
        elif line.startswith("legend "):
            for item in line.split()[1:]:
                ch, v = item.split("=")
                legend[ch] = None if v == "-" else tuple(map(int, v.split(","))) + (255,)
        else:
            rows.append([legend[ch] for ch in line])
    return auto, rows


def touchup_final(path):
    """A touch-up baked: 'final' in it, the picture as drawn for good, whatever its auto picture comes to."""
    return "final" in path.read_text().splitlines()


def touchup_moved(key):
    """How far each touch-up moved its picture in its frame ('moved DX DY': a tile's colors kept, say), to be undone
    in its place on screen: {key: (dx, dy)}."""
    out = {}
    for path in sorted((TOUCHUPS / key).glob("*.txt")) if (TOUCHUPS / key).exists() else []:
        for line in path.read_text().splitlines():
            if line.startswith("moved "):
                out[path.stem.replace("m", "|") if path.stem.endswith("m") else path.stem] = tuple(map(int, line.split()[1:3]))
    return out


def apply_touchups(key, frames):
    """A rival's hand touch-ups (touchups/KEY/FRAME.txt) put in, each only over the auto picture it was drawn on:
    one whose auto picture has changed since is left out, and said so (redo it: touchup.py) -- unless it's final,
    baked: then it's the picture, whatever the NES's shrink now makes."""
    d = TOUCHUPS / key
    if not d.exists():
        return frames
    out = dict(frames)
    for path in sorted(d.glob("*.txt")):
        k = path.stem.replace("m", "|") if path.stem.endswith("m") else path.stem
        if k not in frames:
            print(f"  touch-up {path.name}: no picture {k}")
            continue
        auto, rows = read_touchup(path)
        if auto != frame_hash(frames[k]) and not touchup_final(path):
            print(f"  touch-up {path.relative_to(HERE)} is stale (its auto picture changed): not applied -- redo it")
            continue
        out[k] = rows
    return out


WHITE_DEAR = 20                         # (an eye's white lost: as dear as this many of its distance in other colors)


def _small_whites(fr):
    """A picture's small bright features in his face: eyes' whites, teeth (a light pixel with few others of its kind
    near, none of a glove's red beside it: not his trunks, nor a glove's shine, which its red keeps)."""
    lum = lambda c: 2 * c[0] + 4 * c[1] + c[2]
    red = lambda c: c and c[1] < 0.4 * c[0] and c[2] < 0.4 * c[0]
    H, W = len(fr), len(fr[0])
    at = lambda x, y: fr[y][x] if 0 <= x < W and 0 <= y < H else None
    light = {(x, y) for y in range(H) for x in range(W) if fr[y][x] and lum(from8(fr[y][x][:3])) >= 200}
    return {(x, y) for x, y in light
            if sum((x + i, y + j) in light for i in range(-2, 3) for j in range(-2, 3)) <= 4
            and not any(red(at(x + i, y + j)) for i in (-1, 0, 1) for j in (-1, 0, 1))}


def align_pictures(frames, palettes, reach=7):
    """Each picture moved (up to `reach` pixels, its art kept whole in its frame) to where his colors fit his
    palettes best: a tile can't hold four colors and the mat, so where a tile's edges fall decides whether, say,
    an eye's white and the hair beside it share one (and the white's lost). Its tiles never more than before, so
    nothing more to stream; picture_places finds where he sits in it after, so on screen he's where he was.
    -> (frames, {key: (dx, dy) moved})"""
    import numpy as np
    pal = np.array([[c[:3] for c in p] for p in palettes], dtype=float)
    out, moved = {}, {}
    for key, fr in frames.items():
        mask = np.array([[c is not None for c in row] for row in fr])
        if not mask.any():
            out[key] = fr
            continue
        rgb = np.array([[from8(c[:3]) if c else (0, 0, 0) for c in row] for row in fr], dtype=float)
        small = np.zeros(mask.shape, bool)
        for x, y in _small_whites(fr):
            small[y, x] = True
        errs = []
        for p in pal:                   # (each pixel's cost in this palette: its colors 1-3; eyes' whites dear)
            d = np.min([((rgb - p[k]) ** 2).sum(-1) for k in (1, 2, 3)], axis=0)
            errs.append(np.where(mask, d * np.where(small & (d > 0), WHITE_DEAR, 1), 0))
        errs = np.array(errs)
        ys, xs = np.where(mask)
        H, W = mask.shape
        def score(sx, sy):
            e = np.zeros((len(pal), H + 16, W + 16))
            e[:, 8 + sy:8 + sy + H, 8 + sx:8 + sx + W] = errs
            m = np.zeros((H + 16, W + 16), bool)
            m[8 + sy:8 + sy + H, 8 + sx:8 + sx + W] = mask
            e, m = e[:, 8:8 + H, 8:8 + W], m[8:8 + H, 8:8 + W]
            t = e.reshape(len(pal), H // 8, 8, W // 8, 8).sum((2, 4)).min(0)
            n = m.reshape(H // 8, 8, W // 8, 8).any((1, 3)).sum()
            return t.sum(), n
        base, tiles = score(0, 0)
        best = (base, 0, 0)
        for sy in range(-reach, reach + 1):
            for sx in range(-reach, reach + 1):
                if ys.min() + sy < 0 or ys.max() + sy >= H or xs.min() + sx < 0 or xs.max() + sx >= W:
                    continue
                t, n = score(sx, sy)
                if n <= tiles and t < best[0]:
                    best = (t, sx, sy)
        _, sx, sy = best
        moved[key] = (sx, sy)
        out[key] = [[fr[y - sy][x - sx] if 0 <= y - sy < H and 0 <= x - sx < W else None for x in range(W)] for y in range(H)]
    return out, moved


def import_pictures(frames, palettes):
    """The pictures in his own palettes (the poses'): {key: {"pixels", "cells"}} as import_rival gives poses."""
    def near(c, pal):
        return min((1, 2, 3), key=lambda k: dist(c, pal[k]))
    out = {}
    for key, fr in frames.items():
        small = {y * RW + x for x, y in _small_whites(fr)}   # (an eye's white the palette lacks: dear -- white to pink
        px = [from8(fr[y][x][:3]) if fr[y][x] else None for y in range(RH) for x in range(RW)]   # (as the sheets':
        pix = [0] * (RW * RH); kinds = []                                                         # Color's 5 bits)
        for cy in range(FIGHT_H):
            for cx in range(FIGHT_W):
                cell = [(cy * 8 + y) * RW + cx * 8 + x for y in range(8) for x in range(8)]
                errs = [sum(min(dist(px[i], pal[k]) for k in (1, 2, 3)) * (WHITE_DEAR if i in small else 1)
                            for i in cell if px[i]) for pal in palettes]
                bp = min(range(len(palettes)), key=lambda k: errs[k])
                for i in cell:
                    if px[i]:
                        pix[i] = near(px[i], palettes[bp])
                kinds.append(KINDS[bp])
        light = lambda c: min(c) >= 26
        red = lambda c: c[1] < 0.4 * c[0] and c[2] < 0.4 * c[0]
        around = lambda i: [j for j in (i - 1, i + 1, i - RW, i + RW, i - RW - 1, i - RW + 1, i + RW - 1, i + RW + 1)
                            if 0 <= j < RW * RH]
        lost = [i for i in range(RW * RH) if px[i] and light(px[i])                      # (a white his tile can't
                and not any(light(palettes[KINDS.index(kinds[(i // RW // 8) * FIGHT_W + (i % RW) // 8])][k]) for k in (1, 2, 3))
                and not any(px[j] and red(px[j]) for j in around(i))]
        out[key] = {"pixels": "".join(map(str, pix)), "cells": "".join(kinds)}   # show, not a glove's shine: an eye's,
        if lost:                                                                  # a sprite's on Color)
            out[key]["whites"] = lost
    return out


def _jewel(shape, gem=(236, 106, 100), cloth=(236, 238, 236)):
    """A turban's gem in a frame (Great Tiger's): the smallest patch of its color mostly bordered by the turban's
    white (not a glove), as (x, y) at its middle; None if it isn't showing."""
    pts = {p for p, c in shape.items() if tuple(c[:3]) == gem}
    best, seen = None, set()
    for p0 in pts:
        if p0 in seen:
            continue
        g, st = {p0}, [p0]
        while st:
            x, y = st.pop()
            for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if q in pts and q not in g:
                    g.add(q); st.append(q)
        seen |= g
        if len(g) > 16:
            continue
        ring = {(x + dx, y + dy) for x, y in g for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)} - g
        white = sum(1 for q in ring if q in shape and tuple(shape[q][:3]) == cloth)
        if white * 2 >= len(ring) * 0.6 and (best is None or len(g) < len(best)):
            best = g
    if not best:
        return None
    return (sum(x for x, _ in best) / len(best), sum(y for _, y in best) / len(best))


# The referee from the game: Mario, his three looks (nes_play.ref_frames), scaled as everyone is and set at
# the bottom of the kit's 24x32 frame. Pixels: 1 skin, 2 his cap's red, 3 black, 4 his shirt's white (sprite
# tiles with white take the second palette, his shirt's).
REF_INK = {(236, 180, 176): 1, (152, 34, 32): 2, (0, 0, 0): 3, (236, 238, 236): 4}
REF_COLORS = [[29, 22, 21], [19, 4, 4], [0, 0, 0]]          # skin, cap, black (NES $36, $16, $0F)
REF_SHIRT = [[29, 22, 21], [29, 29, 29], [0, 0, 0]]         # skin, shirt, black ($36, $30, $0F)

def _ref_shapes():
    """His three looks as the game draws them, each {(x, y) from his cap's top-left: color}."""
    import nes_play
    shapes = {}
    for look, img in nes_play.ref_frames().items():
        floor = img[0][0]
        on = {(x, y) for y in range(len(img)) for x in range(len(img[0])) if img[y][x] != floor}
        pieces, seen = [], set()
        for p0 in sorted(on):
            if p0 in seen:
                continue
            g, st = {p0}, [p0]
            while st:
                x, y = st.pop()
                for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if q in on and q not in g:
                        g.add(q); st.append(q)
            seen |= g
            pieces.append(g)
        him = max((g for g in pieces if any(img[y][x] == (152, 34, 32) for x, y in g)), key=len)   # (his cap: not
        cap = [(x, y) for x, y in him if img[y][x] == (152, 34, 32)]                              # the bubble)
        cx, cy = min(x for x, _ in cap), min(y for _, y in cap)     # every look lined up on his cap: what they
        shapes[look] = {(x - cx, y - cy): img[y][x] for x, y in him}  # share (head, legs) shares tiles
    return shapes


def _ref_frame(shapes):
    """Where his looks sit in the kit's 24x32: their box from his cap (x0, y0, W, H), the scale, the offset."""
    REF_W, REF_H = 24, 32
    xs = [x for sh in shapes.values() for x, _ in sh]; ys = [y for sh in shapes.values() for _, y in sh]
    x0, y0, W, H = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    s = min(REF_W / W, REF_H / H)
    small = scale([[None] * W for _ in range(H)], s)
    return x0, y0, W, H, s, (REF_W - len(small[0])) // 2, REF_H - len(small)


def ref_from_nes():
    """His three looks, one scale for all (the largest that fits the kit's 24x32), at the frame's bottom."""
    REF_W, REF_H = 24, 32
    shapes = _ref_shapes()
    x0, y0, W, H, s, _, _ = _ref_frame(shapes)
    out = {}
    for look, sh in shapes.items():
        pic = [[None] * W for _ in range(H)]
        for (x, y), c in sh.items():
            pic[y - y0][x - x0] = tuple(c) + (255,)
        small = scale(pic, s)
        ox, oy = (REF_W - len(small[0])) // 2, REF_H - len(small)
        frame = [[small[y - oy][x - ox] if 0 <= y - oy < len(small) and 0 <= x - ox < len(small[0]) else None
                  for x in range(REF_W)] for y in range(REF_H)]
        out[look] = "".join(str(REF_INK.get(tuple(c[:3]), 3)) if c else "0" for row in frame for c in row)
        baked = TOUCHUPS / "ref" / f"{look}.txt"         # (baked: touchups/ref/LOOK.txt, his eyes redrawn)
        if baked.exists():
            rows = [l for l in baked.read_text().splitlines() if l and not l.startswith(("#", "final"))]
            out[look] = "".join({".": "0", "s": "1", "r": "2", "K": "3", "W": "4"}[c] for r in rows for c in r)
    return out


# His words' bubbles (ref_words.py, the game's), scaled as he is and placed by him as the game places them: the
# letters' 1-pixel strokes kept (a pixel black once a third of what it covers is), each word's pixel grid where
# its letters read best (the scale's 3 NES pixels to 2: a stroke can fall between two).
WORD_PHASE = {"9": (1 / 3, 0), "KO": (2 / 3, 0), "FIGHT": (2 / 3, 1 / 3)}


def ref_words():
    """{word: [[x, y, pixels]]}: each bubble's 8x8 sprites, x and y from his 24x32 frame's top-left (pixels 2
    white, 3 black: his shirt's palette)."""
    import math
    import ref_words as RW
    x0, y0, _, _, s, ox, oy = _ref_frame(_ref_shapes())
    out = {}
    for word, px in RW.words().items():
        X0, Y0 = min(x for x, _ in px), min(y for _, y in px)
        w, h = max(x for x, _ in px) - X0 + 1, max(y for _, y in px) - Y0 + 1
        src = [[0] * w for _ in range(h)]
        for (x, y), c in px.items():
            src[y - Y0][x - X0] = 3 if sum(c) < 300 else 2
        fx, fy = WORD_PHASE.get(word, (0, 0))
        small = {}
        for Y in range(math.ceil(h * s) + 1):
            for X in range(math.ceil(w * s) + 1):
                a0, a1, b0, b1 = (Y - fy) / s, (Y + 1 - fy) / s, (X - fx) / s, (X + 1 - fx) / s
                cov = {0: 0, 2: 0, 3: 0}
                for yy in range(math.floor(a0), math.ceil(a1)):
                    for xx in range(math.floor(b0), math.ceil(b1)):
                        o = (min(a1, yy + 1) - max(a0, yy)) * (min(b1, xx + 1) - max(b0, xx))
                        if o > 0:
                            cov[src[yy][xx] if 0 <= yy < h and 0 <= xx < w else 0] += o
                if cov[2] + cov[3] > cov[0]:
                    small[(X, Y)] = 3 if cov[3] >= 0.35 * (cov[2] + cov[3]) else 2
        dx = round((X0 - x0) * s - fx + ox)     # (where he'd be drawn: his cap's offset, scaled as he is)
        dy = round((Y0 - y0) * s - fy + oy)
        sx, sy = min(x for x, _ in small), min(y for _, y in small)
        tiles = {}
        for (x, y), v in small.items():
            tiles.setdefault(((x - sx) // 8, (y - sy) // 8), {})[((x - sx) % 8, (y - sy) % 8)] = v
        out[word] = [[dx + sx + tx * 8, dy + sy + ty * 8, "".join(str(t.get((i % 8, i // 8), 0)) for i in range(64))]
                     for (tx, ty), t in sorted(tiles.items())]
    return out


def write_joe_frames(path, shapes, cols=8):
    """Every frame of his from a fight, as the game draws it (full size, on the floor's blue), his place at
    the same spot in each cell, in frame order (mirrored ones after): a sprite sheet of Glass Joe."""
    keys = sorted(shapes)
    CW, CH, PX, PY = 112, 140, 56, 134
    rows = (len(keys) + cols - 1) // cols
    img = [[(8, 76, 196, 255)] * (cols * CW) for _ in range(rows * CH)]
    for n, k in enumerate(keys):
        ox, oy = (n % cols) * CW, (n // cols) * CH
        for (x, y), c in shapes[k].items():
            if 0 <= PX + x < CW and 0 <= PY + y < CH:
                img[oy + PY + y][ox + PX + x] = tuple(c) + (255,)
    path.parent.mkdir(exist_ok=True)
    png.write(path, cols * CW, rows * CH, img)
    return [f"{f:02X}" + ("|" if fl else "") for f, fl in keys]


def joe_places(sheet, s, shapes=None, opponent=0):
    """Where each NES frame's pose sits: the game draws every frame at its own offset from his place (leaning
    into a hit, stepping into a hook, down on the mat), and each pose of ours is cut and placed on its own.
    Each frame of his, as the game draws it in a fight, scaled on the grid that puts his place at JOE_ANCHOR,
    is laid over the pose that shows it where they overlap most; that finds his place in the pose. The
    offsets (pixels right and down, from idle's) put the pose where the game draws the frame. {key: [dx, dy]},
    nonzero ones only."""
    shapes = shapes or joe_shapes(opponent)
    frames_map = FIGHTERS[opponent][0]
    ax, ay = round(JOE_ANCHOR[0] / s), round(JOE_ANCHOR[1] / s)
    W, H = round(RW / s) + 40, round(RH / s) + 40           # (room past the frame: a shape may reach out)
    _, _, px = png.read(sheet)
    def pose_rows(name):
        n = FIGHT_POSES.index(name); x0, y0 = (n % 4) * RW, (n // 4) * RH
        return [sum(1 << x for x in range(RW) if px[y0 + y][x0 + x][3]) for y in range(RH)]
    def scaled_rows(shape):                 # his place lands on (JOE_ANCHOR + 14, + 14) after scaling
        img = [[None] * W for _ in range(H)]
        for (x, y), c in shape.items():
            X, Y = x + ax + 20, y + ay + 20
            if 0 <= X < W and 0 <= Y < H:
                img[Y][X] = (255, 255, 255, 255)
        return [sum(1 << x for x, c in enumerate(r) if c) for r in scale(img, s, outline_weight=1.0)]
    pad = round(20 * s)
    def place(shape, name):
        a, b = scaled_rows(shape), pose_rows(name)
        best = (-1, 0, 0)
        for dy in range(-24, 25):
            for dx in range(-24, 25):
                n = 0
                for y, bits in enumerate(a):
                    Y = y - pad + dy
                    if bits and 0 <= Y < RH:
                        sh = dx - pad
                        n += bin((bits << sh if sh >= 0 else bits >> -sh) & b[Y]).count("1")
                if n > best[0]:
                    best = (n, dx, dy)
        return JOE_ANCHOR[0] + best[1], JOE_ANCHOR[1] + best[2]
    found = {key: place(shapes[_key(key)], name) for key, name in frames_map.items() if _key(key) in shapes}
    rx, ry = found.get("00") or next(found[k] for k, n in frames_map.items() if n == "idle" and k in found)   # (his stance)
    best = {}                               # per pose: its own frame's place (the one it was drawn from or
    for key, (x, y) in found.items():       # matched best; frames showing the same pose share it unless the
        best.setdefault(frames_map[key], (x, y))    # game really moves him: the same picture a pixel over
    out = {}                                        # is a jitter)
    for key, (x, y) in found.items():
        bx, by = best[frames_map[key]]
        if abs(x - bx) <= 2 and abs(y - by) <= 2:
            x, y = bx, by
        if (rx - x, ry - y) != (0, 0):
            out[key] = [rx - x, ry - y]
    return out


def mac_down_colors(colors, inks=None):
    """His knockdown palette in the order of his colors: each slot's ink (nearest of MAC_INK) as the NES shows it down."""
    out = []
    for c in colors:
        r, g, b = (v * 255 // 31 for v in c)
        ink = min(MAC_INK, key=lambda k: (k[0] - r) ** 2 + (k[1] - g) ** 2 + (k[2] - b) ** 2)
        out.append([v * 31 // 255 for v in (inks or MAC_DOWN_INK)[MAC_INK.index(ink)]])
    return out


PIC_NEXT = HERE / "out" / "pic-next.json"     # per rival: per picture, the one likely after it (pic_next.py)


def rival_art(key, s, colors, pposes, max_share=24):
    """A rival after Joe (NES_RIVALS) from the game's own frames: his poses (shared down only as far as his fight's
    tiles need, and finer for Color), palettes and where each frame sits."""
    r = NES_RIVALS[key]
    shapes = joe_shapes(r["opp"])
    sheet = HERE / "out" / f"{key}-from-nes.png"
    write_sheet(sheet, joe_from_nes(s, shapes, r["opp"]), RW, RH)
    jewels = dict(joe_from_nes.jewels)
    places = joe_places(sheet, s, shapes, r["opp"])
    poses, pals, moved = import_rival(str(sheet), [26, 28, 31])
    shared, how, report = fit_rival(poses, pals, colors, pposes, max_share, nth=r["nth"])   # (in his own fight)
    print(f"{r['name']}: {report}; tiles shared {how}; {len(places)} frames placed")
    cgb, how, report = fit_cgb(poses, shared, pals, colors, pposes, max_share, nth=r["nth"])
    print(f"{r['name']} on Color: {report}; tiles {how}")
    art = {"poses": shared, "pals": pals, "places": places, "cgb": cgb, "jewels": jewels}
    if r.get("pictures"):               # Color: every NES picture of his, exact (streamed as he shows it)
        every = joe_shapes(r["opp"], everything=True)
        frames_ = pictures_from_nes(s, every, r["opp"], blank_frames(r["opp"]))
        places = picture_places(frames_, s, every)      # (found as drawn, then each picture's move undone: he's
        drawn = frames_                                 # on screen where he was, the idle one's too)
        frames_, moved = align_pictures(frames_, pals)
        frames_ = apply_touchups(key, frames_)           # (hand touch-ups, over the very pictures they were drawn on)
        for k, (dx, dy) in touchup_moved(key).items():   # (and any move of theirs, undone on screen like align's)
            mx, my = moved.get(k, (0, 0))
            moved[k] = (mx + dx, my + dy)
        if key in DESPECKLE:
            frames_ = despeckle(frames_)                 # (then the shrink's stray dots, the touch-ups' hashes kept)
        places = {k: [x - moved.get(k, (0, 0))[0], y - moved.get(k, (0, 0))[1]]
                  for k, (x, y) in {k: places.get(k, [0, 0]) for k in frames_}.items()}
        art["pictures"] = {"poses": import_pictures(frames_, pals), "places": {k: v for k, v in places.items() if v != [0, 0]}}
        if r.get("jewel"):              # (Great Tiger's gem: where each picture shows it, not its pose's)
            gems = {k: _jewel({(x, y): c for y, row in enumerate(f) for x, c in enumerate(row) if c}) for k, f in drawn.items()}
            art["pictures"]["jewel"] = {k: [round(g[0]) + moved.get(k, (0, 0))[0], round(g[1]) + moved.get(k, (0, 0))[1]]
                                        for k, g in sorted(gems.items()) if g}     # (found as drawn, moved with it)
            for k, f in frames_.items():                # (a picture drawn anew -- a touch-up, warp.py's -- its gem
                if (TOUCHUPS / key / f"{touchup_name(k)}.txt").exists():   #  where that drawing has it)
                    g = _jewel({(x, y): c for y, row in enumerate(f) for x, c in enumerate(row) if c})
                    if g:
                        art["pictures"]["jewel"][k] = [round(g[0]), round(g[1])]
                    else:
                        art["pictures"]["jewel"].pop(k, None)
        nxt = json.loads(PIC_NEXT.read_text()).get(key) if PIC_NEXT.exists() else None
        if nxt:                         # (the original: the picture likely next, loaded early: pic_next.py)
            art["pictures"]["next"] = {k: v for k, v in nxt.items() if k in frames_ and v[0] in frames_}
        write_sheet(HERE / "out" / f"{key}-pictures.png", [frames_[k] for k in sorted(frames_)], RW, RH, cols=13)
        print(f"{r['name']}: {len(frames_)} pictures, exact for Color")
    return art


def fit_cgb(raw, shared, pals, colors, pposes, max_share=16, nth=0):
    """A rival's Game Boy Color poses (its second tile bank): unshared if they fit, else shared as little as
    fits. -> (poses, how, report)."""
    tried = {}
    def attempt(n):                     # (sharing more never needs more tiles: the least that fits, by halving)
        if n not in tried:
            cgb = raw if n == 0 else share_rival_tiles(raw, n)
            tried[n] = (cgb,) + tuple(budget(shared, pals, colors, pposes, cgb, nth))
        return tried[n]
    if attempt(0)[1]:
        return raw, "unshared", tried[0][2]
    lo, hi = 0, max_share
    if not attempt(hi)[1]:              # (over even so: his NES pictures are what show, not these)
        return tried[hi][0], f"within {hi} pixels (over: his pictures show)", tried[hi][2]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if attempt(mid)[1]:
            hi = mid
        else:
            lo = mid
    cgb, ok, report = attempt(hi)
    return cgb, f"within {hi} pixels", report


def fit_rival(poses, pals, colors, pposes, max_share=16, nth=0):
    """A rival's poses shared only as far as his fight's tiles need: everything within the least pixels that
    nearly fits, then the closest few pairs more. -> (poses, how it was shared, budget report)."""
    for n in range(max_share + 1):
        shared = share_rival_tiles(poses, n)
        ok, report = budget(shared, pals, colors, pposes, nth=nth)
        if ok:
            return shared, f"within {n} pixels", report
        over = re.search(r"uses (\d+) different 8x8 tiles.*the limit is (\d+)", report)
        extra = 0
        while over and int(over[1]) - int(over[2]) <= 16:   # just misses: the closest few more
            extra += int(over[1]) - int(over[2])
            merged, worst = merge_closest(shared, extra)
            ok, report = budget(merged, pals, colors, pposes, nth=nth)
            if ok:
                return merged, f"within {n} pixels, and {extra} more (up to {worst})", report
            over = re.search(r"uses (\d+) different 8x8 tiles.*the limit is (\d+)", report)
    return shared, f"within {max_share} pixels (still over: his NES pictures are what show, not these)", report


def write_js(colors, pposes, note, faces, mac_pal, rivals, mac_cgb=None, full=None):
    L = ["// Little Mac and his opponents from Punch-Out!! (NES), from a copy of the game. Written by tools/punchout_art/build.py",
         f"// ({note}).", "",
         "// Player sprite colors for slots 1-3.", f"export const MAC_COLORS = {json.dumps(colors)};", "",
         "export const MAC_POSES = {"]
    L += [f"  {n}: '{v}'," for n, v in pposes.items()]
    L += ["};", "", "// The same unshared, for Game Boy Color (its second bank's sprite tiles).", "export const MAC_POSES_CGB = {"]
    L += [f"  {n}: '{v}'," for n, v in (mac_cgb or pposes).items()]
    L += ["};", "", "// Close-ups, 48x48: pixels are slots; cells are each tile's palette, a digit into PORTRAIT_PALETTES.",
          f"export const TEXT_PALETTE = {json.dumps(TEXT_PALETTE)};", f"export const PORTRAIT_PALETTES = {json.dumps(mac_pal)};",
          f"export const PORTRAIT_GREYS = {json.dumps([FULL_GREYS.get(k) for k in range(len(mac_pal))])};   // (the original's greys, per slot)",
          "export const PORTRAITS = {"]
    L += [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in faces.items()]
    L += ["};", "", "// The NES's close-ups at full size (80x72): each rival's, and Doc and Mac (docmac) with the corner's four states.",
          "export const PORTRAITS_FULL = {"]
    L += [f"  {n}: {json.dumps(v)}," for n, v in (full or {}).items()]
    import base64
    L += ["};", "",
          "// What every fight shares of the NES game: Mac, the sound engine (each fighter's own NES data: X_NES).",
          f"export const NES_GAME = {{",
          f"  mac: '{base64.b64encode(DISASM_MAC.read_bytes()).decode()}',",
          f"  sound: '{base64.b64encode(DISASM_BANK.with_name('PRG_Bank008.bin').read_bytes()).decode()}',",
          f"  soundFixed: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x5400:0x5900]).decode()}',",
          f"  samples: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x4000:0x5400]).decode()}',",
          f"  macFrames: {json.dumps(MAC_FRAMES)}, macHome: 176, macScale: {SCALE_MAC},",
          f"  macPictures: {json.dumps(mac_pictures(SCALE_MAC, colors))},",
          f"  macPlaces: {json.dumps({**{k: [v, 1] for k, v in MAC_PLACES.items()}, **{k: [v, 0] for k, v in MAC_LIFTS.items()}})} }};", "",
          "// Little Mac knocked down: the NES's colors for him, slots 1-3 as MAC_COLORS.",
          f"export const MAC_DOWN_COLORS = {json.dumps(mac_down_colors(colors))};", "",
          "// Worn out (no hearts left): the NES turns his skin purple.",
          f"export const MAC_TIRED_COLORS = {json.dumps(mac_down_colors(colors, MAC_TIRED_INK))};", "",
          "// The title's logo: Punch-Out!!'s, from its title screen, over its blue mesh (slots: holes, mesh, orange, red).",
          f"export const TITLE_LOGO = {json.dumps(title_logo())};", "",
          *[line for key, art in rivals.items() for line in _rival_js(key, art)],
          "// The training scene after the Minor Circuit title: New York scrolling by, Doc and Mac (the game's).",
          f"export const INTERMISSION = {json.dumps(intermission_art())};", "",
          "// The screens between fights that aren't a fighter's: TITLE BOUT!!, the KO News page, THE DREAM FIGHT!! (the game's).",
          f"export const NES_SCREENS = {json.dumps(__import__('nes_screens').screens())};", "",
          "// Each fight's crowd color, as the NES game sets it (its background palette 2, color 2).",
          f"export const CROWD_COLORS = {json.dumps(crowd_colors())};", "",
          "// The crowd as the NES draws it: per crowd line, its spectators (\"1\") on the dark (\"\": a rope).",
          f"export const CROWD_ART = {json.dumps(crowd_art())};", "",
          "// Each circuit's ring, as the NES game colors it: the mat (and the posts' pads), the posts.",
          f"export const RING_COLORS = {json.dumps(ring_colors())};", "",
          "// The referee, Mario, from the game: 24x32, pixels 1 skin, 2 cap, 3 black, 4 shirt (its own palette).",
          f"export const REFEREE = {json.dumps({'poses': ref_from_nes(), 'colors': REF_COLORS, 'shirtColors': REF_SHIRT, 'words': ref_words()})};", "",
          "// The glove on the screen after a loss (the title's, as it first shows): slots dark red, light red, black.",
          f"export const LOSE_GLOVE = {json.dumps(lose_glove())};", "",
          "// What Start does on the title: the NES game's glove, flashing behind the logo, then punching out.",
          f"export const TITLE_PUNCH = {json.dumps(title_punch(24))};", "",
          "// The title's gloves either side of the chosen item: 24x16, slots white, red, black (its colors).",
          f"export const TITLE_GLOVES = {json.dumps(title_gloves())};", "",
          "// The ending after Mike Tyson: Mac standing (1:1, each tile's palette), his word, the timings.",
          f"export const ENDING = {json.dumps(ending())};", "",
          f"export const GAME_OVER = {json.dumps(game_over())};", "",
          "// The first screen: MIKE IS WAITING FOR YOUR CHALLENGE!!, the game's own (pixels, each tile's palette).",
          f"export const SPLASH = {json.dumps(splash())};", ""]
    OUT_JS.write_text("\n".join(L))

def _rival_js(key, art):
    """A rival after Joe's exports: his palettes, poses (and Color's), and his NES fighter bank."""
    import base64
    r, up = NES_RIVALS[key], key.upper()
    pose = lambda v: f"  {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }},"
    pic = lambda v: (f"  {{ pixels: '{v['pixels']}', cells: '{v['cells']}'"      # (and an eye's white his tile
                     + (f", whites: {json.dumps(v['whites'])}" if v.get("whites") else "") + " },")   # can't show)
    bank = (DISASM_BANK.with_name(f"PRG_Bank{r['bank']:03X}.bin")).read_bytes()
    return ([f"// {r['name']}: his poses and palettes (from the game's frames), his NES fighter bank (PRG bank {r['bank']}).",
             f"export const {up}_PALETTES = {json.dumps(art['pals'])};", f"export const {up}_POSES = {{"]
            + [f"  {n}:" + pose(v)[1:] for n, v in art["poses"].items()]
            + ["};", f"export const {up}_POSES_CGB = {{"]
            + [f"  {n}:" + pose(v)[1:] for n, v in art["cgb"].items()]
            + ["};"]
            + ([f"export const {up}_PICTURES = {{ poses: {{"]      # (Color: each NES picture of his, exact)
               + [f"  '{k}':" + pic(v)[1:] for k, v in sorted(art["pictures"]["poses"].items())]
               + [f"}}, places: {json.dumps(art['pictures']['places'])}"
                  + (f", next: {json.dumps(art['pictures']['next'])}" if art["pictures"].get("next") else "")
                  + (f", jewel: {json.dumps(art['pictures']['jewel'])}" if art["pictures"].get("jewel") else "") + " };"]
               if art.get("pictures") else [])
            + [f"export const {up}_NES = {{ bank: '{base64.b64encode(bank).decode()}', offset: {r['offset']},",
               f"  frames: {json.dumps(r['frames'])}, home: [135, 182], scale: {SCALE_JOE},",
               f"  places: {json.dumps(art['places'])}" + (f", pictures: {up}_PICTURES" if art.get("pictures") else "")
               + (", eyes: true" if r.get("eyes") else "") + " };"]
            + ([f"export const {up}_JEWEL = {json.dumps(art['jewels'])};   // his turban's gem: per pose, where (pixels in his area)"]
               if art.get("jewels") else []) + [""])


TRAINING_GREYS = [([9, 19, 29], 0), ([19, 26, 28], 0), ([31, 31, 31], 0),       # the training run's greys on the original,
                  ([18, 18, 18], 1), ([9, 25, 4], 1), ([29, 22, 21], 1),        # by what each color is (by brightness alone the
                  ([1, 9, 24], 2), ([1, 15, 0], 2), ([15, 7, 0], 2), ([10, 10, 10], 2),   # sky, the buildings and the grass
                  ([0, 0, 0], 3)]                                               # would be one grey): sky, sidewalk white;
                                                                                # buildings, grass, road light; water dark
TRAINING_POST = ["...##...", "..#BB#..", "..#B##..", "..#BB#..", "..#B##..", "..#BB#..", "..#B##..", "..#BB#..",   # (NES
                 "..#B##..", ".##BB##.", ".##B###.", ".##BB##.", "#.#B##.#", "..#BB#..", "..#B##..", "..#BB#..",  # rows
                 "..#B##..", "..#BB##.", "...#####"]                                                             # 147-165)


def intermission_art():
    """The training scene after the Minor Circuit title, from the game: New York at half size (512 NES pixels
    across: 256, the Game Boy's whole map width, so it scrolls round as the NES's does), six palettes; Doc on his
    bike and Mac running as sprites, a frame each time the game's change. -> dict for the template."""
    import nes_play
    pano, frames = nes_play.montage()
    pano = [list(row) for row in pano]
    for k in range(16):                     # the railing's posts: the NES's sprites (one every 32 pixels, moving
        for dy, line in enumerate(TRAINING_POST):          # with the sidewalk), its background the posts' feet
            for dx, ch in enumerate(line):
                if ch != ".":
                    pano[147 + dy][(24 + 32 * k + dx) % 512] = (0, 0, 0) if ch == "#" else (120, 60, 0)
    img = [[tuple(c) + (255,) for c in row] for row in pano[16:240]]
    small = scale(img, 0.5)                                       # 256 x 112
    for r in range(94, 112):                # the curb and road, the NES's fine checkerboard of its color and black:
        a, b = pano[16 + 2 * r], pano[17 + 2 * r]         # at half size the color flat (as it reads), not halved to
        if all(tuple(c) == (0, 0, 0) for c in a) or all(tuple(c) == (0, 0, 0) for c in b):   # its black; a black
            small[r] = [(0, 0, 0, 255)] * 256                                                  # line in either: black
            continue
        ink = next(tuple(c) for c in a if tuple(c) != (0, 0, 0))
        small[r] = [ink + (255,)] * 256
    sky = small[2][0]
    rows = [[sky] * 256 for _ in range(144 - len(small))] + small   # sky above, to 144
    px = [[from8(c[:3]) for c in row] for row in rows]
    tiles = [[px[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)] for cy in range(18) for cx in range(32)]
    pals = choose_palettes(tiles, 6)
    slots, cells = [0] * (256 * 144), []
    for k, tile in enumerate(tiles):
        best = min(range(len(pals)), key=lambda p: _tile_err(tile, pals[p]))
        cy, cx = divmod(k, 32)
        for n, c in enumerate(tile):
            slots[(cy * 8 + n // 8) * 256 + cx * 8 + n % 8] = min(range(4), key=lambda q: dist(c, pals[best][q]))
        cells.append(best)
    # the riders: the area they're in, each frame at half size, split where a gap of columns falls between them
    def crop(f):
        return [[f[y][x] for x in range(90, 250)] for y in range(160, 236)]
    halves = []
    for f in frames:
        c = scale([[tuple(p) + (255,) if p else None for p in row] for row in crop(f)], 0.625)   # (a little
                                                                                       # bigger than the city: they read)
        halves.append([[(from8(p[:3]) if p else None) for p in row] for row in c])
    H, W = len(halves[0]), len(halves[0][0])
    used = [x for x in range(W) if any(h[y][x] for h in halves for y in range(H))]
    gap = max((b2 for a, b2 in zip(used, used[1:]) if b2 - a > 2), default=None)
    groups = [[x for x in used if gap is None or x < gap], [x for x in used if gap is not None and x >= gap]]
    actors = []
    for xs in [g for g in groups if g]:
        x0, x1 = min(xs), max(xs) + 1
        ys = [y for y in range(H) if any(h[y][x] for h in halves for x in range(x0, x1))]
        y0, y1 = min(ys), max(ys) + 1
        w8, h8 = -(-(x1 - x0) // 8) * 8, -(-(y1 - y0) // 8) * 8
        actors.append({"x": round(90 * 0.625) + x0 - 14, "y": 144 - 16 - h8, "w": w8, "h": h8,
                       "frames": [[[h[y0 + y][x0 + x] if y0 + y < y1 and x0 + x < x1 else None for x in range(w8)]
                                   for y in range(h8)] for h in halves]})
    colors = {}                         # three sprite palettes (3 colors each): the riders' commonest, by tile
    tiles_s = []
    for a in actors:
        for fr in a["frames"]:
            for ty in range(0, a["h"], 8):
                for tx in range(0, a["w"], 8):
                    t = [fr[ty + y][tx + x] for y in range(8) for x in range(8) if fr[ty + y][tx + x]]
                    if t: tiles_s.append(t)
    black = [0, 0, 0]                   # their sprite palettes, from the game's colors: black (the outlines) and
    spals = [[[0, 14, 5], [6, 6, 29], black],           # the bike's green and blue; Mac's pink and skin; Doc's red
             [[29, 11, 22], [29, 22, 21], black],       # jacket and face (three: the fight's five sprite palettes
             [[18, 4, 4], [11, 0, 6], black]]           # kept), black last: on the original 1 light grey, 2 dark,
                                                        # 3 black (OBP0, Mac's); the bike's and Doc's OBP1 (odd)
                                                        # a shade darker (the cutscene's dmgDarkOdd)
    out_actors = []
    for a in actors:
        fl = []
        for fr in a["frames"]:
            pix, cl = [], []
            for ty in range(0, a["h"], 8):
                for tx in range(0, a["w"], 8):
                    t = [fr[ty + y][tx + x] for y in range(8) for x in range(8) if fr[ty + y][tx + x]]
                    cl.append(min(range(len(spals)), key=lambda p: sum(min(dist(c, q) for q in spals[p]) for c in t)) if t else 0)
            for y in range(a["h"]):
                for x in range(a["w"]):
                    c = fr[y][x]
                    p = spals[cl[(y // 8) * (a["w"] // 8) + x // 8]]
                    pix.append(0 if c is None else 1 + min(range(3), key=lambda q: dist(c, p[q])))
            fl.append({"pixels": "".join(map(str, pix)), "cells": "".join(map(str, cl))})
        out_actors.append({"x": a["x"], "y": a["y"], "w": a["w"], "h": a["h"], "frames": fl})
    grey = lambda c: min(TRAINING_GREYS, key=lambda rg: dist(c, rg[0]))[1]     # (the original's greys: by what each
    sky = pals[cells[0]][slots[0]]                                               #  color is, the box's too)
    return {"w": 256, "h": 144, "pixels": "".join(map(str, slots)), "cells": "".join(map(str, cells)),
            "palettes": pals, "greys": [[grey(c) for c in p] for p in pals],
            "boxGreys": [grey(sky), 0, 2, 3], "actors": out_actors, "objPalettes": spals}


# The crowd as the NES draws it (its own tiles, 1:1): its rows between the ropes, the spectators in the crowd's color
# on black. CROWD_ROWS: for each of the Game Boy's crowd lines (24 on), the NES line it shows (None: a rope).
CROWD_ROWS = [48, 49, 50, 51, 52, None, 55, 56, 57, 58, 59, 60, None, 63, 64, 65, 66, 67, 68, None, 72, 73, 74, 75]
CROWD_X = 24                                  # the NES's first crowd column shown (128 of them, the ring's width)

def crowd_art():
    """[24 strings of 128]: per crowd line, "1" a spectator's pixel, "0" the dark behind them; "" a rope."""
    cache = HERE / "out" / "nes-crowd-art.json"
    if cache.exists():
        return json.loads(cache.read_text())
    import cynes_frames as C
    from cynes import NES
    nes = NES(C.rom_path())
    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):
        run(4, C.START); nes[0x01] = 0; run(86)
        if nes[0x00] == 1:
            break
    f = run(200)
    dark = tuple(int(v) for v in f[CROWD_ROWS[0] - 5][CROWD_X])      # (the gap over the crowd: black)
    rows = ["" if y is None else "".join("0" if tuple(int(v) for v in f[y][x]) == dark else "1"
                                         for x in range(CROWD_X, CROWD_X + 128)) for y in CROWD_ROWS]
    cache.write_text(json.dumps(rows))
    return rows


def crowd_colors():
    """{joe, kaiser: RGB555}: the crowd's color in each one's fight, from the game's palette."""
    import nes_boot, nes_play
    cache = HERE / "out" / "nes-crowd.json"            # (each takes the game's boot and a fight to read)
    if cache.exists():
        return json.loads(cache.read_text())
    rgb5 = lambda v: [round(c * 31 / 255) for c in nes_boot.NES_RGB[v & 0x3F]]
    got = {name: rgb5(nes_play.ring_palette(opp)[10]) for name, opp in ((k, r["opp"]) for k, r in NES_RIVALS.items())}
    cache.write_text(json.dumps(got))
    return got


def ring_colors():
    """{circuit: {mat, post}: RGB555}: each circuit's ring from the game's palette (its first fight's)."""
    import nes_boot, nes_play
    cache = HERE / "out" / "nes-rings.json"
    if cache.exists():
        return json.loads(cache.read_text())
    rgb5 = lambda v: [round(c * 31 / 255) for c in nes_boot.NES_RGB[v & 0x3F]]
    got = {}
    for circuit, opp in (("minor", 0), ("major", 3), ("world", 7), ("dream", 13)):
        pal = nes_play.ring_palette(opp)
        got[circuit] = {"mat": rgb5(pal[0]), "post": rgb5(pal[5]), "wall": rgb5(pal[2]), "brick": rgb5(0x07)}
    cache.write_text(json.dumps(got))
    return got


def budget(poses, pals, colors, pposes, cgb=None, nth=0):
    """The fight scene's tiles on the original Game Boy (and with cgb, Color's finer poses' in its second
    bank), measured by the real project checks."""
    from gbstage import project, fight as kit
    p = json.loads(EXAMPLE.read_text())
    fights = [s for s in p["scenes"] if s.get("fight")]
    ft = fights[min(nth, len(fights) - 1)]["fight"]; bg = p["palettes"]["bg"]   # (nth: the game's nth fight's scene)
    for other in fights:                # (the others plain screens meanwhile: only this one is measured)
        if other["fight"] is not ft:
            other["fight"] = None
    for sc in p["scenes"]:              # (cutscenes aside, their sprite palettes too)
        sc.pop("cutscene", None)
    p["palettes"]["obj"] = p["palettes"]["obj"][:8]
    ft.pop("nes", None)                 # the budget is tiles: the NES logic (and a stale copy of it) aside
    ft["referee"].pop("words", None)    # (and the NES's bubbles, only an NES fight's: a plain one's are letters)
    ft["rival"]["poses"] = poses
    ft["rival"].pop("cgbPoses", None)
    if cgb:
        ft["rival"]["cgbPoses"] = cgb
    for k, kind in enumerate("sgh"): bg[ft["rival"]["palettes"][kind]]["colors"] = [bg[ft["rival"]["palettes"][kind]]["colors"][0]] + pals[k][1:]
    ft["player"]["poses"] = pposes
    op = p["palettes"]["obj"][ft["player"]["palette"]]; op["colors"] = [op["colors"][0]] + colors
    try:
        data = project.validate(copy.deepcopy(p))
    except project.ProjectError as e:
        return False, str(e)
    f = next(s for s in data["scenes"] if s.get("fight"))
    color = (f"; Color: rival pose sets {f['fight_cgb']['sizes']}, always-there {len(f['fight_cgb']['perm0']) + len(f['fight_cgb']['perm1'])}"
             if f.get("fight_cgb") else "")
    return True, (f"background tiles {len(f['tiles'])}/256, sprite tiles {f['fight_slots']['used']}/"
                  f"{kit.OBJ_TILE_LIMIT}; rival pose sets {f['fight_swap']['sizes']}" + color)

def write_example(strict=True):
    """examples/joe-vs-mac.gbstage.json, the project the editor builds from this art (the fight tests run it).
    Runs the editor's own code: macOS's JavaScriptCore shell, or Node anywhere."""
    import shutil, subprocess
    mod = str(HERE / "example.mjs")
    tries = [[str(JSC), "-m", mod]] if JSC.exists() else []
    if shutil.which("node"):            # (newer Node finds the modules on its own; older needs the flag)
        tries += [["node", mod], ["node", "--experimental-default-type=module", mod]]
    if not tries:
        print("(no JavaScript runtime here: install Node (nodejs.org), or open Joe vs Mac in the editor and Save it as",
              EXAMPLE.name, "instead)")
        return
    for cmd in tries:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.startswith("{"):
            EXAMPLE.write_text(r.stdout.strip() + "\n")
            print("wrote", EXAMPLE.relative_to(ROOT))
            return
    msg = "couldn't build the example project: " + (r.stderr or r.stdout)[:500]
    if strict:
        sys.exit(msg)
    print("(" + msg.strip() + "; measuring against the last one)")


DESPECKLE = set()                # (rivals whose shrink leaves stray dots: their pictures cleaned of them)
LINE_REDRAW = set()                   # (opponents whose inner lines the shrink breaks to dashes: drawn whole again)


def redraw_lines(img, small, s):
    """The NES picture's inner lines (its dark pixels inside him, not the outline) drawn again at the small size,
    whole: each pair of touching dark pixels a line between where they land, so a muscle's or a fold's line stays
    a line, not dashes. The shrink's colors stay everywhere else."""
    H, W = len(img), len(img[0])
    dark = lambda c: c is not None and sum(c[:3]) < 160
    inside = lambda x, y: all(0 <= x + dx < W and 0 <= y + dy < H and img[y + dy][x + dx] is not None
                              for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    out = [list(row) for row in small]
    h, w = len(out), len(out[0])
    def put(x, y, c):
        if 0 <= x < w and 0 <= y < h and out[y][x] is not None:
            out[y][x] = c
    for y in range(H):
        for x in range(W):
            c = img[y][x]
            if not dark(c) or not inside(x, y):
                continue
            x0, y0 = int(x * s), int(y * s)
            put(x0, y0, c)
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < W and 0 <= q[1] < H and dark(img[q[1]][q[0]]) and inside(*q):
                    x1, y1 = int(q[0] * s), int(q[1] * s)
                    n = max(abs(x1 - x0), abs(y1 - y0))
                    for t in range(1, n + 1):
                        put(x0 + round((x1 - x0) * t / n), y0 + round((y1 - y0) * t / n), c)
    return out


def despeckle(frames):
    """A shrink's stray dark pixel (a line of the NES's broken to a dot): alone, among one color all round (skin,
    trunks), it takes that color. A line's pixels have a dark neighbour and stay; the outline (next to the mat,
    nothing) too."""
    out = {}
    for k, f in frames.items():
        g = [list(row) for row in f]
        H, W = len(f), len(f[0])
        lum = lambda c: sum(c[:3]) if c else None
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                c = f[y][x]
                if not c or lum(c) > 150:
                    continue
                ring = [f[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
                if any(n is None for n in ring) or any(lum(n) <= 150 for n in ring):
                    continue
                kinds = {tuple(n[:3]) for n in ring}
                if len(kinds) == 1:
                    g[y][x] = ring[0]
        out[k] = g
    return out


def preview_only(key, s):
    """One fighter's pictures (or the referee's looks) alone, for a look: from the captures already cached, his
    pictures as the NES draws them (out/KEY-pictures.png) and as Color will show them, in his palettes
    (out/KEY-preview-color.png). Nothing else is rebuilt, and the editor's art isn't touched."""
    out = HERE / "out"
    rgba = lambda c: tuple((v << 3) | (v >> 2) for v in c) + (255,)
    if key == "referee":
        looks = ref_from_nes()
        ink = {v: k for k, v in REF_INK.items()}
        frames = [[[tuple(ink[int(ch)]) + (255,) if ch != "0" else None for ch in px[y * 24:(y + 1) * 24]]
                   for y in range(32)] for px in looks.values()]
        write_sheet(out / "referee-preview.png", frames, 24, 32)
        print("referee:", (out / "referee-preview.png").relative_to(ROOT))
        return
    r = NES_RIVALS[key]
    shapes = joe_shapes(r["opp"])
    sheet = out / f"{key}-from-nes.png"
    write_sheet(sheet, joe_from_nes(s, shapes, r["opp"]), RW, RH)
    _, pals, _ = import_rival(str(sheet), [26, 28, 31])
    every = joe_shapes(r["opp"], everything=True)
    frames_ = pictures_from_nes(s, every, r["opp"], blank_frames(r["opp"]))
    frames_, _ = align_pictures(frames_, pals)
    frames_ = apply_touchups(key, frames_)
    if key in DESPECKLE:
        frames_ = despeckle(frames_)
    write_sheet(out / f"{key}-pictures.png", [frames_[k] for k in sorted(frames_)], RW, RH, cols=13)
    pics = import_pictures(frames_, pals)
    shown = []
    for k in sorted(pics):
        px, cells = pics[k]["pixels"], pics[k]["cells"]
        pal = lambda i: pals[KINDS.index(cells[(i // RW // 8) * FIGHT_W + (i % RW) // 8])]
        shown.append([[rgba(pal(y * RW + x)[int(px[y * RW + x])]) if px[y * RW + x] != "0" else None
                       for x in range(RW)] for y in range(RH)])
    write_sheet(out / f"{key}-preview-color.png", shown, RW, RH, cols=13)
    print(f"{r['name']}: {len(pics)} pictures ->", (out / f"{key}-pictures.png").relative_to(ROOT), "and",
          (out / f"{key}-preview-color.png").relative_to(ROOT))


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--joe", type=float, default=0.7, help="Joe's scale from NES size (default 0.7)")
    a.add_argument("--mac", type=float, default=0.7, help="Mac's scale from NES size (default 0.7, as Joe's: all of him, reaching punches too)")
    a.add_argument("--max-share", type=int, default=10, help="most pixels a tile may change to share another (default 10)")
    a.add_argument("--mac-sheet", type=Path, help="use this edited 24x48-frame sheet instead of the rip")
    a.add_argument("--only", metavar="NAME", help="just one fighter's pictures (joe, kaiser, ... tyson) or 'referee', "
                   "for a look: out/NAME-pictures.png and NAME-preview-color.png; nothing else rebuilt")
    args = a.parse_args()
    if args.only:
        return preview_only(args.only, args.joe)
    write_example(strict=False)         # from the current editor code, so the budget below measures what it builds
    out = HERE / "out"
    mac_sheet = args.mac_sheet
    shapes = joe_shapes()               # his frames as the game draws them in a fight (for where each sits)
    order = write_joe_frames(out / "joe-nes-frames.png", shapes)
    print("Joe's NES frames:", (out / "joe-nes-frames.png").relative_to(ROOT), "-", " ".join(order))
    joe_sheet = out / "joe-from-nes.png"   # (his poses from the game's frames, as every rival's: for the budget below)
    write_sheet(joe_sheet, joe_from_nes(args.joe, shapes), RW, RH)
    if not mac_sheet:
        mac_sheet = out / "mac-from-nes.png"
        write_sheet(mac_sheet, mac_from_nes(args.mac), PW, PH)
    poses, pals, moved = import_rival(str(joe_sheet), [26, 28, 31])
    pposes, colors, pmoved = import_player(str(mac_sheet))
    print(f"Joe: {joe_sheet}  ({moved} tiles had a color moved)\nMac: {mac_sheet}  ({pmoved} pixels moved)")
    # Share near-duplicate tiles, only as much as it takes to fit: for each fighter, the smallest pixel
    # difference that works (the player's limit first, with the rival sharing as much as allowed).
    share = max(args.max_share, 24)    # (the game's frames: as far as the rivals')
    rival = {args.max_share: share_rival_tiles(poses, share)}   # (for measuring the player's)
    player = {n: share_player_tiles(pposes, n) for n in range(args.max_share + 1)}
    global SCALE_JOE, SCALE_MAC
    SCALE_JOE, SCALE_MAC = args.joe, args.mac
    if not EXAMPLE.exists():            # a first build: a provisional pack, so the editor can make the project to measure
        faces, mac_pal, full = portraits()
        write_js(colors, player[args.max_share], "provisional", faces, mac_pal,
                 {key: rival_art(key, args.joe, colors, player[args.max_share]) for key in NES_RIVALS}, full=full)
        write_example()
    def first(test):
        return next((n for n in range(args.max_share + 1) if test(n)), args.max_share)
    spare = 2 * sum(1 for r in NES_RIVALS.values() if r.get("jewel"))   # (room kept for a jewel and its fight)
    def tiles_ok(n):
        rep = budget(rival[args.max_share], pals, colors, player[n])[1]
        used = re.search(r"sprite tiles (\d+)/(\d+)", rep)
        return "player's poses" not in rep and (not used or int(used.group(1)) + spare <= int(used.group(2)))
    plim = first(tiles_ok)
    mac_cgb = share_player_tiles(pposes, 3)   # (Color: all of him, but a tile of a stray pixel or three: a sprite
                                              # each, and the 40 on screen are shared with the rival's head)
    pposes = player[plim]
    poses, how, report = fit_rival(poses, pals, colors, pposes, share)
    ok, report = budget(poses, pals, colors, pposes)
    print(f"{'fits' if ok else 'DOES NOT FIT'}: {report}" + f"; tiles shared {how} (Joe), within {plim} pixels (Mac)")
    write_preview(out / "preview.png", poses, pals, colors, pposes)
    print("preview:", (out / "preview.png").relative_to(ROOT))
    if not ok:
        sys.exit("editor/art/mac-vs-joe.js left as it was.")
    note = (f"rivals at {args.joe}, "
            f"Mac {'from ' + mac_sheet.name if args.mac_sheet else f'at {args.mac}'} of NES size")
    faces, mac_pal, full = portraits()
    rivals = {key: rival_art(key, args.joe, colors, pposes) for key in NES_RIVALS}
    write_js(colors, pposes, note, faces, mac_pal, rivals, mac_cgb, full=full)
    write_example()
    print("wrote", OUT_JS.relative_to(ROOT), "- reopen New > Examples > Joe vs Mac in the editor")

if __name__ == "__main__":
    main()
