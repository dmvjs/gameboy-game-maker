"""Little Mac's state scripts from the NES game (PRG bank B: the interpreter is $8319, its ops $8363-$85CA),
decoded into steps. python3 tools/punchout_art/nes_mac.py"""
from pathlib import Path
import gamefiles
D = gamefiles.banks()
B = (D / "PRG_Bank00B.bin").read_bytes()
rb = lambda a: B[a - 0x8000]
rw = lambda a: rb(a) | rb(a + 1) << 8
NAMES = {0: "none", 1: "waiting", 2: "no_hearts", 3: "dodge_right", 5: "dodge_left", 7: "block", 8: "block_hit",
         9: "right_gut", 10: "left_gut", 11: "right_face", 12: "left_face", 13: "star", 14: "duck",
         0x10: "stunned_right", 0x11: "stunned_left"}

def decode(base, limit=120):
    out, i = [], 0
    while i < limit:
        op = rb(base + i); at = i; i += 1; hi, lo = op >> 4, op & 15
        def b(n=1):
            nonlocal i
            v = [rb(base + i + k) for k in range(n)]; i += n; return v
        if hi == 0: out.append((at, f"frame {b()[0]:02X} for {lo}"))
        elif hi == 1: f, x = b(2); out.append((at, f"frame {f:02X} at x {x} for {lo}"))
        elif hi == 2: v = b()[0]; out.append((at, f"x += {v - 256 if v > 127 else v} for {lo}"))
        elif hi == 3: out.append((at, f"chance {lo}/16 -> {b()[0]:02X}"))
        elif hi == 4: f, v = b(2); out.append((at, f"frame {f:02X}, x += {v - 256 if v > 127 else v} for {lo}"))
        elif 5 <= hi <= 8: out.append((at, f"wait {b()[0]}"))
        elif 9 <= hi <= 0xE:
            sub = ["if right/up -> ", "if left/up -> ", "if down -> ", "if zp ", "duck check -> ", "punch type ", "clock ",
                   "head += ", "body += ", "call ", "return", "HP reset", "sound ", "if16 "][lo] if lo < 14 else "?"
            n = {0: 1, 1: 1, 2: 1, 3: 3, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 2, 10: 0, 11: 0, 12: 1, 13: 4}.get(lo, 0)
            v = b(n); out.append((at, sub + " ".join(f"{x:02X}" for x in v)))
            if lo == 10: break
        else:
            names = ["punch out (landed/blocked/dodged ->)", "jump", "ready", "repeat_to", "done (wait/no hearts)", "repeat",
                     "damage", "defense", "inc zp", "?", "set zp", "pal", "pal2", "hit side $59", "?", "finished"]
            n = {0: 3, 1: 3, 3: 1, 5: 1, 6: 1, 7: 2, 8: 1, 10: 2, 13: 1}.get(lo, 0)
            v = b(n); out.append((at, names[lo] + " " + " ".join(f"{x:02X}" for x in v)))
            if lo in (1, 4, 15): break
    return out

if __name__ == "__main__":
    for k in range(0x16):
        p = rw(0x9800 + 2 * k)
        if not 0x8000 <= p < 0xA000: continue
        print(f"\n== ${k:02X} {NAMES.get(k, '')} (${p:04X})")
        for at, s in decode(p): print(f"  {at:02X} {s}")
