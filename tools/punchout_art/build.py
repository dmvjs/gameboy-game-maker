"""Little Mac and Glass Joe from Punch-Out!! (NES) for the Mac vs Joe test sample. Local only: git ignores
this folder and editor/art/mac-vs-joe.js (.git/info/exclude).

    python3 tools/punchout_art/build.py                    # rebuild from the NES rips at the default scales
    python3 tools/punchout_art/build.py --joe 0.7 --mac 0.75
    python3 tools/punchout_art/build.py --joe-sheet my-joe.png --mac-sheet my-mac.png      # hand-edited sheets

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

def shrink_lines(f, s):
    """Shrink pixel art by dropping whole rows and columns (3 in every 10 at 0.7): in each block the ones that
    most repeat a neighbour, never two side by side, the blocks' phase the one losing least. What's kept is the
    art's own pixels, so thin lines (hair, straps, outlines) stay crisp instead of being voted away."""
    def same(a, b):
        return sum(1 for x, y in zip(a, b) if (x[:3] if x else None) != (y[:3] if y else None))
    def keep(rows):
        n = len(rows)
        cost = [min(same(rows[i], rows[i - 1]) if i else 99, same(rows[i], rows[i + 1]) if i + 1 < n else 99)
                for i in range(n)]
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
FIGHT_POSES = ['idle','idle2','guard','hit_l','hit_r','hit_body','dazed','jab_tell','jab_mid','jab','hook_tell','hook_mid','hook','slip','idle3','hit_back','kd_stagger','kd_fall','kd_down','kd_kneel','taunt','arm_pop','guard_low','tell1','tell2','tell3','tell4','tell5','kd2_stagger','kd2_fall','kd2_down','kd2_kneel']
TELL_FALLBACK = {**{f'tell{k}': 'jab_tell' for k in range(1, 6)}, **{f'kd2_{p}': f'kd_{p}' for p in ('stagger', 'fall', 'down', 'kneel')}}   # (a fighter without his own)
PLAYER_POSES = ['idle','jab','jab_high','dodge','block','hit','star','down','win']
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
    for n in range(count):
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

PLAYER_ORDER = ["idle", "jab", "block", "dodge", "hit", "jab_high", "star", "down", "win"]   # most seen first

def share_player_tiles(poses, limit):
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
                for k, unflip in ((key, lambda t: t), (flip(key), flip)):    # a mirrored tile is free too
                    got = _nearest(k, pool, limit) if limit else (k if k in pool else None)
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
PORTRAIT_PALETTES = {"joe": 5, "mac": 1, "kaiser": 5, "honda": 5, "don": 5, "hippo": 5}      # palettes per fighter's portraits (joe_hurt shares Joe's)
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
    if name in NES_RIVALS:
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

_cell = lambda k: str(k) if k < 10 else chr(65 + k - 10)   # a tile's palette: 0-9, then A-Z

def portraits():
    """({name: {pixels, cells}}, palettes): cells are digits, each tile's palette in the returned list."""
    faces = {name: portrait(name) for name in list(PORTRAITS) + list(NES_RIVALS)}
    out, palettes = {}, []
    for fighter, names in (("joe", ["joe", "joe_hurt"]), ("mac", ["mac"]), *((r, [r]) for r in NES_RIVALS)):
        pals = choose_palettes([t for n in names for t in _tiles(faces[n])], PORTRAIT_PALETTES[fighter])
        for n in names:
            slots, cells = _draw(faces[n], pals)
            out[n] = {"pixels": "".join(map(str, slots)), "cells": "".join(_cell(len(palettes) + c) for c in cells)}
        palettes += pals
    return out, palettes


# ---- output ----

