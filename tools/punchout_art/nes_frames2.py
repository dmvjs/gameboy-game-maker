"""Glass Joe's frames as they come up in a real fight (nes_boot), Mac punching at random: each frame's first
showing, rendered two frames after it's set. out/nes-frames.pkl: {frame: RGB crop around him}."""
import copy, pickle, pathlib, random
import nes_boot as B, png

HERE = pathlib.Path(__file__).parent
W, H = 128, 176

def capture(frames=9000, seed=1):
    b = B.fight_snapshot()
    rng = random.Random(seed)
    held, hold, pending, out = 0, 0, {}, {}
    for t in range(frames):
        if hold == 0:
            held = rng.choice([0, 0, 0x80, 0x40, 0x88, 0x48, 0x02, 0x01, 0x04])
            hold = rng.randrange(2, 20)
        hold -= 1
        b.ram[0x0391] = b.ram[0x0392] = 0x60            # Mac stays up
        b.run(1, lambda f: held)
        f = b.ram[0xA1]
        if f not in out and f not in pending:
            pending[f] = 3
        for k in list(pending):
            pending[k] -= 1
            if pending[k] == 0:
                del pending[k]
                if b.ram[0xA1] == k:
                    x, y = b.ram[0xB0], b.ram[0xB1]
                    img = b.render()
                    x0, y0 = max(0, min(256 - W, x - 64)), max(0, min(240 - H, y - 150))
                    out[k] = {"img": [row[x0:x0 + W] for row in img[y0:y0 + H]], "x": x, "y": y}
    return out

if __name__ == "__main__":
    out = capture()
    pickle.dump(out, open(HERE / "out" / "nes-frames.pkl", "wb"))
    cols = 10
    keys = sorted(out)
    rows = (len(keys) + cols - 1) // cols
    sheet = [[(255, 255, 255, 255)] * (cols * (W + 2)) for _ in range(rows * (H + 2))]
    for n, f in enumerate(keys):
        ox, oy = (n % cols) * (W + 2), (n // cols) * (H + 2)
        for y in range(H):
            for x in range(W):
                sheet[oy + y][ox + x] = tuple(out[f]["img"][y][x]) + (255,)
    png.write(str(HERE / "out" / "nes-frames.png"), len(sheet[0]), len(sheet), sheet)
    print(" ".join(f"{f:02X}" for f in keys))
