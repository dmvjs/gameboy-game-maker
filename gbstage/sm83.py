"""Game Boy CPU (SM83) interpreter with exact instruction timing, in T-cycles (4 per machine cycle).

Used by the profiler to measure generated code. It is deliberately small and strict: anything the
hardware model doesn't cover raises Unsupported instead of producing a number that might be wrong.
"""

Z, N, H, C = 0x80, 0x40, 0x20, 0x10
B_, C_, D_, E_, H_, L_, HL_, A_ = range(8)


class Unsupported(Exception):
    """The program used something the profiler doesn't model, so its measurements can't be trusted."""


class CPU:
    def __init__(self, bus):
        self.bus = bus
        self.r = [0] * 8          # B C D E H L (unused) A
        self.f = 0
        self.sp = 0xFFFE
        self.pc = 0x0100
        self.ime = False
        self.ime_pending = False  # EI takes effect after the next instruction
        self.halted = False
        self.halt_bug = False
        self.ops = self._build_ops()
        self.cb_ops = self._build_cb_ops()

    # ---- register pairs ----------------------------------------------------

    def bc(self): return self.r[B_] << 8 | self.r[C_]
    def de(self): return self.r[D_] << 8 | self.r[E_]
    def hl(self): return self.r[H_] << 8 | self.r[L_]

    def set_bc(self, v): self.r[B_] = v >> 8 & 0xFF; self.r[C_] = v & 0xFF
    def set_de(self, v): self.r[D_] = v >> 8 & 0xFF; self.r[E_] = v & 0xFF
    def set_hl(self, v): self.r[H_] = v >> 8 & 0xFF; self.r[L_] = v & 0xFF

    def af(self): return self.r[A_] << 8 | self.f
    def set_af(self, v): self.r[A_] = v >> 8 & 0xFF; self.f = v & 0xF0

    # ---- fetch helpers -----------------------------------------------------

    def fetch8(self):
        v = self.bus.read(self.pc)
        if self.halt_bug:
            self.halt_bug = False     # HALT bug: the byte after HALT is read twice
        else:
            self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch8()
        return self.fetch8() << 8 | lo

    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self.bus.write(self.sp, v >> 8 & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self.bus.write(self.sp, v & 0xFF)

    def pop(self):
        lo = self.bus.read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        hi = self.bus.read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return hi << 8 | lo

    def get_r(self, i):
        return self.bus.read(self.hl()) if i == HL_ else self.r[i]

    def set_r(self, i, v):
        if i == HL_:
            self.bus.write(self.hl(), v)
        else:
            self.r[i] = v

    def cond(self, cc):
        f = self.f
        return (not f & Z, bool(f & Z), not f & C, bool(f & C))[cc]

    # ---- ALU ---------------------------------------------------------------

    def alu(self, op, v):
        a = self.r[A_]
        if op in (0, 1):            # ADD, ADC
            c = 1 if op == 1 and self.f & C else 0
            res = a + v + c
            self.f = (0 if res & 0xFF else Z) | (H if (a & 0xF) + (v & 0xF) + c > 0xF else 0) | (C if res > 0xFF else 0)
            self.r[A_] = res & 0xFF
        elif op in (2, 3, 7):       # SUB, SBC, CP
            c = 1 if op == 3 and self.f & C else 0
            res = a - v - c
            self.f = N | (0 if res & 0xFF else Z) | (H if (a & 0xF) - (v & 0xF) - c < 0 else 0) | (C if res < 0 else 0)
            if op != 7:
                self.r[A_] = res & 0xFF
        elif op == 4:               # AND
            a &= v
            self.r[A_] = a
            self.f = (0 if a else Z) | H
        elif op == 5:               # XOR
            a ^= v
            self.r[A_] = a
            self.f = 0 if a else Z
        else:                       # OR
            a |= v
            self.r[A_] = a
            self.f = 0 if a else Z

    def inc8(self, v):
        res = (v + 1) & 0xFF
        self.f = (self.f & C) | (0 if res else Z) | (H if (v & 0xF) == 0xF else 0)
        return res

    def dec8(self, v):
        res = (v - 1) & 0xFF
        self.f = (self.f & C) | N | (0 if res else Z) | (H if (v & 0xF) == 0 else 0)
        return res

    def add_sp_e8(self):
        e = self.fetch8()
        sp = self.sp
        self.f = (H if (sp & 0xF) + (e & 0xF) > 0xF else 0) | (C if (sp & 0xFF) + e > 0xFF else 0)
        return (sp + (e - 256 if e > 127 else e)) & 0xFFFF

    def daa(self):
        a, f = self.r[A_], self.f
        if not f & N:
            if f & C or a > 0x99:
                a += 0x60
                f |= C
            if f & H or (a & 0x0F) > 0x09:
                a += 0x06
        else:
            if f & C:
                a -= 0x60
            if f & H:
                a -= 0x06
        a &= 0xFF
        self.r[A_] = a
        self.f = (f & (N | C)) | (0 if a else Z)

    # ---- opcode tables -----------------------------------------------------

    def _build_ops(self):
        ops = [None] * 256
        cpu = self
        r = self.r
        bus = self.bus

        def op(code):
            def deco(fn):
                ops[code] = fn
                return fn
            return deco

        @op(0x00)
        def nop(): return 4

        # 16-bit loads / arithmetic on BC, DE, HL, SP
        getters = [self.bc, self.de, self.hl, lambda: cpu.sp]
        setters = [self.set_bc, self.set_de, self.set_hl, lambda v: setattr(cpu, 'sp', v)]
        for i in range(4):
            g, s = getters[i], setters[i]
            ops[0x01 + i * 16] = (lambda s: lambda: (s(cpu.fetch16()), 12)[1])(s)
            ops[0x03 + i * 16] = (lambda g, s: lambda: (s((g() + 1) & 0xFFFF), 8)[1])(g, s)
            ops[0x0B + i * 16] = (lambda g, s: lambda: (s((g() - 1) & 0xFFFF), 8)[1])(g, s)

            def add_hl(g=g):
                hl, v = cpu.hl(), g()
                res = hl + v
                cpu.f = (cpu.f & Z) | (H if (hl & 0xFFF) + (v & 0xFFF) > 0xFFF else 0) | (C if res > 0xFFFF else 0)
                cpu.set_hl(res & 0xFFFF)
                return 8
            ops[0x09 + i * 16] = add_hl

        # LD (rr),A and LD A,(rr) including HL+ / HL-
        def ld_ind_a(addr_fn, after=None):
            def fn():
                addr = addr_fn()
                bus.write(addr, r[A_])
                if after: after(addr)
                return 8
            return fn

        def ld_a_ind(addr_fn, after=None):
            def fn():
                addr = addr_fn()
                r[A_] = bus.read(addr)
                if after: after(addr)
                return 8
            return fn

        inc_hl = lambda a: cpu.set_hl((a + 1) & 0xFFFF)
        dec_hl = lambda a: cpu.set_hl((a - 1) & 0xFFFF)
        ops[0x02] = ld_ind_a(self.bc)
        ops[0x12] = ld_ind_a(self.de)
        ops[0x22] = ld_ind_a(self.hl, inc_hl)
        ops[0x32] = ld_ind_a(self.hl, dec_hl)
        ops[0x0A] = ld_a_ind(self.bc)
        ops[0x1A] = ld_a_ind(self.de)
        ops[0x2A] = ld_a_ind(self.hl, inc_hl)
        ops[0x3A] = ld_a_ind(self.hl, dec_hl)

        # INC/DEC r, LD r,d8
        for i in range(8):
            if i == HL_:
                ops[0x34] = lambda: (bus.write(cpu.hl(), cpu.inc8(bus.read(cpu.hl()))), 12)[1]
                ops[0x35] = lambda: (bus.write(cpu.hl(), cpu.dec8(bus.read(cpu.hl()))), 12)[1]
                ops[0x36] = lambda: (bus.write(cpu.hl(), cpu.fetch8()), 12)[1]
            else:
                ops[0x04 + i * 8] = (lambda i: lambda: (r.__setitem__(i, cpu.inc8(r[i])), 4)[1])(i)
                ops[0x05 + i * 8] = (lambda i: lambda: (r.__setitem__(i, cpu.dec8(r[i])), 4)[1])(i)
                ops[0x06 + i * 8] = (lambda i: lambda: (r.__setitem__(i, cpu.fetch8()), 8)[1])(i)

        # Rotates on A
        @op(0x07)
        def rlca():
            a = r[A_]; c = a >> 7
            r[A_] = (a << 1 | c) & 0xFF; cpu.f = C if c else 0; return 4

        @op(0x0F)
        def rrca():
            a = r[A_]; c = a & 1
            r[A_] = (a >> 1 | c << 7) & 0xFF; cpu.f = C if c else 0; return 4

        @op(0x17)
        def rla():
            a = r[A_]; c = a >> 7
            r[A_] = (a << 1 | (1 if cpu.f & C else 0)) & 0xFF; cpu.f = C if c else 0; return 4

        @op(0x1F)
        def rra():
            a = r[A_]; c = a & 1
            r[A_] = (a >> 1 | (0x80 if cpu.f & C else 0)); cpu.f = C if c else 0; return 4

        @op(0x08)
        def ld_a16_sp():
            addr = cpu.fetch16()
            bus.write(addr, cpu.sp & 0xFF)
            bus.write((addr + 1) & 0xFFFF, cpu.sp >> 8)
            return 20

        @op(0x10)
        def stop():
            cpu.fetch8()
            raise Unsupported("STOP instruction (speed switching and low-power mode aren't modeled yet)")

        # Relative jumps
        def jr_body():
            e = cpu.fetch8()
            return e - 256 if e > 127 else e

        @op(0x18)
        def jr():
            e = jr_body(); cpu.pc = (cpu.pc + e) & 0xFFFF; return 12

        for cc in range(4):
            def jr_cc(cc=cc):
                e = jr_body()
                if cpu.cond(cc):
                    cpu.pc = (cpu.pc + e) & 0xFFFF
                    return 12
                return 8
            ops[0x20 + cc * 8] = jr_cc

        @op(0x27)
        def daa(): cpu.daa(); return 4

        @op(0x2F)
        def cpl(): r[A_] ^= 0xFF; cpu.f = (cpu.f & (Z | C)) | N | H; return 4

        @op(0x37)
        def scf(): cpu.f = (cpu.f & Z) | C; return 4

        @op(0x3F)
        def ccf(): cpu.f = (cpu.f & Z) | (0 if cpu.f & C else C); return 4

        # LD r,r' (0x40-0x7F) with HALT at 0x76
        for dst in range(8):
            for src in range(8):
                code = 0x40 + dst * 8 + src
                if code == 0x76:
                    continue
                if dst == HL_:
                    ops[code] = (lambda s: lambda: (bus.write(cpu.hl(), r[s]), 8)[1])(src)
                elif src == HL_:
                    ops[code] = (lambda d: lambda: (r.__setitem__(d, bus.read(cpu.hl())), 8)[1])(dst)
                else:
                    ops[code] = (lambda d, s: lambda: (r.__setitem__(d, r[s]), 4)[1])(dst, src)

        @op(0x76)
        def halt():
            if not cpu.ime and cpu.bus.pending_interrupts():
                cpu.halt_bug = True
            else:
                cpu.halted = True
            return 4

        # ALU A,r and ALU A,d8
        for o in range(8):
            for src in range(8):
                if src == HL_:
                    ops[0x80 + o * 8 + src] = (lambda o: lambda: (cpu.alu(o, bus.read(cpu.hl())), 8)[1])(o)
                else:
                    ops[0x80 + o * 8 + src] = (lambda o, s: lambda: (cpu.alu(o, r[s]), 4)[1])(o, src)
            ops[0xC6 + o * 8] = (lambda o: lambda: (cpu.alu(o, cpu.fetch8()), 8)[1])(o)

        # Calls, returns, jumps
        for cc in range(4):
            def ret_cc(cc=cc):
                if cpu.cond(cc):
                    cpu.pc = cpu.pop(); return 20
                return 8

            def jp_cc(cc=cc):
                addr = cpu.fetch16()
                if cpu.cond(cc):
                    cpu.pc = addr; return 16
                return 12

            def call_cc(cc=cc):
                addr = cpu.fetch16()
                if cpu.cond(cc):
                    cpu.push(cpu.pc); cpu.pc = addr; return 24
                return 12
            ops[0xC0 + cc * 8] = ret_cc
            ops[0xC2 + cc * 8] = jp_cc
            ops[0xC4 + cc * 8] = call_cc

        @op(0xC3)
        def jp(): cpu.pc = cpu.fetch16(); return 16

        @op(0xC9)
        def ret(): cpu.pc = cpu.pop(); return 16

        @op(0xD9)
        def reti(): cpu.pc = cpu.pop(); cpu.ime = True; return 16

        @op(0xCD)
        def call():
            addr = cpu.fetch16(); cpu.push(cpu.pc); cpu.pc = addr; return 24

        @op(0xE9)
        def jp_hl(): cpu.pc = cpu.hl(); return 4

        for n in range(8):
            ops[0xC7 + n * 8] = (lambda v: lambda: (cpu.push(cpu.pc), setattr(cpu, 'pc', v), 16)[2])(n * 8)

        # PUSH / POP
        pair_get = [self.bc, self.de, self.hl, self.af]
        pair_set = [self.set_bc, self.set_de, self.set_hl, self.set_af]
        for i in range(4):
            ops[0xC1 + i * 16] = (lambda s: lambda: (s(cpu.pop()), 12)[1])(pair_set[i])
            ops[0xC5 + i * 16] = (lambda g: lambda: (cpu.push(g()), 16)[1])(pair_get[i])

        @op(0xCB)
        def prefix():
            return cpu.cb_ops[cpu.fetch8()]()

        # High-page and absolute loads
        @op(0xE0)
        def ldh_a8_a(): bus.write(0xFF00 | cpu.fetch8(), r[A_]); return 12

        @op(0xF0)
        def ldh_a_a8(): r[A_] = bus.read(0xFF00 | cpu.fetch8()); return 12

        @op(0xE2)
        def ld_c_a(): bus.write(0xFF00 | r[C_], r[A_]); return 8

        @op(0xF2)
        def ld_a_c(): r[A_] = bus.read(0xFF00 | r[C_]); return 8

        @op(0xEA)
        def ld_a16_a(): bus.write(cpu.fetch16(), r[A_]); return 16

        @op(0xFA)
        def ld_a_a16(): r[A_] = bus.read(cpu.fetch16()); return 16

        @op(0xE8)
        def add_sp(): cpu.sp = cpu.add_sp_e8(); return 16

        @op(0xF8)
        def ld_hl_sp(): cpu.set_hl(cpu.add_sp_e8()); return 12

        @op(0xF9)
        def ld_sp_hl(): cpu.sp = cpu.hl(); return 8

        @op(0xF3)
        def di(): cpu.ime = False; cpu.ime_pending = False; return 4

        @op(0xFB)
        def ei(): cpu.ime_pending = True; return 4

        for code in (0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED, 0xF4, 0xFC, 0xFD):
            ops[code] = (lambda c: lambda: (_ for _ in ()).throw(
                Unsupported(f"illegal opcode ${c:02X} at ${(cpu.pc - 1) & 0xFFFF:04X} (it would lock up a real Game Boy)")))(code)
        assert all(ops), [hex(i) for i, o in enumerate(ops) if o is None]
        return ops

    def _build_cb_ops(self):
        cpu, r, bus = self, self.r, self.bus
        ops = [None] * 256

        def shift(kind, v):
            c = cpu.f & C
            if kind == 0: out = v >> 7; res = v << 1 | out             # RLC
            elif kind == 1: out = v & 1; res = v >> 1 | out << 7       # RRC
            elif kind == 2: out = v >> 7; res = v << 1 | (1 if c else 0)  # RL
            elif kind == 3: out = v & 1; res = v >> 1 | (0x80 if c else 0)  # RR
            elif kind == 4: out = v >> 7; res = v << 1                 # SLA
            elif kind == 5: out = v & 1; res = v >> 1 | (v & 0x80)     # SRA
            elif kind == 6: out = 0; res = (v << 4 | v >> 4)           # SWAP
            else: out = v & 1; res = v >> 1                           # SRL
            res &= 0xFF
            cpu.f = (0 if res else Z) | (C if out else 0)
            return res

        for code in range(256):
            group, reg = code >> 3, code & 7
            hl = reg == HL_
            if group < 8:
                def fn(kind=group, reg=reg, hl=hl):
                    cpu.set_r(reg, shift(kind, cpu.get_r(reg)))
                    return 16 if hl else 8
            elif group < 16:
                def fn(bit=group - 8, reg=reg, hl=hl):
                    v = cpu.get_r(reg)
                    cpu.f = (cpu.f & C) | H | (0 if v >> bit & 1 else Z)
                    return 12 if hl else 8
            elif group < 24:
                def fn(bit=group - 16, reg=reg, hl=hl):
                    cpu.set_r(reg, cpu.get_r(reg) & ~(1 << bit) & 0xFF)
                    return 16 if hl else 8
            else:
                def fn(bit=group - 24, reg=reg, hl=hl):
                    cpu.set_r(reg, cpu.get_r(reg) | 1 << bit)
                    return 16 if hl else 8
            ops[code] = fn
        return ops

    # ---- execution ---------------------------------------------------------

    def service_interrupts(self):
        """Dispatch a pending interrupt if allowed. Returns cycles used (0 if none)."""
        pending = self.bus.pending_interrupts()
        if not pending:
            return 0
        woke = 4 if self.halted else 0
        self.halted = False
        if not self.ime:
            return woke
        bit = (pending & -pending).bit_length() - 1
        self.bus.clear_interrupt(bit)
        self.ime = False
        self.push(self.pc)
        self.pc = 0x40 + bit * 8
        self.bus.on_interrupt(bit)
        return 20 + woke

    def step(self):
        """Run one instruction (or one idle HALT slice). Returns (cycles, pc_before, halted)."""
        cycles = self.service_interrupts()
        if self.halted:
            return 4, self.pc, True
        pc = self.pc
        enable = self.ime_pending
        cycles += self.ops[self.fetch8()]()
        if enable:
            self.ime_pending = False
            self.ime = True
        return cycles, pc, False