def write_preview(path, poses, pals, colors, pposes, zoom=3):
    """What the game will show: every rival pose, then every player pose, in Game Boy Color colors."""
    rgb = lambda c: tuple((v << 3) | (v >> 2) for v in c) + (255,)
    mat = rgb(pals[0][0]); n = len(poses); cols = 6
    cw, chh = RW + 4, RH + 4
    W = cols * cw; H = ((n + cols - 1) // cols) * chh + PH + 8
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
    **{k: "idle" for k in ("00", "01", "58", "54", "12", "13", "1C", "05")},     # (05 is his duck: no pose for it)
    **{k: "dodge" for k in ("08", "09", "0A", "60", "07")}, **{k: "dodge|" for k in ("0B", "0C", "61", "0D")},  # (the art is 0A)
    **{k: "block" for k in ("5F", "5E", "06", "23", "24")},
    **{k: "jab" for k in ("0E", "0F", "10", "11")}, **{k: "jab|" for k in ("14", "15", "16")},   # (11, 16: full reach)
    **{k: "jab_high" for k in ("17", "18", "19")}, **{k: "jab_high|" for k in ("1D", "1E", "1F")},
    **{f"{k:02X}": "star" for k in range(0x25, 0x2F)},
    **{k: "hit" for k in ("2F", "30", "33")}, **{k: "hit|" for k in ("31", "32", "34")},
    "3A": "hit", "3B": "hit",                               # his knockdown: knocked back, facing us,
    **{f"{k:02X}": "down" for k in range(0x3C, 0x44)},     # then sinking below the screen's edge (40-43: gone),
    **{f"{k:02X}": "idle" for k in range(0x44, 0x48)},     # and back up from behind, rising into view
    "48": "idle",                                           # (its top, $48, is him standing: the intro, and up)
    "55": "win", "56": "win", "57": "win",                  # he's won: turned to the camera, gloves up
    "19": "jab_high", "1A": "jab_high", "1B": "jab_high", "1F": "jab_high|", "20": "jab_high|", "21": "jab_high|",   # his punch to the face, all the way up
    "35": "hit", **{f"{k:02X}": "down" for k in range(0x36, 0x3A)},           # his other knockdown: back, then sinking
    **{f"{k:02X}": "idle" for k in range(0x49, 0x54)},     # the round's start: up into view from below
    "04": "block",                                          # (his duck: the block, lower)
}
# ... where those frames sit (pixels down: the NES draws them lower each frame, cut off at the screen's
# bottom; 48 is all the way under) and in his knockdown colors, pink (NES $25), green ($2A), dark ($08):
# the colors he flashes whenever he's hit.
MAC_PLACES = {**{f"{k:02X}": 0 for k in range(0x2F, 0x35)},          # (hit, he shows the same colors)
              "3A": 0, "3B": 0, "3C": 0, "3D": 6, "3E": 11, "3F": 17, "40": 48, "41": 48, "42": 48, "43": 48,
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


# Little Mac's poses from the NES game's own frames (mac_nes.py draws them as bank B does); the rest from the rip.
MAC_NES = dict(idle=0x00, jab=0x10, jab_high=0x1A, dodge=0x0A, block=0x5F, hit=0x2F, down=0x3C, win=0x55)
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
            small = shrink_lines(f, s)          # (the game's own pixels, kept crisp)
        else:
            small = scale(cut(rip, boxes[MAC[pose]]), s, outline_weight=1.0)
        out.append(place(small, PW, PH, PH - len(small)))
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
    "3A": "taunt", "3C": "arm_pop",
}
HONDA_FROM_NES = dict(idle="C0", idle2="C2", idle3="04", guard="08", guard_low="42|", jab_tell="40", jab_mid="16",
                      jab="18", hook_tell="54|", hook_mid="48", hook="3E|", slip="4A", hit_l="22", hit_r="1E",
                      hit_body="1C", hit_back="1A", dazed="C8", kd_stagger="26", kd_fall="28", kd_down="2A",
                      kd_kneel="2C", taunt="3A", arm_pop="3C", tell1="0A", tell2="D0", tell3="CE", tell4="80",
                      tell5="82", kd2_stagger="30|", kd2_fall="32|", kd2_down="34|", kd2_kneel="36|")
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
    "3A": "taunt", "3E": "tell3",
}
DON_FROM_NES = dict(idle="C0", idle2="C4", idle3="C2", guard="08", guard_low="0A", jab_tell="10", jab_mid="18",
                    jab="40", hook_tell="16", hook_mid="18", hook="1A", slip="C6", hit_l="22|", hit_r="1E",
                    hit_body="1C", hit_back="24", dazed="C8", kd_stagger="26", kd_fall="28", kd_down="2A",
                    kd_kneel="2C", taunt="3A", arm_pop="3E", tell1="3C", tell2="CC", tell3="3E", tell4="82",
                    tell5="86", kd2_stagger="30", kd2_fall="32", kd2_down="34", kd2_kneel="36|")
