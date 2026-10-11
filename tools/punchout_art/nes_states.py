"""Glass Joe's state scripts from the NES game, decoded into steps (from the disassembly cloned at
~/code/mike-tysons-punch-out-disassembly: PRG bank 0 holds his data; the interpreter is OppStateUpdate in
bank DEF). Used to give the Game Boy fight Joe's real timing and movement.

    python3 tools/punchout_art/nes_states.py     # print every state's steps
"""
from pathlib import Path

import gamefiles
DISASM = gamefiles.root()
BANK = DISASM / "original_files" / "PRG_Bank000.bin"       # mapped at $8000
STATE_TABLE = 0x8AEF                                        # Glass Joe's state pointers
STATE_NAMES = ["-", "wait", "face_punch_left", "dodge_right", "dodge_right_b", "face_block", "face_block_b",
               "stomach_block", "stomach_block_b", "face_guard", "face_guard_b", "stomach_guard", "stomach_guard_b",
               "face_hit_left1", "face_hit_right1", "gut_hit_left1", "gut_hit_right1", "face_hit_left2",
               "face_hit_right2", "gut_hit_left2", "gut_hit_right2", "right_hook", "straight_punch", "-", "-",
               "taunt"]


def nib(v):
    return v - 16 if v & 8 else v


def move(b):
    """A movement byte: upper nibble x, lower nibble y, each signed (UpdateMemPair)."""
    return nib(b >> 4), nib(b & 15)


class Rom:
    def __init__(self):
        self.d = BANK.read_bytes()

    def b(self, addr):
        return self.d[addr - 0x8000]

    def w(self, addr):
        return self.b(addr) | self.b(addr + 1) << 8


def decode(rom, base, limit=400):
    """[(index, op, args)] for the state at base, read straight through (branches listed, not taken)."""
    out, i = [], 0
    while i < limit:
        op = rom.b(base + i); start = i; i += 1
        hi, lo = op >> 4, op & 15
        def take(n):
            nonlocal i
            v = [rom.b(base + i + k) for k in range(n)]; i += n; return v
        def skip_zero():
            nonlocal i
            if rom.b(base + i) == 0: i += 1
        if hi in (0, 4):
            (f,) = take(1); out.append((start, "frame", dict(frames=lo, pose=f))); skip_zero()
        elif hi in (1, 5):
            f, x, y = take(3); out.append((start, "frame_at", dict(frames=lo, pose=f, x=x, y=y)))
        elif hi == 2:
            x, y = take(2); out.append((start, "at", dict(frames=lo, x=x, y=y)))
        elif hi == 3:
            (t,) = take(1); out.append((start, "cond", dict(test=lo, to=t)))
        elif hi == 6:
            (m,) = take(1); out.append((start, "move", dict(frames=lo, dx=move(m)[0], dy=move(m)[1]))); skip_zero()
        elif hi == 7:
            (m,) = take(1); dx, dy = move(m)
            out.append((start, "moves", dict(every=(lo & 3) + 1, times=(lo >> 2) + 1, dx=dx, dy=dy))); skip_zero()
        elif hi == 8:
            (t,) = take(1); out.append((start, "wait", dict(frames=t)))
        elif hi == 9:
            v = take(2 + lo); out.append((start, "poke", dict(n=lo, data=v)))
        elif hi == 0xA:
            (t,) = take(1); out.append((start, "bigmove", dict(frames=lo, to=t)))
        elif hi in (0xB, 0xC, 0xD, 0xE):
            if lo == 0: (a, h) = take(2); out.append((start, "call", dict(addr=a | h << 8)))
            elif lo == 1: out.append((start, "return", {}))
            elif lo == 4: out.append((start, "var_time", {}))
            elif lo == 5: out.append((start, "not_punching", {}))
            elif lo in (6, 7): out.append((start, f"ppu{lo}", {}))
            elif lo == 8: v = take(4); out.append((start, "cond16", dict(data=v)))
            elif lo == 9: v = take(1); out.append((start, "clock", dict(data=v)))
            elif lo == 0xC: (s,) = take(1); out.append((start, "sound", dict(id=s)))
            else: out.append((start, f"?{op:02X}", {}))
        else:   # 0xF
            if lo == 0: v = take(3); out.append((start, "punch_active", dict(blocked=v[0], ducked=v[1], dodged=v[2])))
            elif lo == 1: a, h, t = take(3); out.append((start, "jump", dict(addr=a | h << 8, to=t))); break
            elif lo == 2: a, v, t = take(3); out.append((start, "if", dict(addr=a, eq=v, to=t)))
            elif lo == 3: (t,) = take(1); out.append((start, "repeat_to", dict(to=t)))
            elif lo == 4: out.append((start, "to_wait", {})); break
            elif lo == 5: (n,) = take(1); out.append((start, "repeat", dict(n=n)))
            elif lo == 6: s, dmg = take(2); out.append((start, "punch_side", dict(side=s, damage=dmg))); skip_zero()
            elif lo == 7: v = take(4); out.append((start, "defense", dict(face=v[:2], gut=v[2:]))); skip_zero()
            elif lo == 9: out.append((start, "punching", {}))
            elif lo == 0xA: a, v = take(2); out.append((start, "set", dict(addr=a, value=v))); skip_zero()
            elif lo == 0xB: out.append((start, "combo_timer", {}))
            elif lo == 0xC: out.append((start, "combo_wait", {}))
            elif lo == 0xD: (v,) = take(1); out.append((start, "set5A", dict(v=v)))
            elif lo == 0xE: out.append((start, "state82", {})); break
            elif lo == 0xF: out.append((start, "end", {})); break
            else: out.append((start, f"?{op:02X}", {}))
    return out


