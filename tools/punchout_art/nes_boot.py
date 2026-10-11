"""Punch-Out!! booted in cpu6502 with just enough PPU to see its screens: the VRAM address latch, nametable
and palette writes, sprite DMA, the status read (vblank always reported), MMC2's CHR bank registers.
An NMI a frame. render() draws the background (and sprites) from the CHR banks as the game set them up."""
import pathlib
import cpu6502

import gamefiles
D = gamefiles.root()
CHR = {k: (D / "original_files" / f"CHR_Bank{k:03X}.bin").read_bytes() for k in range(32)
       if (D / "original_files" / f"CHR_Bank{k:03X}.bin").exists()}

# the NES's palette (2C02), RGB
NES_RGB = [(84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136), (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
           (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0), (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0),
           (152, 150, 152), (8, 76, 196), (48, 50, 236), (92, 30, 228), (136, 20, 176), (160, 20, 100), (152, 34, 32),
           (120, 60, 0), (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40), (0, 102, 120), (0, 0, 0), (0, 0, 0), (0, 0, 0),
           (236, 238, 236), (76, 154, 236), (120, 124, 236), (176, 98, 236), (228, 84, 236), (236, 88, 180), (236, 106, 100),
           (212, 136, 32), (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108), (56, 180, 204), (60, 60, 60), (0, 0, 0), (0, 0, 0),
           (236, 238, 236), (168, 204, 236), (188, 188, 236), (212, 178, 236), (236, 174, 236), (236, 174, 212), (236, 180, 176),
           (228, 196, 144), (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180), (160, 214, 228), (160, 162, 160), (0, 0, 0), (0, 0, 0)]


class Boot(cpu6502.Nes):
    def __init__(self):
        super().__init__(D, 0)
        self.vram = bytearray(0x800)            # two nametables
        self.pal = bytearray(0x20)
        self.oam = bytearray(0x100)
        self.ctrl = self.mask = 0
        self.addr = 0
        self.latch = False
        self.chr = {0xB000: 0, 0xC000: 0, 0xD000: 0, 0xE000: 0}
        self.vertical = True
        self.scroll_x = self.scroll_y = 0
        self.lo = self.bank(0)

    def read(self, a):
        if 0x2000 <= a < 0x4000:
            r = a & 7
            if r == 2:
                self.latch = False
                return 0x80
            return 0
        return super().read(a)

    def _nt(self, a):
        a &= 0x0FFF
        table, off = a >> 10, a & 0x3FF
        page = (table & 1) if self.vertical else (table >> 1)
        return page * 0x400 + off

    def write(self, a, v):
        v &= 0xFF
        if 0x2000 <= a < 0x4000:
            r = a & 7
            if r == 0: self.ctrl = v
            elif r == 1: self.mask = v
            elif r == 6:
                self.addr = (v & 0x3F) << 8 if not self.latch else (self.addr & 0xFF00) | v
                self.latch = not self.latch
            elif r == 5:                    # scroll: X, then Y
                if not self.latch: self.scroll_x = v
                else: self.scroll_y = v
                self.latch = not self.latch
            elif r == 7:
                a2 = self.addr
                if 0x2000 <= a2 < 0x3F00: self.vram[self._nt(a2)] = v
                elif a2 >= 0x3F00:
                    p = a2 & 0x1F
                    if p in (0x10, 0x14, 0x18, 0x1C): p -= 0x10
                    self.pal[p] = v
                self.addr = (a2 + (32 if self.ctrl & 4 else 1)) & 0x3FFF
            return
        if a == 0x4014:
            self.oam[:] = bytes(self.ram[v * 256 + k] for k in range(256))
            return
        if 0xB000 <= a < 0xF000:
            self.chr[a & 0xF000] = v & 0x1F
            return
        if 0xF000 <= a:
            self.vertical = not (v & 1)
            return
        super().write(a, v)

    def run(self, frames, buttons=lambda f: 0, per_frame=12000):
        c = self.cpu
        if not hasattr(self, "_booted"):
            c.pc = self.read(0xFFFC) | self.read(0xFFFD) << 8
            self._booted = 0
        for f in range(frames):
            self.buttons = buttons(self._booted)
            for _ in range(per_frame):
                c.step()
            if self.ctrl & 0x80:                    # NMI
                c.push(c.pc >> 8); c.push(c.pc & 0xFF); c.push(c.flags(0))
                c.pc = self.read(0xFFFA) | self.read(0xFFFB) << 8
            self._booted += 1

    def tile(self, table, t):
        """CHR tile t of pattern table 0/1, by the MMC2 banks (the $FE banks: the latches' usual state)."""
        bank = self.chr[0xC000] if table == 0 else self.chr[0xE000]
        data = CHR[bank >> 0][t * 16:t * 16 + 16] if (bank >> 0) in CHR else bytes(16)
        return [[((data[y] >> (7 - x)) & 1) | (((data[y + 8] >> (7 - x)) & 1) << 1) for x in range(8)] for y in range(8)]

    def render(self, sprites=True, limit=True):
        """256x240 RGB of nametable 0 (with attributes and the palette), and the sprites. MMC2: the background's
        bank switches as tiles $FD/$FE are drawn (latch per pattern table, left to right, top to bottom)."""
        table = 1 if self.ctrl & 0x10 else 0
        img = [[NES_RGB[self.pal[0] & 0x3F]] * 256 for _ in range(240)]
        latch = {0: 0xFE, 1: 0xFE}
        def bank(tbl):
            return self.chr[(0xB000 if latch[tbl] == 0xFD else 0xC000) if tbl == 0 else (0xD000 if latch[tbl] == 0xFD else 0xE000)]
        def tile(tbl, t):
            data = CHR.get(bank(tbl), bytes(4096))[t * 16:t * 16 + 16]
            g = [[((data[y] >> (7 - x)) & 1) | (((data[y + 8] >> (7 - x)) & 1) << 1) for x in range(8)] for y in range(8)]
            if t in (0xFD, 0xFE): latch[tbl] = t
            return g
        sx0 = getattr(self, "scroll_x", 0) + (self.ctrl & 1) * 256     # the nametable PPUCTRL picks, scrolled
        for ty in range(30):
            for col in range(33):
                wx = sx0 + col * 8 - (sx0 & 7)
                page, tx = (wx >> 8) & 1, (wx & 0xFF) >> 3
                base = (page * 0x400) if self.vertical else 0
                t = self.vram[base + ty * 32 + tx]
                at = self.vram[base + 0x3C0 + (ty >> 2) * 8 + (tx >> 2)]
                pal = (at >> (((ty & 2) << 1) | (tx & 2))) & 3
                g = tile(table, t)
                for y in range(8):
                    for x in range(8):
                        X = col * 8 - (sx0 & 7) + x
                        v = g[y][x]
                        if v and 0 <= X < 256:
                            img[ty * 8 + y][X] = NES_RGB[self.pal[pal * 4 + v] & 0x3F]
        if sprites:                         # scanline by scanline, as the PPU fetches: up to 8 per line in OAM
            stable = 1 if self.ctrl & 0x08 else 0   # order, each fetch of tile $FD/$FE flipping MMC2's latch
            lat = getattr(self, "spr_latch", 0xFE)
            for Y in range(240):
                on = []
                for i in range(64):
                    sy, t, a, sx = self.oam[i * 4:i * 4 + 4]
                    if sy < 0xEF and sy + 1 <= Y < sy + 9:
                        on.append((i, sy, t, a, sx))
                    if len(on) == 8 and limit:      # (the hardware's limit; off: every sprite, no flicker)
                        break
                rows = []
                for i, sy, t, a, sx in on:
                    bank = (self.chr[0xB000] if lat == 0xFD else self.chr[0xC000]) if stable == 0 else \
                           (self.chr[0xD000] if lat == 0xFD else self.chr[0xE000])
                    yy = Y - sy - 1
                    if a & 0x80: yy = 7 - yy
                    d = CHR.get(bank, bytes(4096))[t * 16:t * 16 + 16]
                    rows.append((i, sx, a, [((d[yy] >> (7 - x)) & 1) | (((d[yy + 8] >> (7 - x)) & 1) << 1) for x in range(8)]))
                    if t in (0xFD, 0xFE) and yy == (7 if a & 0x80 else 0) or t in (0xFD, 0xFE):
                        lat = t
                for i, sx, a, row in reversed(rows):    # lower OAM index on top
                    for x in range(8):
                        v = row[7 - x if a & 0x40 else x]
                        X = sx + x
                        if v and X < 256:
                            img[Y][X] = NES_RGB[self.pal[0x10 + (a & 3) * 4 + v] & 0x3F]
            self.spr_latch = lat
        return img


def fight_snapshot():
    """The game booted into the Glass Joe fight (Start through the title and intro screens), saved once to
    out/boot-fight.pkl: what the frame tools draw from."""
    import pickle
    path = pathlib.Path(__file__).parent / "out" / "boot-fight.pkl"
    if path.exists():
        return pickle.load(open(path, "rb"))
    b = Boot()
    b.run(600)
    for _ in range(40):
        b.run(30, lambda f: 0x10 if (f % 90) < 4 and f >= 605 else 0)
        if b.ram[0x00] == 1 and b.ram[0x90] & 0x7F == 0x40 and b.ram[0x04] == 0xFF:
            b.run(120)
            break
    path.parent.mkdir(exist_ok=True)
    pickle.dump(b, open(path, "wb"))
    return b


def save(img, path):
    import png
    png.write(path, len(img[0]), len(img), [[(r, g, b, 255) for r, g, b in row] for row in img])


if __name__ == "__main__":
    import sys
    b = Boot()
    for n in range(int(sys.argv[1]) if len(sys.argv) > 1 else 6):
        b.run(30)
        save(b.render(), f"out/boot{n}.png")
        print(n, "ctrl", hex(b.ctrl), "mask", hex(b.mask), "chr", {hex(k): v for k, v in b.chr.items()}, "pc", hex(b.cpu.pc))
