"""The fight's sound on both machines, from the same moments: the Game Boy port played (PyBoy, the bot, buttons
only), every frame's sound requests to its engine noted; the NES's own sound engine (bank 8, the original ROM's
code, in the 6502 interpreter) handed the same requests from the same state, its sound registers rendered by
blargg's Nes_Apu (libgme: tools/nes_apu). Both written out, and compared a frame at a time: loudness, the balance
low/mid/high, the strongest pitch.

  python tools/sound_ab.py ROM SCENE [FRAMES] [OUT_DIR]   -> OUT_DIR/ab-nes.wav, ab-gb.wav, ab-both.wav (L NES, R GB)
  (needs tools/nes_apu/render built: see its source; GME=path to libgme's gme/ to build it here)"""
import os, subprocess, sys, tempfile, wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RATE, FPS = 48000, 60
PER = RATE // FPS


def render_tool():
    exe = ROOT / "tools" / "nes_apu" / "render"
    if exe.exists():
        return exe
    gme = Path(os.environ.get("GME", ""))
    src = [gme / n for n in ("Nes_Apu.cpp", "Nes_Oscs.cpp", "Blip_Buffer.cpp")]
    if not all(p.exists() for p in src):
        sys.exit("tools/nes_apu/render isn't built: GME=<libgme's gme/ directory> to build it")
    subprocess.run(["c++", "-O2", "-std=c++11", f"-I{gme}", "-DBLARGG_LITTLE_ENDIAN=1",
                    str(ROOT / "tools" / "nes_apu" / "render.cpp")] + [str(p) for p in src] + ["-o", str(exe)], check=True)
    return exe


def play_gb(rom, scene, frames):
    """The fight on the Game Boy: each frame's sound (a frame's worth) and the engine's state as it's entered."""
    from gbstage import bot
    S, B = bot._symbols(rom)
    w, apu = S["wNes"], S["wApu"]
    rec = {"live": False, "req": [], "snd": [], "start": None, "pending": None}
    oinit, otick = bot.Game.__init__, bot.Game.tick

    def init(self, *a, **k):
        oinit(self, *a, **k)
        m = self.m

        def entry(_):
            if not rec["live"]:
                return
            if rec["start"] is None and m[S["hScene"]] == scene:
                rec["start"] = (bytes(m[w + a] for a in range(0x800)), bytes(m[apu + k] for k in range(0x18)))
            if rec["start"] is not None:
                rec["pending"] = bytes(m[w + a] for a in range(0xF0, 0xF4))
        self.pb.hook_register(B["SoundEngine"], S["SoundEngine"], entry, None)

    def tick(self, render=True):
        rec["live"] = render
        rec["pending"] = None
        otick(self, render)
        rec["live"] = False
        if not render or rec["start"] is None:
            return
        a = self.pb.sound.ndarray.astype("float64").mean(axis=1) if self.pb.sound.ndarray.size else np.zeros(1)
        rec["snd"].append(np.interp(np.linspace(0, len(a) - 1, PER), np.arange(len(a)), a))
        rec["req"].append(rec["pending"])          # (None: the engine wasn't run this frame)

    bot.Game.__init__, bot.Game.tick = init, tick
    try:
        bot.play(rom, scene, frames=frames, cgb=True, sound=True)
    finally:
        bot.Game.__init__, bot.Game.tick = oinit, otick
    return rec


def from_sameboy(d, scene):
    """The same from a SameBoy run (its sbreplay, SB_WAV=DIR/gb.raw SB_SND="<SoundEngine> <bank> <wNes> <wApu>"):
    the engine's state each time it was entered, each video frame's sound."""
    d = Path(d)
    ram = [l.split() for l in (d / "ram.txt").read_text().splitlines()]
    ends = [int(next(f for f in r if f.startswith("s="))[2:]) for r in ram]
    scn = [int(r[-1]) for r in ram]
    pcm = np.frombuffer((d / "gb.raw").read_bytes(), "<i2").astype(float)
    raw, size = (d / "snd.bin").read_bytes(), 4 + 0x800 + 0x18
    calls = {}
    for i in range(0, len(raw) - size + 1, size):
        v = int.from_bytes(raw[i:i + 4], "little", signed=True)
        calls[v] = raw[i + 4:i + size]
    first = next(v for v in sorted(calls) if 0 <= v < len(scn) and scn[v] == scene)
    rec = {"start": (calls[first][:0x800], calls[first][0x800:]), "req": [], "snd": []}
    for v in range(first, len(ram)):
        a = pcm[(ends[v - 1] if v else 0):ends[v]]
        if len(a) == 0:
            a = np.zeros(1)
        rec["snd"].append(np.interp(np.linspace(0, len(a) - 1, PER), np.arange(len(a)), a))
        rec["req"].append(calls[v][0xF0:0xF4] if v in calls else None)
    return rec


