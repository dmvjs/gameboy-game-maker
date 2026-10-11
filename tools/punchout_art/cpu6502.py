"""A small 6502 interpreter for running routines from the NES Punch-Out!! disassembly's ROM banks: drawing
Glass Joe's frames exactly as the game does, and checking the Game Boy port of the fight logic against the
original. Official opcodes only; no decimal mode (the NES has none). Memory: 2 KB RAM mirrored to $2000,
PPU/APU writes captured, PRG bank 0 at $8000 and the fixed banks at $A000-$FFFF.
"""


class CPU:
    def __init__(self, read, write):
        self.read, self.write = read, write
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.c = self.z = self.i = self.d = self.v = self.n = 0
        self.cycles = 0

    # ---- helpers ----
    def r16(self, a):
        return self.read(a) | self.read((a + 1) & 0xFFFF) << 8

    def r16bug(self, a):            # JMP ($xxFF) wraps within the page
        return self.read(a) | self.read((a & 0xFF00) | ((a + 1) & 0xFF)) << 8

    def push(self, v):
        self.write(0x100 | self.sp, v & 0xFF); self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF; return self.read(0x100 | self.sp)

    def nz(self, v):
        v &= 0xFF; self.z = int(v == 0); self.n = v >> 7; return v

    def flags(self, b=1):
        return self.c | self.z << 1 | self.i << 2 | self.d << 3 | b << 4 | 1 << 5 | self.v << 6 | self.n << 7

    def set_flags(self, p):
        self.c, self.z, self.i, self.d = p & 1, p >> 1 & 1, p >> 2 & 1, p >> 3 & 1
        self.v, self.n = p >> 6 & 1, p >> 7 & 1

    def fetch(self):
        v = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF; return v

    def fetch16(self):
        v = self.r16(self.pc); self.pc = (self.pc + 2) & 0xFFFF; return v

    # ---- addressing: returns an address (or None for accumulator/implied) ----
    def addr(self, mode):
        if mode == "imm": a = self.pc; self.pc = (self.pc + 1) & 0xFFFF; return a
        if mode == "zp": return self.fetch()
        if mode == "zpx": return (self.fetch() + self.x) & 0xFF
        if mode == "zpy": return (self.fetch() + self.y) & 0xFF
        if mode == "abs": return self.fetch16()
        if mode == "abx": return (self.fetch16() + self.x) & 0xFFFF
        if mode == "aby": return (self.fetch16() + self.y) & 0xFFFF
        if mode == "izx":
            z = (self.fetch() + self.x) & 0xFF
            return self.read(z) | self.read((z + 1) & 0xFF) << 8
        if mode == "izy":
            z = self.fetch()
            return ((self.read(z) | self.read((z + 1) & 0xFF) << 8) + self.y) & 0xFFFF
        raise ValueError(mode)

    def adc(self, m):
        t = self.a + m + self.c
        self.v = int(((self.a ^ t) & (m ^ t) & 0x80) != 0)
        self.c = int(t > 0xFF)
        self.a = self.nz(t)

    def cmp(self, r, m):
        t = (r - m) & 0x1FF
        self.c = int(r >= m); self.nz(t)

    def branch(self, cond):
        off = self.fetch()
        if cond:
            self.pc = (self.pc + (off - 256 if off & 0x80 else off)) & 0xFFFF

    def step(self):
        op = self.fetch()
        self.cycles += 1
        e = OPS.get(op)
        if e is None:
            raise RuntimeError(f"unknown opcode ${op:02X} at ${(self.pc - 1) & 0xFFFF:04X}")
        name, mode = e
        getattr(self, "op_" + name)(mode)

    def nmi_frame(self, entry=0xA669, limit=2_000_000):
        """Run the game's per-frame engine as the NMI would: A, X, Y and a return frame on the stack."""
        c = self
        c.push(0xFF); c.push(0xFE); c.push(c.flags())      # RTI returns to $FFFF (sentinel... -1 handled)
        c.push(0); c.push(0); c.push(0)                      # A, X, Y it pulls back
        c.pc = entry
        for _ in range(limit):
            if c.pc in (0xFFFE, 0xFFFF):
                return
            c.step()
        raise RuntimeError("the frame didn't end")

    def call(self, addr, limit=2_000_000):
        """JSR addr and run until it returns (a sentinel return address on the stack)."""
        self.push(0xFF); self.push(0xFE)          # returns to $FFFF
        self.pc = addr
        for _ in range(limit):
            if self.pc == 0xFFFF:
                return
            self.step()
        raise RuntimeError(f"routine ${addr:04X} didn't return")

    # ---- instructions ----
    def op_lda(self, m): self.a = self.nz(self.read(self.addr(m)))
    def op_ldx(self, m): self.x = self.nz(self.read(self.addr(m)))
    def op_ldy(self, m): self.y = self.nz(self.read(self.addr(m)))
    def op_sta(self, m): self.write(self.addr(m), self.a)
    def op_stx(self, m): self.write(self.addr(m), self.x)
    def op_sty(self, m): self.write(self.addr(m), self.y)
    def op_tax(self, m): self.x = self.nz(self.a)
    def op_tay(self, m): self.y = self.nz(self.a)
    def op_txa(self, m): self.a = self.nz(self.x)
    def op_tya(self, m): self.a = self.nz(self.y)
    def op_tsx(self, m): self.x = self.nz(self.sp)
    def op_txs(self, m): self.sp = self.x
    def op_pha(self, m): self.push(self.a)
    def op_php(self, m): self.push(self.flags())
    def op_pla(self, m): self.a = self.nz(self.pull())
    def op_plp(self, m): self.set_flags(self.pull())
    def op_and(self, m): self.a = self.nz(self.a & self.read(self.addr(m)))
    def op_ora(self, m): self.a = self.nz(self.a | self.read(self.addr(m)))
    def op_eor(self, m): self.a = self.nz(self.a ^ self.read(self.addr(m)))
    def op_adc(self, m): self.adc(self.read(self.addr(m)))
    def op_sbc(self, m): self.adc(self.read(self.addr(m)) ^ 0xFF)
    def op_cmp(self, m): self.cmp(self.a, self.read(self.addr(m)))
    def op_cpx(self, m): self.cmp(self.x, self.read(self.addr(m)))
    def op_cpy(self, m): self.cmp(self.y, self.read(self.addr(m)))
    def op_bit(self, m):
        v = self.read(self.addr(m)); self.z = int((self.a & v) == 0); self.n = v >> 7; self.v = v >> 6 & 1

    def _rmw(self, m, f):
        if m == "acc":
            self.a = self.nz(f(self.a))
        else:
            a = self.addr(m); self.write(a, self.nz(f(self.read(a))))

    def op_asl(self, m):
        def f(v): self.c = v >> 7; return (v << 1) & 0xFF
        self._rmw(m, f)

    def op_lsr(self, m):
        def f(v): self.c = v & 1; return v >> 1
        self._rmw(m, f)

    def op_rol(self, m):
        def f(v): c = self.c; self.c = v >> 7; return ((v << 1) | c) & 0xFF
        self._rmw(m, f)

    def op_ror(self, m):
        def f(v): c = self.c; self.c = v & 1; return (v >> 1) | c << 7
        self._rmw(m, f)

    def op_inc(self, m): self._rmw(m, lambda v: (v + 1) & 0xFF)
    def op_dec(self, m): self._rmw(m, lambda v: (v - 1) & 0xFF)
    def op_inx(self, m): self.x = self.nz(self.x + 1)
    def op_iny(self, m): self.y = self.nz(self.y + 1)
    def op_dex(self, m): self.x = self.nz(self.x - 1)
    def op_dey(self, m): self.y = self.nz(self.y - 1)
    def op_clc(self, m): self.c = 0
    def op_sec(self, m): self.c = 1
    def op_cli(self, m): self.i = 0
    def op_sei(self, m): self.i = 1
    def op_cld(self, m): self.d = 0
    def op_sed(self, m): self.d = 1
    def op_clv(self, m): self.v = 0
    def op_nop(self, m): pass
    def op_bpl(self, m): self.branch(not self.n)
    def op_bmi(self, m): self.branch(self.n)
    def op_bvc(self, m): self.branch(not self.v)
    def op_bvs(self, m): self.branch(self.v)
    def op_bcc(self, m): self.branch(not self.c)
    def op_bcs(self, m): self.branch(self.c)
    def op_bne(self, m): self.branch(not self.z)
    def op_beq(self, m): self.branch(self.z)
    def op_jmp(self, m):
        self.pc = self.fetch16() if m == "abs" else self.r16bug(self.fetch16())
    def op_jsr(self, m):
        t = self.fetch16(); r = (self.pc - 1) & 0xFFFF
        self.push(r >> 8); self.push(r); self.pc = t
    def op_rts(self, m):
        lo = self.pull(); hi = self.pull(); self.pc = ((hi << 8 | lo) + 1) & 0xFFFF
    def op_rti(self, m):
        self.set_flags(self.pull()); lo = self.pull(); hi = self.pull(); self.pc = hi << 8 | lo
    def op_brk(self, m):
        raise RuntimeError(f"BRK at ${(self.pc - 1) & 0xFFFF:04X}")


