"""Joe's frames rendered from real fight state: the NES RAM the exact port logged when each frame/orientation
was on screen, set into the booted game's fight (nes_boot), his script stopped, the frame redrawn by the game's
own code. out/nes-frames3.pkl: {(frame, flip): RGB crop}."""
import copy, pickle, pathlib
import nes_boot as B

HERE = pathlib.Path(__file__).parent
KEEP = set(range(0x100, 0x300)) | {0x1D, 0x1E, 0x04}      # the stack and sprite page are the boot's; NMI mode too

def render(snap, base):
    b = copy.deepcopy(base)
    for a in list(range(0x80, 0x84)) + list(range(0x90, 0xB4)):    # his animation and place only
        b.ram[a] = snap[a]
    b.ram[0x90] = 0                                     # his script stopped
    b.ram[0x50] = 0
    b.ram[0xA0] = 0x80                                  # redraw his frame
    b.run(3)
    x, y = b.ram[0xB0], b.ram[0xB1]
    img = b.render()
    x0, y0 = max(0, min(256 - 112, x - 56)), max(0, min(240 - 150, y - 140))
    return [row[x0:x0 + 112] for row in img[y0:y0 + 150]]

if __name__ == "__main__":
    base = B.fight_snapshot()
    snaps = pickle.load(open(HERE / "out" / "ram-snaps.pkl", "rb"))
    out = {k: render(s, base) for k, s in snaps.items()}
    pickle.dump(out, open(HERE / "out" / "nes-frames3.pkl", "wb"))
    import png
    keys = sorted(out); cols = 9; W, H = 112, 150
    rows = (len(keys) + cols - 1) // cols
    sheet = [[(255, 255, 255, 255)] * (cols * (W + 2)) for _ in range(rows * (H + 2))]
    for n, k in enumerate(keys):
        ox, oy = (n % cols) * (W + 2), (n // cols) * (H + 2)
        for yy in range(H):
            for xx in range(W): sheet[oy + yy][ox + xx] = tuple(out[k][yy][xx]) + (255,)
    png.write(str(HERE / "out" / "nes-frames3.png"), len(sheet[0]), len(sheet), sheet)
    print(" ".join(f"{f:02X}/{fl}" for f, fl in keys))
