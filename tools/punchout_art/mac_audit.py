"""Little Mac's frames as the NES draws them, checked against the pictures the Game Boy shows him in (mac_nes.py's,
from the NES's own code). cynes (the accurate emulator) plays fights against each opponent (the bot's, buttons
only); each frame Mac's shown in is rendered with every sprite hidden (sprite 0 kept: its hit splits the screen's
scroll), and his picture (mac_nes.mac_frame_at) looked for in it near where the NES puts it: the share of his
pixels found there, each of his colors one of the NES's (its palette as the fight sets it).

  python mac_audit.py [OPP ...] [--frames N]  -> out/audit/mac.json, mac.png (NES | ours); exit 1 on a mismatch"""
import collections, json, random, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
GOOD = 0.97
import build
MAC_KEYS = set(build.MAC_FRAMES)
LOOKS = 4


def audit(opps, frames):
    import cynes_frames as C, mac_nes, frame_audit as F
    from cynes import NES
    from gbstage import bot
    ours = {}
    results = collections.defaultdict(list)          # frame -> [(score, nes crop, (x, y))]
    for opp in opps:
        nes = NES(C.rom_path())

        def run(n, b=0):
            f = None
            for _ in range(n):
                nes.controller = b
                f = nes.step()
            return f
        run(600)
        for _ in range(40):
            run(4, C.START); nes[0x01] = opp; run(86)
            if nes[0x00] == 1:
                break
        state = {"last": None, "still": 0}

        def look():
            if nes[0x00] != 1 or nes[0x01] != opp:
                return
            f = nes[0x61]
            state["still"] = state["still"] + 1 if f == state["last"] else 0
            state["last"] = f
            if state["still"] != 2 or len(results[f]) >= LOOKS:
                return
            if "%02X" % f not in MAC_KEYS:     # (the referee's count, a bubble: not him)
                return
            if f not in ours:
                ours[f] = mac_nes.mac_frame_at(f)
            if not ours[f]:
                return
            s = nes.save()
            for p in range(0x204, 0x300, 4):
                nes[p] = 0xF8
            nes[0x17] = 1
            img = run(1).copy()
            nes.load(s)
            mine, (mx, my) = ours[f]
            import numpy as np
            h, w = len(mine), len(mine[0])
            mask = np.array([[c is not None for c in row] for row in mine])
            col = np.array([[c[:3] if c else (0, 0, 0) for c in row] for row in mine], dtype=np.int16)
            scr = np.asarray(img[:, :, :3], dtype=np.int16)
            n = int(mask.sum())
            best = (0, 0, 0)
            for y0 in range(max(0, my - 16), min(240 - h, my + 16) + 1):          # (his band scrolls sideways)
                band = scr[y0:y0 + h]
                for x0 in range(0, 256 - w + 1, 1):
                    win = band[:, x0:x0 + w]          # (where he's drawn, not the canvas; then his colors)
                    hit = 2 * int(((win != (8, 76, 196)).any(axis=2) & mask).sum()) + int(((win == col).all(axis=2) & mask).sum())
                    if hit > best[0]:
                        best = (hit, x0, y0)
            if best[0] == 0:  # (nothing)
                results[f].append((0.0, [[(0, 0, 0)] * w for _ in range(h)]))
                return
            x0, y0 = best[1], best[2]
            crop = [[tuple(int(v) for v in scr[y0 + y][x0 + x]) for x in range(w)] for y in range(h)]
            pairs = collections.Counter((mine[y][x][:3], crop[y][x]) for y in range(h) for x in range(w) if mine[y][x])
            to = {}                                    # (his palette's as the fight sets it: each of ours, one of the
            for (a, b), k in pairs.most_common():      # NES's, kept to)
                to.setdefault(a, b)
            score = sum(k for (a, b), k in pairs.items() if to[a] == b) / n
            results[f].append((score, crop))
        g = F.NesGame(nes, nes.save(), 0, look)
        game, bot.Game = bot.Game, lambda *a, **k: g
        try:
            bot.play("", 0, frames=frames)
        finally:
            bot.Game = game
        print(f"opp {opp}: Mac frames seen {len(results)}", flush=True)
    return results, ours


if __name__ == "__main__":
    args = sys.argv[1:]
    frames = 6000
    if "--frames" in args:
        i = args.index("--frames")
        frames = int(args[i + 1])
        del args[i:i + 2]
    opps = [int(a) for a in args] or [0, 6, 13]
    results, ours = audit(opps, frames)
    report = {"%02X" % f: round(sorted(s for s, _ in ls)[len(ls) // 2], 3) for f, ls in results.items() if ls}
    bad = {k: v for k, v in report.items() if v < GOOD}
    out = HERE / "out" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mac.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    from PIL import Image, ImageDraw
    if bad:
        keys = sorted(bad)
        im = Image.new("RGB", (160 * min(6, len(keys)), 130 * ((len(keys) + 5) // 6)), (40, 40, 40))
        d = ImageDraw.Draw(im)
        for n, k in enumerate(keys):
            f = int(k, 16)
            crop = sorted(results[f], key=lambda t: t[0])[len(results[f]) // 2][1]
            mine = ours[f][0]
            ox, oy = 160 * (n % 6), 130 * (n // 6)
            for y, row in enumerate(crop[:110]):
                for x, c in enumerate(row[:75]):
                    im.putpixel((ox + x, oy + y), c)
            for y, row in enumerate(mine[:110]):
                for x, c in enumerate(row[:75]):
                    if c:
                        im.putpixel((ox + 80 + x, oy + y), c[:3])
            d.text((ox + 2, oy + 116), f"{k} NES | ours {bad[k]}", fill=(255, 255, 0))
        im.save(out / "mac.png")
    print(f"Mac: {len(report)} frames judged, {len(bad)} mismatched:", " ".join(sorted(bad)))
    sys.exit(1 if bad else 0)
