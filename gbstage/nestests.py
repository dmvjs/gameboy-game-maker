"""NES opponent engine tests: the Game Boy port (kit_nes.asm) against the original NES routines.

Both run from the same RAM, with the same random numbers and the same inputs each frame: the NES game's
own code in a 6502 interpreter (tools/punchout_art/cpu6502.py, on the ROM banks from the disassembly)
and the port in the Game Boy machine. After every frame all of the NES RAM must match, byte for byte.
Needs the disassembly at ~/code/mike-tysons-punch-out-disassembly and the Joe vs Mac example.
"""

import json
import random
import re
import sys
from pathlib import Path

from . import codegen
from .build import build_rom
from .machine import Machine

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
DISASM = Path.home() / "code" / "mike-tysons-punch-out-disassembly"
SENTINEL = 0x0000
POINTER_HI = (0x32, 0x34, 0x3C, 0x95, 0x9F, 0x55, 0x7F)   # pointers into the NES banks: GB = NES - $4000
SKIP = set(range(0x00, 0x20)) | set(range(0xE0, 0xF0)) | set(range(0x100, 0x300)) | {0x4C9} \
    | set(range(0x480, 0x4B0)) | set(range(0x6A0, 0x6A9))   # system, scratch, stack, OAM; palette effects and
    # raw controller polls (not ported: the GB draws and reads its own)


def lfsr(s):
    s = s or 1
    s <<= 1
    if s > 0xFF:
        s = (s ^ 0x1D) & 0xFF
    return s


class Nes:
    """The NES routines, with $18 (its random byte) fed the Game Boy port's sequence."""

    def __init__(self):
        sys.path.insert(0, str(ROOT / "tools" / "punchout_art"))
        import cpu6502
        self.nes = cpu6502.Nes(DISASM, 0)
        hi = bytearray(self.nes.hi)
        # drawing: the Game Boy does its own. What's left is $C890's flags: his sprite changes taken
        # ($A0 = 0) and a sprite transfer asked of the vblank ($17 = 1).
        hi[0xC890 - 0xA000:0xC89D - 0xA000] = bytes.fromhex("A5A0F008A90085A0A9018517") + b"\x60"
        self.nes.hi = bytes(hi)
        self.rand = 0

    def call(self, addr, bank=None):
        if bank is not None:
            self.nes.lo = self.nes.bank(bank)
        cpu = self.nes.cpu
        cpu.push(0xFF); cpu.push(0xFE)
        cpu.pc = addr
        for _ in range(200_000):
            if cpu.pc == 0xFFFF:
                return
            if self.nes.read(cpu.pc) == 0xA5 and self.nes.read(cpu.pc + 1) == 0x18:   # LDA $18: the next random
                self.rand = lfsr(self.rand)
                self.nes.ram[0x18] = self.rand
            cpu.step()
        raise RuntimeError(f"NES ${addr:04X} didn't return")


class Gb:
    def __init__(self, project):
        build = build_rom(codegen.generate_asm(project), "TEST", cgb=True)
        self.sym = {}
        for line in build.sym.splitlines():
            m = re.match(r"([0-9a-fA-F]+):([0-9a-fA-F]{4}) (\S+)", line)
            if m:
                self.sym[m.group(3)] = (int(m.group(1), 16), int(m.group(2), 16))
        self.m = Machine(build.rom, True)
        self.wnes = self.sym["wNes"][1]
        self.m.write(0x2000, self.sym["NesFighter"][0])

    def call(self, name, a=None, bank=None):
        m, cpu = self.m, self.m.cpu
        if bank:
            m.write(0x2000, self.sym[bank][0])
        if a is not None:
            self.set_a(a)
        cpu.sp = 0xDFF0
        m.write(0xDFEE, SENTINEL & 0xFF); m.write(0xDFEF, SENTINEL >> 8)
        cpu.sp = 0xDFEE
        cpu.pc = self.sym[name][1]
        for _ in range(500_000):
            if cpu.pc == SENTINEL:
                return
            m.step()
        raise RuntimeError(f"GB {name} didn't return")

    def set_a(self, a):
        # sm83 keeps A in r[7] (b c d e h l - a order); see sm83.py
        self.m.cpu.r[7] = a

    def ram(self, addr):
        return self.m.read(self.wnes + addr)

    def poke(self, addr, v):
        self.m.write(self.wnes + addr, v)


ROUTINES = [(0xB069, "NesTimeline"), (0xB10A, "NesAiMode"), (0xC291, "NesGuard"), (0xB196, "NesAi"), (0xC4E7, "NesOppTick")]


