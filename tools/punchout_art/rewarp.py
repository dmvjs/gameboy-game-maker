"""rewarp.py RIVAL [KEYS]: each warped picture redrawn with his frame 96 rows tall (no shrink to fit 80, no feet
cut): its scale, height, tiles; and whether today's touch-up is exactly warp.py's 80-row drawing."""
import sys, json
from pathlib import Path
import warp, build, touchup
rival = sys.argv[1]; want = sys.argv[2:]
D = Path(__file__).parent / "touchups" / rival
res = {}
for p in sorted(D.glob("*.txt")):
    key = p.stem[:-1] + "|" if p.stem.endswith("m") else p.stem
    if want and key not in want: continue
    lines = p.read_text().splitlines()
    if "warp.py" not in lines[0]: continue
    auto, rows = build.read_touchup(p)
    legend = {}
    for l in lines:
        if l.startswith("legend "):
            for it in l.split()[1:]:
                ch, v = it.split("="); legend[ch] = v
    g80, nes, mv80 = warp.warp(rival, key)
    black80 = warp.fit.blacked
    same = ["".join(r) for r in g80] == [l for l in lines if l and not l.startswith(("#", "auto", "final", "moved", "legend"))]
    old = (build.RH, build.FIGHT_H)
    build.RH, build.FIGHT_H = 96, 12
    try:
        warp.fit.force = None
        g96, nes, mv96 = warp.warp(rival, key)
        free = (g96, mv96, warp.fit.blacked)
        # (his head where today's has it on the tile grid: the same tiles, so the same colors, in his face)
        base = [l for l in lines if l and not l.startswith(("#", "auto", "final", "moved", "legend"))]
        top = next(y for y, r in enumerate(base) if r.strip("."))
        head = [(y, x, base[y][x]) for y in range(top, min(top + 22, len(base))) for x in range(64) if base[y][x] != "."]
        def off(g):
            best = None
            for dy in range(-16, 24):
                for dx in range(-12, 13):
                    d = sum(1 for y, x, c in head if not (0 <= y + dy < len(g) and 0 <= x + dx < 64 and g[y + dy][x + dx] == c))
                    if best is None or d < best[0]: best = (d, dy, dx)
            return best
        hd = off(g96)
        for _ in range(4):                  # (till his head's on today's grid)
            if not (hd[1] % 8 or hd[2] % 8):
                break
            last = warp.fit.last
            warp.fit.force = ((last[0] - hd[1]) % 8, (last[1] - hd[2]) % 8)
            g96, nes, mv96 = warp.warp(rival, key)
            hd = off(g96)
        forced_black = warp.fit.blacked if warp.fit.force is not None else free[2]
        if forced_black > max(black80, free[2]) + 4:        # (his head's grid kept cost colors: the free fit instead)
            g96, mv96 = free[0], free[1]; forced_black = free[2]; hd = off(g96)
    finally:
        build.RH, build.FIGHT_H = old
        warp.fit.force = None
    ys80 = [y for y, r in enumerate(g80) for c in r if c != "."]; ys96 = [y for y, r in enumerate(g96) for c in r if c != "."]
    t96 = len({t for ty in range(12) for tx in range(8) for t in [tuple(g96[y][x] for y in range(ty*8, ty*8+8) for x in range(tx*8, tx*8+8))] if any(c != "." for c in t)})
    crop = lambda g: (lambda ys, xs: tuple("".join(g[y][min(xs):max(xs) + 1]) for y in range(min(ys), max(ys) + 1)))(
        [y for y, r in enumerate(g) for c in r if c != "."], [x for r in g for x, c in enumerate(r) if c != "."])
    res[key] = dict(black=(black80, free[2], forced_black), head=hd, changed=crop(g80) != crop(g96), same=same, h80=max(ys80)-min(ys80)+1, h96=max(ys96)-min(ys96)+1, mv80=mv80, mv96=mv96, tiles96=t96)
    print(rival, key, res[key], flush=True)
    (Path(__file__).parent / "out" / f"rewarp-{rival}-{p.stem}.json").write_text(json.dumps({"rows": ["".join(r) for r in g96], "mv": mv96}))
