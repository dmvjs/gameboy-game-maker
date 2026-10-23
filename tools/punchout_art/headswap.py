"""A rival's head as the NES draws it, 1:1, on his shrunk body: the face a 0.7 shrink can't keep (an eye, a brow,
a nose a pixel each) kept whole. The same way every time:

  the head: the NES frame's pixels joined to his hair, from its top down to a neck row; gloves left out, and from
    just above the eyes (3 rows: a shoulder can rise that high) only his face's columns and his hair (and the ink and white touching it: an ear), not a shoulder
    (where a shoulder rises beside his face, its columns are given: COLS; where there's no neck, the cut: CUT;
    from behind or face down, his hair alone: HAIR);
  the cut: below the chin (the eyes' row and 11), a row as wide as a neck (half his face's width to all of it;
    failing that, to 1.4 of it, further down) whose outline, laid on ours below it, lines up best (the edges'
    distance; then the narrower; then the higher) of those that fit the frame;
  laid at the neck where the 0.7 picture has it; ours inside its outline (row by row) and his 0.7 hair and its ink cleared;
    our gloves over it again; too tall for the frame, a head row the same as the one under it out, from the top;
  then moved in its frame to where his tiles keep the most of his colors (each 8x8 tile three: of the 64 ways the
    tiles can fall, the one losing fewest pixels, a head's five times dear (an eye's white a sprite shows); then the
    least move); hair a tile still can't show, its dark (not skin's pink). 'moved' in the
    touch-up undoes it on screen; '# head Y0 Y1' tells fidelity.py and optimize.py where the 1:1 head is.

  python headswap.py RIVAL FRAMES|all [--dry]   -> touchups/RIVAL/FRAME.txt (over a touch-up there already, its
  body kept)"""
import argparse, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, fidelity, touchup

LEGEND = {"K": (32, 42, 0), "R": (152, 34, 32), "H": (212, 136, 32), "S": (236, 174, 212), "W": (236, 238, 236)}
SHOWS = {"s": "WSK", "g": "SHK", "h": "SRK"}   # (what each tile kind can show: build.KINDS' palettes)
TOP = 16                                # (room above the frame for a head taller than his 0.7 one)
HEAD_DEAR, EYE_DEAR = 5, 0        # (a head's pixel lost to its tile: as dear as five others; an eye's white none, a
                                  #  sprite shows it on Color: build.import_pictures' whites)
COLS = {                                # (where his shoulders rise beside his face: its columns below the eyes, by eye)
    "joe": {"1C": (7, 21), "C8": (7, 21), "CA": (7, 21), "10": (10, 22)},
}
HAIR = {                                # (from behind, face down: his head's his hair, the back under it his body's)
    "joe": {"28", "2C", "32", "32|", "36", "36|"},
}
CUT = {                                 # (no neck to find, his head sunk in his shoulders: the row under his mouth)
    "joe": {"10": 24},
}
TRACE = False


def char(c):
    return min(LEGEND, key=lambda k: sum((a - b) ** 2 for a, b in zip(c[:3], LEGEND[k])))


def component(grid, seeds, ok):
    """The pixels 8-joined to seeds through ok ones."""
    H, W = len(grid), len(grid[0])
    seen, st = set(seeds), list(seeds)
    while st:
        y, x = st.pop()
        for j in (-1, 0, 1):
            for i in (-1, 0, 1):
                q = (y + j, x + i)
                if q not in seen and 0 <= q[0] < H and 0 <= q[1] < W and ok(*q):
                    seen.add(q); st.append(q)
    return seen


def near(grid, y, x, colours):
    H, W = len(grid), len(grid[0])
    return any(0 <= y + j < H and 0 <= x + i < W and grid[y + j][x + i] in colours
               for j in (-1, 0, 1) for i in (-1, 0, 1))


def gloved(grid, y, x):
    """A glove's pixel: its red, or ink or shine touching its red."""
    return grid[y][x] == "R" or (grid[y][x] in "KW" and near(grid, y, x, "R"))


def edges(cells, y):
    xs = [x for (yy, x) in cells if yy == y]
    return (min(xs), max(xs)) if xs else None


