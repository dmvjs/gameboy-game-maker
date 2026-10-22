"""A rival's pictures touched up by hand: each one a text file, a character a pixel, applied by build.py over the
very auto picture it was drawn on (its hash kept in the file; a changed one is reported, not applied).

  python touchup.py RIVAL FRAME start   -> touchups/RIVAL/FRAME.txt, the auto picture to edit (if not there yet)
  python touchup.py RIVAL FRAME check   -> fresh (its auto picture unchanged) or stale
  python touchup.py RIVAL FRAMES show OUT.png -> auto | touched up, his head enlarged, in his palettes
(a mirrored frame: 56| is 56m)"""
import json, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build


def auto_pictures(rival):
    """The rival's pictures as build.py makes them before touch-ups (shrunk, aligned in his fight's palettes)."""
    r = build.NES_RIVALS[rival]
    p = json.loads(build.EXAMPLE.read_text())
    ft = [s for s in p["scenes"] if s.get("fight")][r["nth"]]["fight"]
    bg = p["palettes"]["bg"]
    pals = [bg[ft["rival"]["palettes"][k]]["colors"] for k in "sgh"]
    every = build.joe_shapes(r["opp"], everything=True)
    frames, _ = build.align_pictures(build.pictures_from_nes(0.7, every, r["opp"], build.blank_frames(r["opp"])), pals)
    return frames, pals


def legend_of(frames):
    """A letter for each of his colors, by what it is: K black (outline), W white, R red, H hair (orange), S skin;
    others A, B, C..."""
    cols = sorted({c[:3] for f in frames.values() for row in f for c in row if c}, key=lambda c: sum(c))
    out, spare = {}, iter("ABCDEFGIJLMNOPQTUVXYZ")
    out[cols[0]] = "K"
    for c in cols[1:]:
        r, g, b = c
        ch = ("W" if min(c) > 200 else "R" if g < 0.4 * r and b < 0.4 * r else "H" if b < 0.4 * r and g < 0.8 * r
              else "S" if r > 150 else None)
        out[c] = ch if ch and ch not in out.values() else next(spare)
    return out


def main():
    rival, keys, cmd = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
    frames, pals = auto_pictures(rival)
    d = build.TOUCHUPS / rival
    d.mkdir(parents=True, exist_ok=True)
    if cmd == "start":
        leg = legend_of(frames)
        for k in keys:
            path = d / f"{build.touchup_name(k)}.txt"
            if path.exists():
                print(path, "already there"); continue
            lines = [f"# {build.NES_RIVALS[rival]['name']}, picture {k}: touched up by hand (touchup.py; build.py applies it)",
                     f"auto {build.frame_hash(frames[k])}",
                     "legend .=- " + " ".join(f"{ch}={','.join(map(str, c))}" for c, ch in leg.items())]
            lines += ["".join(leg[c[:3]] if c else "." for c in row) for row in frames[k]]
            path.write_text("\n".join(lines) + "\n")
            print("wrote", path)
    elif cmd == "check":
        for k in keys:
            auto, _ = build.read_touchup(d / f"{build.touchup_name(k)}.txt")
            print(k, "fresh" if auto == build.frame_hash(frames[k]) else "STALE")
    elif cmd == "show":
        from PIL import Image
        out, Z, rows = sys.argv[4], 8, []
        for k in keys:
            path = d / f"{build.touchup_name(k)}.txt"
            pics = [frames[k]] + ([build.read_touchup(path)[1]] if path.exists() else [])
            im = Image.new("RGB", (64 * len(pics) + 4 * (len(pics) - 1), 32), (40, 40, 40))
            top = min(y for y, row in enumerate(frames[k]) for c in row if c)
            for n, f in enumerate(pics):
                for y in range(32):
                    for x in range(64):
                        c = f[top + y][x] if top + y < len(f) else None
                        im.putpixel((n * 68 + x, y), c[:3] if c else (8, 72, 192))
            rows.append(im.resize((im.width * Z, im.height * Z), Image.NEAREST))
        sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 6 for r in rows)), (20, 20, 20))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height + 6
        sheet.save(out)
        print(out)


if __name__ == "__main__":
    main()