def play_nes(rec, log_path, image_path):
    """The NES's engine from the same state, handed the same requests: its register writes, a frame at a time."""
    from gbstage import nestests
    nes = nestests.Nes(0)
    n = nes.nes
    n.lo = n.bank(8)
    ram, regs = rec["start"]
    for a in range(0x800):
        n.ram[a] = ram[a]
    writes, frame = [], [0]
    for k in range(0x16):                          # (its sound registers as the Game Boy's engine had them)
        if k not in (0x11, 0x14):
            writes.append((0, 0x4000 + k, regs[k]))
    owrite = n.write

    def write(a, v):
        if 0x4000 <= a < 0x4018:
            writes.append((frame[0], a, v & 0xFF))
        owrite(a, v)
    n.cpu.write = write
    for f, req in enumerate(rec["req"]):
        frame[0] = f
        if req is None:
            continue
        for i, v in enumerate(req):
            n.ram[0xF0 + i] = v
        nes.call(0x8000)
    Path(log_path).write_text("".join(f"{f} {a:x} {v:x}\n" for f, a, v in writes))
    Path(image_path).write_bytes(bytes(n.lo[:0x2000]) + bytes(n.hi[:0x6000]))


def bands(x):
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / RATE)
    return [sp[(fr >= lo) & (fr < hi)].sum() for lo, hi in ((40, 250), (250, 2000), (2000, 12000))], fr[np.argmax(sp[1:]) + 1]


def save(path, sig, ch=1):
    w = wave.open(str(path), "wb")
    w.setnchannels(ch); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(np.clip(sig * 32767, -32768, 32767).astype("<i2").tobytes()); w.close()


def main():
    args = sys.argv[1:]
    rom, scene = args[0], int(args[1])     # (ROM: a .gb[c], or a SameBoy run's directory)
    frames = int(args[2]) if len(args) > 2 else 2400
    out = Path(args[3] if len(args) > 3 else ".").expanduser()
    out.mkdir(parents=True, exist_ok=True)
    exe = render_tool()
    rec = from_sameboy(rom, scene) if Path(rom).is_dir() else play_gb(rom, scene, frames)
    with tempfile.TemporaryDirectory() as tmp:
        log, img, raw = Path(tmp) / "apu.log", Path(tmp) / "image.bin", Path(tmp) / "nes.raw"
        play_nes(rec, log, img)
        subprocess.run([str(exe), str(img), str(log), str(raw)], check=True)
        nes = np.frombuffer(raw.read_bytes(), "<i2").astype(float) / 32768
    gb = np.concatenate(rec["snd"]); gb -= np.convolve(gb, np.ones(533) / 533, "same")    # (its DC: the NES's 90 Hz)
    n = min(len(nes), len(gb)) // PER * PER
    nes, gb = nes[:n], gb[:n]
    nes /= max(1e-9, np.sqrt((nes ** 2).mean())); gb /= max(1e-9, np.sqrt((gb ** 2).mean()))   # (same loudness overall)
    peak = max(np.abs(nes).max(), np.abs(gb).max()) / 0.9
    save(out / "ab-nes.wav", nes / peak); save(out / "ab-gb.wav", gb / peak)
    save(out / "ab-both.wav", np.stack([nes, gb], axis=1).reshape(-1) / peak, 2)
    rows = []
    for i in range(0, n - 4 * PER, 4 * PER):       # (4 frames a look)
        a, fa = bands(nes[i:i + 4 * PER]); b, fb = bands(gb[i:i + 4 * PER])
        rows.append((np.sqrt(sum(a)), np.sqrt(sum(b)), a, b, fa, fb))
    la, lb = np.array([r[0] for r in rows]), np.array([r[1] for r in rows])
    print(f"{n // PER} frames compared")
    print(f"loudness, frame to frame: correlation {np.corrcoef(la, lb)[0, 1]:.3f}")
    tot_a, tot_b = np.sum([r[2] for r in rows], axis=0), np.sum([r[3] for r in rows], axis=0)
    for name, x, y in zip(("low 40-250 Hz", "mid 250-2k", "high 2k-12k"), tot_a / tot_a.sum(), tot_b / tot_b.sum()):
        print(f"  {name:14s} NES {100 * x:5.1f}%  GB {100 * y:5.1f}%  ({10 * np.log10(max(y, 1e-12) / max(x, 1e-12)):+.1f} dB)")
    loud = [r for r in rows if r[0] > np.median(la)]
    same = sum(1 for r in loud if abs(12 * np.log2(max(r[5], 1) / max(r[4], 1))) < 0.5)
    print(f"strongest pitch the same (within a quarter tone), louder half: {same}/{len(loud)}")
    print("files:", out / "ab-nes.wav", out / "ab-gb.wav", out / "ab-both.wav")


if __name__ == "__main__":
    main()
