"""Punch-Out!!'s screens between the fights that aren't a fighter's, from the game itself (cynes, played; cached):
"NEXT IS ... TITLE BOUT!!" before each circuit's title bout, the KO News page after the World Circuit's (its paper
creeping up into place) and THE DREAM FIGHT!! after it, their big letters' colors in turn; for the Game Boy at 5/8
the NES's size (its 160 x 144 to the NES's 256 x 240), the words in the Game Boy's own font around them.

  screens() -> dict for the template (NES_SCREENS)"""
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
CACHE = HERE / "out" / "nes-screens.pkl"
SCALE = 0.625
ORANGE = (212, 136, 32)                         # the big letters' own color, before and after their turn of colors


def _frames():
    """The NES's frames: TITLE BOUT!! (after Von Kaiser beaten), the KO News page and THE DREAM FIGHT!! (after Super
    Macho Man), each settled; and the big letters' colors in turn (a pixel of them, a frame at a time)."""
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    import numpy as np
    import nes_reference as R

    def after_win(opp, presses, until, at):
        nes = R._start(opp)
        for _ in range(4):
            nes.controller = R.START
            nes.step()
        t, tf, won, shots, seq = 0, None, None, {}, []
        while won is None or t - won <= until:
            if nes[0x00] == 1 and tf is None:
                tf = t
            if tf is not None and won is None and t - tf == 200:
                nes[0x00] = 0xFC
            if tf is not None and won is None and nes[0x00] != 1 and t - tf > 210:
                won = t
            k = t - won if won is not None else -1
            nes.controller = R.START if any(p <= k < p + 4 for p in presses) else 0
            f = nes.step()
            t += 1
            if k + 1 in at:
                shots[k + 1] = np.asarray(f[:, :, :3]).copy()
            seq.append(np.asarray(f[:, :, :3]).copy() if won is not None else None)
        return shots, [s for s in seq if s is not None]
    tb, tbseq = after_win(1, [400], 870, {514})
    news, newsseq = after_win(12, [400, 1200], 1570, {448, 703, 1249})
    got = {"title_bout": tb[514], "news": news[703], "news_first": news[448], "dream": news[1249],
           "tb_seq": [tuple(int(v) for v in f[80, 64]) for f in tbseq[500:870]],
           "dream_seq": [tuple(int(v) for v in f[24, 80]) for f in newsseq[1240:1570]]}
    CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(CACHE, "wb"))
    return got


CHAMP_CACHE = HERE / "out" / "nes-champion.pkl"


def _champ_frames():
    """The NES's title-bout win screens (Mac, a trophy: the circuit's), settled: the Minor's, Major's and World's."""
    if CHAMP_CACHE.exists():
        return pickle.load(open(CHAMP_CACHE, "rb"))
    import numpy as np
    import nes_reference as R
    got = {}
    for opp, name in ((2, "minor"), (6, "major"), (12, "world")):
        nes = R._start(opp)
        for _ in range(4):
            nes.controller = R.START
            nes.step()
        nes.controller = 0
        t, tf, won = 0, None, None
        while t < 6000:
            f = nes.step()
            t += 1
            if nes[0x00] == 1 and tf is None:
                tf = t
            if tf is not None and won is None and t - tf == 200:
                nes[0x00] = 0xFC
            if tf is not None and won is None and nes[0x00] != 1 and t - tf > 210:
                won = t
            if won is not None and t - won == 600:
                got[name] = np.asarray(f[:, :, :3]).copy()
                break
    CHAMP_CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(CHAMP_CACHE, "wb"))
    return got


