"""Glass Joe's frames as the NES game draws them in a real fight: the game booted (nes_boot), Mac played by a
fixed script (punching, dodging, standing, getting up), Joe's health held low so his knockdowns come too. Each
frame is taken as his drawing routine ($CC8B) draws it, with its "mirrored" flag ($A2, which that routine
reads and clears at $CC9D), and pictured once it has been up for a few frames. Some of his frame numbers
mean a different picture in another of his tables (the game switches them), so only pictures from a fight
are trusted: forcing a frame number from outside gives whatever table is in place.

joe_frames(wanted) -> {(frame, mirrored): (RGB crop 128x192, (x, y) of his place in it)}, cached in
out/nes-joe-play.pkl."""
import pickle, random
import nes_boot as B

HERE = B.pathlib.Path(__file__).parent
CACHE = HERE / "out" / "nes-joe-play.pkl"
A, BTN_B, START, UP, DOWN, LEFT, RIGHT = 0x80, 0x40, 0x10, 0x08, 0x04, 0x02, 0x01
DRAW_START = 0xC8A7                         # STY OppAnimFlags: his new frame being drawn (every table's way;
                                            # $A2, its "mirrored", still set: $CC9D clears it after)
DRAW_PLAIN = 0xC873                         # STA $A2 (0): his frame drawn by the round's own routine, as it is
WAITING = 0xAF06                            # the game waiting for the next frame, TransTimer ($1F) not yet 0
SETTLED = 3                                 # frames a picture of his has been up when it's taken


class Fight(B.Boot):
    """The game, with the sprite-0 hit the HUD's split waits for (it comes and goes as the game polls it)."""
    s0 = 0

    def read(self, a):
        if 0x2000 <= a < 0x4000 and a & 7 == 2:
            self.s0 ^= 0x40
            self.latch = False
            return 0x80 | self.s0
        return super().read(a)

    def frame(self, buttons):
        """One frame; returns (frame number, mirrored) if his drawing routine drew one."""
        c, drawn = self.cpu, None
        if not hasattr(self, "_booted"):
            c.pc = self.read(0xFFFC) | self.read(0xFFFD) << 8
            self._booted = 0
        self.buttons = buttons
        for _ in range(12000):
            pc = c.pc
            if pc == WAITING and self.ram[0x1F]:    # still waiting on the frame (TransTimer): on to its NMI
                break
            if pc == DRAW_START:
                drawn = (self.ram[0xA1], self.ram[0xA2] & 1)
            elif pc == DRAW_PLAIN:
                drawn = (self.ram[0xA1], 0)
            c.step()
        if self.ctrl & 0x80:
            c.push(c.pc >> 8); c.push(c.pc & 0xFF); c.push(c.flags(0))
            c.pc = self.read(0xFFFA) | self.read(0xFFFB) << 8
        self._booted += 1
        return drawn


def sprites_only(b, colors=None):
    """The sprites alone over nothing (None): Joe is sprites (Mac is the background), every one of them (no
    8-a-line limit: the game lays him out to show whole), MMC2's sprite latches as render() keeps them. 8x16
    sprites (PPUCTRL bit 5: some fighters' frames) take their pattern table from the tile's low bit."""
    img = [[None] * 256 for _ in range(240)]
    tall = bool(b.ctrl & 0x20)
    h = 16 if tall else 8
    lat = {0: 0xFE, 1: 0xFE}
    lat[1 if b.ctrl & 0x08 else 0] = getattr(b, "spr_latch", 0xFE)
    banks = {0: (0xB000, 0xC000), 1: (0xD000, 0xE000)}       # per table: its $FD bank, its $FE bank
    for Y in range(240):
        rows = []
        for i in range(64):
            sy, t, a, sx = b.oam[i * 4:i * 4 + 4]
            if not (sy < 0xEF and sy + 1 <= Y < sy + 1 + h):
                continue
            yy = Y - sy - 1
            if a & 0x80: yy = h - 1 - yy
            if tall:
                table, tile = t & 1, (t & 0xFE) + (yy >> 3)
            else:
                table, tile = (1 if b.ctrl & 0x08 else 0), t
            fd, fe = banks[table]
            bank = b.chr[fd] if lat[table] == 0xFD else b.chr[fe]
            yy &= 7
            d = B.CHR.get(bank, bytes(4096))[tile * 16:tile * 16 + 16]
            rows.append((sx, a, [((d[yy] >> (7 - x)) & 1) | (((d[yy + 8] >> (7 - x)) & 1) << 1) for x in range(8)]))
            if tile in (0xFD, 0xFE):
                lat[table] = tile
        for sx, a, row in reversed(rows):   # lower OAM index on top
            for x in range(8):
                v = row[7 - x if a & 0x40 else x]
                if v and sx + x < 256:
                    img[Y][sx + x] = B.NES_RGB[(colors or b.pal[0x10:0x20])[(a & 3) * 4 + v] & 0x3F]
    return img


