"""Every Little Mac frame as the NES draws it (into the background, bank B $8020), from the real fight snapshot:
his script stopped, the frame set ($61, $60 = $81), the game's own frame run. out/mac-audit.png beside our poses."""
import copy, pickle, pathlib
import nes_boot as B, png, build

HERE = pathlib.Path(__file__).parent
USED = [0x00, 0x01, 0x02, 0x04, 0x05, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13,
        0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1C, 0x1D, 0x1E, 0x1F, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x34, 0x3A, 0x3C, 0x3E,
        0x40, 0x43, 0x45, 0x48, 0x54, 0x58, 0x5E, 0x5F, 0x60, 0x61]
base = B.fight_snapshot()
out = {}
for f in USED:
    b = copy.deepcopy(base)
    b.ram[0x50] = 0                         # his script stopped
    b.ram[0x61] = f
    b.ram[0x60] = 0x81
    b.ram[0x15] = 176
    b.run(3)
    img = b.render()
    out[f] = [row[80:176] for row in img[120:240]]
pickle.dump(out, open(HERE / "out" / "mac-frames.pkl", "wb"))
px = build.load("little-mac.png"); boxes = build.components(px, 70)
cur = {int(k, 16): v for k, v in build.MAC_FRAMES.items()}
CW, CH = 96, 120
cols = 6
cell = CW + 40
rows = (len(USED) + cols - 1) // cols
sheet = [[(255, 255, 255, 255)] * (cols * cell) for _ in range(rows * (CH + 10))]
for n, f in enumerate(USED):
    ox, oy = (n % cols) * cell, (n // cols) * (CH + 10) + 8
    for y in range(CH):
        for x in range(CW): sheet[oy + y][ox + x] = tuple(out[f][y][x]) + (255,)
    pose = cur.get(f, "idle"); mir = pose.endswith("|"); pose = pose.rstrip("|")
    r = build.cut(px, boxes[build.MAC[pose]])
    if mir: r = [list(reversed(row)) for row in r]
    for y in range(min(CH, len(r))):
        for x in range(min(38, len(r[0]))):
            sheet[oy + y][ox + CW + 1 + x] = tuple(r[y][x]) if r[y][x] else (190, 190, 190, 255)
    for k in range(f >> 4):
        for yy in range(3): sheet[oy - 8 + yy][ox + 2 + k * 3] = (200, 160, 0, 255)
    for k in range(f & 15):
        for yy in range(3): sheet[oy - 4 + yy][ox + 2 + k * 3] = (60, 60, 60, 255)
Z = 2
png.write(str(HERE / "out" / "mac-audit.png"), len(sheet[0]) * Z, len(sheet) * Z, [[c for c in r for _ in range(Z)] for r in sheet for _ in range(Z)])
print(" ".join(f"{f:02X}:{cur.get(f, 'idle')}" for f in USED))
