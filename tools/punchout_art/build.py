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
import argparse, copy, json, sys
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
           kd_down=49, kd_kneel=45, taunt=6, arm_pop=10, guard_low=31)
MAC = dict(idle=0, jab=2, jab_high=7, dodge=5, block=38, hit=34, star=30, down=37, win=24)
KD = {"kd_fall", "kd_down", "kd_kneel", "kd_stagger"}     # sit on the floor of the frame
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
                    score[k] = score.get(k, 0) + oy * ox * (outline_weight if k == dark else 1)
            k = max(score, key=score.get)
            row.append(k + (255,) if k else None)
        out.append(row)
    return out

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
FIGHT_POSES = ['idle','idle2','guard','hit_l','hit_r','hit_body','dazed','jab_tell','jab_mid','jab','hook_tell','hook_mid','hook','slip','idle3','hit_back','kd_stagger','kd_fall','kd_down','kd_kneel','taunt','arm_pop','guard_low']
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
PORTRAIT_PALETTES = {"joe": 5, "mac": 2}      # palettes per fighter's portraits (joe_hurt shares Joe's)
FRAME = [31, 31, 31]

def portrait(name):
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

def portraits():
    """({name: {pixels, cells}}, palettes): cells are digits, each tile's palette in the returned list."""
    faces = {name: portrait(name) for name in PORTRAITS}
    out, palettes = {}, []
    for fighter, names in (("joe", ["joe", "joe_hurt"]), ("mac", ["mac"])):
        pals = choose_palettes([t for n in names for t in _tiles(faces[n])], PORTRAIT_PALETTES[fighter])
        for n in names:
            slots, cells = _draw(faces[n], pals)
            out[n] = {"pixels": "".join(map(str, slots)), "cells": "".join(str(len(palettes) + c) for c in cells)}
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
    "08": "guard", "0A": "guard_low", "0C": "idle2", "0E": "jab", "10": "guard_low", "12": "guard", "14": "guard",
    "C6": "guard", "16": "hook_tell", "18": "hook", "1A": "hook_mid", "1C": "hit_body", "1E": "hit_r",
    "20": "hit_r", "22": "hit_l", "24": "hit_back", "C8": "dazed", "CA": "dazed", "CC": "jab_tell",
    "80": "guard", "82": "idle", "84": "slip", "86": "jab_mid", "26": "kd_fall", "30": "kd_stagger",
    "28": "kd_fall", "32": "kd_stagger", "2A": "kd_down", "34": "kd_down", "2C": "kd_kneel", "36": "kd_stagger",
    "2E": "kd_kneel", "38": "kd_stagger", "3A": "taunt",
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
    **{f"{k:02X}": "down" for k in range(0x3A, 0x48)},     # his knockdown: falling, gone below, rising (40/43
                                                            # draw nothing: he's under the screen's edge)
    "48": "idle",                                           # (its top, $48, is him standing: the intro, and up)
}

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
                out.append(1 if x % 3 == 0 or y % 3 == 0 else 0)
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


# Little Mac's poses from the NES game's own frames (mac_nes.py draws them as bank B does); the rest from the rip.
MAC_NES = dict(idle=0x00, jab=0x10, jab_high=0x18, dodge=0x0A, block=0x5F, hit=0x2F, down=0x3C)
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
        else:
            f = cut(rip, boxes[MAC[pose]])
        small = scale(f, s, outline_weight=1.0)
        out.append(place(small, PW, PH, PH - len(small)))
    return out


