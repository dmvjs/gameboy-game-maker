"""A fighter's NES frames as the game builds them, and what they share: each frame's sprites from the game's own
routine (nes_render.sprites: tile, place, flips), and the pieces frames have in common -- the same tiles in the
same places relative to each other -- found by laying each frame over each other one where the most of them
agree. The parts a Game Boy fighter can be drawn from, each once.

  python parts.py RIVAL            -> how much his frames share; out/RIVAL-parts.json"""
import collections, json, pickle, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build, cpu6502, nes_render


def frame_sprites(rival):
    """{frame: [(x, y, tile, attr)]} for each of his frames the fights show (unmirrored: a mirror is its flip)."""
    r = build.NES_RIVALS[rival]
    got = pickle.load(open(HERE / "out" / f"nes-opp{r['opp']}-play.pkl", "rb"))
    keys = sorted({k[0] for k in got})
    out = {}
    for f in keys:
        nes = cpu6502.Nes(nes_render.D, r["bank"]); ram = nes.ram
        for a in range(0x200, 0x300): ram[a] = 0xF8 if a % 4 == 0 else 0
        ram[0x03] = r["offset"]; ram[0xA0] = 0x80; ram[0xA1] = f; ram[0xB0], ram[0xB1] = 128, 182
        ram[0x80] = 8; ram[0x82] = 0xFF
        try:
            nes.cpu.call(0xC890)
        except Exception as e:
            continue
        spr = []
        for i in range(0, 256, 4):
            sy, t, a, sx = ram[0x200 + i:0x204 + i]
            if sy < 0xEF and t != 0xFF:
                spr.append((sx, sy + 1, t, a & 0xC3))
        if spr:
            out[f] = spr
    return out


def common(a, b):
    """The most sprites of a and b that agree (same tile and flips) at one offset: (count, offset, [a's indexes])."""
    votes = collections.Counter()
    bi = collections.defaultdict(list)
    for s in b:
        bi[s[2:4] if len(s) == 4 and not isinstance(s[2], tuple) else s[2]].append(s[:2])
    for s in a:
        for X, Y in bi[s[2:4] if len(s) == 4 and not isinstance(s[2], tuple) else s[2]]:
            votes[(X - s[0], Y - s[1])] += 1
    if not votes:
        return 0, None, []
    off, n = votes.most_common(1)[0]
    k = lambda s: s[2:4] if len(s) == 4 and not isinstance(s[2], tuple) else s[2]
    bs = {(s[0], s[1], k(s)) for s in b}
    idx = [i for i, s in enumerate(a) if (s[0] + off[0], s[1] + off[1], k(s)) in bs]
    return len(idx), off, idx


def main():
    rival = sys.argv[1]
    fr = frame_sprites(rival)
    placed = sum(len(v) for v in fr.values())
    tiles = {(t, a) for v in fr.values() for _, _, t, a in v}
    print(f"{rival}: {len(fr)} frames, {placed} sprites placed, {len(tiles)} distinct tiles ({placed / max(1, len(tiles)):.1f}x)")
    # (each sprite: is it in a piece some other frame has too, 4 sprites or more together?)
    shared = 0
    for f, a in fr.items():
        hit = set()
        for g, b in fr.items():
            if g == f:
                continue
            n, off, idx = common(a, b)
            if n >= 4:
                hit |= set(idx)
        shared += len(hit)
    print(f"  {shared} of {placed} sprites ({100 * shared / placed:.0f}%) are in a piece another frame shares (4+ sprites)")
    json.dump({f"{f:02X}": v for f, v in fr.items()}, open(HERE / "out" / f"{rival}-sprites.json", "w"))


if __name__ == "__main__":
    main()


def find_parts(fr, min_common=4):
    """Parts: sprites linked across frames (each pair of frames laid over where most agree), classes of the
    same sprite in each frame; classes in exactly the same frames, at fixed places to each other, one part.
    -> [{"frames": [f...], "sprites": {f: [index...]}}], biggest first; and each frame's sprites in none."""
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b):
        parent[find(a)] = find(b)
    keys = sorted(fr)
    for i, f in enumerate(keys):
        for g in keys[i + 1:]:
            n, off, idx = common(fr[f], fr[g])
            if n >= min_common:
                kk = lambda s: s[2:4] if len(s) == 4 and not isinstance(s[2], tuple) else s[2]
                bs = {(s[0], s[1], kk(s)): j for j, s in enumerate(fr[g])}
                for k in idx:
                    s = fr[f][k]
                    union((f, k), (g, bs[(s[0] + off[0], s[1] + off[1], kk(s))]))
    classes = collections.defaultdict(list)
    for f in keys:
        for k in range(len(fr[f])):
            classes[find((f, k))].append((f, k))
    by_sig = collections.defaultdict(list)
    alone = collections.defaultdict(list)
    for members in classes.values():
        frames = frozenset(f for f, _ in members)
        if len(frames) < 2 or len(frames) < len(members):     # (in one frame only, or twice in one: its own)
            for f, k in members:
                alone[f].append(k)
            continue
        by_sig[frames].append(members)
    parts = []
    for frames, cls in by_sig.items():
        sp = collections.defaultdict(list)
        for members in cls:
            for f, k in members:
                sp[f].append(k)
        parts.append({"frames": sorted(frames), "sprites": dict(sp)})
    parts.sort(key=lambda p: -len(p["frames"]) * len(next(iter(p["sprites"].values()))))
    return parts, dict(alone)