def _celled(img, box, colors, pals, near):
    """The box at 5/8 (it lands on whole tiles: its top-left on one), each 8x8 cell in whichever of pals (slot 1-3
    colors, as indices into colors; 0 the backdrop) shows its pixels best, a color not in it its near one's."""
    a = _scaled(img, box, colors)
    w, h, px = a["w"], a["h"], [int(c) for c in a["pixels"]]
    W, H = (w + 7) // 8 * 8, (h + 7) // 8 * 8
    grid = [[px[y * w + x] if x < w and y < h else 0 for x in range(W)] for y in range(H)]
    out, cells = [[0] * W for _ in range(H)], []
    for cy in range(H // 8):
        for cx in range(W // 8):
            used = [grid[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)]
            def slot(c, p):
                c2 = c
                while c2 and c2 not in p:
                    c2 = near.get(c2, 0)
                return 0 if not c2 else p.index(c2) + 1
            cost = lambda p: sum(1 for c in used if c and (c not in p))
            k = min(range(len(pals)), key=lambda k: cost(pals[k]))
            cells.append(k)
            for y in range(8):
                for x in range(8):
                    out[cy * 8 + y][cx * 8 + x] = slot(grid[cy * 8 + y][cx * 8 + x], pals[k])
    return {"w": W, "h": H, "pixels": "".join(str(v) for r in out for v in r), "cells": cells}


def _scaled(img, box, colors, ink=False):
    """The box of the frame at 5/8, each pixel the color covering most of its area (one of colors -> its index); ink:
    the darkest (the last of colors) wherever it covers a third, so lettering's thin strokes hold."""
    x0, y0, x1, y1 = box
    w, h = round((x1 - x0) * SCALE), round((y1 - y0) * SCALE)
    out = []
    for y in range(h):
        for x in range(w):
            ya, yb, xa, xb = y0 + y / SCALE, y0 + (y + 1) / SCALE, x0 + x / SCALE, x0 + (x + 1) / SCALE
            vote = {}
            for yy in range(int(ya), -int(-yb // 1)):
                for xx in range(int(xa), -int(-xb // 1)):
                    a = (min(yb, yy + 1) - max(ya, yy)) * (min(xb, xx + 1) - max(xa, xx))
                    if a > 0:
                        c = tuple(int(v) for v in img[yy][xx])
                        k = colors.index(c) if c in colors else 0
                        vote[k] = vote.get(k, 0) + a
            total = sum(vote.values())
            dark = len(colors) - 1
            out.append(dark if ink and vote.get(dark, 0) >= total / 3 else max(vote, key=vote.get))
    return {"w": w, "h": h, "pixels": "".join(map(str, out))}


def _cycle(seq):
    """The big letters' colors in turn: when they start turning, how long each holds, the colors, how many rounds."""
    start = next(k for k, c in enumerate(seq) if c == ORANGE)
    runs = []
    for c in seq[start:]:
        if runs and runs[-1][0] == c:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    colors = [c for c, _ in runs[1:13]]        # (twelve: the last orange again)
    turns = [c for c, _ in runs[1:]]
    loops = 0
    while turns[loops * 12:loops * 12 + 12] == colors:
        loops += 1
    held = runs[loops * 12][1]                 # (the last round's orange, held, then the fade)
    return {"after": runs[0][1], "every": runs[1][1], "colors": colors, "loops": loops, "hold": held}


def _champion(s5, navy):
    """A title bout won: Mac on the left, the circuit's trophy on the right (the NES's art at 5/8, on whole tiles:
    Mac from tile row 9 at the left edge, the trophy's tiles at columns 17-19), each tile in one of their palettes."""
    f = _champ_frames()
    black, skin, blue, red, white = (0, 0, 0), (236, 180, 176), (76, 154, 236), (152, 34, 32), (236, 238, 236)
    gold, brown, cream = (212, 136, 32), (60, 24, 0), (228, 196, 144)
    mac_colors = [navy, skin, red, blue, white, black]          # (indices: 1 skin, 2 red, 3 blue, 4 white, 5 black)
    mac_pals = [[1, 2, 5], [1, 3, 5], [4, 1, 5]]
    y0 = 24 + (72 - 8) / SCALE                                  # (tile row 9: the NES's y there, its header at 8)
    mac = _celled(f["major"], (20, round(y0), 72, round(y0) + 112), mac_colors, mac_pals, {4: 1, 3: 2, 2: 3})
    mac["palettes"] = [[s5(navy)] + [s5(mac_colors[c]) for c in p] for p in mac_pals]
    mac["greys"] = [[3, 0, 1, 2], [3, 0, 1, 2], [3, 0, 0, 2]]   # (the original, light on black: his black dark grey)
    tro_colors = [navy, cream, gold, brown, white, black]
    tro_pals = [[1, 2, 5], [2, 3, 5]]
    trophies = {}
    for k in ("minor", "major", "world"):
        x0 = 203                                                # (from 5 left of the World's: on tile column 17, its 3)
        t = _celled(f[k], (x0, round(y0), x0 + 38, round(y0) + 112), tro_colors, tro_pals, {4: 1, 3: 5})
        t["palettes"] = [[s5(navy)] + [s5(tro_colors[c]) for c in p] for p in tro_pals]
        t["greys"] = [[3, 0, 1, 2], [3, 1, 2, 2]]
        trophies[k] = t
    return {"mac": mac, "trophies": trophies, "row": 9,
            "lines": [["LADIES AND", 80], ["GENTLEMEN!", 89], ["WE HAVE A NEW", 104], ["CHAMPION!!", 113]]}


def screens():
    import build
    f = _frames()
    s5 = lambda c: build.from8(c)
    tb, df = f["title_bout"], f["dream"]
    navy, cyan, red, light = (8, 16, 144), (56, 180, 204), (152, 34, 32), (236, 106, 100)
    letters = lambda img, box: _scaled(img, box, [navy, ORANGE])
    paper, white, dark, black = (152, 150, 152), (236, 238, 236), (84, 84, 84), (0, 0, 0)
    news = f["news"]
    piece = lambda box, ink=False: _scaled(news, box, [white, paper, dark, black], ink)
    tcy, dcy = _cycle(f["tb_seq"]), _cycle(f["dream_seq"])
    return {
        "navy": s5(navy), "cyan": s5(cyan), "orange": s5(ORANGE), "glove": [s5(red), s5(light)],
        "titleBout": {"letters": letters(tb, (48, 80, 208, 176)), "y": 80, "music": 0x08,
                      **{k: tcy[k] for k in ("after", "every", "loops", "hold")}},
        "dreamFight": {"letters": letters(df, (40, 24, 216, 176)), "y": 24, "music": 0x0E,
                       **{k: dcy[k] for k in ("after", "every", "loops", "hold")},
                       "lines": ["LADIES", "AND", "GENTLEMEN !", "KID DYNAMITE,", "MIKE TYSON"]},
        "cycleColors": [s5(c) for c in tcy["colors"]],
        "champion": _champion(s5, navy),
        "news": {"colors": [s5(white), s5(paper), s5(dark), s5(black)], "music": 0x04,
                 "from": 32, "every": 8,                       # (the page 32 lines low, a line up every 8 frames)
                 "masthead": piece((0, 0, 240, 34), True), "headline": piece((116, 48, 230, 72), True),
                 "photo": piece((16, 54, 108, 170)), "macho": piece((202, 182, 236, 216))},
    }


if __name__ == "__main__":
    import json
    d = screens()
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: (vv if not isinstance(vv, dict) else (vv.get("w"), vv.get("h")))
                                                               for kk, vv in v.items()}) for k, v in d.items()}, indent=1)[:3000])
