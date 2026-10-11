"""Each NES frame (as the game draws it) beside the rip frame its pose shows now: out/audit.png."""
import pickle, pathlib
import build, png
HERE = pathlib.Path(__file__).parent
# the orientations the fight shows each frame in ($A2), logged from the NES-exact port over whole fights
USED = {0x00: [0], 0x02: [0, 1], 0x04: [0], 0x06: [0, 1], 0x08: [0], 0x0A: [0, 1], 0x0E: [0], 0x10: [0, 1], 0x16: [0],
        0x18: [0], 0x1A: [0], 0x1E: [0, 1], 0x20: [0, 1], 0x28: [1], 0x2A: [1], 0x2C: [1], 0x2E: [1], 0x30: [1],
        0x32: [1], 0x3A: [0], 0x80: [0, 1], 0x82: [0], 0xC0: [0, 1], 0xC2: [0, 1], 0xC4: [0, 1], 0xCC: [0]}
data = pickle.load(open(HERE / "out" / "nes-frames.pkl", "rb"))
frames = data["frames"]
px = build.load("glass-joe.png"); boxes = build.components(px, 120)
current = {int(k, 16): v for k, v in build.NES_FRAMES.items()}
CW, CH = 76, 120
import sys
part = int(sys.argv[1]) if len(sys.argv) > 1 else 0
keys = [(f, fl) for f in sorted(USED) for fl in USED[f]]
keys = keys[part * 18:(part + 1) * 18]
cols = 6
cell_w = CW * 2 + 6
rows = (len(keys) + cols - 1) // cols
sheet = [[(255, 255, 255, 255)] * (cols * cell_w) for _ in range(rows * (CH + 12))]
for n, (f, fl) in enumerate(keys):
    img = frames[(f, fl)]
    ox, oy = (n % cols) * cell_w, (n // cols) * (CH + 12) + 10
    for y in range(CH):
        for x in range(CW):
            sheet[oy + y][ox + x] = tuple(img[36 + y][24 + x]) + (255,)
    pose = current.get(f)
    if pose in build.JOE:
        r = build.cut(px, boxes[build.JOE[pose]])
        for y in range(min(CH, len(r))):
            for x in range(min(CW, len(r[0]))):
                sheet[oy + y][ox + CW + 2 + x] = tuple(r[y][x]) if r[y][x] else (190, 190, 190, 255)
    for k in range(f >> 4):                       # frame number: high nibble yellow, low white bars
        for yy in range(3): sheet[oy - 9 + yy][ox + 2 + k * 3] = (200, 160, 0, 255)
    for k in range(f & 15):
        for yy in range(3): sheet[oy - 5 + yy][ox + 2 + k * 3] = (60, 60, 60, 255)
Z = 2
png.write(str(HERE / "out" / f"audit{part}.png"), len(sheet[0]) * Z, len(sheet) * Z, [[c for c in r for _ in range(Z)] for r in sheet for _ in range(Z)])
print(" ".join(f"{f:02X}/{fl}:{current.get(f)}" for f, fl in keys))
