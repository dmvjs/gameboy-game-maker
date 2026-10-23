"""How far a rival's picture is from the NES's, as the eye sees it: the NES frame shrunk to ours by area (each of
our pixels the average of what it covers: the ideal 0.7), laid over ours where the silhouettes agree best, both
blurred a little (the eye's own averaging), then compared pixel by pixel in lightness. A map of where ours is too
dark (red) or too light (cyan), and the error by region; a pasted 1:1 head ('head' in its touch-up) is compared
1:1 instead.

  python fidelity.py RIVAL FRAME [--sigma 0.7]   -> out/RIVAL-FRAME-fidelity.png, opened"""
import argparse, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, touchup

UP, DOWN = 7, 10                        # (0.7 exactly: each NES pixel 7x7, then 10x10 boxes)


def shown(rival, key):
    """Our picture as Game Boy Color shows it (its tiles' palettes): RGB float array and its mask."""
    frames, pals = touchup.auto_pictures(rival)
    frames = build.apply_touchups(rival, frames)
    pic = build.import_pictures({key: frames[key]}, pals)[key]
    px, cells = pic["pixels"], pic["cells"]
    rgb = np.zeros((build.RH, build.RW, 3)); mask = np.zeros((build.RH, build.RW), bool)
    for i, ch in enumerate(px):
        if ch != "0":
            pal = pals[build.KINDS.index(cells[(i // build.RW // 8) * build.FIGHT_W + (i % build.RW) // 8])]
            rgb[i // build.RW, i % build.RW] = [(v << 3) | (v >> 2) for v in pal[int(ch)]]
            mask[i // build.RW, i % build.RW] = True
    return rgb, mask


def nes_frame(rival, key):
    every = build.joe_shapes(build.NES_RIVALS[rival]["opp"], everything=True)
    shape = every.get(build._key(key))
    if shape is None:                   # (a picture only caught the other way round: that one flipped)
        other = every[build._key(key[:-1]) if key.endswith("|") else build._key(key + "|")]
        shape = {(-x, y): c for (x, y), c in other.items()}
    xs, ys = [x for x, _ in shape], [y for _, y in shape]
    x0, y0 = min(xs), min(ys)
    rgb = np.zeros((max(ys) - y0 + 1, max(xs) - x0 + 1, 3)); a = np.zeros(rgb.shape[:2])
    for (x, y), c in shape.items():
        rgb[y - y0, x - x0] = c[:3]; a[y - y0, x - x0] = 1
    return rgb, a


def shrink(rgb, a, px, py):
    """The NES frame at 0.7 by area, its grid's phase (px, py) in 10ths of an NES pixel: premultiplied colour, coverage."""
    big = np.repeat(np.repeat(np.dstack([rgb * a[..., None], a]), UP, 0), UP, 1)
    big = np.pad(big, ((py, DOWN * 2), (px, DOWN * 2), (0, 0)))
    H, W = big.shape[0] // DOWN, big.shape[1] // DOWN
    s = big[:H * DOWN, :W * DOWN].reshape(H, DOWN, W, DOWN, 4).mean((1, 3))
    return s[..., :3], s[..., 3]


def blur(img, sigma):
    r = max(1, int(3 * sigma + 0.5)); k = np.exp(-np.arange(-r, r + 1) ** 2 / (2 * sigma * sigma)); k /= k.sum()
    pad = [(r, r), (r, r)] + [(0, 0)] * (img.ndim - 2)
    p = np.pad(img, pad, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, p)


def lum(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114]) / 255


def register(ours_mask, nes_rgb, nes_a):
    """The phase and offset laying the shrunk NES frame over ours where the silhouettes agree best."""
    best = None
    for py in range(DOWN):
        for px in range(DOWN):
            _, cov = shrink(nes_rgb, nes_a, px, py)
            h, w = cov.shape            # (offsets: the coverage correlated with our mask)
            m = ours_mask.astype(float)
            F = np.fft.rfft2(m, s=(build.RH + h, build.RW + w))
            G = np.fft.rfft2(cov[::-1, ::-1], s=(build.RH + h, build.RW + w))
            c = np.fft.irfft2(F * G, s=(build.RH + h, build.RW + w))
            union = m.sum() + cov.sum()
            iy, ix = np.unravel_index(np.argmax(c), c.shape)
            score = c[iy, ix] / union
            if best is None or score > best[0]:
                best = (score, px, py, ix - (w - 1), iy - (h - 1))
    return best[1:]


def placement(rival, key):
    """The NES frame and where it lies over ours at 0.7: (rgb, alpha, phase x, phase y, offset x, offset y)."""
    rgb, a = nes_frame(rival, key)
    _, mask = shown(rival, key)
    hb = head_box(rival, key)
    if hb:                              # (laid over by the body: the head's 1:1, not 0.7)
        mask = mask.copy(); mask[:hb[1]] = False
        a = a.copy(); a[:hb[1] - hb[0]] = 0   # (its NES rows: 0 up to the cut, 1:1)
    px, py, ox, oy = register(mask, rgb, a)
    rgb, a = nes_frame(rival, key)
    return rgb, a, px, py, ox, oy


def target(rival, key):
    """The NES frame as ours should look: on our canvas, colour (premultiplied) and coverage."""
    rgb, a, px, py, ox, oy = placement(rival, key)
    col, cov = shrink(rgb, a, px, py)
    T = np.zeros((build.RH, build.RW, 3)); C = np.zeros((build.RH, build.RW))
    for y in range(cov.shape[0]):
        for x in range(cov.shape[1]):
            Y, X = y + oy, x + ox
            if 0 <= Y < build.RH and 0 <= X < build.RW:
                T[Y, X], C[Y, X] = col[y, x], cov[y, x]
    return T, C


MAT = np.array([8, 76, 196], float)
EYE = 0.8                               # (the eye's blur, in NES pixels: about one)


def nes_fine(rival, key):
    """The NES frame at its own size on our canvas's fine grid (a unit a 10th of our pixel, a 7th of the NES's):
    our pixel (X, Y) is fine [10Y:10Y+10, 10X:10X+10]. RGB over the mat."""
    rgb, a, px, py, ox, oy = placement(rival, key)
    big = np.repeat(np.repeat(np.dstack([rgb * a[..., None] + (1 - a)[..., None] * MAT]), UP, 0), UP, 1)
    F = np.tile(MAT, (build.RH * DOWN, build.RW * DOWN, 1))
    Y0, X0 = oy * DOWN + py, ox * DOWN + px          # (the shrink's pad, then its offset)
    h, w = big.shape[:2]
    ys, xs = slice(max(0, Y0), min(F.shape[0], Y0 + h)), slice(max(0, X0), min(F.shape[1], X0 + w))
    F[ys, xs] = big[ys.start - Y0:ys.stop - Y0, xs.start - X0:xs.stop - X0]
    return F


def gauss(sigma):
    r = int(3 * sigma + 0.5); k = np.exp(-np.arange(-r, r + 1) ** 2 / (2 * sigma * sigma))
    return k / k.sum(), r


def sep_blur(img, k):
    """Separable blur, edges held."""
    r = len(k) // 2
    p = np.pad(img, [(r, r), (0, 0)] + [(0, 0)] * (img.ndim - 2), mode="edge")
    img = sum(k[i] * p[i:i + img.shape[0]] for i in range(len(k)))
    p = np.pad(img, [(0, 0), (r, r)] + [(0, 0)] * (img.ndim - 2), mode="edge")
    return sum(k[i] * p[:, i:i + img.shape[1]] for i in range(len(k)))


def head_box(rival, key):
    """The 1:1 head's rows in our frame (touch-up line '# head Y0 Y1': our rows Y0.. are the NES frame's from its
    top, 1:1, to Y1), or None."""
    path = build.TOUCHUPS / rival / f"{build.touchup_name(key)}.txt"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("# head "):
                return tuple(map(int, line.split()[2:4]))
    return None


def error_map(rival, key, sigma=0.7):
    """Signed lightness error, ours minus the NES's (each blurred, mat as background), and our mask."""
    O, M = shown(rival, key)
    T, C = target(rival, key)
    mat = np.array([8, 76, 196], float)
    Ov = np.where(M[..., None], O, mat)
    Tv = T + (1 - C)[..., None] * mat
    E = blur(lum(Ov), sigma) - blur(lum(Tv), sigma)
    return E, M, C, Ov, Tv


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("rival"); ap.add_argument("frame")
    ap.add_argument("--sigma", type=float, default=0.7); ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    key = a.frame.replace("m", "|")
    E, M, C, Ov, Tv = error_map(a.rival, key, a.sigma)
    hb = head_box(a.rival, key)
    body = (M | (C > 0.3)).copy()
    if hb:
        body[hb[0]:hb[1]] = False
    rms = float(np.sqrt((E[body] ** 2).mean())) if body.any() else 0.0
    dark = float(np.clip(-E[body], 0, None).sum()); light = float(np.clip(E[body], 0, None).sum())
    print(f"{a.rival} {key}: body lightness rms {rms:.4f}  too dark {dark:.2f}  too light {light:.2f}"
          + (f"  (head rows {hb[0]}-{hb[1]} 1:1, not here)" if hb else ""))
    Z = 6
    def pic(arr):
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize((build.RW * Z, build.RH * Z), Image.NEAREST)
    heat = np.zeros((build.RH, build.RW, 3)); s = np.clip(np.abs(E) / 0.25, 0, 1)
    heat[..., 0] = np.where(E < 0, 255 * s, 0)               # (ours darker: red)
    heat[..., 1] = np.where(E > 0, 255 * s, 0); heat[..., 2] = heat[..., 1]   # (lighter: cyan)
    heat = np.where(body[..., None], heat * 0.85 + lum(Ov)[..., None] * 40, 20)
    sheet = Image.new("RGB", (build.RW * Z * 3 + 40, build.RH * Z + 16), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate((("NES shrunk by area (target)", pic(Tv)), ("ours, as Color shows it", pic(Ov)),
                                 (f"ours too dark (red) / light (cyan), rms {rms:.3f}", pic(heat)))):
        sheet.paste(im, (i * (build.RW * Z + 20), 16)); d.text((i * (build.RW * Z + 20) + 2, 2), t, fill=(255, 255, 0))
    for y in range(0, build.RH, 5):
        d.text((2 * (build.RW * Z + 20) + 2, 16 + y * Z), str(y), fill=(255, 255, 0))
    out = HERE / "out" / f"{a.rival}-{build.touchup_name(key)}-fidelity.png"
    sheet.save(out); print(out)
    if not a.no_open:
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