def _crop(b, colors=None):
    img = sprites_only(b, colors)           # (he's sprites: Mac is the background)
    x, y = b.ram[0xB0], b.ram[0xB1]
    x0, y0 = max(0, min(256 - 128, x - 64)), max(0, min(240 - 192, y - 158))
    return [row[x0:x0 + 128] for row in img[y0:y0 + 192]], (x - x0, y - y0)


def fight(opponent=0):
    """The game booted into a fight: opponent 0 Glass Joe, 1 Von Kaiser, ... (RAM $01, the game's opponent
    number, set as the challenger screen comes up)."""
    b = Fight()
    for _ in range(600):
        b.frame(0)
    for _ in range(40):                     # Start through the title and the challenger screen
        for _ in range(4): b.frame(START)
        b.ram[0x01] = opponent
        for _ in range(86): b.frame(0)
        if b.ram[0x00] == 1 and b.ram[0x90] & 0x7F == 0x40:
            break
    return b


def joe_frames(wanted, budget=40000):
    return fighter_frames(0, wanted, budget)


def fighter_frames(opponent, wanted=None, budget=40000):
    """{(frame, mirrored): (crop, place)} for this opponent: until every wanted one is in, or (wanted None)
    the whole budget of frames played. Cached per opponent (out/nes-joe-play.pkl for Joe)."""
    cache = CACHE if opponent == 0 else HERE / "out" / f"nes-opp{opponent}-play.pkl"
    got = pickle.load(open(cache, "rb")) if cache.exists() else {}
    if got and (wanted is None or set(wanted) <= set(got)):
        return got
    b = fight(opponent)
    import copy
    start = copy.deepcopy(b)                # his fight from the top: back to it whenever a fight ends
    colors = bytes(b.pal[0x10:0x20])        # the sprites' palettes as they are (a hit's flash whitens his)
    rng = random.Random(1)
    held, hold, pending, ages = 0, 0, None, {k: SETTLED for k in got}
    styles = ["aggressive", "defensive", "standing", "mixed"]
    for n in range(budget):
        style = styles[(n // 2500) % len(styles)]
        if hold <= 0:
            held = {"aggressive": lambda: rng.choice([UP | A, UP | BTN_B, A, BTN_B, UP | A, 0, LEFT, RIGHT]),
                    "defensive": lambda: rng.choice([LEFT, RIGHT, DOWN, 0, 0, UP | A]),
                    "standing": lambda: 0 if rng.random() < 0.97 else A,
                    "mixed": lambda: rng.choice([A, BTN_B, UP | A, UP | BTN_B, LEFT, RIGHT, DOWN, 0])}[style]()
            hold = rng.randrange(2, 22)
        hold -= 1
        btn = held
        if b.ram[0x05] == 2:                # Mac down: mash to get up
            btn = A if n & 2 else 0
        if b.ram[0x00] != 1 and n % 60 < 3:  # between rounds, or after a fight: on
            btn = START
        if style in ("aggressive", "mixed") and b.ram[0x05] == 0:
            for a in (0x0398, 0x0399):      # (his health held low: his knockdowns come)
                if b.ram[a] > 20:
                    b.ram[a] = 20
        if b.ram[0x00] in (0xFB, 0xFC, 0xFD, 0xFE):        # over (the next fight isn't his): again
            b = copy.deepcopy(start)
            pending = None
            continue
        drawn = b.frame(btn)
        if drawn is not None:
            pending = (drawn, 0)
        elif pending is not None and b.ram[0x00] == 1:
            key, age = pending
            age += 1
            pending = (key, age)
            if age <= SETTLED and ages.get(key, 0) < age and b.ram[0xA1] == key[0]:
                if True:                                # the longest it's been up yet (some only stay a
                    crop, place = _crop(b, colors)      # frame or two), in his own colors; merged with the
                    old = got.get(key) if age > 1 else None     # frames before (a wide fighter's sprites take
                    if old and old[1] == place:                 # turns, flickering: each frame shows part)
                        crop = [[c if c is not None else o for c, o in zip(row, orow)] for row, orow in zip(crop, old[0])]
                    got[key] = (crop, place)
                    ages[key] = age
                if wanted is not None and set(wanted) <= {k for k in got if ages.get(k, SETTLED) >= min(SETTLED, 2)}:
                    break
    cache.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(cache, "wb"))
    return got


def ring_palette(opponent=0):
    """The fight's background palettes (16 NES colors): the ring, the ropes, the crowd, as the game sets them."""
    b = fight(opponent)
    for _ in range(60):
        b.frame(0)
    return list(b.pal[:16])


# The referee (Mario) is drawn in the background, with Mac. His three looks, from the same played fight:
# standing as the round opens, his arm out (the count, and "FIGHT!"), his fist up (the KO / TKO call).
REF_CACHE = HERE / "out" / "nes-ref-play.pkl"
REF_AT = {"stand": 8, "count": 1264, "wave": 2444}  # frames into the fight, played as ref_frames plays it


def ref_frames():
    """{look: (RGB crop of the ring around him, floor color)}: the referee as the game draws him."""
    if REF_CACHE.exists():
        return pickle.load(open(REF_CACHE, "rb"))
    b = Fight()
    for _ in range(600):
        b.frame(0)
    for _ in range(40):
        for _ in range(4): b.frame(START)
        for _ in range(86): b.frame(0)
        if b.ram[0x00] == 1 and b.ram[0x90] & 0x7F == 0x40:
            break
    at = {n: look for look, n in REF_AT.items()}
    got = {}
    for i in range(max(REF_AT.values()) + 1):
        btn = 0
        if b.ram[0x00] != 1 and i % 60 < 3:
            btn = START
        if b.ram[0x05] == 0:                # Joe's health held low, Mac punching: his knockdowns, the TKO
            for a in (0x0398, 0x0399):
                if b.ram[a] > 8:
                    b.ram[a] = 8
            btn = [UP | A, 0, UP | BTN_B, 0][(i // 6) % 4]
        b.frame(btn)
        if i in at:
            img = b.render(sprites=False)
            got[at[i]] = [row[140:250] for row in img[110:215]]
    CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(REF_CACHE, "wb"))
    return got


def vs_screen(opponent):
    """The challenger ("vs.") screen as the game shows it for this opponent: RGB rows."""
    cache = HERE / "out" / f"nes-vs{opponent}.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    b = Fight()
    for _ in range(600):
        b.frame(0)
    for _ in range(4):
        b.frame(START)
    b.ram[0x01] = opponent
    for _ in range(250):
        b.frame(0)
    img = b.render()
    cache.parent.mkdir(exist_ok=True)
    pickle.dump(img, open(cache, "wb"))
    return img


def splash_screen():
    """The game's first screen, MIKE IS WAITING FOR YOUR CHALLENGE!!, as it shows from power-on: RGB rows."""
    cache = HERE / "out" / "nes-splash.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    b = Fight()
    for _ in range(300):
        b.frame(0)
    img = b.render()
    cache.parent.mkdir(exist_ok=True)
    pickle.dump(img, open(cache, "wb"))
    return img


def ending_screen():
    """The game's last screen, after Mike Tyson: Mac standing, his record, THE END (reached by setting the win
    ($00 = $FC) in his fight: only its pictures are wanted). RGB rows, cached."""
    cache = HERE / "out" / "nes-ending.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    b = fight(13)
    for _ in range(300):
        b.frame(0)
    b.ram[0x00] = 0xFC
    for _ in range(4300):
        b.frame(0)
    img = b.render()
    pickle.dump(img, open(cache, "wb"))
    return img


MONTAGE_CACHE = HERE / "out" / "nes-montage.pkl"


def montage():
    """The training scene after the Minor Circuit title (Mac running, Doc on his bike past New York): the
    background's two screens side by side (RGB rows, 512 wide), and the sprites each time they change (RGB rows
    with None where none). Played to: Piston Honda beaten, his title screen gone by."""
    if MONTAGE_CACHE.exists():
        return pickle.load(open(MONTAGE_CACHE, "rb"))
    b = fight(2)
    n, ended = 0, None
    while n < 60000:
        st = b.ram[0x00]
        if ended is None:
            btn = [UP | A, 0, UP | BTN_B, 0][(n // 5) % 4]
            if b.ram[0x05] == 2: btn = A if n & 2 else 0
            if st != 1 and n % 60 < 3: btn = START
            if b.ram[0x05] == 0:
                for a in (0x398, 0x399):
                    if b.ram[a] > 2: b.ram[a] = 2
            if st in (0xFC, 0xFE): ended = n
        else:
            k = n - ended
            btn = START if k % 240 < 3 and 500 < k < 800 else 0
            if k == 1300: break
        b.frame(btn); n += 1
    sx, ct = b.scroll_x, b.ctrl
    pano = [[None] * 512 for _ in range(240)]
    for half in (0, 1):
        b.scroll_x, b.ctrl = 0, (ct & ~1) | half
        img = b.render(sprites=False)
        for y in range(240):
            pano[y][half * 256:half * 256 + 256] = img[y]
    b.scroll_x, b.ctrl = sx, ct
    frames, seen = [], set()
    for _ in range(96):
        b.frame(0)
        key = tuple(b.oam[k * 4 + 1] for k in range(64))
        if key not in seen:
            seen.add(key)
            frames.append(sprites_only(b))
    got = (pano, frames)
    MONTAGE_CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(MONTAGE_CACHE, "wb"))
    return got
