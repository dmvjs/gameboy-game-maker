"""Glass Joe's frames drawn exactly as the NES game draws them: its own routine ($C890, run in cpu6502)
places the sprites, and the tiles come from the CHR banks in the disassembly."""
import pathlib
import cpu6502, png

import gamefiles
D = gamefiles.root()
CHR = {k: (D / "original_files" / f"CHR_Bank{k:03X}.bin").read_bytes() for k in range(32)
       if (D / "original_files" / f"CHR_Bank{k:03X}.bin").exists()}


def sprites(index, height=8, x=135, y=182, base=None):
    nes = cpu6502.Nes(D, 0); ram = nes.ram
    for a in range(0x200, 0x300): ram[a] = 0xF8 if a % 4 == 0 else 0
    ram[0x03] = 0; ram[0xA0] = 0x80; ram[0xA1] = index; ram[0xB0], ram[0xB1] = x, y
    ram[0x80] = height; ram[0x82] = 0xFF
    if base:                                   # partial frames ($80+) draw over a full one
        for k, v in base.items(): ram[k] = v
    nes.cpu.call(0xC890)
    out = []
    for i in range(0, 256, 4):
        sy, t, a, sx = ram[0x200 + i:0x204 + i]
        if sy < 0xEF and t != 0xFF: out.append((sx, sy + 1, t, a))
    return out, bytes(ram[0x200:0x300])


def tile(bank, t):
    d = CHR[bank][t * 16:t * 16 + 16]
    return [[((d[y] >> (7 - x)) & 1) | (((d[y + 8] >> (7 - x)) & 1) << 1) for x in range(8)] for y in range(8)]


def draw(spr, bank, W=96, H=128, ox=None, oy=None, pal=None):
    pal = pal or [None, (255, 200, 180, 255), (200, 40, 20, 255), (20, 20, 30, 255)]
    xs = [s[0] for s in spr] or [0]; ys = [s[1] for s in spr] or [0]
    ox = min(xs) - 8 if ox is None else ox; oy = min(ys) - 8 if oy is None else oy
    img = [[(40, 80, 200, 255)] * W for _ in range(H)]
    for sx, sy, t, a in spr:
        g = tile(bank, t)
        for yy in range(8):
            for xx in range(8):
                v = g[7 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]
                X, Y = sx - ox + xx, sy - oy + yy
                if v and 0 <= X < W and 0 <= Y < H: img[Y][X] = pal[v]
    return img


def draw16(spr, lo, hi, W=96, H=160, pal=None, ox=None, oy=None):
    """8x16 sprites: tile bit 0 picks the pattern table ($0000 = CHR bank lo, $1000 = hi)."""
    pal = pal or [None, (255, 200, 180, 255), (200, 40, 20, 255), (20, 20, 30, 255)]
    xs = [s[0] for s in spr] or [0]; ys = [s[1] for s in spr] or [0]
    ox = min(xs) - 4 if ox is None else ox; oy = min(ys) - 4 if oy is None else oy
    img = [[(40, 80, 200, 255)] * W for _ in range(H)]
    for sx, sy, t, a in spr:
        bank = hi if t & 1 else lo
        top, bot = tile(bank, t & 0xFE), tile(bank, (t & 0xFE) + 1)
        g = top + bot
        for yy in range(16):
            for xx in range(8):
                v = g[15 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]
                X, Y = sx - ox + xx, sy - oy + yy
                if v and 0 <= X < W and 0 <= Y < H: img[Y][X] = pal[v]
    return img