OPS = {}
def _ops(name, table):
    for op, mode in table.items():
        OPS[op] = (name, mode)

_ops("lda", {0xA9: "imm", 0xA5: "zp", 0xB5: "zpx", 0xAD: "abs", 0xBD: "abx", 0xB9: "aby", 0xA1: "izx", 0xB1: "izy"})
_ops("ldx", {0xA2: "imm", 0xA6: "zp", 0xB6: "zpy", 0xAE: "abs", 0xBE: "aby"})
_ops("ldy", {0xA0: "imm", 0xA4: "zp", 0xB4: "zpx", 0xAC: "abs", 0xBC: "abx"})
_ops("sta", {0x85: "zp", 0x95: "zpx", 0x8D: "abs", 0x9D: "abx", 0x99: "aby", 0x81: "izx", 0x91: "izy"})
_ops("stx", {0x86: "zp", 0x96: "zpy", 0x8E: "abs"})
_ops("sty", {0x84: "zp", 0x94: "zpx", 0x8C: "abs"})
for n, op in (("tax", 0xAA), ("tay", 0xA8), ("txa", 0x8A), ("tya", 0x98), ("tsx", 0xBA), ("txs", 0x9A),
              ("pha", 0x48), ("php", 0x08), ("pla", 0x68), ("plp", 0x28), ("inx", 0xE8), ("iny", 0xC8),
              ("dex", 0xCA), ("dey", 0x88), ("clc", 0x18), ("sec", 0x38), ("cli", 0x58), ("sei", 0x78),
              ("cld", 0xD8), ("sed", 0xF8), ("clv", 0xB8), ("nop", 0xEA), ("rts", 0x60), ("rti", 0x40), ("brk", 0x00)):
    OPS[op] = (n, None)