def run(log=print):
    """Each ending the NES frame reaches, both machines byte for byte all the way."""
    return all([
        scenario(log, "Mac busy: punching, dodging, aiming", frames=6000, seed=7, busy=True),
        full(log, "Mac fights: Joe down and up, then out on the third (TKO)", 14000, 3, low=True),
        full(log, "Mac stands there: down, counted out", 14000, 2),
        full(log, "Mac gets up by mashing: down three times (TKO)", 14000, 3, idle=True, style="mash"),
        full(log, "Mac defends: three rounds to the final bell", 14000, 1, style="defend"),
        sound(log, "the sound engine: effects, music and samples at random", 6000, 2),
    ])


# NES RAM the Game Boy doesn't keep: its drawing (OAM, PPU update buffers, palettes, the crowd's palette
# animation at $41-$47), its sound engine's ($F0-$FF, $0700+), and display copies of the numbers.
NES_ONLY = (set(range(0x00, 0x17)) | set(range(0x18, 0x1E)) | set(range(0x1F, 0x20)) | set(range(0x41, 0x48)) | set(range(0x61, 0x6A)) | set(range(0x80, 0x83))
            | set(range(0xE0, 0x100)) | set(range(0x100, 0x300)) | set(range(0x0303, 0x0304))
            | set(range(0x030B, 0x0310)) | set(range(0x0326, 0x0328)) | set(range(0x0344, 0x0349)) | set(range(0x034A, 0x034B))
            | set(range(0x0395, 0x0397)) | set(range(0x039C, 0x039E)) | set(range(0x03F1, 0x0400))
            | set(range(0x0400, 0x04C8)) | set(range(0x04C9, 0x04CA)) | set(range(0x06A0, 0x06A9))
            | set(range(0x0730, 0x0800)))


def vblank(ram):
    """The NMI's part before the engine ($A5C3), as far as RAM goes: two transfers (sprites $17, Mac's
    new pose $60 = 1), then if one's left, the HUD part for the frame count's turn ($A61A); the count."""
    budget = 2
    if ram[0x17]:
        ram[0x17] = 0; budget -= 1
    if ram[0x60] == 1:
        ram[0x60] = 0; budget -= 1
    if budget:
        for a in {0: (0x0325, 0x0349), 1: (0x03F0,), 2: (0x030A,), 3: (0x0394, 0x039B)}[ram[0x1E] & 3]:
            if ram[a] & 0x80:
                ram[a] = 0
    ram[0x1E] = (ram[0x1E] + 1) & 0xFF


