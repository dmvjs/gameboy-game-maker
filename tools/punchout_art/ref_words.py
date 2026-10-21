"""The referee's words as the NES game draws them (cynes, the real game; the bot plays, buttons only): his speech
bubbles beside him -- the count's 1-10 and "KO!" from a fight won by a KO, "TKO" from one won by three knockdowns
in a round, "Fight!" from a round's start -- each as its pixels around his cap's top-left (white and black).

  words() -> {"1": {(x, y): (r, g, b)}, ..., "10", "KO", "TKO", "FIGHT"}   (cached: out/nes-ref-words.pkl)"""
import pickle, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
CACHE = HERE / "out" / "nes-ref-words.pkl"
FLOOR, CAP, SKIN, WHITE, BLACK = (8, 76, 196), (152, 34, 32), (236, 180, 176), (236, 238, 236), (0, 0, 0)


def _pieces(img, y0=100, y1=230):
    import numpy as np
    H, W, _ = img.shape
    on = np.zeros((H, W), bool)
    on[y0:y1] = (img[y0:y1] != FLOOR).any(2)
    lab = -np.ones((H, W), int)
    out = []
    for y, x in zip(*np.where(on)):
        if lab[y, x] >= 0:
            continue
        st, g = [(y, x)], []
        lab[y, x] = len(out)
        while st:
            a, b = st.pop()
            g.append((a, b))
            for c, d in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                if 0 <= c < H and 0 <= d < W and on[c, d] and lab[c, d] < 0:
                    lab[c, d] = len(out)
                    st.append((c, d))
        out.append(g)
    return out


def bubble(img):
    """The bubble beside the referee in a frame: {(x, y) from his cap's top-left: color}, or None."""
    import numpy as np
    col = lambda a, b: tuple(int(v) for v in img[a, b])
    ps, him = _pieces(img), None
    for g in ps:                        # (him: cap, skin, shirt and black only -- a fighter's gloves share the red)
        cs = {col(a, b) for a, b in g}
        if {CAP, SKIN, WHITE} <= cs <= {CAP, SKIN, WHITE, BLACK} and (him is None or len(g) > len(him)):
            him = g
    if him is None:
        return None
    cy = min(a for a, b in him if col(a, b) == CAP)
    cx = min(b for a, b in him if col(a, b) == CAP)
    px = {}
    for g in ps:
        if g is him or len(g) <= 20 or not {col(a, b) for a, b in g} <= {WHITE, BLACK}:
            continue
        if abs(np.mean([a for a, _ in g]) - (cy + 12)) < 16 and -60 < np.mean([b for _, b in g]) - cx < 70:
            px.update({(b - cx, a - cy): col(a, b) for a, b in g})
    if not px:
        return None
    xs, ys = [x for x, _ in px], [y for _, y in px]
    for a in range(min(ys) + cy, max(ys) + cy + 1):        # (the letters inside it, black)
        for b in range(min(xs) + cx, max(xs) + cx + 1):
            if col(a, b) == BLACK:
                px.setdefault((b - cx, a - cy), BLACK)
    return px


def _fight(opp, each, frames, tko=False):
    """The bot (buttons only) in a fight; each(nes, img) every frame shown."""
    import cynes_frames as C, frame_audit as F
    from cynes import NES
    from gbstage import bot
    nes = NES(C.rom_path())

    def run(n, b=0):
        for _ in range(n):
            nes.controller = b
            nes.step()
    run(600)
    for _ in range(40):
        run(4, C.START); nes[0x01] = opp; run(86)
        if nes[0x00] == 1:
            break
    g = F.NesGame(nes, nes.save(), 0, lambda: None)

    def tick(render=True):
        if tko and nes[0x05] != 1:
            nes[0x03CA] = 2              # (two knockdowns this round already: the next is the TKO)
        g.c.controller = sum(F.BITS[b] for b in g.held)
        img = g.c.step()
        if render:
            each(nes, img)
    g.tick = tick
    game, bot.Game = bot.Game, lambda *a, **k: g
    try:
        bot.play("", 0, frames=frames)
    finally:
        bot.Game = game


def words():
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    import numpy as np
    import cynes_frames as C
    from cynes import NES
    got = {}
    st = {"c1": None, "since": 0}

    def ko(nes, img):                   # each number 20 frames after the count reaches it; KO! once said
        img = np.asarray(img[:, :, :3])
        if nes[0x05] == 1:
            c = nes[0xC1] - 0x99
            st["since"] = 0 if c != st["c1"] else st["since"] + 1
            st["c1"] = c
            if 1 <= c <= 10 and st["since"] == 20 and str(c) not in got:
                got[str(c)] = bubble(img)
        if nes[0xF4] == 0x0E or st.get("ko"):
            st["ko"] = st.get("ko", 0) + 1
            b = bubble(img) if st["ko"] > 8 and "KO" not in got else None
            if b and min(x for x, _ in b) > 0:          # (right of him, his arm up)
                got["KO"] = b
    _fight(0, ko, 6000)

    def tko(nes, img):
        if nes[0x05] == 1 or st.get("t"):
            st["t"] = st.get("t", 0) + 1
            if st["t"] == 400:
                got["TKO"] = bubble(np.asarray(img[:, :, :3]))
    _fight(0, tko, 6000, tko=True)

    nes = NES(C.rom_path())             # "Fight!": the round's start, nothing pressed
    frames = []
    for n in range(600 + 40 * 90 + 900):
        nes.controller = C.START if 600 <= n < 3600 and (n - 600) % 90 < 4 and nes[0x00] != 1 else 0
        if 600 <= n < 3600 and (n - 600) % 90 == 4:
            nes[0x01] = 0
        img = nes.step()
        if nes[0x00] == 1:
            b = bubble(np.asarray(img[:, :, :3]))
            if b and min(x for x, _ in b) < -30:        # (the long one, left of him)
                frames.append(b)
    got["FIGHT"] = frames[len(frames) // 2]
    missing = [k for k in [str(n) for n in range(1, 11)] + ["KO", "TKO", "FIGHT"] if not got.get(k)]
    assert not missing, f"the referee's words not seen: {missing}"
    CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(CACHE, "wb"))
    return got