for n, base in (("ora", 0x00), ("and", 0x20), ("eor", 0x40), ("adc", 0x60), ("cmp", 0xC0), ("sbc", 0xE0)):
    _ops(n, {base | 0x09: "imm", base | 0x05: "zp", base | 0x15: "zpx", base | 0x0D: "abs", base | 0x1D: "abx",
             base | 0x19: "aby", base | 0x01: "izx", base | 0x11: "izy"})
_ops("cpx", {0xE0: "imm", 0xE4: "zp", 0xEC: "abs"})
_ops("cpy", {0xC0: "imm", 0xC4: "zp", 0xCC: "abs"})
_ops("bit", {0x24: "zp", 0x2C: "abs"})
for n, base in (("asl", 0x00), ("rol", 0x20), ("lsr", 0x40), ("ror", 0x60)):
    _ops(n, {base | 0x0A: "acc", base | 0x06: "zp", base | 0x16: "zpx", base | 0x0E: "abs", base | 0x1E: "abx"})
_ops("inc", {0xE6: "zp", 0xF6: "zpx", 0xEE: "abs", 0xFE: "abx"})
_ops("dec", {0xC6: "zp", 0xD6: "zpx", 0xCE: "abs", 0xDE: "abx"})
_ops("jmp", {0x4C: "abs", 0x6C: "ind"})
_ops("jsr", {0x20: "abs"})
for n, op in (("bpl", 0x10), ("bmi", 0x30), ("bvc", 0x50), ("bvs", 0x70), ("bcc", 0x90), ("bcs", 0xB0),
              ("bne", 0xD0), ("beq", 0xF0)):
    OPS[op] = (n, "rel")


class Nes:
    """RAM plus the Punch-Out!! PRG banks: bank `prg` at $8000, the fixed DEF banks at $A000-$FFFF."""

    def __init__(self, disasm, prg=0):
        import pathlib
        d = pathlib.Path(disasm) / "original_files"
        self.dir = d
        self.banks = {}
        self.ram = bytearray(0x800)
        self.lo = self.bank(prg)
        self.hi = (d / "PRG_BankDEF.bin").read_bytes()
        self.ppu_writes, self.mapper_writes = [], []
        self.apu, self.apu_new, self.apu_reload = bytearray(0x18), bytearray(5), bytearray(2)
        self.buttons = 0                # the controller: A $80, B $40, select $20, start $10, U D L R
        self._shift = 0
        self.watch = None               # optional: called on every RAM write (addr, value, cpu)
        self.cpu = CPU(self.read, self.write)

    def bank(self, n):
        """PRG bank n (8 KB) as mapped at $8000."""
        if n not in self.banks:
            self.banks[n] = (self.dir / f"PRG_Bank{n:03X}.bin").read_bytes()
        return self.banks[n]

    def read(self, a):
        if a < 0x2000: return self.ram[a & 0x7FF]
        if a == 0x4016:                 # controller 1, a bit at a time (A first)
            v = (self._shift >> 7) & 1
            self._shift = (self._shift << 1) & 0xFF
            return v
        if a < 0x8000: return 0
        if a < 0xA000: return self.lo[a - 0x8000]
        return self.hi[a - 0xA000]

    def write(self, a, v):
        if a < 0x2000:
            if self.watch: self.watch(a & 0x7FF, v & 0xFF, self.cpu)
            self.ram[a & 0x7FF] = v & 0xFF
        elif a == 0x4016:
            self._shift = self.buttons      # strobe: latch the buttons
        elif 0x4000 <= a < 0x4018:          # the sound registers: as last written, and the writes that start things
            self.apu[a - 0x4000] = v & 0xFF
            if a in (0x4003, 0x4007, 0x400B, 0x400F, 0x4015):
                self.apu_new[{0x4003: 0, 0x4007: 1, 0x400B: 2, 0x400F: 3, 0x4015: 4}[a]] = v & 0xFF
            if a in (0x4001, 0x4005):
                self.apu_reload[(a >> 2) & 1] = v & 0xFF
        elif a < 0x4020: pass               # PPU: not modeled
        elif 0xA000 <= a < 0xB000: self.lo = self.bank(v & 0x0F)   # the PRG bank at $8000 ($AFFF)
        elif a >= 0x8000: self.mapper_writes.append((a, v))