# King Hippo (opponent 4, bank 1): his jab 12-C6-16 (states 05, 15), his big swing 14|-C6-3C|-3C (state 16), his
# mouth open as he winds up (24, 3A; both arms 20, 22: the opening), his shout CC (19); down, he sits (28, 80-88).
HIPPO_FRAMES = {
    "C0": "idle", "C4": "idle2", "C8": "idle3", "CA": "idle2", "00": "idle", "10": "guard",
    "12": "jab_tell", "C6": "jab_mid", "16": "jab", "14|": "hook_tell", "3C|": "hook_mid", "3C": "hook",
    "24": "tell1", "24|": "tell2", "3A": "tell3", "20": "tell4", "22": "tell5", "CC": "taunt",
    "26": "hit_back", "30|": "hit_l", "30": "hit_r",
    "28": "kd_fall", "80": "kd_down", "82": "kd_down", "86": "kd_kneel", "88": "kd_kneel",
}
HIPPO_FROM_NES = dict(idle="C0", idle2="C4", idle3="C8", guard="10", guard_low="00", jab_tell="12", jab_mid="C6",
                      jab="16", hook_tell="14|", hook_mid="3C|", hook="3C", slip="C6", hit_l="30|", hit_r="26",
                      hit_body="26", hit_back="26", dazed="30|", kd_stagger="26", kd_fall="28", kd_down="80",
                      kd_kneel="86", taunt="CC", arm_pop="20", tell1="24", tell2="24|", tell3="3A", tell4="20",
                      tell5="22", kd2_stagger="26", kd2_fall="28", kd2_down="82", kd2_kneel="88")
# The rivals after Joe, from their NES fights: opponent number, fighter bank (and offset), frames, and the game's
# nth fight (where their tiles are measured).
NES_RIVALS = {
    "kaiser": dict(name="Von Kaiser", opp=1, bank=2, offset=0x00, frames=KAISER_FRAMES, canon=KAISER_FROM_NES, nth=1),
    "honda": dict(name="Piston Honda", opp=2, bank=5, offset=0x30, frames=HONDA_FRAMES, canon=HONDA_FROM_NES, nth=2),
    "don": dict(name="Don Flamenco", opp=3, bank=0, offset=0x10, frames=DON_FRAMES, canon=DON_FROM_NES, nth=3),
    "hippo": dict(name="King Hippo", opp=4, bank=1, offset=0x00, frames=HIPPO_FRAMES, canon=HIPPO_FROM_NES, nth=4),
}
FIGHTERS = {0: (NES_FRAMES, JOE_FROM_NES), **{r["opp"]: (r["frames"], r["canon"]) for r in NES_RIVALS.values()}}


def joe_shapes(opponent=0):
    """{(frame, mirrored): {(x, y) from his place: color}}: each frame of his from a fight, his biggest piece
    (not a speck of another sprite, nor the referee)."""
    import nes_play
    frames_map, canon = FIGHTERS[opponent]
    wanted = {_key(k) for k in list(frames_map) + list(canon.values())} if opponent == 0 else None
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
        him = max(near or pieces, key=len)
        out[key] = {(x - px, y - py): img[y][x] for x, y in him}
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
    frames, moved = [], {}
    for name in FIGHT_POSES:
        shape = shapes[_key(canon.get(name) or canon[TELL_FALLBACK[name]])]
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
        small = scale(img, s)
        frame = [[small[y][x] if y < len(small) and x < len(small[0]) else None for x in range(RW)] for y in range(RH)]
        frames.append(frame)
        moved[name] = (round(mx * s), round(my * s))
    joe_from_nes.moved = moved
    return frames


