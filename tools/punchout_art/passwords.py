"""Punch-Out!!'s pass keys, by the NES's own code (bank 7, run in cpu6502): a record and circuit to its ten
digits ($8FF0), ten digits to the record and circuit they stand for, or not a pass key ($8EC1).

  encode(wins, losses, kos, circuit) -> [10 digits]       circuit: 0 minor, 1 major, 2 world
  decode(digits) -> (wins, losses, kos, circuit) or None
  SPECIAL: the six the NES knows by heart (PswrdDatTbl, $8DA2)

  python passwords.py ENCODE W L K C | DECODE 0075416113"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
DISASM = HERE / "disassembly"
SPECIAL = {"busy1": "0755416113", "busy2": "8004222602", "busy3": "2068822040",
           "another_world": "1357924680", "credits": "1061130120", "tyson": "0073735963"}
ENTERED = 0x0110                # EnteredPasswd: the encoder's digits here; the decoder reads $0120 on
RECORD = 0x0170                 # the record the encoder takes: wins, losses, KOs, two decimal digits each


def _nes():
    import cpu6502
    return cpu6502.Nes(DISASM, 7)


def _call(nes, addr):
    cpu = nes.cpu
    cpu.sp = 0xFF
    cpu.push(0xFF); cpu.push(0xFE)          # (returns to $FFFF)
    cpu.pc = addr
    for _ in range(100_000):
        if cpu.pc == 0xFFFF:
            return cpu.a
        cpu.step()
    raise RuntimeError(f"${addr:04X} didn't return")


def _digits2(n):
    return [n // 10 % 10, n % 10]


def encode(wins, losses, kos, circuit):
    nes = _nes()
    for i, d in enumerate(_digits2(wins) + _digits2(losses) + _digits2(kos)):
        nes.ram[RECORD + i] = d
    nes.ram[0x09] = (nes.ram[0x09] & ~0x30 & 0xFF) | (0x30 ^ ((circuit + 1) << 4))   # ($9001 reads it back:
    _call(nes, 0x8FF0)                                                                # (EOR $30) - $10, /4)
    return [nes.ram[ENTERED + i] for i in range(10)]


def decode(digits):
    nes = _nes()
    for i, d in enumerate(digits):
        nes.ram[0x0120 + i] = int(d)
    if _call(nes, 0x8EC1):
        return None
    r = [nes.ram[0x0130 + i] for i in range(6)]
    return r[0] * 10 + r[1], r[2] * 10 + r[3], r[4] * 10 + r[5], nes.ram[0x0136]


if __name__ == "__main__":
    if sys.argv[1].upper() == "ENCODE":
        print("".join(map(str, encode(*map(int, sys.argv[2:6])))))
    else:
        print(decode(sys.argv[2]))