def fight_sprites(opponent, wanted, budget=40000):
    """{(frame, mirrored): (sprites [(x, y, (bank, tile), attr)], (x, y) his place)} read from a real fight
    (nes_play's way: Mac punching at random), each frame's sprite list as it's on screen -- frames the game
    draws over the one before ($80 on), which can't be drawn alone. Cached in out/nes-opp{N}-sprites.pkl."""
    import copy, random
    import nes_play as NP
    cache = HERE / "out" / f"nes-opp{opponent}-sprites.pkl"
    got = pickle.load(open(cache, "rb")) if cache.exists() else {}
    if set(wanted) <= set(got):
        return got
    b = NP.fight(opponent)
    for _ in range(450):
        b.frame(0)
    start = copy.deepcopy(b)
    rng = random.Random(1)
    held, hold, pending, ages = 0, 0, None, {k: NP.SETTLED for k in got}
    for n in range(budget):
        style = ("aggressive", "defensive", "standing", "mixed")[(n // 2500) % 4]    # (nes_play's: some frames
        if hold <= 0:                                                                 #  come only one way)
            held = {"aggressive": [NP.UP | NP.A, NP.UP | NP.BTN_B, NP.A, NP.BTN_B, NP.UP | NP.A, 0, NP.LEFT, NP.RIGHT],
                    "defensive": [NP.LEFT, NP.RIGHT, NP.DOWN, 0, 0, NP.UP | NP.A],
                    "standing": [0] * 33 + [NP.A],
                    "mixed": [NP.A, NP.BTN_B, NP.UP | NP.A, NP.UP | NP.BTN_B, NP.LEFT, NP.RIGHT, NP.DOWN, 0]}[style]
            held = rng.choice(held)
            hold = rng.randrange(2, 22)
        hold -= 1
        btn = held
        if b.ram[0x05] == 2:
            btn = NP.A if n & 2 else 0
        if b.ram[0x00] != 1 and n % 60 < 3:
            btn = NP.START
        if style in ("aggressive", "mixed") and b.ram[0x05] == 0:
            for a in (0x0398, 0x0399):              # (his health held low: his knockdowns come)
                if b.ram[a] > 20:
                    b.ram[a] = 20
        if b.ram[0x00] in (0xFB, 0xFC, 0xFD, 0xFE):
            b = copy.deepcopy(start); pending = None
            continue
        drawn = b.frame(btn)
        if drawn is not None:
            pending = (drawn, 0)
        elif pending is not None and b.ram[0x00] == 1:
            key, age = pending
            age += 1
            pending = (key, age)
            if age <= NP.SETTLED and b.ram[0xA1] == key[0] and key in wanted and ages.get(key, 0) < age:
                got[key] = (_oam_sprites(b), (b.ram[0xB0], b.ram[0xB1]))     # (the longest it's been up: some
                ages[key] = age                                               #  only stay a frame or two)
                if set(wanted) <= {k for k in got if ages.get(k, NP.SETTLED) >= min(NP.SETTLED, 2)}:
                    break
    pickle.dump(got, open(cache, "wb"))
    return got


def _oam_sprites(b):
    """The sprites on screen now, each (x, y, (CHR bank, tile), attr): its bank as MMC2's latches pick it."""
    import nes_play as NP
    tall = bool(b.ctrl & 0x20)
    lat = {0: 0xFE, 1: 0xFE}
    lat[1 if b.ctrl & 0x08 else 0] = getattr(b, "spr_latch", 0xFE)
    banks = {0: (0xB000, 0xC000), 1: (0xD000, 0xE000)}
    out = []
    for i in range(64):
        sy, t, a, sx = b.oam[i * 4:i * 4 + 4]
        if sy >= 0xEF:
            continue
        table = (t & 1) if tall else (1 if b.ctrl & 0x08 else 0)
        fd, fe = banks[table]
        bank = b.chr[fd] if lat[table] == 0xFD else b.chr[fe]
        out.append((sx, sy + 1, (bank, t), a & 0xC3))
        if t in (0xFD, 0xFE):
            lat[table] = t
    return out


def joe_like_frames(rival):
    """{frame: [(dx, dy, key, block)]}: each of his frames' sprites, placed from his place, keyed by tile, flips
    and its very pixels (a block of 64 colors from the captured picture: banks the mapper switched mid-frame
    can't fool it), from the game's routine where a frame draws alone, else from a real fight."""
    r = build.NES_RIVALS[rival]
    crops = pickle.load(open(HERE / "out" / f"nes-opp{r['opp']}-play.pkl", "rb"))
    alone = frame_sprites(rival)
    fought = {}
    cache = HERE / "out" / f"nes-opp{r['opp']}-sprites.pkl"
    if cache.exists():
        fought = pickle.load(open(cache, "rb"))
    out = {}
    for f in sorted({k[0] for k in crops}):
        key = (f, 0) if (f, 0) in crops else (f, 1)
        img, (px, py) = crops[key]
        if key in fought:
            spr, (bx, by) = fought[key]
            spr = [(x - bx, y - by, t[1] if isinstance(t, tuple) else t, a) for x, y, t, a in spr]
        elif f in alone and f < 0x4E and f != 0x0C:
            spr = [(x - 128, y - 182, t, a) for x, y, t, a in alone[f]]
        else:
            continue
        H, W = len(img), len(img[0])
        got = []
        for dx, dy, t, a in spr:
            blk = tuple(tuple(img[py + dy + j][px + dx + i][:3]) if 0 <= py + dy + j < H and 0 <= px + dx + i < W
                        and img[py + dy + j][px + dx + i] else None for j in range(8) for i in range(8))
            if any(blk):
                got.append((dx, dy, (t, a, hash(blk)), blk))
        out[(f, key[1])] = got
    return out