def full(log, title, frames, seed, low=False, idle=False, style=None):
    """The Game Boy's NesEngineFrame against the NES game's own frame ($A669, as its NMI runs it)."""
    if not DISASM.exists():
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    gb, nes = Gb(project), Nes()
    gb.call("NesFightStart", bank="NesFighter")
    gb.call("NesRoundStart", 1, bank="NesFighter")
    ram = nes.nes.ram
    for a in range(0x800):
        v = gb.ram(a)
        ram[a] = (v + 0x40) & 0xFF if a in POINTER_HI and v else v
    ram[0x02] = 0; ram[0x03] = 0; ram[0x04] = 0xFF
    rng = random.Random(seed)
    nes.rand = rng.randrange(1, 256)
    held, hold = 0, 0
    crowd = random.Random(seed + 1)
    failures, seen, macs, events = [], set(), set(), []
    last = (0, 0)
    for frame in range(frames):
        if hold == 0:
            held = rng.choice([0, 0, 0, 0x80, 0x40, 0x88, 0x48, 0x01, 0x02, 0x04, 0x80, 0x40, 0x10])
            if idle and rng.random() < 0.95:    # Mac stands there: Joe's punches land, the clock runs
                held = 0
            if style == "defend":               # blocks and dodges only: the rounds go the distance
                held = rng.choice([0, 0x04, 0x02, 0x01, 0x04, 0])
            hold = rng.randrange(1, 25)
        if style in ("mash", "defend") and ram[0x05] == 0 and ram[0x03B1] < 40:
            ram[0x03B1] = 40; gb.poke(0x03B1, 40)   # he's landed enough to be allowed up
        if style in ("mash", "defend") and ram[0x05] == 2:  # down: mash to get up
            held = 0x80 if frame & 2 else 0
        hold -= 1
        if style == "defend" and ram[0x05] == 0:    # Mac can't be hurt: the round runs out
            if 0 < ram[0x0391] < 0x60:
                ram[0x0391] = 0x60; gb.poke(0x0391, 0x60)
        if low and ram[0x05] == 0:
            for a in (0x0398, 0x0399):
                if ram[a] > 3:
                    ram[a] = 3; gb.poke(a, 3)
        for k in range(0, 8, 2):
            ram[0x6A0 + k] = held
        gb.poke(0xD0, held)
        gb.m.write(gb.sym["wNesRand"][1], nes.rand)
        nes.nes.lo = nes.nes.bank(7); ram[0x0D] = 7
        vblank(ram)
        cpu = nes.nes.cpu
        cpu.push(0xFF); cpu.push(0xFE); cpu.push(cpu.flags()); cpu.push(0); cpu.push(0); cpu.push(0)
        cpu.pc = 0xA669
        cheer = None                        # the stack depth while the crowd ($8A6F) runs
        for _ in range(400_000):
            if cpu.pc in (0xFFFE, 0xFFFF):
                break
            if cpu.pc == 0x8A6F and nes.nes.lo is nes.nes.bank(7):
                cheer = cpu.sp
            elif cheer is not None and cpu.sp > cheer:
                cheer = None
            if nes.nes.read(cpu.pc) == 0xA5 and nes.nes.read(cpu.pc + 1) == 0x18:
                if cheer is not None:
                    ram[0x18] = crowd.randrange(256)    # the crowd's own (its draws are only looks)
                else:
                    nes.rand = lfsr(nes.rand); ram[0x18] = nes.rand
            cpu.step()
        gb.call("NesEngineFrame")
        seen.add(ram[0x90] & 0x7F); macs.add(ram[0x50] & 0x7F)
        now = (ram[0x05], ram[0x00])
        if now != last:
            events.append(f"{frame}:KD{now[0]:X}/{now[1]:02X}"); last = now
        bad = []
        for a in range(0x800):
            if a in NES_ONLY:
                continue
            want, got = ram[a], gb.ram(a)
            if a in POINTER_HI and got:
                got = (got + 0x40) & 0xFF
            if got != want:
                bad.append(f"${a:03X} NES {want:02X} GB {got:02X}")
        if bad:
            failures.append(f"frame {frame}: Joe {ram[0x90]:02X} Mac {ram[0x50]:02X} buttons {held:02X}: " + ", ".join(bad[:8]))
            break
        if ram[0x00] == 0xFF and ram[0x06] < 3:     # time: the next round ($A9AA)
            ram[0x06] += 1
            gb.m.write(gb.sym["wNesRand"][1], nes.rand)
            nes.call(0xAB4E)                        # his knockdowns this round, then $AB58 from
            nes.call(0xAB96, bank=7)                # where the screen's drawn: places, $ABB3
            gb.call("NesRoundStart", ram[0x06], bank="NesFighter")
            events.append(f"{frame}:R{ram[0x06]}")
            continue
        if ram[0x00] & 0x80:
            break
    ok = not failures
    log(("  ✓" if ok else "  ✗") + f" {title}: matches for {frame + 1} frames; {' '.join(events[:12])}"
        f" (Joe {', '.join(f'{s:02X}' for s in sorted(seen))}; Mac {', '.join(f'{s:02X}' for s in sorted(macs))})")
    for f in failures:
        log("      " + f)
    return ok


