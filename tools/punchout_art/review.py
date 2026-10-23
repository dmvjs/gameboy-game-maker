"""One rival's pictures for review, a row each, most-shown first: the NES's own frame, and ours as Game Boy Color
shows it (touch-ups in, at whole zooms near the NES's size: no pixel drawn wider than another). Seconds, from the captures.

  python review.py RIVAL [FRAMES...]   -> out/RIVAL-review.png (FRAMES: just those; default all)"""
import json, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, touchup
from PIL import Image, ImageDraw

SCREEN_TIME = {"joe": ["C4", "3A", "34", "C0", "20", "22", "1E", "C2", "32", "2A"]}   # (bot fights: most shown first)


def main():
    rival, only = sys.argv[1], [f.replace("m", "|") for f in sys.argv[2:]]
    r = build.NES_RIVALS[rival]
    frames, pals = touchup.auto_pictures(rival)
    frames = build.apply_touchups(rival, frames)
    if rival in build.DESPECKLE:
        frames = build.despeckle(frames)
    pics = build.import_pictures(frames, pals)
    every = build.joe_shapes(r["opp"], everything=True)
    order = [k for k in SCREEN_TIME.get(rival, []) if k in pics] + sorted(k for k in pics if k not in SCREEN_TIME.get(rival, []))
    order = [k for k in order if not only or k in only]
    rgb = lambda c: tuple((v << 3) | (v >> 2) for v in c)
    Z = ZO = 4; rows = []          # (one zoom for both: true sizes side by side)
    for k in order:
        shape = every.get(build._key(k)) or {}
        if shape:
            xs, ys = [x for x, _ in shape], [y for _, y in shape]
            nes = Image.new("RGB", (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1), (8, 76, 196))
            for (x, y), c in shape.items():
                nes.putpixel((x - min(xs), y - min(ys)), tuple(c[:3]))
        else:
            nes = Image.new("RGB", (8, 8), (40, 40, 40))
        px, cells = pics[k]["pixels"], pics[k]["cells"]
        ours = Image.new("RGB", (build.RW, build.RH), (8, 76, 196))
        for i, ch in enumerate(px):
            if ch != "0":
                pal = pals[build.KINDS.index(cells[(i // build.RW // 8) * build.FIGHT_W + (i % build.RW) // 8])]
                ours.putpixel((i % build.RW, i // build.RW), rgb(pal[int(ch)]))
        bb = ours.getbbox() or (0, 0, 1, 1)
        ours = ours.crop((max(0, bb[0] - 1), max(0, bb[1] - 1), bb[2] + 1, bb[3] + 1))
        rows.append((k, nes, ours))
    W = max(n.width * Z + o.width * ZO for _, n, o in rows) + 60
    H = sum(max(n.height * Z, o.height * ZO) + 14 for _, n, o in rows)
    sheet = Image.new("RGB", (W, H), (24, 24, 24))
    d, y = ImageDraw.Draw(sheet), 0
    for k, nes, ours in rows:
        d.text((4, y + 2), f"{k}  NES | ours", fill=(255, 255, 0))
        sheet.paste(nes.resize((nes.width * Z, nes.height * Z), Image.NEAREST), (4, y + 14))
        sheet.paste(ours.resize((ours.width * ZO, ours.height * ZO), Image.NEAREST), (nes.width * Z + 24, y + 14))
        y += max(nes.height * Z, ours.height * ZO) + 14
    out = HERE / "out" / f"{rival}-review.png"
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
