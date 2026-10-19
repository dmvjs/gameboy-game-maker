"""Whole-fight videos of the Joe vs Mac example: the bot (gbstage/bot.py, buttons only) plays each fight on the
ROM in PyBoy, Game Boy Color and the original Game Boy, with its sound. CI renders them all (.github/workflows/
fight-videos.yml) and publishes them on the project's GitHub Pages.

  python tools/fight_videos.py rom OUT.gbc                  build the example's ROM (and OUT.gbc.sym)
  python tools/fight_videos.py list                         the fights: key, scene, name (JSON)
  python tools/fight_videos.py record ROM KEY OUT.mp4 [--grey]   one whole fight; also OUT.gif, a short preview
  python tools/fight_videos.py site DIR                     DIR/index.html for the videos in DIR

Needs PyBoy, NumPy, Pillow and imageio-ffmpeg."""
import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"

NAMES = {"joe": "Glass Joe", "kaiser": "Von Kaiser", "honda": "Piston Honda", "don": "Don Flamenco",
         "hippo": "King Hippo", "tiger": "Great Tiger", "bull": "Bald Bull", "honda2": "Piston Honda II",
         "soda": "Soda Popinski", "bull2": "Bald Bull II", "don2": "Don Flamenco II", "sandman": "Mr. Sandman",
         "macho": "Super Macho Man", "tyson": "Mike Tyson"}
# the original Game Boy's screen: its own four greens, not white to black
DMG_LCD = [(0xE0, 0xF8, 0xD0), (0x88, 0xC0, 0x70), (0x34, 0x68, 0x56), (0x08, 0x18, 0x20)]
FPS = 59.7275
RATE = 48000
PREVIEW = (20, 8)               # the preview: seconds in, seconds long


def fights():
    """[(key, scene, name)] in the game's order."""
    project = json.loads(EXAMPLE.read_text())
    out = []
    for i, s in enumerate(project["scenes"]):
        if s.get("fight"):
            key = s["name"].split(":")[-1].strip().lower() if ":" in s["name"] else "joe"
            out.append((key, i, NAMES.get(key, key)))
    return out


def build(out):
    from gbstage import codegen
    from gbstage.build import build_rom
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    b = build_rom(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    Path(out).write_bytes(b.rom)
    Path(out + ".sym").write_text(b.sym)
    print("built", out, len(b.rom) // 1024, "KB")


def record(rom, key, out, grey=False):
    import imageio_ffmpeg
    import numpy
    from gbstage import bot
    scene = {k: s for k, s, _ in fights()}[key]
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    lcd = numpy.array(DMG_LCD, dtype="uint8")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    tmp = out + ".tmp"
    video = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "160x144",
                              "-r", str(FPS), "-i", "-", "-vf", "scale=640:576:flags=neighbor", "-c:v", "libx264",
                              "-pix_fmt", "yuv420p", "-crf", "16", tmp + ".mp4"], stdin=subprocess.PIPE)
    wav = wave.open(tmp + ".wav", "wb")
    wav.setnchannels(2)
    wav.setsampwidth(1)
    wav.setframerate(RATE)
    state = {"on": False, "n": 0, "due": 0.0, "written": 0}
    otick, ostop = bot.Game.tick, bot.Game.stop

    def tick(self, render=True):
        otick(self, render)
        if not render:
            return
        state["on"] = state["on"] or self.hram("hScene") == scene
        if not state["on"]:
            return
        px = self.pb.screen.ndarray[:, :, :3]
        if grey:
            lum = px.astype("uint16").sum(axis=2)
            px = lcd[(lum < 600).astype("uint8") + (lum < 380) + (lum < 150)]
        video.stdin.write(px.tobytes())
        # each frame's sound stretched to exactly a frame's time (PyBoy's run a little short, and short frames
        # around a load), so the sound can't drift from the picture
        a = self.pb.sound.ndarray.astype("float64")
        state["due"] += RATE / FPS
        want = int(state["due"]) - state["written"]
        if len(a) == 0:
            a = numpy.zeros((1, 2))
        x = numpy.linspace(0, len(a) - 1, want)
        s = numpy.stack([numpy.interp(x, numpy.arange(len(a)), a[:, c]) for c in (0, 1)], axis=1)
        state["written"] += want
        wav.writeframes((numpy.round(s).astype("int16") + 128).clip(0, 255).astype("uint8").tobytes())
        state["n"] += 1

    def stop(self):
        for _ in range(420):                # the knockout and what follows, a few seconds
            tick(self)
        ostop(self)

    bot.Game.tick, bot.Game.stop = tick, stop
    if grey:                                # as a real one boots (A = $01; PyBoy gives $11)
        oinit = bot.Game.__init__

        def init(self, *a, **k):
            oinit(self, *a, **k)
            S, B = bot._symbols(rom)
            self.pb.hook_register(B["Start"], S["Start"], lambda _: setattr(self.pb.register_file, "A", 1), None)
        bot.Game.__init__ = init
    r = bot.play(rom, scene, sound=True, cgb=not grey)
    video.stdin.close()
    video.wait()
    wav.close()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", tmp + ".mp4", "-i", tmp + ".wav", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", out], check=True)
    gif = str(Path(out).with_suffix(".gif"))
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(PREVIEW[0]), "-t", str(PREVIEW[1]), "-i", tmp + ".mp4",
                    "-vf", "fps=30,scale=320:288:flags=neighbor,split[a][b];[a]palettegen=max_colors=64[p];"
                    "[b][p]paletteuse=dither=none", gif], check=True)
    for p in (tmp + ".mp4", tmp + ".wav"):
        Path(p).unlink()
    r.pop("events", None)
    print(key, "grey" if grey else "color", r, state["n"], "frames")
    if not r.get("won"):
        sys.exit(f"{key}: the bot didn't win")


def site(d):
    d = Path(d)
    rows = []
    for key, _, name in fights():
        cells = "".join(
            f'<figure><video controls preload="none" poster="{key}-{m}.gif" src="{key}-{m}.mp4"></video>'
            f"<figcaption>{label}</figcaption></figure>"
            for m, label in (("color", "Game Boy Color"), ("grey", "Game Boy")) if (d / f"{key}-{m}.mp4").exists())
        rows.append(f'<section id="{key}"><h2>{name}</h2><div class="pair">{cells}</div></section>')
    (d / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Joe vs Mac fights</title>
<style>
:root {{ --bg: #f4f4f0; --fg: #1a1a1a; --muted: #666; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #141414; --fg: #eee; --muted: #999; }} }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; margin: 0 auto;
       max-width: 1360px; padding: 24px 16px; }}
p {{ color: var(--muted); }}
.pair {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
figure {{ margin: 0; }}
video {{ width: 100%; aspect-ratio: 10 / 9; image-rendering: pixelated; background: #000; }}
figcaption {{ color: var(--muted); font-size: 14px; }}
</style></head><body>
<h1>Joe vs Mac: every fight</h1>
<p>Each fight played start to knockout by the bot (buttons only) on the ROM built from this repo, in PyBoy,
on Game Boy Color and the original Game Boy. Rendered by CI.</p>
{chr(10).join(rows)}
</body></html>
""")
    print("wrote", d / "index.html")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "rom":
        build(args[0])
    elif cmd == "list":
        print(json.dumps([{"key": k, "scene": s, "name": n} for k, s, n in fights()]))
    elif cmd == "record":
        record(args[0], args[1], args[2], "--grey" in args)
    elif cmd == "site":
        site(args[0])
    else:
        sys.exit(__doc__)