def lost(grid, pals, weight):
    """Pixels his tiles can't show (as import_pictures picks each tile's palette), each its weight."""
    fr = [[(LEGEND[c] + (255,)) if c != "." else None for c in r] for r in grid]
    cells = build.import_pictures({"x": fr}, pals)["x"]["cells"]
    return sum(weight(y, x) for y, r in enumerate(grid) for x, c in enumerate(r)
               if c != "." and c not in SHOWS[cells[(y // 8) * build.FIGHT_W + x // 8]])


def swap(rival, key, frames, pals):
    path = build.TOUCHUPS / rival / f"{build.touchup_name(key)}.txt"
    src = build.read_touchup(path)[1] if path.exists() else frames[key]
    base = [[char(c) if c else "." for c in r] for r in src]
    rgb, a, px, py, ox, oy = fidelity.placement(rival, key)
    nes = [[char(rgb[y, x]) if a[y, x] else "." for x in range(a.shape[1])] for y in range(a.shape[0])]
    nh, nw = len(nes), len(nes[0])
    hair = [(y, x) for y in range(nh) for x in range(nw) if nes[y][x] == "H"]
    if not hair:
        return None, "no hair: no head to take"
    hy1 = max(y for y, _ in hair)
    if key in HAIR.get(rival, ()):              # (his hair and its ink alone, laid where his 0.7 hair's foot is)
        head = {(y, x) for y in range(nh) for x in range(nw) if nes[y][x] == "H"
                or (nes[y][x] in "KW" and near(nes, y, x, "H") and not gloved(nes, y, x))}
        cut = max(y for y, _ in head)
        xs = [x for y, x in head if y >= cut - 2]
        to_ours = lambda y, x: ((y * fidelity.UP + py) // fidelity.DOWN + oy, int((x * fidelity.UP + px) // fidelity.DOWN) + ox)
        Yc, Xc = to_ours(cut, (min(xs) + max(xs)) / 2)
        res = place(key, frames, pals, base, nes, ((0, 0, cut), cut, head, Yc, Xc - round((min(xs) + max(xs)) / 2)),
                    hair_only=True)
        return res, "ok" if res else "too tall for the frame"
    eyes = [y for y in range(min(nh, hy1 + 4)) for x in range(nw) if nes[y][x] == "W" and not gloved(nes, y, x)]
    eye_row = min(eyes) + 1 if eyes else hy1        # (his eyes: the highest whites, two rows; not his teeth)
    low = eye_row + 11 if eyes else hy1 + 2
    face = component(nes, [p for p in hair if p[0] <= eye_row],
                     lambda y, x: y <= eye_row and nes[y][x] != "." and not gloved(nes, y, x))
    fe = edges(face, eye_row) or (0, nw - 1)
    fw = fe[1] - fe[0]
    cols = COLS.get(rival, {}).get(key, (fe[0] - 3, fe[1] + 3))   # (a chin, a jaw a little past the eyes' width)
    to_ours = lambda y, x: ((y * fidelity.UP + py) // fidelity.DOWN + oy, int((x * fidelity.UP + px) // fidelity.DOWN) + ox)
    given = CUT.get(rival, {}).get(key)
    for wide, span in ((1.0, 10), (1.4, 16)) if given is None else ((99, 1),):
        found = [c for c in (neck(nes, hair, cut, eye_row, cols, base, to_ours)
                             for cut in (range(low, min(nh, low + span)) if given is None else [given]))
                 if c and fw / 2 <= c[0][1] <= fw * wide]
        for c in sorted(found, key=lambda c: c[0]):     # (the best that fits the frame)
            res = place(key, frames, pals, base, nes, c)
            if res:
                return res, "ok"
    return None, "no neck row fits the frame"


def neck(nes, hair, cut, eye_row, cols, base, to_ours):
    """The head cut at this row, and how its neck lies on ours below: ((seam, width, cut), cut, head, Yc, sx)."""
    head = component(nes, [p for p in hair if p[0] <= cut],
                     lambda y, x: y <= cut and nes[y][x] != "." and not gloved(nes, y, x)
                     and (y <= eye_row - 3 or cols[0] <= x <= cols[1] or nes[y][x] == "H"
                          or (nes[y][x] in "KW" and near(nes, y, x, "H"))))
    e = edges(head, cut)
    if not e:
        return None
    Yc, Xc = to_ours(cut, (e[0] + e[1]) / 2)
    if not 0 <= Yc + 1 < build.RH:
        return None
    runs, run = [], []                  # (ours below the cut: the run of its row nearest the neck's middle)
    for x in range(build.RW + 1):
        if x < build.RW and base[Yc + 1][x] != ".":
            run.append(x)
        elif run:
            runs.append(run); run = []
    if not runs:
        return None
    r = min(runs, key=lambda r: min(abs(x - Xc) for x in r))
    L, R = r[0], r[-1]
    sx = round((L + R) / 2 - (e[0] + e[1]) / 2)
    seam = abs(e[0] + sx - L) + abs(e[1] + sx - R)
    if TRACE:
        print(f"   cut {cut}: width {e[1] - e[0]} seam {seam} (ours {L}-{R} at row {Yc + 1}, NES {e[0]}-{e[1]})")
    return (seam, e[1] - e[0], cut), cut, head, Yc, sx


def place(key, frames, pals, base, nes, best, hair_only=False):
    (seam, _, _), cut, head, Yc, sx = best
    H, W = build.RH + TOP, build.RW
    grid = [["."] * W for _ in range(TOP)] + [r[:] for r in base]
    yc = Yc + TOP
    glove = {(y, x): grid[y][x] for y in range(yc + 1) for x in range(W) if grid[y][x] != "." and gloved(grid, y, x)}
    span = {}
    for y, x in head:                               # (the new head's outline, row by row: ours inside it cleared,
        Y, X = yc - (cut - y), x + sx               #  and his old hair; his shoulders and arms outside kept)
        lo, hi = span.get(Y, (X, X)); span[Y] = (min(lo, X), max(hi, X))
    was = [r[:] for r in grid]
    bx0, bx1 = min(lo for lo, _ in span.values()), max(hi for _, hi in span.values())
    old = component(was, [(y, x) for y in range(yc + 1) for x in range(W) if was[y][x] == "H"],
                    lambda y, x: y <= yc and was[y][x] != "." and not gloved(was, y, x))
    for y in range(yc + 1):
        for x in range(W):
            if (was[y][x] == "H" or (y in span and span[y][0] <= x <= span[y][1])
                    or (was[y][x] == "K" and near(was, y, x, "H"))      # (his old hair, and its outline,
                    or ((y, x) in old and bx0 <= x <= bx1 and not hair_only)):   #  and his old face where the new head is)
                grid[y][x] = "."
    off, mine = 0, set()
    for y, x in head:
        Y, X = yc - (cut - y), x + sx
        if 0 <= Y < H and 0 <= X < W:
            grid[Y][X] = nes[y][x]; mine.add((Y, X))
        else:
            off += 1
    for (y, x), c in glove.items():
        grid[y][x] = c; mine.discard((y, x))
    ys = [y for y in range(H) for x in range(W) if grid[y][x] != "."]
    top, bot = min(ys), max(ys)
    dropped = 0
    while bot - top + 1 > build.RH:
        same = [y for y in range(top, yc) if grid[y] == grid[y + 1]]
        if not same:
            break
        del grid[same[0]]; grid.insert(0, ["."] * W)
        mine = {(y + (y < same[0]), x) for y, x in mine if y != same[0]}
        top += 1; dropped += 1
    if bot - top + 1 > build.RH:
        return None
    xs = [x for y in range(H) for x in range(W) if grid[y][x] != "."]
    left, right = min(xs), max(xs)
    trials = {}
    for dy in range(-top, build.RH - bot):          # (grid row y lands at y + dy)
        for dx in range(-left, W - right):
            ph = ((top + dy) % 8, (left + dx) % 8)
            mv = abs(dx) + abs(dy + TOP)            # (from where it was: TOP rows up, as the frame had it)
            if ph not in trials or mv < trials[ph][0]:
                trials[ph] = (mv, dx, dy)
    best = None
    for mv, dx, dy in sorted(trials.values()):
        g = [["."] * W for _ in range(build.RH)]
        for y in range(top, bot + 1):
            for x in range(left, right + 1):
                if grid[y][x] != ".":
                    g[y + dy][x + dx] = grid[y][x]
        n = lost(g, pals, lambda y, x: (EYE_DEAR if g[y][x] == "W" else HEAD_DEAR) if (y - dy, x - dx) in mine else 1)
        if best is None or (n, mv) < best[0]:
            best = ((n, mv), dx, dy, g)
    (n, _), dx, dy, g = best
    cells = build.import_pictures({"x": [[(LEGEND[c] + (255,)) if c != "." else None for c in r] for r in g]}, pals)["x"]["cells"]
    for y in range(build.RH):                       # (hair its tile can't show: its dark, not skin's pink)
        for x in range(W):
            if g[y][x] == "H" and "H" not in SHOWS[cells[(y // 8) * build.FIGHT_W + x // 8]]:
                g[y][x] = "K"
    return dict(rows=g, moved=(dx, dy + TOP), head=(min(y for y, _ in mine) + dy, yc + dy + 1), cut=cut,
                seam=seam, off=off, dropped=dropped, lost=n, auto=build.frame_hash(frames[key]))


def write(rival, key, res):
    path = build.TOUCHUPS / rival / f"{build.touchup_name(key)}.txt"
    lines = [f"# {build.NES_RIVALS[rival]['name']}, picture {key}: the NES head 1:1 (headswap.py), body touched up (optimize.py)",
             f"auto {res['auto']}", f"moved {res['moved'][0]} {res['moved'][1]}",
             f"# head {res['head'][0]} {res['head'][1]}",
             "legend .=- " + " ".join(f"{k}={','.join(map(str, v))}" for k, v in LEGEND.items())]
    lines += ["".join(r) for r in res["rows"]]
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("rival"); ap.add_argument("frames")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    frames, pals = touchup.auto_pictures(a.rival)
    keys = sorted(frames) if a.frames == "all" else [k.replace("m", "|") for k in a.frames.split(",")]
    for k in keys:
        res, why = swap(a.rival, k, frames, pals)
        if res is None:
            print(f"{k}: skipped ({why})"); continue
        print(f"{k}: cut at NES row {res['cut']} (seam off {res['seam']}px), moved {res['moved']}, head rows "
              f"{res['head'][0]}-{res['head'][1]}, {res['lost']} weighed pixels lost to tiles"
              + (f", {res['off']} off the frame" if res["off"] else "")
              + (f", {res['dropped']} repeated rows out" if res["dropped"] else ""))
        if not a.dry:
            write(a.rival, k, res)


if __name__ == "__main__":
    main()