def states(rom=None):
    rom = rom or Rom()
    out = {}
    for k, name in enumerate(STATE_NAMES):
        p = rom.w(STATE_TABLE + 2 * k)
        if name != "-" and p:
            out[name] = (p, decode(rom, p))
    return out


if __name__ == "__main__":
    for name, (addr, steps) in states().items():
        print(f"\n== {name} (${addr:04X})")
        for i, op, a in steps:
            print(f"  {i:02X} {op:13} " + " ".join(f"{k}={v:#04x}" if k in ("pose", "addr", "to") and isinstance(v, int) else f"{k}={v}" for k, v in a.items()))


# ---- the AI: round timeline and AI scripts (bank DEF $B069 and $B196) ----

TIMELINE = 0x940E          # per fight: at clock values, set AI mode / copy AI tables into $0500
AI_TABLES = 0x9452         # pointers to the data blocks the timeline copies


def decode_timeline(rom, base=TIMELINE, n=80):
    out, i = [], 0
    while i < n:
        t = rom.b(base + i); i += 1
        when = None
        if t < 0xD0:
            when = t
            op = rom.b(base + i); i += 1
        else:
            op = t
        while True:
            if op < 0xE0:
                act = ("ai_mode", op & 0x87)
            elif op == 0xE0:
                act = ("nop",)
            elif op < 0xF0:
                k = op & 15; a = rom.w(base + i); i += 2
                act = ("poke", a, [rom.b(base + i + j) for j in range(k)]); i += k
            elif op == 0xFF:
                x, cnt, idx = rom.b(base + i), rom.b(base + i + 1), rom.b(base + i + 2); i += 3
                act = ("copy", f"$05{x:02X}", cnt, f"${rom.w(AI_TABLES + idx):04X}")
            elif op in (0xFE, 0xFD):
                k = 1 if op == 0xFE else 2; v = []
                for _ in range(k): v.append((f"$05{rom.b(base + i):02X}", rom.b(base + i + 1))); i += 2
                act = ("set", v)
            else:
                act = (f"?{op:02X}",)
            out.append((when, act))
            nxt = rom.b(base + i)
            if nxt != 0: break
            i += 1; op = rom.b(base + i); i += 1
    return out


def decode_ai(rom, base, n=64):
    """An AI script: which state Joe goes into next, and when (while he waits)."""
    out, i = [], 0
    while i < n:
        op = rom.b(base + i); at = i; i += 1
        lo = op & 15
        if op < 0x10:
            out.append((at, "state", dict(delay=lo, state=STATE_NAMES[rom.b(base + i)] if rom.b(base + i) < len(STATE_NAMES) else rom.b(base + i)))); i += 1
        elif op < 0x20:
            out.append((at, "chance_jump", dict(chance=f"{lo}/16" if lo < 15 else "always", to=rom.b(base + i)))); i += 1
        elif op < 0x30:
            out.append((at, "random_state", dict(delay=lo, states=[STATE_NAMES[rom.b(base + i + k)] if rom.b(base + i + k) < len(STATE_NAMES) else rom.b(base + i + k) for k in range(8)]))); i += 8
        elif 0x80 <= op < 0x90:
            if lo == 0: out.append((at, "delay", dict(n=rom.b(base + i)))); i += 1
            elif lo == 1: out.append((at, "delay_random", dict(a=rom.b(base + i), b=rom.b(base + i + 1)))); i += 2
            else: out.append((at, "delay", dict(n=lo * 4)))
        elif 0x90 <= op < 0xF0:
            k = lo; a = rom.w(base + i); out.append((at, "poke", dict(addr=f"${a:04X}", data=[rom.b(base + i + 2 + j) for j in range(k)]))); i += 2 + k
        elif op == 0xF0: out.append((at, "mode_back", {}))
        elif op == 0xF1: out.append((at, "clear36", {}))
        elif op == 0xF2: out.append((at, "if_mem", dict(addr=rom.b(base + i), eq=rom.b(base + i + 1), to=rom.b(base + i + 2)))); i += 3
        elif op == 0xF3: out.append((at, "loop_n", dict(n=rom.b(base + i)))); i += 1
        elif op == 0xF4: out.append((at, "loop_to", dict(to=rom.b(base + i)))); i += 1
        else: out.append((at, f"?{op:02X}", {})); break
    return out
