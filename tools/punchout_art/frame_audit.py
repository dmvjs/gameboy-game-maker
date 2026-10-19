"""Every opponent frame the NES draws, checked against the art the Game Boy shows for it. cynes (the accurate
emulator) plays each fight: the walk-in, fighting in several styles, his knockdowns and getting up, the end. Each
frame he's drawn in is cropped (him alone: two renders of one state, the second with his sprites hidden; sprite 0
stays, its hit splits the screen's scroll), a few looks of each merged pixel by pixel (Mac in front of him, a hit's
flash: the most common look wins), and the result compared, from his place, with the capture the Game Boy's picture
for that frame is made from (out/nes-opp{n}-play.pkl, as build.py's joe_shapes reads it).

  python frame_audit.py [OPP ...] [--frames N] [--fights N] [--fix]
      -> out/audit/opp{n}.json (mismatched frames), opp{n}.png (NES | ours), out/nes-opp{n}-audit.pkl (the
         merged looks); --fix puts the merged look in the capture for each mismatched frame. Exit 1 on a mismatch.

Needs out/po.nes (gamefiles builds it from your game files)."""
import collections, json, os, pickle, random, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
A, BTN_B, START, UP, DOWN, LEFT, RIGHT = 0x80, 0x40, 0x10, 0x08, 0x04, 0x02, 0x01
OPPS = [0, 1, 2, 3, 4, 5, 6, 8, 11, 12, 13]
GOOD = 0.99                     # of the two's pixels together, drawn the same color at the same place
LOOKS = 15                      # looks of a frame kept to merge
DEBUG = __import__("os").environ.get("AUDIT_DEBUG")
MIN_LOOKS = 3                   # (a frame seen less: not judged, too few looks to merge)


def rel(img, place):
    px, py = place
    return {(x - px, y - py): tuple(c) for y, r in enumerate(img) for x, c in enumerate(r) if c}


def merge(looks):
    """His pixels as most looks have them, from his place: a pixel's most common color, if it's there in at
    least half the looks (Mac, in front of him in some, hides a few; a hit's flash recolors one or two)."""
    count = collections.defaultdict(collections.Counter)
    for look in looks:
        for p, c in look.items():
            count[p][c] += 1
    return {p: cs.most_common(1)[0][0] for p, cs in count.items() if sum(cs.values()) * 2 >= len(looks)}


def body(px):
    """Him, without specks apart from him (a sweat drop, a spark, a star: sprites of their own, not his
    picture; a strip at the screen's edge): pieces more than 2 pixels from him (8, 12 pixels or more: boots
    drawn apart)."""
    pieces, seen = [], set()
    for p0 in px:
        if p0 in seen:
            continue
        g, st = {p0}, [p0]
        while st:
            x, y = st.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    if q in px and q not in g:
                        g.add(q); st.append(q)
        seen |= g
        pieces.append(g)
    if not pieces:
        return px
    main = max(pieces, key=len)
    keep = set(main)
    for g in pieces:
        if g is not main and any(abs(x - a) <= (8 if len(g) >= 12 else 2) and abs(y - b) <= (8 if len(g) >= 12 else 2)
                                 for x, y in g for a, b in main):
            keep |= g
    return {p: px[p] for p in keep}


def score(a, b, shape=False):
    both = set(a) | set(b)
    if not both:
        return 1.0
    if shape:
        return len(set(a) & set(b)) / len(both)
    return sum(1 for p in both if a.get(p) == b.get(p)) / len(both)


BITS = {"a": 0x80, "b": 0x40, "select": 0x20, "start": 0x10, "up": 0x08, "down": 0x04, "left": 0x02, "right": 0x01}


class NesGame:
    """gbstage/bot.py's Game on the NES itself (cynes): the same NES RAM the Game Boy's fight keeps, so the bot
    plays the original as it plays the port. hScene: the fight's until it's won or lost; hFtActive: fighting."""

    def __init__(self, nes, start, scene, on_tick):
        self.c, self.scene, self.on_tick = nes, scene, on_tick
        self.c.load(start)
        self.held = set()

    def nes(self, a):
        return self.c[a]

    def hram(self, name):
        mode = self.c[0x00]
        if name == "hScene":
            return -1 if mode in (0xFB, 0xFC, 0xFD, 0xFE) else self.scene
        return 1 if mode == 1 else 0

    def hold(self, buttons):
        self.held = set(buttons)

    def tick(self, render=True):
        self.c.controller = sum(BITS[b] for b in self.held)
        self.c.step()
        if render:
            self.on_tick()

    def save(self):
        return self.c.save(), set(self.held)

    def load(self, snap):
        self.c.load(snap[0])
        self.held = set(snap[1])

    def stop(self):
        pass


