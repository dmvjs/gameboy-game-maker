"""The fight's sound, frame by frame, the same on two ROMs: each plays one fight with the same buttons each frame
(seeded, the same on both), and after every frame the sound's state is compared: the NES game's RAM (its sound
engine's state with it), the APU as the GB port holds it (wApu..wApuEnd, its scratch left out), and every sound
register the hardware reads back, the wave pattern too. For proving a speed-up of the sound code changes nothing.

  python tools/sound_equiv.py OLD.gbc NEW.gbc SCENE [FRAMES] [--dmg]   (each with its .sym beside it)"""
import random, sys, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
SCRATCH = ("wTicks", "wSwCtl", "wSwPeriod", "wSwTarget")
BUTTONS = ["a", "b", "up", "down", "left", "right", "start"]


def symbols(rom):
    out = {}
    for line in open(rom + ".sym"):
        f = line.split()
        if len(f) == 2 and ":" in f[0] and not line.startswith(";"):
            out[f[1]] = int(f[0].split(":")[1], 16)
    return out


def run(rom, scene, frames, cgb):
    from gbstage import bot
    S = symbols(rom)
    skip = set()
    for n in SCRATCH:
        size = {"wSwPeriod": 2, "wSwTarget": 2}.get(n, 1)
        skip.update(range(S[n], S[n] + size))
    apu = [a for a in range(S["wApu"], S["wApuEnd"]) if a not in skip]
    g = bot.Game(rom, scene, cgb)
    rng = random.Random(1987)
    held, out, f = [], [], 0
    while len(out) < frames and f < frames + 6000:
        f += 1
        if g.hram("hScene") == scene and g.hram("hFtActive") == 1:
            if rng.random() < 0.15:
                held = [b for b in BUTTONS[:6] if rng.random() < 0.3]
            g.hold(held)
        else:
            g.hold(["start"] if f % 40 < 3 else [])
        g.tick(False)
        if g.hram("hFtActive") != 1:
            continue
        m = g.m
        state = bytes(m[S["wNes"] + i] for i in range(0x800)) + bytes(m[a] for a in apu) + \
            bytes(m[a] for a in range(0xFF10, 0xFF27)) + bytes(m[a] for a in range(0xFF30, 0xFF40))
        out.append((zlib.crc32(state), state))
    g.stop()
    return out, len(apu)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    old, new, scene = args[0], args[1], int(args[2])
    frames = int(args[3]) if len(args) > 3 else 3000
    cgb = "--dmg" not in sys.argv
    a, napu = run(old, scene, frames, cgb)
    b, _ = run(new, scene, frames, cgb)
    for k, ((ha, sa), (hb, sb)) in enumerate(zip(a, b)):
        if ha != hb:
            diff = [i for i in range(len(sa)) if sa[i] != sb[i]][:12]
            where = ["wNes+$%03X" % i if i < 0x800 else "apu+%d" % (i - 0x800) if i < 0x800 + napu
                     else "$FF%02X" % (0x10 + i - 0x800 - napu) if i < 0x800 + napu + 0x17 else "wave+%d" % (i - 0x800 - napu - 0x17)
                     for i in diff]
            print(f"frame {k}: differ at {', '.join(f'{w} {sa[i]:02X}/{sb[i]:02X}' for w, i in zip(where, diff))}")
            sys.exit(1)
    print(f"same for {min(len(a), len(b))} frames ({'Color' if cgb else 'original'})")
