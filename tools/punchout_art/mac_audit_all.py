"""Every one of Little Mac's frames (all of mac_nes's, not only those a fight happens to hold still): each put up
in the real game (cynes: his frame number and draw flag set mid-fight, his drawing left to the game's own code),
rendered with the sprites hidden (Mac is background), and looked for as mac_audit.py looks: his picture's shape,
each of its colors one of the NES's.

  python mac_audit_all.py   -> out/audit/mac-all.json; exit 1 on a mismatch"""
import collections, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
GOOD = 0.97


def judge(img, mine, my):
    h, w = len(mine), len(mine[0])
    mask = np.array([[c is not None for c in row] for row in mine])
    col = np.array([[c[:3] if c else (0, 0, 0) for c in row] for row in mine], dtype=np.int16)
    scr = np.asarray(img[:, :, :3], dtype=np.int16)
    n = int(mask.sum())
    best = (0, 0, 0)
    for y0 in range(max(0, my - 24), min(240 - h, my + 24) + 1):
        band = scr[y0:y0 + h]
        for x0 in range(0, 256 - w + 1):
            win = band[:, x0:x0 + w]
            hit = 2 * int(((win != (8, 76, 196)).any(axis=2) & mask).sum()) + int(((win == col).all(axis=2) & mask).sum())
            if hit > best[0]:
                best = (hit, x0, y0)
    x0, y0 = best[1], best[2]
    crop = [[tuple(int(v) for v in scr[y0 + y][x0 + x]) for x in range(w)] for y in range(h)]
    pairs = collections.Counter((mine[y][x][:3], crop[y][x]) for y in range(h) for x in range(w) if mine[y][x])
    to = {}
    for (a, b), k in pairs.most_common():
        to.setdefault(a, b)
    return sum(k for (a, b), k in pairs.items() if to[a] == b) / max(1, n)


def main():
    import cynes_frames as C, mac_nes, build
    from cynes import NES
    nes = NES(C.rom_path())

    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):
        run(4, C.START); nes[0x01] = 0; run(86)
        if nes[0x00] == 1:
            break
    run(400)
    base = nes.save()
    report = {}
    for key in sorted(build.MAC_FRAMES):
        if key == "3A":                 # (not him: GET UP!, the NES's words while he's down; the GB writes them itself)
            continue
        f = int(key, 16)
        got = mac_nes.mac_frame_at(f)
        if not got:
            continue
        mine, (mx, my) = got
        nes.load(base)
        nes[0x61], nes[0x60] = f, 0x80
        run(1)
        for p in range(0x204, 0x300, 4):
            nes[p] = 0xF8
        nes[0x17] = 1
        img = run(1).copy()
        report[key] = round(judge(img, mine, my), 3) if nes[0x61] == f else None
    bad = {k: v for k, v in report.items() if v is not None and v < GOOD}
    skipped = [k for k, v in report.items() if v is None]
    out = HERE / "out" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mac-all.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    print(f"Mac: {len(report) - len(skipped)} of {len(build.MAC_FRAMES)} frames judged, {len(bad)} mismatched:",
          " ".join(f"{k}={v}" for k, v in sorted(bad.items())), "| not held (the game moved on):", " ".join(skipped))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
