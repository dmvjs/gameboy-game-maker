"""Memory map, timers and screen timing around the SM83 core, for measuring ROMs.

What's modeled: ROM (no mapper, MBC1, MBC5), VRAM/WRAM banks, OAM DMA, Game Boy Color general-purpose
DMA, timer, serial output, LY/STAT timing and the VBlank and LYC interrupts, Game Boy Color palettes.
What isn't (STOP and double speed, H-blank DMA, STAT mode interrupts, sprites and window in rendering)
raises Unsupported.

It also catches hardware-rule violations that silently fail on a real Game Boy, such as writing
video memory while the screen is drawing.
"""

import random

from .sm83 import CPU, Unsupported

FRAME = 70224
LINE = 456
DMG_GRAYS = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]


class Machine:
    def __init__(self, rom, cgb):
        if len(rom) < 0x8000:
            raise Unsupported("ROM is smaller than 32 KB")
        self.rom = bytes(rom)
        self.cgb = cgb
        cart = rom[0x147]
        if cart == 0x00:
            self.mbc = None
        elif cart in (0x01, 0x02, 0x03):
            self.mbc = "mbc1"
        elif 0x19 <= cart <= 0x1E:
            self.mbc = "mbc5"
        else:
            raise Unsupported(f"cartridge type ${cart:02X} isn't modeled")
        self.rom_bank = 1
        self.ram_bank = 0
        self.ram_enabled = False
        self.ext_ram = bytearray(0x20000)

        # Real hardware powers on with random RAM; fill it with a fixed pseudo-random pattern so code
        # that forgets to initialize memory fails here too (and the same way every run).
        noise = random.Random(0x6B).randbytes if hasattr(random.Random, "randbytes") else None
        fill = (lambda n: bytearray(noise(n))) if noise else (lambda n, r=random.Random(0x6B): bytearray(r.getrandbits(8) for _ in range(n)))
        self.vram = [bytearray(0x2000), bytearray(0x2000)]
        self.vbk = 0
        self.wram = [fill(0x1000) for _ in range(8)]
        self.svbk = 1
        self.oam = bytearray(0xA0)
        self.hram = fill(0x7F)
        self.io = bytearray(0x80)
        self.bg_pal = bytearray(64)
        self.obj_pal = bytearray(64)
        self.ie = 0

        self.cycles = 0           # total T-cycles since power-on handoff
        self.div_counter = 0xABCC
        self.lcd_dots = 0         # position within the frame while the LCD is on
        self.serial = []
        self.stall = 0            # cycles the CPU is frozen by a DMA transfer started this instruction
        self.buttons = set()      # held: "a", "b", "select", "start", "right", "left", "up", "down"
        self.violations = []
        self.interrupt_hook = None
        self.vblank_hook = None   # called when the screen enters VBlank (LY 144)

        io = self.io
        for addr, val in {0x00: 0xCF, 0x07: 0xF8, 0x0F: 0xE1, 0x40: 0x91, 0x41: 0x85, 0x47: 0xFC}.items():
            io[addr] = val

        self.cpu = CPU(self)
        r = self.cpu.r
        if cgb:
            r[:] = [0x00, 0x00, 0xFF, 0x56, 0x00, 0x0D, 0, 0x11]
            self.cpu.f = 0x80
        else:
            r[:] = [0x00, 0x13, 0x00, 0xD8, 0x01, 0x4D, 0, 0x01]
            self.cpu.f = 0xB0

    # ---- interrupts --------------------------------------------------------

    def pending_interrupts(self):
        return self.ie & self.io[0x0F] & 0x1F

    def clear_interrupt(self, bit):
        self.io[0x0F] &= ~(1 << bit) & 0xFF

    def request(self, bit):
        self.io[0x0F] |= 1 << bit

    def on_interrupt(self, bit):
        if self.interrupt_hook:
            self.interrupt_hook(bit)

    # ---- screen timing -----------------------------------------------------

    def lcd_on(self):
        return self.io[0x40] & 0x80

    def mode(self):
        if not self.lcd_on():
            return 0
        line, dot = divmod(self.lcd_dots, LINE)
        if line >= 144:
            return 1
        if dot < 80:
            return 2
        return 3 if dot < 80 + 172 else 0

    def ly(self):
        return self.lcd_dots // LINE if self.lcd_on() else 0

    def _check_lyc(self):
        if self.ly() == self.io[0x45] and self.io[0x41] & 0x40:
            self.request(1)

    def advance(self, cycles):
        self.cycles += cycles
        old = self.div_counter
        new = old + cycles
        self.div_counter = new & 0xFFFF
        tac = self.io[0x07]
        if tac & 4:
            bit = (9, 3, 5, 7)[tac & 3]
            ticks = (new >> (bit + 1)) - (old >> (bit + 1))
            for _ in range(ticks):
                tima = self.io[0x05] + 1
                if tima > 0xFF:
                    tima = self.io[0x06]
                    self.request(2)
                self.io[0x05] = tima
        if self.lcd_on():
            old_line = self.lcd_dots // LINE
            self.lcd_dots += cycles
            new_line = self.lcd_dots // LINE
            if new_line != old_line:
                for line in range(old_line + 1, new_line + 1):
                    ly = line % 154
                    if ly == 144:
                        self.request(0)
                        if self.io[0x41] & 0x10:
                            self.request(1)
                        if self.vblank_hook:
                            self.vblank_hook()
                    if ly == self.io[0x45] and self.io[0x41] & 0x40:
                        self.request(1)
                self.lcd_dots %= FRAME

    # ---- memory ------------------------------------------------------------

    def read(self, addr):
        if addr < 0x4000:
            return self.rom[addr]
        if addr < 0x8000:
            off = self.rom_bank * 0x4000 + addr - 0x4000
            return self.rom[off % len(self.rom)]
        if addr < 0xA000:
            return self.vram[self.vbk][addr - 0x8000]
        if addr < 0xC000:
            return self.ext_ram[self.ram_bank * 0x2000 + addr - 0xA000] if self.ram_enabled else 0xFF
        if addr < 0xD000:
            return self.wram[0][addr - 0xC000]
        if addr < 0xE000:
            return self.wram[self.svbk][addr - 0xD000]
        if addr < 0xFE00:
            return self.read(addr - 0x2000)
        if addr < 0xFEA0:
            return self.oam[addr - 0xFE00]
        if addr < 0xFF00:
            return 0xFF
        if addr < 0xFF80:
            return self.read_io(addr & 0x7F)
        if addr < 0xFFFF:
            return self.hram[addr - 0xFF80]
        return self.ie

    def write(self, addr, v):
        if addr < 0x8000:
            return self._mbc_write(addr, v)
        if addr < 0xA000:
            if self.lcd_on() and self.mode() == 3:
                self._violation(f"wrote video memory ${addr:04X} while the screen was drawing (ignored on hardware)")
                return
            self.vram[self.vbk][addr - 0x8000] = v
        elif addr < 0xC000:
            if self.ram_enabled:
                self.ext_ram[self.ram_bank * 0x2000 + addr - 0xA000] = v
        elif addr < 0xD000:
            self.wram[0][addr - 0xC000] = v
        elif addr < 0xE000:
            self.wram[self.svbk][addr - 0xD000] = v
        elif addr < 0xFE00:
            self.write(addr - 0x2000, v)
        elif addr < 0xFEA0:
            if self.lcd_on() and self.mode() in (2, 3):
                self._violation(f"wrote sprite memory ${addr:04X} while the screen was drawing (ignored on hardware)")
                return
            self.oam[addr - 0xFE00] = v
        elif addr < 0xFF00:
            pass
        elif addr < 0xFF80:
            self.write_io(addr & 0x7F, v)
        elif addr < 0xFFFF:
            self.hram[addr - 0xFF80] = v
        else:
            self.ie = v

    def _mbc_write(self, addr, v):
        if self.mbc is None:
            return
        if addr < 0x2000:
            self.ram_enabled = (v & 0x0F) == 0x0A
        elif addr < 0x3000 and self.mbc == "mbc5":
            self.rom_bank = (self.rom_bank & 0x100) | v
        elif addr < 0x4000:
            if self.mbc == "mbc5":
                self.rom_bank = (self.rom_bank & 0xFF) | (v & 1) << 8
            else:
                self.rom_bank = (v & 0x1F) or 1
        elif addr < 0x6000:
            self.ram_bank = v & 0x0F if self.mbc == "mbc5" else v & 3

    def _violation(self, message):
        if len(self.violations) < 50:
            self.violations.append({"cycle": self.cycles, "pc": self.cpu.pc, "message": message})

    def read_io(self, reg):
        io = self.io
        if reg == 0x00:
            low = 0x0F
            if not io[0] & 0x10:
                low &= ~sum(1 << i for i, b in enumerate(("right", "left", "up", "down")) if b in self.buttons)
            if not io[0] & 0x20:
                low &= ~sum(1 << i for i, b in enumerate(("a", "b", "select", "start")) if b in self.buttons)
            return 0xC0 | (io[0] & 0x30) | (low & 0x0F)
        if reg == 0x04:
            return self.div_counter >> 8
        if reg == 0x0F:
            return io[0x0F] | 0xE0
        if reg == 0x41:
            coincidence = 4 if self.ly() == io[0x45] else 0
            return 0x80 | (io[0x41] & 0x78) | coincidence | self.mode()
        if reg == 0x44:
            return self.ly()
        if self.cgb:
            if reg == 0x4F:
                return 0xFE | self.vbk
            if reg == 0x69:
                return self.bg_pal[io[0x68] & 0x3F]
            if reg == 0x6B:
                return self.obj_pal[io[0x6A] & 0x3F]
            if reg == 0x70:
                return 0xF8 | self.svbk
        elif reg in (0x4D, 0x4F, 0x51, 0x52, 0x53, 0x54, 0x55, 0x68, 0x69, 0x6A, 0x6B, 0x70):
            return 0xFF
        return io[reg]

    def write_io(self, reg, v):
        io = self.io
        if reg == 0x02:
            io[2] = v
            if v & 0x81 == 0x81:
                self.serial.append(chr(io[1]))
                io[1] = 0xFF
                io[2] = v & 0x7F
                self.request(3)
            return
        if reg == 0x04:
            self.div_counter = 0
            return
        if reg == 0x40:
            was_on = self.lcd_on()
            if was_on and not v & 0x80 and self.mode() != 1:
                self._violation("turned the screen off outside VBlank (can damage a real Game Boy's LCD)")
            io[0x40] = v
            if not was_on and v & 0x80:
                self.lcd_dots = 0
            return
        if reg == 0x41:
            if v & 0x28:
                raise Unsupported("STAT mode 0/2 interrupts aren't modeled yet")
            io[0x41] = v & 0x78
            return
        if reg == 0x44:
            return
        if reg == 0x46:
            if self.lcd_on() and self.mode() in (2, 3):
                self._violation("started sprite DMA while the screen was drawing (sprites would glitch)")
            src = v << 8
            for i in range(0xA0):
                self.oam[i] = self.read(src + i)
            io[0x46] = v
            return
        if self.cgb:
            if reg == 0x4D:
                io[0x4D] = v & 1
                return
            if reg == 0x4F:
                self.vbk = v & 1
                return
            if reg in (0x51, 0x52, 0x53, 0x54):
                io[reg] = v
                return
            if reg == 0x55:
                return self._gdma(v)
            if reg in (0x69, 0x6B):
                if self.lcd_on() and self.mode() == 3:
                    self._violation("wrote a color palette while the screen was drawing (ignored on hardware)")
                spec = io[reg - 1]
                pal = self.bg_pal if reg == 0x69 else self.obj_pal
                pal[spec & 0x3F] = v
                if spec & 0x80:
                    io[reg - 1] = 0x80 | ((spec + 1) & 0x3F)
                return
            if reg == 0x70:
                self.svbk = (v & 7) or 1
                return
        elif reg in (0x4D, 0x4F, 0x51, 0x52, 0x53, 0x54, 0x55, 0x68, 0x69, 0x6A, 0x6B, 0x70):
            return                          # Color-only registers don't exist on an original Game Boy
        io[reg] = v

    def _gdma(self, v):
        """General-purpose DMA: copy (v & $7F) + 1 blocks of 16 bytes into VRAM, freezing the CPU
        for 32 cycles per block (Pan Docs: 8 M-cycles per $10 bytes at normal speed)."""
        if v & 0x80:
            raise Unsupported("H-blank DMA isn't modeled yet")
        io = self.io
        src = (io[0x51] << 8 | io[0x52]) & 0xFFF0
        dst = (io[0x53] << 8 | io[0x54]) & 0x1FF0
        blocks = (v & 0x7F) + 1
        if 0x8000 <= src < 0xA000 or src >= 0xE000:
            raise Unsupported(f"DMA from ${src:04X} (video memory or above $E000) isn't valid")
        if self.lcd_on() and self.mode() == 3:
            self._violation("started a DMA into video memory while the screen was drawing")
        for i in range(blocks * 16):
            self.vram[self.vbk][(dst + i) & 0x1FFF] = self.read(src + i)
        io[0x55] = 0xFF
        self.stall += blocks * 32

    # ---- running -----------------------------------------------------------

    def step(self):
        cycles, pc, halted = self.cpu.step()
        cycles += self.stall
        self.stall = 0
        self.advance(cycles)
        return cycles, pc, halted

    def render_background(self, sprites=True):
        """Render the screen as it currently stands. Returns 160*144 (r, g, b) tuples."""
        lcdc = self.io[0x40] if sprites else self.io[0x40] & ~0x02
        if not lcdc & 0x80:
            return [(255, 255, 255)] * (160 * 144)
        if lcdc & 0x20:
            raise Unsupported("rendering the window layer isn't modeled yet")
        if lcdc & 0x04:
            raise Unsupported("rendering 8x16 sprites isn't modeled yet")
        bg_off = not self.cgb and not lcdc & 1
        scx, scy, bgp = self.io[0x43], self.io[0x42], self.io[0x47]
        map_base = 0x1C00 if lcdc & 0x08 else 0x1800
        unsigned = lcdc & 0x10
        v0, v1 = self.vram
        out, bg_index = [], []
        for y in range(144):
            by = (y + scy) & 0xFF
            for x in range(160):
                if bg_off:
                    out.append((255, 255, 255))
                    bg_index.append(0)
                    continue
                bx = (x + scx) & 0xFF
                m = map_base + (by >> 3) * 32 + (bx >> 3)
                tile = v0[m]
                attr = v1[m] if self.cgb else 0
                base = tile * 16 if unsigned else 0x1000 + (tile - 256 if tile > 127 else tile) * 16
                row = 7 - (by & 7) if attr & 0x40 else by & 7
                col = 7 - (bx & 7) if attr & 0x20 else bx & 7
                bank = self.vram[1] if attr & 0x08 else v0
                lo, hi = bank[base + row * 2], bank[base + row * 2 + 1]
                ci = (lo >> (7 - col) & 1) | (hi >> (7 - col) & 1) << 1
                bg_index.append(ci)
                if self.cgb:
                    p = (attr & 7) * 8 + ci * 2
                    c = self.bg_pal[p] | self.bg_pal[p + 1] << 8
                    out.append(tuple(((c >> s & 31) << 3) | ((c >> s & 31) >> 2) for s in (0, 5, 10)))
                else:
                    out.append(DMG_GRAYS[bgp >> (ci * 2) & 3])
        if lcdc & 0x02:
            self._render_sprites(out, bg_index)
        return out

    def _render_sprites(self, out, bg_index):
        """8x8 sprites with flips, palettes, BG priority and the 10-per-line limit."""
        sprites = [(i, self.oam[i * 4] - 16, self.oam[i * 4 + 1] - 8, self.oam[i * 4 + 2], self.oam[i * 4 + 3])
                   for i in range(40)]
        for y in range(144):
            on_line = [s for s in sprites if s[1] <= y < s[1] + 8][:10]
            # Lower priority first, so higher priority sprites draw over them.
            if self.cgb:
                order = sorted(on_line, key=lambda s: -s[0])
            else:
                order = sorted(on_line, key=lambda s: (-s[2], -s[0]))
            for i, sy, sx, tile, attr in order:
                row = y - sy
                if attr & 0x40:
                    row = 7 - row
                bank = self.vram[1] if self.cgb and attr & 0x08 else self.vram[0]
                lo, hi = bank[tile * 16 + row * 2], bank[tile * 16 + row * 2 + 1]
                for col in range(8):
                    x = sx + col
                    if not 0 <= x < 160:
                        continue
                    bit = col if attr & 0x20 else 7 - col
                    ci = (lo >> bit & 1) | (hi >> bit & 1) << 1
                    if ci == 0:
                        continue
                    if attr & 0x80 and bg_index[y * 160 + x]:
                        continue
                    if self.cgb:
                        p = (attr & 7) * 8 + ci * 2
                        c = self.obj_pal[p] | self.obj_pal[p + 1] << 8
                        out[y * 160 + x] = tuple(((c >> s & 31) << 3) | ((c >> s & 31) >> 2) for s in (0, 5, 10))
                    else:
                        obp = self.io[0x49] if attr & 0x10 else self.io[0x48]
                        out[y * 160 + x] = DMG_GRAYS[obp >> (ci * 2) & 3]
