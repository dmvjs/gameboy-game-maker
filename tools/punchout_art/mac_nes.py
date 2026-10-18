"""Little Mac's frames exactly as the NES draws them: bank B's $8280 (which frame, where) and $8020 (its tiles
into the nametable) run from the real fight's state (nes_boot); the cells they write, drawn with his CHR bank
($69) and the attribute palettes. mac_frame(f) -> rows of RGBA (None: clear)."""
import copy, pickle, pathlib
import nes_boot as B

HERE = pathlib.Path(__file__).parent
_base = None

def mac_frame(f):
    """His NES frame f, cropped to what's drawn (None: nothing)."""
    r = mac_frame_at(f)
    return r[0] if r else None


def mac_frame_at(f):
    """His NES frame f, cropped, and where the NES draws its top-left (pixels on the screen): (img, (x, y))."""
    global _base
    if _base is None:
        _base = B.fight_snapshot()
    b = copy.deepcopy(_base)
    b.lo = b.bank(0x0B)
    b.ram[0x60], b.ram[0x61] = 0x81, f
    b.cpu.call(0x8280)
    before = bytes(b.vram)
    b.cpu.call(0x8020)
    cells = [i for i in range(0x800) if b.vram[i] != before[i] and (i & 0x3FF) < 0x3C0]
    if not cells:
        return None
    bank = b.ram[0x69]
    data = B.CHR[bank]
    rows = sorted({(i & 0x3FF) >> 5 for i in cells}); cols = sorted({i & 31 for i in cells})
    r0, c0 = rows[0], cols[0]
    H, W = (rows[-1] - r0 + 1) * 8, (cols[-1] - c0 + 1) * 8
    img = [[None] * W for _ in range(H)]
    for i in cells:
        base = i & 0x400; r, c = (i & 0x3FF) >> 5, i & 31
        t = b.vram[i]
        at = b.vram[base + 0x3C0 + (r >> 2) * 8 + (c >> 2)]
        pal = (at >> (((r & 2) << 1) | (c & 2))) & 3
        d = data[t * 16:t * 16 + 16]
        for y in range(8):
            for x in range(8):
                v = ((d[y] >> (7 - x)) & 1) | (((d[y + 8] >> (7 - x)) & 1) << 1)
                if v:
                    img[(r - r0) * 8 + y][(c - c0) * 8 + x] = B.NES_RGB[b.pal[pal * 4 + v] & 0x3F] + (255,)
    # trim to what's drawn
    ys = [y for y in range(H) if any(img[y])]; xs = [x for x in range(W) if any(img[y][x] for y in range(H))]
    if not ys:
        return None
    return [row[xs[0]:xs[-1] + 1] for row in img[ys[0]:ys[-1] + 1]], (c0 * 8 + xs[0], r0 * 8 + ys[0])

if __name__ == "__main__":
    import png
    frames = [0x00, 0x0E, 0x0F, 0x10, 0x11, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1D, 0x1E, 0x1F, 0x0A, 0x0C, 0x5F,
              0x2F, 0x31, 0x3C, 0x40, 0x48, 0x05]
    imgs = [(f, mac_frame(f)) for f in frames]
    W = max(len(i[0]) for _, i in imgs if i) + 4; H = max(len(i) for _, i in imgs if i) + 4
    sheet = [[(40, 80, 200, 255)] * (W * len(imgs)) for _ in range(H)]
    for n, (f, im) in enumerate(imgs):
        if not im: continue
        for y in range(len(im)):
            for x in range(len(im[0])):
                if im[y][x]: sheet[y + 2][n * W + x + 2] = im[y][x]
    Z = 3
    png.write(str(HERE / "out" / "mac-nes.png"), len(sheet[0]) * Z, H * Z, [[c for c in r for _ in range(Z)] for r in sheet for _ in range(Z)])
    print([(hex(f), (len(i[0]), len(i)) if i else None) for f, i in imgs])
