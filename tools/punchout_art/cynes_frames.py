"""An opponent's frames from cynes (an accurate NES emulator: its PPU and MMC2 bank latches exactly), for
the fighters whose frames switch CHR banks mid-sprite (nes_play's renderer only approximates that). Each
frame is rendered twice from one saved state, the second with every sprite hidden (the OAM buffer at $0200
blanked, $17 set so the NMI copies it): what differs is him (Mac and the referee are the background).

cynes_frames(opponent) -> {(frame, mirrored): (RGB crop 128x192 with None where he isn't, (x, y) of his
place in it)}, the per-pixel most common of a few looks (a hit's flash recolors him for a frame or two),
cached in out/nes-opp{n}-cynes.pkl. Needs out/po.nes (gamefiles builds it from your game files)."""
import collections, pickle, random
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
A, BTN_B, START, UP, DOWN, LEFT, RIGHT = 0x80, 0x40, 0x10, 0x08, 0x04, 0x02, 0x01
SAMPLES = 5


def rom_path():
    import gamefiles, hashlib
    out = HERE / "out" / "po.nes"
    if not out.exists():
        d = gamefiles.banks()
        body = b"".join((d / f"PRG_Bank{k:03X}.bin").read_bytes() for k in range(13)) + (d / "PRG_BankDEF.bin").read_bytes() \
             + b"".join((d / f"CHR_Bank{k:03X}.bin").read_bytes() for k in range(32))
        assert hashlib.sha1(body).hexdigest() == gamefiles.SHA1
        out.write_bytes(b"NES\x1a\x08\x10\x90\x00" + bytes(8) + body)
    return str(out)


def cynes_frames(opponent, frames=40000, cache=True, styles=None, want=None):
    path = HERE / "out" / f"nes-opp{opponent}-cynes.pkl"
    if cache and path.exists():
        return pickle.load(open(path, "rb"))
    old = pickle.load(open(path, "rb")) if path.exists() else {}
    from cynes import NES
    nes = NES(rom_path())
    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):                     # Start through the title and the challenger screen (his)
        run(4, START); nes[0x01] = opponent; run(86)
        if nes[0x00] == 1 and nes[0x90] & 0x7F == 0x40:
            break
    start = nes.save()
    looks = collections.defaultdict(list)
    rng = random.Random(1)
    held = hold = 0
    last, still = None, 0
    styles = styles or ["aggressive", "standing", "defensive", "mixed"]
    for n in range(frames):
        style = styles[(n // 3000) % len(styles)]
        if hold <= 0:
            held = {"aggressive": lambda: rng.choice([UP | A, UP | BTN_B, A, BTN_B, 0, LEFT, RIGHT]),
                    "standing": lambda: 0 if rng.random() < 0.97 else A,
                    "defensive": lambda: rng.choice([LEFT, RIGHT, DOWN, 0, 0]),
                    "mixed": lambda: rng.choice([A, BTN_B, UP | A, UP | BTN_B, LEFT, RIGHT, DOWN, 0]),
                    "pressing": lambda: rng.choice([UP | A, UP | BTN_B, A, BTN_B, 0, LEFT, RIGHT])}[style]()
            hold = rng.randrange(2, 15)
        hold -= 1
        btn = held
        if nes[0x05] == 2:                  # Mac down: up
            btn = A if n & 2 else 0
        if nes[0x00] != 1 and n % 60 < 3:
            btn = START
        if nes[0x00] in (0xFB, 0xFC, 0xFD, 0xFE) and n % 600 == 599:
            nes.load(start)                 # (the fight over: again)
        if style in ("aggressive", "mixed", "pressing") and nes[0x05] == 0:
            for a in (0x398, 0x399):        # (his health low: his knockdowns)
                if nes[a] > 4:
                    nes[a] = 4
        run(1, btn)
        key = nes[0xA1]
        still = still + 1 if key == last else 0
        last = key
        if still == 2 and nes[0x00] in (1, 0xFC, 0xFE):
            oam = [nes[a] for a in range(0x200, 0x300)]
            shown = [oam[i + 2] for i in range(0, 256, 4) if oam[i] < 0xEF]
            if not shown:
                continue
            mirrored = int(sum(1 for i in range(0, 256, 4) if oam[i] < 0xEF and oam[i + 2] & 0x40) * 2 > len(shown))
            k = (key, mirrored)
            if len(looks[k]) >= SAMPLES or (want and key not in want):
                continue
            s = nes.save()
            a = run(1).copy()
            nes.load(s)
            for p in range(0x200, 0x300, 4):
                nes[p] = 0xF8
            nes[0x17] = 1
            b = run(1).copy()
            nes.load(s)
            x, y = nes[0xB0], nes[0xB1]
            x0, y0 = max(0, min(256 - 128, x - 64)), max(0, min(240 - 192, y - 158))
            mask = (a != b).any(axis=2)
            crop = [[tuple(int(v) for v in a[y0 + j][x0 + i]) if mask[y0 + j][x0 + i] else None for i in range(128)]
                    for j in range(192)]
            looks[k].append((crop, (x - x0, y - y0)))
    got = {}
    for k, ls in looks.items():             # each pixel: its most common look (at the most common place)
        if not ls:
            continue
        place = collections.Counter(p for _, p in ls).most_common(1)[0][0]
        ls = [c for c, p in ls if p == place]
        crop = [[collections.Counter(c[j][i] for c in ls).most_common(1)[0][0] for i in range(128)] for j in range(192)]
        got[k] = (crop, place)
    path.parent.mkdir(exist_ok=True)
    got = {**old, **got}                    # (added to what an earlier capture found)
    pickle.dump(got, open(path, "wb"))
    return got
