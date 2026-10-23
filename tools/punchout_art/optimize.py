"""A touch-up's body redrawn to be as near the NES's as the eye can tell, Shannon's way: the least distortion for
what the picture can hold, found the same way every time.

Distortion: ours seen at the NES's size (each of our pixels 1/0.7 of the NES's) against the NES frame itself, both
blurred by the eye (about an NES pixel), in colour (lightness weighed most): a line lost costs what it costs to the
eye, and dithering buys nothing a line doesn't. What it can hold: each tile its own three colours (its palette as
now), the silhouette and its outline as they are, the 1:1 head locked. A prior for clean pixel art: a lone dot of a
colour, or a 2x2 block of ink, costs, and a pixel only takes a colour already beside it (an edge moved, a line
thinned or thickened: nothing from nowhere); so does each pixel changed from the hand touch-up (--keep). Each pixel, in
reading order, tried in each colour its tile allows, a change kept only if the whole costs less, till a sweep
changes none: no chance in it anywhere.

  python optimize.py RIVAL FRAME [--keep K] [--lone L] [--blob B] [--dry]   -> the touch-up rewritten (the old one
  in out/RIVAL-FRAME-before-optimize.txt)"""
import argparse, shutil, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, fidelity

LUMA = np.array([[0.299, 0.587, 0.114], [-0.169, -0.331, 0.5], [0.5, -0.419, -0.081]]) * np.array([[1], [0.5], [0.5]])
LONE, BLOB, KEEP = 0.03, 0.03, 0.01     # (the prior: a lone dot of a colour, a 2x2 of ink, a pixel changed)
ALLOWED = {"s": "WSK", "g": "SHK", "h": "SRK"}   # (each tile kind's colours: build.KINDS' palettes)
F = fidelity.DOWN                       # (fine units to our pixel)


def load(path):
    text = path.read_text().splitlines()
    first = next(i for i, l in enumerate(text) if l.startswith("legend ")) + 1
    ink = {}
    for item in text[first - 1].split()[1:]:
        ch, v = item.split("=")
        ink[ch] = fidelity.MAT if v == "-" else np.array(list(map(int, v.split(","))), float)
    return text, first, ink, [list(l) for l in text[first:first + build.RH]]