def sound(log, title, frames, seed, music=0x1F):
    """The sound engine (bank 8, $8000) against the Game Boy's SoundEngine, a frame at a time, with effects,
    music and samples asked for at random: its RAM ($F0-$FF, $0700-$072F), the sound registers as last
    written, and which writes this frame start something ($4003/$4007/$400B/$400F/$4015, sweeps $4001/$4005)."""
    if not DISASM.exists():
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    gb, nes = Gb(project), Nes()
    nes.nes.lo = nes.nes.bank(8)
    ram = nes.nes.ram
    sym = gb.sym
    rng = random.Random(seed)
    gb.call("ApuInit", bank="NesSnd")
    for a in range(0x800):
        gb.poke(a, 0)
    requests = {0xF2: music}
    failures, seen = [], set()
    for frame in range(frames):
        for a, v in requests.items():
            ram[a] = v; gb.poke(a, v)
        requests = {}
        if rng.random() < 0.06:
            requests[0xF0] = rng.choice(list(range(1, 0x19)) + [0x80])
        if rng.random() < 0.06:
            requests[0xF1] = rng.choice(list(range(1, 0x16)) + [0x80])
        if rng.random() < 0.002:
            requests[0xF2] = rng.choice(list(range(1, 0x20)) + [0x80])
        if rng.random() < 0.01:
            requests[0xF3] = rng.choice(list(range(1, 8)) + [0x80])
        nes.nes.apu_new[:] = bytes(5); nes.nes.apu_reload[:] = bytes(2)
        nes.call(0x8000)
        gb.call("SoundEngine", bank="NesSnd")
        seen.add((ram[0xF4], ram[0xF5], ram[0xF6]))
        bad = []
        for a in list(range(0xF0, 0x100)) + list(range(0x700, 0x730)) + [0xE0]:
            if ram[a] != gb.ram(a):
                bad.append(f"${a:03X} NES {ram[a]:02X} GB {gb.ram(a):02X}")
        rd = lambda name, k: gb.m.read(sym[name][1] + k)
        for k in range(0x18):
            if k not in (0x11, 0x14, 0x16) and nes.nes.apu[k] != rd("wApu", k):
                bad.append(f"${0x4000 + k:04X} NES {nes.nes.apu[k]:02X} GB {rd('wApu', k):02X}")
        for k in range(5):
            if nes.nes.apu_new[k] != rd("wApuNew", k):
                bad.append(f"new {k} NES {nes.nes.apu_new[k]:02X} GB {rd('wApuNew', k):02X}")
        for k in range(2):
            if nes.nes.apu_reload[k] != rd("wApuSweepReload", k):
                bad.append(f"sweep {k} NES {nes.nes.apu_reload[k]:02X} GB {rd('wApuSweepReload', k):02X}")
        if bad:
            failures.append(f"frame {frame}: SQ1 {ram[0xF4]:02X} SQ2 {ram[0xF5]:02X} music {ram[0xF6]:02X}: " + ", ".join(bad[:8]))
            break
        gb.call("ApuOut", bank="NesSnd")     # the GB side takes them (and mustn't fall over)
    ok = not failures
    log(("  ✓" if ok else "  ✗") + f" {title}: matches for {frame + 1} frames ({len(seen)} effect/music combinations)")
    for f in failures:
        log("      " + f)
    return ok


def fight(log, title, frames, seed):
    """Buttons -> both fighters -> the exchange, as the NES frame runs them (bank 0 Joe, B Mac, 7 exchange)."""
    if not DISASM.exists():
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    gb, nes = Gb(project), Nes()
    gb.call("NesFightStart", bank="NesFighter")
    gb.call("NesRoundStart", 1)
    ram = nes.nes.ram
    for a in range(0x800):
        v = gb.ram(a)
        ram[a] = (v + 0x40) & 0xFF if a in POINTER_HI and v else v
    ram[0x02] = 0                           # the fight's bank (Glass Joe)
    ram[0x04] = 0xFF                        # playing, not the demo
    ram[0x00] = 0x01                        # the fight phase ($B530 -> $B549)
    rng = random.Random(seed)
    nes.rand = rng.randrange(1, 256)
    held, hold = 0, 0
    failures, seen, macs, downs = [], set(), set(), []
    for frame in range(frames):
        if hold == 0:                       # press something (or nothing) for a while
            held = rng.choice([0, 0, 0, 0x80, 0x40, 0x88, 0x48, 0x01, 0x02, 0x04, 0x10, 0x80, 0x40])
            hold = rng.randrange(1, 25)
        hold -= 1
        for a in (0x0391, 0x0392, 0x0398, 0x0399):     # no knockdowns here (their hand-off is step 3)
            ram[a] = 96
            gb.poke(a, 96)
        if frame % 60 == 59:
            v = (ram[0x0311] - 1) & 0xFF
            ram[0x0311] = v; gb.poke(0x0311, v)
        ram[0xD0] = held; gb.poke(0xD0, held)
        gb.m.write(gb.sym["wNesRand"][1], nes.rand)
        ram[0xE3] = 0x80
        for k in range(0, 8, 2):            # the raw polls the NES checks against each other ($B021)
            ram[0x6A0 + k] = held
        nes.call(0xAFBD); gb.call("NesButtons")
        for addr, name in ROUTINES:
            nes.call(addr, bank=0); gb.call(name, bank="NesFighter")
        nes.call(0x8119, bank=0x0B); gb.call("NesMacInput", bank="NesMac")
        nes.call(0x8319, bank=0x0B); gb.call("NesMacTick", bank="NesMac")
        nes.call(0x805D, bank=0x07); gb.call("NesExchange", bank="NesFighter")
        ram[0x00] = 0x01                    # the fight phase
        nes.call(0xB530, bank=0); gb.call("NesFightPhase")
        seen.add(ram[0x90] & 0x7F); macs.add(ram[0x50] & 0x7F)
        knocked = ram[0x05]
        bad = []
        for a in range(0x800):
            if a in SKIP:
                continue
            want, got = ram[a], gb.ram(a)
            if a in POINTER_HI and got:
                got = (got + 0x40) & 0xFF
            if got != want:
                bad.append(f"${a:03X} NES {want:02X} GB {got:02X}")
        if bad:
            failures.append(f"frame {frame}: Joe {ram[0x90]:02X} Mac {ram[0x50]:02X} buttons {held:02X}: " + ", ".join(bad[:8]))
            break
        if knocked:                         # a knockdown: its setup matched; the count is the phase machine's
            downs.append(knocked)           # (step 3), so both start the round again from here
            for a in (0x05, 0x0300, 0x0301):
                ram[a] = 0; gb.poke(a, 0)
            for a, v in ((0x90, 0x81), (0x50, 0x81), (0x51, 0x80), (0x91, 0)):
                ram[a] = v; gb.poke(a, v)
    ok = not failures
    log(("  ✓" if ok else "  ✗") + f" {title}: matches the NES game byte for byte for {frame + 1} frames, {len(downs)} knockdowns"
        f" (Joe {', '.join(f'{s:02X}' for s in sorted(seen))}; Mac {', '.join(f'{s:02X}' for s in sorted(macs))})")
    for f in failures:
        log("      " + f)
    return ok