# The referee from the game: Mario, his three looks (nes_play.ref_frames), scaled as everyone is and set at
# the bottom of the kit's 24x32 frame. Pixels: 1 skin, 2 his cap's red, 3 black, 4 his shirt's white (sprite
# tiles with white take the second palette, his shirt's).
REF_INK = {(236, 180, 176): 1, (152, 34, 32): 2, (0, 0, 0): 3, (236, 238, 236): 4}
REF_COLORS = [[29, 22, 21], [19, 4, 4], [0, 0, 0]]          # skin, cap, black (NES $36, $16, $0F)
REF_SHIRT = [[29, 22, 21], [29, 29, 29], [0, 0, 0]]         # skin, shirt, black ($36, $30, $0F)

def ref_from_nes():
    """His three looks, one scale for all (the largest that fits the kit's 24x32), at the frame's bottom."""
    import nes_play
    REF_W, REF_H = 24, 32
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
    xs = [x for sh in shapes.values() for x, _ in sh]; ys = [y for sh in shapes.values() for _, y in sh]
    x0, y0, W, H = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    s = min(REF_W / W, REF_H / H)
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
    rx, ry = found["00"]
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


def rival_art(key, s, colors, pposes, max_share=24):
    """A rival after Joe (NES_RIVALS) from the game's own frames: his poses (shared down only as far as his fight's
    tiles need, and finer for Color), palettes and where each frame sits."""
    r = NES_RIVALS[key]
    shapes = joe_shapes(r["opp"])
    sheet = HERE / "out" / f"{key}-from-nes.png"
    write_sheet(sheet, joe_from_nes(s, shapes, r["opp"]), RW, RH)
    places = joe_places(sheet, s, shapes, r["opp"])
    poses, pals, moved = import_rival(str(sheet), [26, 28, 31])
    shared, how, report = fit_rival(poses, pals, colors, pposes, max_share, nth=r["nth"])   # (in his own fight)
    print(f"{r['name']}: {report}; tiles shared {how}; {len(places)} frames placed")
    cgb, how, report = fit_cgb(poses, shared, pals, colors, pposes, max_share, nth=r["nth"])
    print(f"{r['name']} on Color: {report}; tiles {how}")
    return {"poses": shared, "pals": pals, "places": places, "cgb": cgb}


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
    if not attempt(hi)[1]:
        sys.exit("The rival's Game Boy Color poses don't fit.")
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
    sys.exit("The rival's poses don't fit his fight's tiles.")


