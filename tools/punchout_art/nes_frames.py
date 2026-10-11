"""Every Glass Joe frame as the NES game draws it: from a snapshot of the real fight (nes_boot), his script
stopped, his frame set, two frames run so its own drawing code places him. Writes out/nes-frames.pkl:
{frame: RGB crop}, and out/nes-frames.png with them side by side."""
import copy, pickle, pathlib
import nes_boot as B, png

HERE = pathlib.Path(__file__).parent
FRAMES = [k for k in range(0x00, 0x3C, 2)] + [0x80, 0x82, 0x84, 0x86] + [k for k in range(0xC0, 0xCE, 2)]
BOX = (72, 24, 200, 216)                    # x0, y0, x1, y1 around him at his place

def render_all():
    base = B.fight_snapshot()
    empty = None
    out = {}
    for f in [None] + [(k, fl) for fl in (0, 1) for k in FRAMES]:
        b = copy.deepcopy(base)
        b.ram[0x90] = 0                     # his script stopped
        if f is not None:
            f, flip = f
            b.ram[0xA2] = flip              # drawn mirrored ($A2, as his script's $C5C8 sets it)
        b.ram[0xB0], b.ram[0xB1] = 0x87, 0xB6
        if f is not None:
            b.ram[0xA1] = f
        b.ram[0xA0] = 0x80 if f is not None else 0
        b.run(2)
        img = b.render()
        crop = [row[BOX[0]:BOX[2]] for row in img[BOX[1]:BOX[3]]]
        if f is None:
            empty = crop
        else:
            out[(f, flip)] = crop
    return empty, out

if __name__ == "__main__":
    empty, out = render_all()
    pickle.dump({"empty": empty, "frames": out}, open(HERE / "out" / "nes-frames.pkl", "wb"))
    W, H = BOX[2] - BOX[0], BOX[3] - BOX[1]
    cols = 10
    rows = (len(out) + cols - 1) // cols
    sheet = [[(255, 255, 255, 255)] * (cols * (W + 2)) for _ in range(rows * (H + 2))]
    for n, (f, crop) in enumerate(sorted(out.items())):
        ox, oy = (n % cols) * (W + 2), (n // cols) * (H + 2)
        for y in range(H):
            for x in range(W):
                sheet[oy + y][ox + x] = tuple(crop[y][x]) + (255,)
        f = f[0]
    png.write(str(HERE / "out" / "nes-frames.png"), len(sheet[0]), len(sheet), sheet)
    print(len(out))