def audit(opp, frames, fights=6):
    import cynes_frames as C
    from cynes import NES
    ref = {k: rel(*v) for k, v in pickle.load(open(HERE / "out" / f"nes-opp{opp}-play.pkl", "rb")).items()}
    nes = NES(C.rom_path())

    def run(n, b=0):
        f = None
        for _ in range(n):
            nes.controller = b
            f = nes.step()
        return f
    run(600)
    for _ in range(40):                 # Start through the title and his challenger screen, to his walk-in
        run(4, START); nes[0x01] = opp; run(86)
        if nes[0x00] == 1:
            break
    start = nes.save()

    def crop():
        """(mirrored, {(x, y) from his place: color}): his sprites alone, the background off (none of his colors
        lost where they match what's behind him; all of him, Mac in front of him or not). A pixel not the
        backdrop's is his; where his own colors include the backdrop's, also any the sprites change over the
        background (sprite 0 kept: its hit splits the screen's scroll)."""
        key0, pos0 = nes[0xA1], (nes[0xB0], nes[0xB1])
        s = nes.save()
        run(1)                          # (the next frame's sprites: the ones the render shows)
        oam = [nes[a] for a in range(0x200, 0x300)]
        shown = [i for i in range(4, 256, 4) if oam[i] < 0xEF]
        if not shown or nes[0xA1] != key0:
            nes.load(s)
            return None
        mirrored = int(sum(1 for i in shown if oam[i + 2] & 0x40) * 2 > len(shown))
        tiles = tuple(oam[i + 1] for i in shown)
        x, y = nes[0xB0], nes[0xB1]
        drawn = nes.save()
        run(1)                          # (him still: not knocked back or stepping, his sprites mid-move)
        moved = (x, y) != pos0 or (nes[0xB0], nes[0xB1]) != pos0
        nes.load(drawn)
        if moved:
            nes.load(s)
            return None
        nes[0x200] = 0xF8               # (sprite 0: not his)
        nes[0x2001] = 0x14
        solo = run(1).copy()
        nes.load(drawn)
        back = solo[239][0]
        mask = (solo != back).any(axis=2)
        if nes[0x480] in [nes[a] for a in range(0x490, 0x4A0) if a % 4]:
            a = run(1).copy()
            nes.load(drawn)
            for p in range(0x204, 0x300, 4):
                nes[p] = 0xF8
            nes[0x17] = 1
            b = run(1).copy()
            mask |= (a != b).any(axis=2)
        nes.load(s)
        js, is_ = mask.nonzero()
        return mirrored, (tiles, {(int(i) - x, int(j) - y): tuple(int(v) for v in solo[j][i]) for j, i in zip(js, is_)})

    for _ in range(2000):               # (past his walk-in, waiting: where each of his states is forced from)
        nes[0x391] = 0x60
        run(1)
        if nes[0x00] == 1 and nes[0x90] & 0x7F == 1:
            break
    waiting = nes.save()
    rng = random.Random(opp)
    held = hold = 0
    last, still = None, 0
    seen = collections.Counter()
    looks = collections.defaultdict(list)
    where = {}
    states = set()
    restarts = collections.Counter()
    drawn = collections.Counter()
    styles = ["standing", "aggressive", "defensive", "mixed"]
    for n in range(frames):
        style = styles[(n // 2500) % len(styles)]
        if hold <= 0:
            held = {"aggressive": lambda: rng.choice([UP | A, UP | BTN_B, A, BTN_B, 0, LEFT, RIGHT]),
                    "standing": lambda: 0 if rng.random() < 0.97 else A,
                    "defensive": lambda: rng.choice([LEFT, RIGHT, DOWN, 0, 0]),
                    "mixed": lambda: rng.choice([A, BTN_B, UP | A, UP | BTN_B, LEFT, RIGHT, DOWN, 0])}[style]()
            hold = rng.randrange(2, 15)
        hold -= 1
        btn = held
        if nes[0x05] == 2:              # Mac down: up
            btn = A if n & 2 else 0
        if nes[0x00] != 1 and n % 60 < 3:
            btn = START
        if nes[0x01] != opp or nes[0x00] in (0xFB, 0xFC, 0xFD, 0xFE) and n % 300 == 299:
            nes.load(start)             # (the fight over, or on to the next one: again, from the walk-in)
            restarts[nes[0x00]] += 1
        nes[0x391] = 0x60               # (Mac's health kept: the fight goes on, every round, all his moves)
        if style in ("aggressive", "mixed") and nes[0x05] == 0:
            for a in (0x398, 0x399):    # (his health low: his knockdowns)
                if nes[a] > 4:
                    nes[a] = 4
        run(1, btn)
        if nes[0x00] == 1 and nes[0x01] == opp:
            states.add(nes[0x90] & 0x7F)
        key = nes[0xA1]
        drawn[(nes[0x00], key)] += 1
        still = still + 1 if key == last else 0
        last = key
        if still < 1 or nes[0x00] != 1:     # (the frame he changes on: his sprites are last frame's; only
            continue                        # the fight itself, not the referee's sprites between rounds)
        if len(looks[(key, 0)]) >= LOOKS and len(looks[(key, 1)]) >= LOOKS:
            continue
        got = crop()
        if not got:
            continue
        mi, look = got
        k = (key, mi)
        seen[k] += 1
        if len(looks[k]) < LOOKS and seen[k] % 2:
            looks[k].append(look)
            where.setdefault(k, (n, nes[0x90]))
    obs = {"last": None, "still": 0}

    def observe():                      # (each frame the bot plays: as play's frames are looked at)
        if nes[0x00] != 1 or nes[0x01] != opp:
            return
        key = nes[0xA1]
        obs["still"] = obs["still"] + 1 if key == obs["last"] else 0
        obs["last"] = key
        if obs["still"] < 1 or len(looks[(key, 0)]) >= LOOKS and len(looks[(key, 1)]) >= LOOKS:
            return
        states.add(nes[0x90] & 0x7F)
        got = crop()
        if not got:
            return
        mi, look = got
        k = (key, mi)
        seen[k] += 1
        if len(looks[k]) < LOOKS:
            looks[k].append(look)
            where.setdefault(k, (-1000, nes[0x90]))
    sys.path.insert(0, str(HERE.parent.parent))
    from gbstage import bot
    results = []
    for _ in range(fights):             # the bot's fights: his whole fight, knockdowns and all, as a player sees it
        nes.load(start)
        run(rng.randrange(0, 120))      # (each from a moment on: his choices go another way)
        g = NesGame(nes, nes.save(), 0, observe)
        game, bot.Game = bot.Game, lambda *a, **k: g
        try:
            r = bot.play("", 0, frames=12000)
        finally:
            bot.Game = game
        results.append((r["won"], r["round"], r["his_knockdowns"]))
    if DEBUG:
        print("bot fights", results)
        print("restarts", restarts, "modes", collections.Counter(m for m, _ in drawn.elements()).most_common(6),
              "frames in mode 1", sorted("%02X" % k for m, k in drawn if m == 1))
    played = {k for k, ls in looks.items() if len(ls) >= MIN_LOOKS}
    for st in sorted(states):           # each state he's been in, forced from waiting (and so his frames in it
        for _ in range(3):              # that play seldom reaches: not other states, his own only; looks only
                                        # for frames play didn't judge, forced ones never mixed with those)
            nes.load(waiting)
            run(rng.randrange(1, 60))
            nes[0x90] = 0x80 | st
            last, still = None, 0
            for n in range(240):
                nes[0x391] = 0x60           # (Mac's health kept: his state plays out)
                run(1)
                if nes[0x00] != 1 or nes[0x01] != opp:
                    break
                key = nes[0xA1]
                still = still + 1 if key == last else 0
                last = key
                if still < 1 or len(looks[(key, 0)]) >= LOOKS and len(looks[(key, 1)]) >= LOOKS:
                    continue
                got = crop()
                if not got:
                    continue
                mi, look = got
                k = (key, mi)
                if k in played:
                    continue
                seen[k] += 1
                if len(looks[k]) < LOOKS:
                    looks[k].append(look)
                    where.setdefault(k, (-st, nes[0x90]))
    dump = os.environ.get("AUDIT_KEYDUMP")
    if dump:                            # (the looks of one frame, side by side: out/audit/looks-{key}.png)
        from PIL import Image
        k = (int(dump[:2], 16), int(dump.endswith("|")))
        ls = looks.get(k, [])
        im = Image.new("RGB", (128 * max(1, len(ls)), 192), (40, 40, 40))
        for n, (_, look) in enumerate(ls):
            for (x, y), c in look.items():
                if -64 <= x < 64 and -158 <= y < 34:
                    im.putpixel((128 * n + 64 + x, 158 + y), c)
        im.save(HERE / "out" / "audit" / f"looks-{dump.replace('|', 'm')}.png")
    merged = {}
    for k, ls in looks.items():         # (the NES redraws him in pieces, over a frame or two: a look half the
        sigs = collections.Counter(s for s, _ in ls)    # frame before's is no drawing of this one; his
        sig, n = sigs.most_common(1)[0] if ls else (None, 0)    # sprites' tiles as most looks have them are)
        if n >= MIN_LOOKS:
            merged[k] = body(merge([look for s, look in ls if s == sig]))
    palette = {c for v in ref.values() for c in v.values()}
    report = {}
    for k, m in merged.items():
        flash = not set(m.values()) <= palette      # (always seen in a hit's flash: the Game Boy flashes its own
        s = score(m, ref.get(k, {}), shape=flash)   # palettes, so only his shape)
        if s < GOOD:
            report["%02X%s" % (k[0], "|" * k[1])] = {"score": round(s, 3), "looks": len(looks[k]), "flash": flash,
                                                    "missing": k not in ref, "frame": where[k][0],
                                                    "state": "%02X" % where[k][1]}
    return report, merged, ref, seen


def sheet(report, merged, ref, out):
    from PIL import Image, ImageDraw
    keys = sorted(report)
    if not keys:
        if out.exists():
            out.unlink()
        return
    im = Image.new("RGB", (256 * min(4, len(keys)), 208 * ((len(keys) + 3) // 4)), (40, 40, 40))
    d = ImageDraw.Draw(im)
    for i, name in enumerate(keys):
        k = (int(name[:2], 16), int(name.endswith("|")))
        ox, oy = 256 * (i % 4), 208 * (i // 4)
        for j, img in enumerate((merged[k], ref.get(k, {}))):
            for (x, y), c in img.items():
                if -64 <= x < 64 and -158 <= y < 34:
                    im.putpixel((ox + 128 * j + 64 + x, oy + 158 + y), c)
        d.text((ox + 2, oy + 194), f"{name} NES | ours  {report[name]['score']}", fill=(255, 255, 0))
    im.save(out)


def fix(opp, report, merged):
    """The merged look in the capture for each mismatched frame (a 128x192 crop, his place at (64, 158))."""
    path = HERE / "out" / f"nes-opp{opp}-play.pkl"
    cap = pickle.load(open(path, "rb"))
    for name in report:
        if report[name]["flash"]:       # (its colors the flash's: left to look at)
            continue
        k = (int(name[:2], 16), int(name.endswith("|")))
        img = [[None] * 128 for _ in range(192)]
        for (x, y), c in merged[k].items():
            if 0 <= x + 64 < 128 and 0 <= y + 158 < 192:
                img[y + 158][x + 64] = c
        cap[k] = (img, (64, 158))
    pickle.dump(cap, open(path, "wb"))


if __name__ == "__main__":
    args = sys.argv[1:]
    frames = 20000
    if "--frames" in args:
        i = args.index("--frames")
        frames = int(args[i + 1])
        del args[i:i + 2]
    fights = 3
    if "--fights" in args:
        i = args.index("--fights")
        fights = int(args[i + 1])
        del args[i:i + 2]
    do_fix = "--fix" in args
    args = [a for a in args if a != "--fix"]
    opps = [int(a) for a in args] or OPPS
    outd = HERE / "out" / "audit"
    outd.mkdir(parents=True, exist_ok=True)
    failed = False
    for opp in opps:
        report, merged, ref, seen = audit(opp, frames, fights)
        pickle.dump(merged, open(HERE / "out" / f"nes-opp{opp}-audit.pkl", "wb"))
        (outd / f"opp{opp}.json").write_text(json.dumps(report, indent=1, sort_keys=True))
        sheet(report, merged, ref, outd / f"opp{opp}.png")
        unjudged = sorted("%02X%s" % (k[0], "|" * k[1]) for k in seen if k not in merged)
        print(f"opp {opp}: {len(merged)} frames judged, {len(report)} mismatched:", " ".join(sorted(report)),
              f"| too rarely seen: {' '.join(unjudged)}" if unjudged else "", flush=True)
        if do_fix and report:
            fix(opp, report, merged)
            print(f"opp {opp}: fixed {len(report)} in its capture")
        failed |= bool(report)
    sys.exit(1 if failed else 0)