def write_js(poses, pals, colors, pposes, note, faces, mac_pal, places=None, rivals=None, joe_cgb=None, mac_cgb=None):
    L = ["// Little Mac and Glass Joe from Punch-Out!! (NES), for local testing only. Written by tools/punchout_art/build.py",
         f"// ({note}). Not original art: keep it out of commits and builds you share.", "",
         "// Rival palettes s, g, h (slot 0 is the mat, replaced at load).",
         f"export const JOE_PALETTES = {json.dumps(pals)};", "", "export const JOE_POSES = {"]
    L += [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in poses.items()]
    L += ["};", "", "// The same, finer, for Game Boy Color (its second tile bank)."]
    L += ["export const JOE_POSES_CGB = {"] + [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in (joe_cgb or poses).items()]
    L += ["};", "", "// Player sprite colors for slots 1-3.", f"export const MAC_COLORS = {json.dumps(colors)};", "",
          "export const MAC_POSES = {"]
    L += [f"  {n}: '{v}'," for n, v in pposes.items()]
    L += ["};", "", "// The same unshared, for Game Boy Color (its second bank's sprite tiles).", "export const MAC_POSES_CGB = {"]
    L += [f"  {n}: '{v}'," for n, v in (mac_cgb or pposes).items()]
    L += ["};", "", "// Close-ups, 48x48: pixels are slots; cells are each tile's palette, a digit into PORTRAIT_PALETTES.",
          f"export const TEXT_PALETTE = {json.dumps(TEXT_PALETTE)};", f"export const PORTRAIT_PALETTES = {json.dumps(mac_pal)};",
          "export const PORTRAITS = {"]
    L += [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in faces.items()]
    import base64
    L += ["};", "", "// Glass Joe's NES fighter bank (Punch-Out!! PRG bank 0) and our pose for each of its frames.",
          f"export const JOE_NES = {{ bank: '{base64.b64encode(DISASM_BANK.read_bytes()).decode()}', offset: 0,",
          f"  frames: {json.dumps(NES_FRAMES)}, home: [135, 182], scale: {SCALE_JOE},",
          f"  places: {json.dumps(places or {})},",
          f"  mac: '{base64.b64encode(DISASM_MAC.read_bytes()).decode()}',",
          f"  sound: '{base64.b64encode(DISASM_BANK.with_name('PRG_Bank008.bin').read_bytes()).decode()}',",
          f"  soundFixed: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x5400:0x5900]).decode()}',",
          f"  samples: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x4000:0x5400]).decode()}',",
          f"  macFrames: {json.dumps(MAC_FRAMES)}, macHome: 176, macScale: {SCALE_MAC},",
          f"  macPlaces: {json.dumps({**{k: [v, 1] for k, v in MAC_PLACES.items()}, **{k: [v, 0] for k, v in MAC_LIFTS.items()}})} }};", "",
          "// Little Mac knocked down: the NES's colors for him, slots 1-3 as MAC_COLORS.",
          f"export const MAC_DOWN_COLORS = {json.dumps(mac_down_colors(colors))};", "",
          "// Worn out (no hearts left): the NES turns his skin purple.",
          f"export const MAC_TIRED_COLORS = {json.dumps(mac_down_colors(colors, MAC_TIRED_INK))};", "",
          "// The title's logo: Punch-Out!!'s, from its title screen, over its blue mesh (slots: holes, mesh, orange, red).",
          f"export const TITLE_LOGO = {json.dumps(title_logo())};", "",
          *[line for key, art in (rivals or {}).items() for line in _rival_js(key, art)],
          "// The training scene after the Minor Circuit title: New York scrolling by, Doc and Mac (the game's).",
          f"export const INTERMISSION = {json.dumps(intermission_art())};", "",
          "// Each fight's crowd color, as the NES game sets it (its background palette 2, color 2).",
          f"export const CROWD_COLORS = {json.dumps(crowd_colors())};", "",
          "// Each circuit's ring, as the NES game colors it: the mat (and the posts' pads), the posts.",
          f"export const RING_COLORS = {json.dumps(ring_colors())};", "",
          "// The referee, Mario, from the game: 24x32, pixels 1 skin, 2 cap, 3 black, 4 shirt (its own palette).",
          f"export const REFEREE = {json.dumps({'poses': ref_from_nes(), 'colors': REF_COLORS, 'shirtColors': REF_SHIRT})};", "",
          "// The glove on the screen after a loss (the title's, as it first shows): slots dark red, light red, black.",
          f"export const LOSE_GLOVE = {json.dumps(lose_glove())};", "",
          "// What Start does on the title: the NES game's glove, flashing behind the logo, then punching out.",
          f"export const TITLE_PUNCH = {json.dumps(title_punch(24))};", ""]
    OUT_JS.write_text("\n".join(L))

