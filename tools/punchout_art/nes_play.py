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


def sprites_only(b):
    """The sprites alone over nothing (None): Joe is sprites (Mac is the background), every one of them (no
    8-a-line limit: the game lays him out to show whole), MMC2's sprite latch as render() keeps it."""
    img = [[None] * 256 for _ in range(240)]
    stable = 1 if b.ctrl & 0x08 else 0
    lat = getattr(b, "spr_latch", 0xFE)
    for Y in range(240):
        rows = []
        for i in range(64):
            sy, t, a, sx = b.oam[i * 4:i * 4 + 4]
            if not (sy < 0xEF and sy + 1 <= Y < sy + 9):
                continue
            bank = (b.chr[0xB000] if lat == 0xFD else b.chr[0xC000]) if stable == 0 else \
                   (b.chr[0xD000] if lat == 0xFD else b.chr[0xE000])
            yy = Y - sy - 1
            if a & 0x80: yy = 7 - yy
            d = B.CHR.get(bank, bytes(4096))[t * 16:t * 16 + 16]
            rows.append((sx, a, [((d[yy] >> (7 - x)) & 1) | (((d[yy + 8] >> (7 - x)) & 1) << 1) for x in range(8)]))
            if t in (0xFD, 0xFE):
                lat = t
        for sx, a, row in reversed(rows):   # lower OAM index on top
            for x in range(8):
                v = row[7 - x if a & 0x40 else x]
                if v and sx + x < 256:
                    img[Y][sx + x] = B.NES_RGB[b.pal[0x10 + (a & 3) * 4 + v] & 0x3F]
    return img


def _crop(b):
    img = sprites_only(b)                   # (he's sprites: Mac is the background)
    x, y = b.ram[0xB0], b.ram[0xB1]
    x0, y0 = max(0, min(256 - 128, x - 64)), max(0, min(240 - 192, y - 158))
    return [row[x0:x0 + 128] for row in img[y0:y0 + 192]], (x - x0, y - y0)


def joe_frames(wanted, budget=40000):
    got = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
    if set(wanted) <= set(got):
        return got
    b = Fight()
    for _ in range(600):
        b.frame(0)
    for _ in range(40):                     # Start through the title and the challenger screen
        for _ in range(4): b.frame(START)
        for _ in range(86): b.frame(0)
        if b.ram[0x00] == 1 and b.ram[0x90] & 0x7F == 0x40:
            break
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
                if bytes(b.pal[0x10:0x20]) == colors:   # the longest it's been up yet (some only stay a
                    got[key] = _crop(b)                 # frame or two), in his own colors
                    ages[key] = age
                if set(wanted) <= {k for k in got if ages.get(k, SETTLED) >= min(SETTLED, 2)}:
                    break
    CACHE.parent.mkdir(exist_ok=True)
    pickle.dump(got, open(CACHE, "wb"))
    return got