def distortion_parts(rival, key, rows, ink):
    """The fine error (ours blown up and blurred, minus the NES's blurred), its weights, and a pixel's blurred
    footprint."""
    to = lambda rgb: (rgb / 255) @ LUMA.T
    g, r = fidelity.gauss(fidelity.EYE * fidelity.UP)
    N = to(fidelity.nes_fine(rival, key))
    O = np.array([[to(ink[c]) for c in row] for row in rows])
    U = np.repeat(np.repeat(O, F, 0), F, 1)
    E = fidelity.sep_blur(U, g) - fidelity.sep_blur(N, g)
    Wf = np.ones(E.shape[:2])
    hb = fidelity.head_box(rival, key)
    if hb:
        Wf[:(hb[1] + 1) * F] = 0                   # (the head's measured 1:1, not here)
    p1 = np.convolve(np.ones(F), g)
    return E, Wf, np.outer(p1, p1), r, to


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("rival"); ap.add_argument("frame")
    ap.add_argument("--lone", type=float, default=LONE); ap.add_argument("--blob", type=float, default=BLOB)
    ap.add_argument("--keep", type=float, default=KEEP); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--inks", default="SK", help="the colours it may trade (skin and its shadow: stripes, a belt's or"
                    " laces', can't line up with the NES's at 0.7, so a blur's measure only scrambles them)")
    a = ap.parse_args()
    key = a.frame.replace("m", "|")
    path = build.TOUCHUPS / a.rival / f"{build.touchup_name(key)}.txt"
    text, first, ink, rows = load(path)
    H, W = len(rows), len(rows[0])
    E, Wf, P, r, to = distortion_parts(a.rival, key, rows, ink)
    P2 = P * P
    tile = build.import_pictures({key: build.read_touchup(path)[1]}, fidelity.touchup.auto_pictures(a.rival)[1])[key]["cells"]
    solid = np.array([[c != "." for c in row] for row in rows])
    inner = solid & np.roll(solid, 1, 0) & np.roll(solid, -1, 0) & np.roll(solid, 1, 1) & np.roll(solid, -1, 1)
    hb = fidelity.head_box(a.rival, key)
    free = inner.copy()
    if hb:
        free[:hb[1] + 1] = False                   # (the head and its neck's first row: the NES's own)
    orig = [row[:] for row in rows]
    for y in range(H):                             # (only what lies wholly in its inks' own region: a belt's,
        for x in range(W):                         #  a boot's, a glove's edges stay as drawn)
            if free[y, x] and any(0 <= y + j < H and 0 <= x + i < W and orig[y + j][x + i] not in a.inks + "."
                                  for j in (-1, 0, 1) for i in (-1, 0, 1)):
                free[y, x] = False
    at = lambda y, x: rows[y][x] if 0 <= y < H and 0 <= x < W else "."

    def prior(y, x):
        """The prior's cost of the pixels near (y, x), as rows stand."""
        c = 0.0
        for yy in range(y - 1, y + 2):
            for xx in range(x - 1, x + 2):
                v = at(yy, xx)
                if v != "." and not any(at(yy + j, xx + i) == v for j in (-1, 0, 1) for i in (-1, 0, 1) if i or j):
                    c += a.lone
        for yy in range(y - 1, y + 1):
            for xx in range(x - 1, x + 1):
                if at(yy, xx) == at(yy + 1, xx) == at(yy, xx + 1) == at(yy + 1, xx + 1) == "K":
                    c += a.blob
        return c

    def window(y, x):
        Y0, X0 = y * F - r, x * F - r
        ys, xs = slice(max(0, Y0), min(E.shape[0], Y0 + P.shape[0])), slice(max(0, X0), min(E.shape[1], X0 + P.shape[1]))
        return ys, xs, (slice(ys.start - Y0, ys.stop - Y0), slice(xs.start - X0, xs.stop - X0))

    total = lambda: float((Wf[..., None] * E * E).sum()) / F ** 2
    before = total()
    for sweep in range(20):
        n = 0
        for y in range(H):
            for x in range(W):
                if not free[y, x]:
                    continue
                cur = rows[y][x]
                ys, xs, (py, px) = window(y, x)
                wp = P[py, px] * Wf[ys, xs]
                g1 = (wp[..., None] * E[ys, xs]).sum(axis=(0, 1))
                g2 = float((P2[py, px] * Wf[ys, xs]).sum())
                base = prior(y, x)
                best, bd = None, -1e-12
                near = {at(y - 1, x), at(y + 1, x), at(y, x - 1), at(y, x + 1)}
                for ch in ALLOWED[tile[(y // 8) * build.FIGHT_W + x // 8]]:
                    if ch == cur or ch not in near or cur not in a.inks or ch not in a.inks:     # (an edge moved or a line thinned: no colour from nowhere)
                        continue
                    d = to(ink[ch]) - to(ink[cur])
                    dd = (2 * float(g1 @ d) + g2 * float(d @ d)) / F ** 2
                    rows[y][x] = ch
                    dd += prior(y, x) - base + a.keep * ((ch != orig[y][x]) - (cur != orig[y][x]))
                    rows[y][x] = cur
                    if dd < bd:
                        best, bd = ch, dd
                if best:
                    d = to(ink[best]) - to(ink[cur])
                    E[ys, xs] += P[py, px][..., None] * d
                    rows[y][x] = best; n += 1
        if not n:
            break
    diff = sum(rows[y][x] != orig[y][x] for y in range(H) for x in range(W))
    print(f"{a.rival} {key}: distortion {before:.2f} -> {total():.2f}, {diff} pixels changed, {sweep + 1} sweeps")
    if a.dry:
        return
    shutil.copy(path, HERE / "out" / f"{a.rival}-{build.touchup_name(key)}-before-optimize.txt")
    text[first:first + H] = ["".join(row) for row in rows]
    path.write_text("\n".join(text))


if __name__ == "__main__":
    main()