def _rival_js(key, art):
    """A rival after Joe's exports: his palettes, poses (and Color's), and his NES fighter bank."""
    import base64
    r, up = NES_RIVALS[key], key.upper()
    pose = lambda v: f"  {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }},"
    bank = (DISASM_BANK.with_name(f"PRG_Bank{r['bank']:03X}.bin")).read_bytes()
    return ([f"// {r['name']}: his poses and palettes (from the game's frames), his NES fighter bank (PRG bank {r['bank']}).",
             f"export const {up}_PALETTES = {json.dumps(art['pals'])};", f"export const {up}_POSES = {{"]
            + [f"  {n}:" + pose(v)[1:] for n, v in art["poses"].items()]
            + ["};", f"export const {up}_POSES_CGB = {{"]
            + [f"  {n}:" + pose(v)[1:] for n, v in art["cgb"].items()]
            + ["};", f"export const {up}_NES = {{ bank: '{base64.b64encode(bank).decode()}', offset: {r['offset']},",
               f"  frames: {json.dumps(r['frames'])}, home: [135, 182], scale: {SCALE_JOE},",
               f"  places: {json.dumps(art['places'])} }};", ""])


def intermission_art():
    """The training scene after the Minor Circuit title, from the game: New York at half size (512 NES pixels
    across: 256, the Game Boy's whole map width, so it scrolls round as the NES's does), six palettes; Doc on his
    bike and Mac running as sprites, a frame each time the game's change. -> dict for the template."""
    import nes_play
    pano, frames = nes_play.montage()
    img = [[tuple(c) + (255,) for c in row] for row in pano[16:240]]
    small = scale(img, 0.5)                                       # 256 x 112
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
    spals = [[black, [29, 11, 22], [29, 22, 21]],       # Mac's pink and skin; Doc's red jacket and face;
             [black, [18, 4, 4], [11, 0, 6]],           # the bike's green and blue (three: the fight's five
             [black, [0, 14, 5], [6, 6, 29]]]           # sprite palettes are kept)
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
    return {"w": 256, "h": 144, "pixels": "".join(map(str, slots)), "cells": "".join(map(str, cells)),
            "palettes": pals, "actors": out_actors, "objPalettes": spals}