def scenario(log, title, frames, seed, busy):
    if not DISASM.exists():
        log(f"NES tests skipped: no disassembly at {DISASM}")
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    gb, nes = Gb(project), Nes()
    gb.call("NesFightStart")
    gb.call("NesRoundStart", 1)
    ram = nes.nes.ram
    for a in range(0x800):                 # the NES starts from the same RAM, its pointers as the NES had them
        v = gb.ram(a)
        ram[a] = (v + 0x40) & 0xFF if a in POINTER_HI and v else v
    rng = random.Random(seed)
    nes.rand = rand = rng.randrange(1, 256)
    gb.poke(0x18, 0); gb.m.write(gb.sym["wNesRand"][1], rand)
    mac, failures, seen = 1, [], set()
    for frame in range(frames):
        # the same inputs to both: what Mac is doing, where he aims, his punches, how the rival's punch went
        if rng.random() < (0.05 if busy else 0.01):
            mac = rng.choice([1, 1, 1, 3, 5, 7, 9, 0x0A, 0x0B, 0x0C, 0x0E] if busy else [1, 1, 1, 7])
        inputs = {0x50: mac, 0xD2: 8 if rng.random() < 0.3 else 0}
        if rng.random() < (0.04 if busy else 0.002):
            inputs[0x99] = 1
            inputs[0x74] = rng.choice([0, 1, 2, 3, 0x80])
        if busy and rng.random() < 0.012:   # a punch lands or is blocked: the state bank 7 would set
            inputs[0x90] = rng.choice([0x85, 0x86, 0x87, 0x88] + list(range(0x8D, 0x95)))
        if ram[0x98] == 0x80 and rng.random() < 0.5:
            inputs[0x98] = rng.choice([1, 2, 3, 4])
        if frame % 60 == 59:
            inputs[0x0311 & 0x7FF] = (ram[0x0311] - 1) & 0xFF
        for a, v in inputs.items():
            ram[a] = v
            gb.poke(a, v)
        gb.m.write(gb.sym["wNesRand"][1], nes.rand)
        for addr, name in ROUTINES:
            ram[0xE3] = 0x80        # as the NES's drawing ($C890) leaves it each frame
            nes.call(addr)
            gb.call(name)
        nes.rand = gb.m.read(gb.sym["wNesRand"][1]) if False else nes.rand
        seen.add(ram[0x90])
        bad = []
        for a in range(0x800):
            if a in SKIP:
                continue
            want = ram[a]
            got = gb.ram(a)
            if a in POINTER_HI and got:
                got = (got + 0x40) & 0xFF
            if got != want:
                bad.append(f"${a:03X} NES {want:02X} GB {got:02X}")
        if bad:
            failures.append(f"frame {frame}: state {ram[0x90]:02X}: " + ", ".join(bad[:6]))
            break
    ok = not failures
    log(("  ✓" if ok else "  ✗") + f" {title}: matches the NES game byte for byte for {frame + 1} frames"
        f" (states seen: {', '.join(f'{s:02X}' for s in sorted(seen))})")
    for f in failures:
        log("      " + f)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