def write_js(poses, pals, colors, pposes, note, faces, mac_pal):
    L = ["// Little Mac and Glass Joe from Punch-Out!! (NES), for local testing only. Written by tools/punchout_art/build.py",
         f"// ({note}). Not original art: keep it out of commits and builds you share.", "",
         "// Rival palettes s, g, h (slot 0 is the mat, replaced at load).",
         f"export const JOE_PALETTES = {json.dumps(pals)};", "", "export const JOE_POSES = {"]
    L += [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in poses.items()]
    L += ["};", "", "// Player sprite colors for slots 1-3.", f"export const MAC_COLORS = {json.dumps(colors)};", "",
          "export const MAC_POSES = {"]
    L += [f"  {n}: '{v}'," for n, v in pposes.items()]
    L += ["};", "", "// Close-ups, 48x48: pixels are slots; cells are each tile's palette, a digit into PORTRAIT_PALETTES.",
          f"export const TEXT_PALETTE = {json.dumps(TEXT_PALETTE)};", f"export const PORTRAIT_PALETTES = {json.dumps(mac_pal)};",
          "export const PORTRAITS = {"]
    L += [f"  {n}: {{ pixels: '{v['pixels']}', cells: '{v['cells']}' }}," for n, v in faces.items()]
    import base64
    L += ["};", "", "// Glass Joe's NES fighter bank (Punch-Out!! PRG bank 0) and our pose for each of its frames.",
          f"export const JOE_NES = {{ bank: '{base64.b64encode(DISASM_BANK.read_bytes()).decode()}', offset: 0,",
          f"  frames: {json.dumps(NES_FRAMES)}, home: [135, 182], scale: {SCALE_JOE},",
          f"  mac: '{base64.b64encode(DISASM_MAC.read_bytes()).decode()}',",
          f"  sound: '{base64.b64encode(DISASM_BANK.with_name('PRG_Bank008.bin').read_bytes()).decode()}',",
          f"  soundFixed: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x5400:0x5900]).decode()}',",
          f"  samples: '{base64.b64encode(DISASM_BANK.with_name('PRG_BankDEF.bin').read_bytes()[0x4000:0x5400]).decode()}',",
          f"  macFrames: {json.dumps(MAC_FRAMES)}, macHome: 176, macScale: {SCALE_MAC} }};", "",
          "// The title's logo: Punch-Out!!'s, from its title screen, over its blue mesh (slots: holes, mesh, orange, red).",
          f"export const TITLE_LOGO = {json.dumps(title_logo())};", "",
          "// What Start does on the title: the NES game's glove, flashing behind the logo, then punching out.",
          f"export const TITLE_PUNCH = {json.dumps(title_punch(24))};", ""]
    OUT_JS.write_text("\n".join(L))

def budget(poses, pals, colors, pposes):
    """The fight scene's tiles on the original Game Boy, measured by the real project checks."""
    from gbstage import project, fight as kit
    p = json.loads(EXAMPLE.read_text())
    ft = next(s for s in p["scenes"] if s.get("fight"))["fight"]; bg = p["palettes"]["bg"]
    ft.pop("nes", None)                 # the budget is tiles: the NES logic (and a stale copy of it) aside
    ft["rival"]["poses"] = poses
    for k, kind in enumerate("sgh"): bg[ft["rival"]["palettes"][kind]]["colors"] = [bg[ft["rival"]["palettes"][kind]]["colors"][0]] + pals[k][1:]
    ft["player"]["poses"] = pposes
    op = p["palettes"]["obj"][ft["player"]["palette"]]; op["colors"] = [op["colors"][0]] + colors
    try:
        data = project.validate(copy.deepcopy(p))
    except project.ProjectError as e:
        return False, str(e)
    f = next(s for s in data["scenes"] if s.get("fight"))
    return True, (f"background tiles {len(f['tiles'])}/256, sprite tiles {kit.OBJ_FIRST_TILE + len(f['fight_obj'])}/"
                  f"{kit.OBJ_TILE_LIMIT}; rival pose sets {f['fight_swap']['sizes']}")

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
    a.add_argument("--mac-sheet", type=Path, help="use this edited 24x48-frame sheet instead of the rip")
    args = a.parse_args()
    write_example(strict=False)         # from the current editor code, so the budget below measures what it builds
    out = HERE / "out"
    joe_sheet, mac_sheet = args.joe_sheet, args.mac_sheet
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
    rival = {n: share_rival_tiles(poses, n) for n in range(args.max_share + 1)}
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
    rlim = first(lambda n: budget(rival[n], pals, colors, player[plim])[0])
    poses, pposes = rival[rlim], player[plim]
    ok, report = budget(poses, pals, colors, pposes)
    print(f"{'fits' if ok else 'DOES NOT FIT'}: {report}" + f"; tiles shared within {rlim} pixels (Joe), {plim} (Mac)")
    write_preview(out / "preview.png", poses, pals, colors, pposes)
    print("preview:", (out / "preview.png").relative_to(ROOT))
    if not ok:
        sys.exit("editor/art/mac-vs-joe.js left as it was.")
    note = (f"Joe {'from ' + joe_sheet.name if args.joe_sheet else f'at {args.joe}'}, "
            f"Mac {'from ' + mac_sheet.name if args.mac_sheet else f'at {args.mac}'} of NES size")
    faces, mac_pal = portraits()
    write_js(poses, pals, colors, pposes, note, faces, mac_pal)
    write_example()
    print("wrote", OUT_JS.relative_to(ROOT), "- reopen New > Examples > Joe vs Mac in the editor")

if __name__ == "__main__":
    main()