def crowd_colors():
    """{joe, kaiser: RGB555}: the crowd's color in each one's fight, from the game's palette."""
    import nes_boot, nes_play
    cache = HERE / "out" / "nes-crowd.json"            # (each takes the game's boot and a fight to read)
    if cache.exists():
        return json.loads(cache.read_text())
    rgb5 = lambda v: [round(c * 31 / 255) for c in nes_boot.NES_RGB[v & 0x3F]]
    got = {name: rgb5(nes_play.ring_palette(opp)[10]) for name, opp in (("joe", 0), *((k, r["opp"]) for k, r in NES_RIVALS.items()))}
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


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--joe", type=float, default=0.7, help="Joe's scale from NES size (default 0.7)")
    a.add_argument("--mac", type=float, default=0.7, help="Mac's scale from NES size (default 0.7, as Joe's: all of him, reaching punches too)")
    a.add_argument("--max-share", type=int, default=10, help="most pixels a tile may change to share another (default 10)")
    a.add_argument("--joe-sheet", type=Path, help="use this edited 64x80-frame sheet instead of the rip")
    a.add_argument("--joe-rip", dest="joe_nes", action="store_false", help="Joe's poses from the rip sheet instead of the game's own frames (as the rivals after him)")
    a.add_argument("--mac-sheet", type=Path, help="use this edited 24x48-frame sheet instead of the rip")
    args = a.parse_args()
    write_example(strict=False)         # from the current editor code, so the budget below measures what it builds
    out = HERE / "out"
    joe_sheet, mac_sheet = args.joe_sheet, args.mac_sheet
    shapes = joe_shapes()               # his frames as the game draws them in a fight (for where each sits)
    order = write_joe_frames(out / "joe-nes-frames.png", shapes)
    print("Joe's NES frames:", (out / "joe-nes-frames.png").relative_to(ROOT), "-", " ".join(order))
    if not joe_sheet and args.joe_nes:  # (his poses drawn from them too: more tiles than a fight has on the
        joe_sheet = out / "joe-from-nes.png"        # original Game Boy, shared down to fit)
        write_sheet(joe_sheet, joe_from_nes(args.joe, shapes), RW, RH)
    if not joe_sheet:
        joe_sheet = out / "joe-from-rip.png"
        write_sheet(joe_sheet, frames_from_rip(HERE / "sources" / "glass-joe.png", JOE, args.joe, RW, RH, 104, JOE_ROWS, 112), RW, RH)
    if not mac_sheet:
        mac_sheet = out / "mac-from-nes.png"
        write_sheet(mac_sheet, mac_from_nes(args.mac), PW, PH)
    poses, pals, moved = import_rival(str(joe_sheet), [26, 28, 31])
    pposes, colors, pmoved = import_player(str(mac_sheet))
    print(f"Joe: {joe_sheet}  ({moved} tiles had a color moved)\nMac: {mac_sheet}  ({pmoved} pixels moved)")
    # Share near-duplicate tiles, only as much as it takes to fit: for each fighter, the smallest pixel
    # difference that works (the player's limit first, with the rival sharing as much as allowed).
    share = max(args.max_share, 24) if args.joe_nes else args.max_share   # (the game's frames: as far as the rivals')
    rival = {args.max_share: share_rival_tiles(poses, share)}   # (for measuring the player's)
    player = {n: share_player_tiles(pposes, n) for n in range(args.max_share + 1)}
    global SCALE_JOE, SCALE_MAC
    SCALE_JOE, SCALE_MAC = args.joe, args.mac
    if not EXAMPLE.exists():            # a first build: a provisional pack, so the editor can make the project to measure
        faces, mac_pal = portraits()
        write_js(rival[args.max_share], pals, colors, player[args.max_share], "provisional", faces, mac_pal)
        write_example()
    def first(test):
        return next((n for n in range(args.max_share + 1) if test(n)), args.max_share)
    plim = first(lambda n: "player's poses" not in budget(rival[args.max_share], pals, colors, player[n])[1])
    mac_cgb = share_player_tiles(pposes, 3)   # (Color: all of him, but a tile of a stray pixel or three: a sprite
                                              # each, and the 40 on screen are shared with the rival's head)
    pposes = player[plim]
    raw = poses
    poses, how, report = fit_rival(poses, pals, colors, pposes, share)
    joe_cgb, cgb_how, cgb_report = fit_cgb(raw, poses, pals, colors, pposes, share)
    print(f"Joe on Color: {cgb_report}; tiles {cgb_how}")
    ok, report = budget(poses, pals, colors, pposes)
    print(f"{'fits' if ok else 'DOES NOT FIT'}: {report}" + f"; tiles shared {how} (Joe), within {plim} pixels (Mac)")
    write_preview(out / "preview.png", poses, pals, colors, pposes)
    print("preview:", (out / "preview.png").relative_to(ROOT))
    if not ok:
        sys.exit("editor/art/mac-vs-joe.js left as it was.")
    note = (f"Joe {'from ' + joe_sheet.name if args.joe_sheet else f'at {args.joe}'}, "
            f"Mac {'from ' + mac_sheet.name if args.mac_sheet else f'at {args.mac}'} of NES size")
    faces, mac_pal = portraits()
    places = joe_places(joe_sheet, args.joe, shapes)
    print("Joe's frames placed as the NES draws them:", len(places), "moved")
    rivals = {key: rival_art(key, args.joe, colors, pposes) for key in NES_RIVALS}
    write_js(poses, pals, colors, pposes, note, faces, mac_pal, places, rivals, joe_cgb, mac_cgb)
    write_example()
    print("wrote", OUT_JS.relative_to(ROOT), "- reopen New > Examples > Joe vs Mac in the editor")

if __name__ == "__main__":
    main()
