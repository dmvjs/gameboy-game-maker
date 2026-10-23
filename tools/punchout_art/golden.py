"""Which of a rival's pictures are golden, and why not: the same test every time.

  1. its 1:1 head (headswap.py) is the NES's, pixel for pixel, as Color shows it (gloves over it aside);
  2. nothing of it lost to its tiles (each 8x8 three colors): a strand of hair, a glove's shine (an eye's white a
     sprite shows on Color: build.import_pictures' whites);
  3. none of the NES's head cut off at its edges (a chin, a nose: the head's own pixels left on the NES side).

  python golden.py RIVAL [FRAMES]   -> a line a picture: golden, or what's wrong and where"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, fidelity, headswap, touchup


def shown_chars(rival, frames, pals, key):
    pic = build.import_pictures({key: frames[key]}, pals)[key]
    px, cells = pic["pixels"], pic["cells"]
    names = {"s": ".WSK", "g": ".SHK", "h": ".SRK"}
    return [[names[cells[(y // 8) * build.FIGHT_W + x // 8]][int(px[y * build.RW + x])] for x in range(build.RW)]
            for y in range(build.RH)]


def check(rival, key, frames, pals):
    path = build.TOUCHUPS / rival / f"{build.touchup_name(key)}.txt"
    src = [[headswap.char(c) if c else "." for c in r] for r in frames[key]]
    seen = shown_chars(rival, frames, pals, key)
    lost = {}
    for y in range(build.RH):
        for x in range(build.RW):
            if src[y][x] != "." and seen[y][x] != src[y][x] and not (src[y][x] == "W" and not headswap.near(src, y, x, "R")):
                lost.setdefault(f"{src[y][x]}>{seen[y][x]}", []).append((x, y))
    out = []
    for k, v in sorted(lost.items()):
        ys = sorted({y for _, y in v})
        out.append(f"{len(v)} {k} (rows {ys[0]}-{ys[-1]})")
    hb = fidelity.head_box(rival, key)
    if hb and path.exists():
        rgb, a, *_ = fidelity.placement(rival, key)
        nes = [[headswap.char(rgb[y, x]) if a[y, x] else "." for x in range(a.shape[1])] for y in range(a.shape[0])]
        h = hb[1] - hb[0]
        # (the head as pasted: find the NES head's offset in ours by its best match, then what of it isn't there)
        best = None
        for dx in range(-build.RW, build.RW):
            m = sum(1 for y in range(min(h, len(nes))) for x in range(len(nes[0]))
                    if nes[y][x] in "HW" and 0 <= hb[0] + y < build.RH and 0 <= x + dx < build.RW
                    and src[hb[0] + y][x + dx] == nes[y][x])
            if best is None or m > best[0]:
                best = (m, dx)
        dx = best[1]
        missing = [(x + dx, hb[0] + y) for y in range(min(h, len(nes))) for x in range(len(nes[0]))
                   if nes[y][x] in "SK" and 0 <= hb[0] + y < build.RH and 0 <= x + dx < build.RW
                   and src[hb[0] + y][x + dx] == "." and any(src[hb[0] + y][xx] != "." for xx in range(build.RW))]
        edge = [p for p in missing if any(abs(p[0] - q[0]) <= 1 and abs(p[1] - q[1]) <= 1
                                          for q in [(xx, yy) for yy in range(hb[0], hb[1]) for xx in range(build.RW)
                                                    if src[yy][xx] != "."])]
        if edge:
            ys = sorted({y for _, y in edge})
            out.append(f"{len(edge)} NES head pixels cut off at its edge (rows {ys[0]}-{ys[-1]})")
    return out


def main():
    rival = sys.argv[1]
    frames, pals = touchup.auto_pictures(rival)
    frames = build.apply_touchups(rival, frames)
    keys = sorted(frames) if len(sys.argv) < 3 else [k.replace("m", "|") for k in sys.argv[2].split(",")]
    gold = []
    for k in keys:
        bad = check(rival, k, frames, pals)
        if bad:
            print(f"{k:4} " + "; ".join(bad))
        else:
            gold.append(k)
    print(f"golden ({len(gold)}): {' '.join(gold)}")


if __name__ == "__main__":
    main()
