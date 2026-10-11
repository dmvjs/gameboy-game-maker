"""A small 6502 disassembler over the Punch-Out!! banks (uses cpu6502's opcode table)."""
import pathlib, sys
from cpu6502 import OPS
import gamefiles
D = gamefiles.banks()
LEN = {None: 1, "acc": 1, "imm": 2, "zp": 2, "zpx": 2, "zpy": 2, "izx": 2, "izy": 2, "rel": 2,
       "abs": 3, "abx": 3, "aby": 3, "ind": 3}

def bank(name, base):
    data = (D / name).read_bytes()
    return lambda a: data[a - base]

def dis(rd, start, end):
    a = start; out = []
    while a < end:
        op = rd(a); e = OPS.get(op)
        if not e:
            out.append(f"{a:04X}: .byte ${op:02X}"); a += 1; continue
        n, m = e; L = LEN[m]
        arg = [rd(a + k) for k in range(1, L)]
        if m in ("abs", "abx", "aby", "ind"): v = arg[0] | arg[1] << 8; s = f"${v:04X}"
        elif m == "rel": s = f"${(a + 2 + (arg[0] - 256 if arg[0] & 0x80 else arg[0])) & 0xFFFF:04X}"
        elif m in (None, "acc"): s = ""
        else: s = f"${arg[0]:02X}"
        fmt = {"imm": "#{}", "zpx": "{},X", "abx": "{},X", "zpy": "{},Y", "aby": "{},Y", "izx": "({},X)", "izy": "({}),Y", "ind": "({})"}.get(m, "{}")
        out.append(f"{a:04X}: {n.upper()} {fmt.format(s) if s else ''}".rstrip()); a += L
    return out

if __name__ == "__main__":
    name, base, s, e = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16)
    print("\n".join(dis(bank(name, base), s, e)))
