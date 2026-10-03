"""Puzzle grid kit tests: the real ROM, run in the profiler's machine, against the reference rules.

Boards are written straight into the ROM's RAM, the ROM resolves them, and the result must match
puzzle.resolve cell for cell, including the score. Controls, setup and hardware limits are checked too.
"""

import json
import random
from pathlib import Path

from . import codegen, profiler, sfx
from . import puzzle as kit
from .build import build_rom
from .machine import FRAME, Machine

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "capsule-clinic.gbstage.json"
PZ = {name: n for n, name in enumerate(["SPAWN", "FALL", "CHECK", "CLEARING", "SETTLE", "END"])}


class Game:
    """The example ROM running in the machine, with helpers to drive and inspect the puzzle."""

    def __init__(self, cgb=True, project_file=EXAMPLE):
        project = codegen.validate(json.loads(Path(project_file).read_text()))
        self.project = project
        self.build = build_rom(codegen.generate_asm(project), "TEST", cgb=True)
        self.L = profiler.parse_sym(self.build.sym)
        keep = codegen.reachable_scenes(project)
        self.pz_scene = next(n for n, i in enumerate(keep) if project["scenes"][i].get("puzzle"))
        self.scene = next(project["scenes"][i] for i in keep if project["scenes"][i].get("puzzle"))
        g = self.scene["puzzle"]["grid"]
        self.w, self.h, self.gx, self.gy = g["w"], g["h"], g["x"], g["y"]
        self.lut = self.scene["kit_lut"]
        self.m = Machine(self.build.rom, cgb)
        self.frames = 0
        self.max_frame = 0
        self.max_vblank = 0
        self._busy = 0
        self._vb_start = None
        self.m.vblank_hook = self._on_vblank
        self.sounds = []          # (frame, effect name, transpose) for every PlaySfx call
        self._sfx_names = list(sfx.SFX)
        while self.m.cpu.pc != self.L["MainLoop"]:
            self.m.step()

    def _on_vblank(self):
        self.frames += 1
        self.max_frame = max(self.max_frame, self._busy)
        self._busy = 0
        self._vb_start = self.m.cycles

    def run(self, frames, buttons=()):
        """Run whole frames with the given buttons held."""
        self.m.buttons = set(buttons)
        target = self.frames + frames
        done, vb = self.L["VBlankDone"], self.L.get("LoadScene")
        loading = None
        while self.frames < target:
            cpu = self.m.cpu
            if cpu.halted and not self.m.pending_interrupts():
                self.m.advance(456 - self.m.lcd_dots % 456 if self.m.lcd_on() else 456)
                continue
            if cpu.pc == done and self._vb_start is not None:
                self.max_vblank = max(self.max_vblank, self.m.cycles - self._vb_start)
                self._vb_start = None
            if cpu.pc == vb:
                loading = cpu.sp + 2
            if cpu.pc == self.L["PlaySfx"]:
                self.sounds.append((self.frames, self._sfx_names[cpu.r[7]], self.hram("hSfxTranspose")))
            cycles, pc, halted = self.m.step()
            if loading is not None:
                if cpu.sp == loading and self.m.read(pc) in profiler.RETURNS:
                    loading = None
            elif not halted:
                self._busy += cycles
        self.m.buttons = set()

    def tap(self, button, hold=2, after=4):
        self.run(hold, [button])
        self.run(after)

    def hram(self, name):
        return self.m.read(self.L[name])

    def set_hram(self, name, value):
        self.m.write(self.L[name], value & 0xFF)

    def grid(self):
        base = self.L["wGrid"]
        return [self.m.read(base + i) for i in range(self.w * self.h)]

    def score(self):
        b = [self.m.read(self.L["wScore"] + k) for k in range(3)]
        return int("".join(f"{v:02X}" for v in b))

    def wait_state(self, states, limit=600):
        for _ in range(limit):
            if self.hram("hScene") == self.pz_scene and self.hram("hPzState") in states:
                return True
            self.run(1)
        return False

    def to_puzzle(self):
        """Title -> Settings -> Playfield, then wait for the first capsule."""
        self.run(30)
        self.tap("a")
        self.run(90)
        self.tap("start")
        assert self.wait_state({PZ["FALL"]}, 400), "never reached the puzzle"

    def load_board(self, grid, state="CHECK", speed=None):
        """Write a board into RAM (cells, tiles, dirty rows) and set the state."""
        base, tiles = self.L["wGrid"], self.L["wGridTiles"]
        for i, v in enumerate(grid):
            self.m.write(base + i, v)
            self.m.write(tiles + i, self.lut[v])
        for r in range(self.h):
            self.m.write(self.L["wDirtyRows"] + r, 1)
            self.m.write(self.L["wTouchRows"] + r, 1)       # an arbitrary board: check every line
        for c in range(self.w):
            self.m.write(self.L["wTouchCols"] + c, 1)
        self.set_hram("hMarkCount", 0)
        self.set_hram("hGridDirty", 1)
        self.set_hram("hPzViruses", sum(1 for v in grid if kit.shape_of(v) == kit.VIRUS))
        if speed is not None:
            self.set_hram("hPzSpeed", speed)
        self.set_hram("hPzBase", int(str(kit.POINTS[self.hram("hPzSpeed")]), 16))
        for k in range(3):
            self.m.write(self.L["wScore"] + k, 0)
        self.set_hram("hPzState", PZ[state])
        self.set_hram("hUpdateJump", 0xC3)
        upd = self.L["PuzzleUpdate"]
        self.set_hram("hUpdateJump", 0xC3)
        self.m.write(self.L["hUpdateJump"] + 1, upd & 0xFF)
        self.m.write(self.L["hUpdateJump"] + 2, upd >> 8)

    def screen_matches_ram(self):
        """Rows not waiting to be redrawn must show exactly the tiles RAM says."""
        bad = []
        for r in range(self.h):
            if self.m.read(self.L["wDirtyRows"] + r):
                continue
            for c in range(self.w):
                i = r * self.w + c
                want = self.lut[self.m.read(self.L["wGrid"] + i)]
                if self.m.read(self.L["wGridTiles"] + i) != want:
                    bad.append((r, c, "tile buffer"))
                if self.m.vram[0][0x1800 + (self.gy + r) * 32 + self.gx + c] != want:
                    bad.append((r, c, "screen"))
        return bad


def random_board(rng, w, h, density):
    """A board of viruses, singles and capsule pairs, with plenty of near-matches."""
    g = [0] * (w * h)
    for r in range(h):
        for c in range(w):
            i = r * w + c
            if g[i] or rng.random() > density:
                continue
            kind = rng.random()
            col = rng.randrange(3)
            if kind < 0.35:
                g[i] = kit.cell(kit.VIRUS, col)
            elif kind < 0.55:
                g[i] = kit.cell(kit.SINGLE, col)
            elif kind < 0.8 and c + 1 < w and not g[i + 1]:
                g[i] = kit.cell(kit.LEFT, col)
                g[i + 1] = kit.cell(kit.RIGHT, rng.randrange(3))
            elif r > 0 and not g[i - w]:
                g[i] = kit.cell(kit.BOTTOM, col)
                g[i - w] = kit.cell(kit.TOP, rng.randrange(3))
            else:
                g[i] = kit.cell(kit.SINGLE, col)
    return g


def show(g, w):
    return "\n".join(" ".join(f"{kit.shape_of(v)}{kit.color_of(v)}" if v else ".." for v in g[r * w:(r + 1) * w])
                     for r in range(len(g) // w))


def run(log=print, fuzz=150):
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        log(f"  {'✓' if ok else '✗'} {name}" + (f": {detail}" if detail and not ok else ""))
        return ok

    log("Puzzle kit tests (Capsule Clinic ROM, Game Boy Color)\n")
    game = Game()
    game.to_puzzle()
    w, h = game.w, game.h
    g = game.grid()
    viruses = [i for i, v in enumerate(g) if kit.shape_of(v) == kit.VIRUS]
    level = 5
    check("new game: 4 x (level + 1) viruses", len(viruses) == kit.virus_count(level, w, h),
          f"{len(viruses)} viruses, want {kit.virus_count(level, w, h)}")
    check("new game: viruses only in the lower rows", all(i // w >= kit.virus_top(h) for i in viruses))
    check("new game: virus count shown matches the board", game.hram("hPzViruses") == len(viruses))
    game.run(3)
    check("screen shows exactly what RAM holds", not game.screen_matches_ram(), str(game.screen_matches_ram()[:3]))

    # ---- controls ----
    def piece():
        return (game.hram("hPzRow"), game.hram("hPzCol"), game.hram("hPzVert"), game.hram("hPzC1"), game.hram("hPzC2"))

    game.load_board([0] * (w * h), state="SPAWN")
    game.run(2)
    r0, c0, v0, a, b = piece()
    check("a capsule spawns flat at the top middle", (r0, c0, v0) == (0, w // 2 - 1, 0), str(piece()))
    game.tap("left", hold=1, after=1)
    check("left moves one column", piece()[1] == c0 - 1, str(piece()))
    game.tap("right", hold=1, after=1)
    game.tap("right", hold=1, after=1)
    check("right moves one column", piece()[1] == c0 + 1, str(piece()))
    game.tap("a", hold=1, after=1)
    check("A works in the top row (the capsule stands on row 1)", piece()[2] == 1 and piece()[0] == 1, str(piece()))
    game.tap("b", hold=1, after=1)
    game.run(game.hram("hPzDrop") + 1)
    rows_before = piece()[0]
    game.tap("a", hold=1, after=1)
    r, c, v, c1, c2 = piece()
    check("A turns it upright, first color at the bottom", v == 1 and (c1, c2) == (a, b), str(piece()))
    game.tap("a", hold=1, after=1)
    r, c, v, c1, c2 = piece()
    check("A again lays it flat with the top half on the left", v == 0 and (c1, c2) == (b, a), str(piece()))
    game.tap("b", hold=1, after=1)
    r, c, v, c1, c2 = piece()
    check("B turns it upright the other way", v == 1 and (c1, c2) == (a, b), str(piece()))
    for _ in range(w):
        game.tap("right", hold=1, after=1)
    r, c, v, _, _ = piece()
    check("an upright capsule reaches the right wall", c == w - 1, str(piece()))
    game.tap("b", hold=1, after=1)
    r, c, v, _, _ = piece()
    check("turning flat at the wall nudges it left", v == 0 and c == w - 2, str(piece()))
    g = game.grid()
    on_board = sum(1 for x in g if x)
    check("the falling capsule is exactly two cells on the board", on_board == 2, str(on_board))

    for speed, frames in enumerate(kit.SPEED_FRAMES):
        game.load_board([0] * (w * h), state="SPAWN", speed=speed)
        game.set_hram("hPzDrop", frames)
        game.run(2)
        start = piece()[0]
        game.run(frames * 3)
        check(f"speed {['LOW', 'MED', 'HI'][speed]}: one row every {frames} frames", piece()[0] - start == 3,
              f"moved {piece()[0] - start} rows in {frames * 3} frames")

    # ---- scenarios ----
    def scenario(name, board, speed=1):
        game.load_board(board, speed=speed)
        want, want_score, _ = kit.resolve(board, w, h, speed, 0)
        ok = game.wait_state({PZ["SPAWN"], PZ["END"]}, 900)
        got = game.grid()
        same = ok and got == want and game.score() == want_score
        detail = "" if same else f"\nwant score {want_score}:\n{show(want, w)}\n got score {game.score()}:\n{show(got, w)}"
        return check(name, same, detail)

    B = lambda: [0] * (w * h)
    put = lambda b, r, c, s, col: b.__setitem__(r * w + c, kit.cell(s, col))
    b = B()
    for c in range(3):
        put(b, h - 1, c, kit.VIRUS, 2)
    put(b, h - 1, 3, kit.LEFT, 2); put(b, h - 1, 4, kit.RIGHT, 1)
    put(b, h - 2, 1, kit.SINGLE, 1)
    put(b, h - 3, 6, kit.TOP, 0); put(b, h - 2, 6, kit.BOTTOM, 0)
    put(b, h - 1, 7, kit.VIRUS, 0)
    scenario("4 in a row clears; partner becomes single; loose pieces fall", b)
    b = B()
    for r in range(h - 4, h):
        put(b, r, 2, kit.VIRUS if r == h - 1 else kit.SINGLE, 1)
    put(b, h - 1, 5, kit.VIRUS, 0)
    scenario("4 in a column clears", b)
    b = B()
    for c in range(4):
        put(b, h - 1, c, kit.VIRUS, 0)
    for c in range(4):
        put(b, h - 2, c, kit.SINGLE, 1)
    for c in range(1, 4):
        put(b, h - 3, c, kit.VIRUS, 1)
    put(b, h - 1, 6, kit.VIRUS, 2)
    scenario("chain: a clear drops pieces into a second match", b)
    b = B()
    for c in range(5):
        put(b, h - 1, c, kit.VIRUS, 2)
    put(b, h - 1, 7, kit.VIRUS, 1)
    scenario("5 viruses at once score 100+200+400+800+1600 (x speed)", b, speed=2)

    # ---- a real stack: yellow virus, then capsules dropped on it with button presses ----
    def place(g, col, vert):
        for _ in range(300):
            if g.hram("hPzState") == PZ["FALL"]:
                break
            g.run(1)
        for _ in range(4):
            if g.hram("hPzVert") == vert:
                break
            g.run(1, ["a"]); g.run(1)
        for _ in range(10):
            c = g.hram("hPzCol")
            if c == col:
                break
            g.run(1, ["left" if c > col else "right"]); g.run(1)
        for _ in range(200):
            if g.hram("hPzState") != PZ["FALL"]:
                break
            g.run(1, ["down"])
    b = B()
    put(b, h - 1, 1, kit.VIRUS, 1); put(b, h - 1, 6, kit.VIRUS, 2)
    game.load_board(b, state="SPAWN")
    for r in range(h):
        game.m.write(game.L["wTouchRows"] + r, 0)
    for c in range(w):
        game.m.write(game.L["wTouchCols"] + c, 0)
    game.set_hram("hPzNext1", 1); game.set_hram("hPzNext2", 1); game.run(1)
    game.set_hram("hPzNext1", 1); game.set_hram("hPzNext2", 2)
    place(game, 1, 1); game.run(40)
    v1 = game.hram("hPzViruses")
    place(game, 1, 1); game.run(120)
    check("stacking 3 yellow halves on a yellow virus clears it", game.hram("hPzViruses") < v1)

    # ---- fuzz: random boards ----
    rng = random.Random(1990)
    mismatches = 0
    for n in range(fuzz):
        board = random_board(rng, w, h, rng.choice([0.4, 0.6, 0.8]))
        if not any(kit.shape_of(v) == kit.VIRUS for v in board):
            board[-1] = kit.cell(kit.VIRUS, 0)
        game.load_board(board, speed=n % 3)
        want, want_score, _ = kit.resolve(board, w, h, n % 3, 0)
        ok = game.wait_state({PZ["SPAWN"], PZ["END"]}, 2000)
        if not (ok and game.grid() == want and game.score() == want_score):
            mismatches += 1
            if mismatches == 1:
                log(f"      first mismatch (board {n}):\n{show(board, w)}\n      want:\n{show(want, w)}\n      got:\n{show(game.grid(), w)}")
    check(f"{fuzz} random boards resolve exactly like the reference", mismatches == 0, f"{mismatches} differ")

    # ---- real play: a simple player, every lock checked against the reference ----
    rng = random.Random(7)
    locks = mismatched = frames_max = vblank_max = 0
    violations = []
    games = 0
    while locks < 60 and games < 6:
        games += 1
        real = Game()
        real.to_puzzle()
        real.max_frame = real.max_vblank = 0
        snapshot, prev, plan = None, real.hram("hPzState"), []
        for step in range(6000):
            if real.hram("hScene") != real.pz_scene:
                break
            state = real.hram("hPzState")
            if state == PZ["CHECK"] and prev == PZ["FALL"]:
                snapshot = (real.grid(), real.score(), real.hram("hPzSpeed"))
            if snapshot and state in (PZ["SPAWN"], PZ["END"]):
                locks += 1
                want, want_score, _ = kit.resolve(snapshot[0], w, h, snapshot[2], snapshot[1])
                if real.grid() != want or real.score() != want_score:
                    mismatched += 1
                snapshot = None
            if state == PZ["FALL"] and prev != PZ["FALL"]:
                # a new capsule: maybe turn it, slide it to a random column, then drop it
                col = rng.randrange(w - 1)
                plan = [rng.choice(["a", "b"])] * rng.randrange(3)
                plan += ["left" if col < w // 2 - 1 else "right"] * abs(col - (w // 2 - 1)) + ["down"] * 40
            prev = state
            if state == PZ["FALL"] and plan:
                b = plan.pop(0)
                real.run(1, [b])
                if b != "down":
                    real.run(1)
            else:
                real.run(1)
        frames_max = max(frames_max, real.max_frame)
        vblank_max = max(vblank_max, real.max_vblank)
        violations += real.m.violations
    check(f"real play ({games} games): {locks} capsules landed, each resolved exactly like the reference",
          locks >= 40 and mismatched == 0, f"{locks} locks, {mismatched} differ")
    # The peak is the match check in the frame after a clear (pieces that fell flag their columns).
    check(f"real play: busiest frame {frames_max:,} of {FRAME:,} cycles (under a third)", frames_max < FRAME // 3)
    check(f"real play: VBlank work {vblank_max:,} of {profiler.VBLANK_CYCLES:,} cycles", vblank_max <= profiler.VBLANK_CYCLES)
    check("real play: no hardware rule broken", not violations, str(violations[:2]))

    # ---- winning and losing ----
    b = B()
    for c in range(4):
        put(b, h - 1, c, kit.VIRUS, 1)
    game.load_board(b)
    game.wait_state({PZ["END"]}, 600)
    game.run(200)
    win_scene = codegen.reachable_scenes(game.project).index(game.scene["puzzle"]["win"])
    check("clearing the last virus goes to the win scene", game.hram("hScene") == win_scene, f"scene {game.hram('hScene')}")

    game2 = Game()
    game2.to_puzzle()
    b = [0] * (w * h)
    for r in range(h):
        for c in range(w):
            if r > 0 or c not in (w // 2 - 1, w // 2):
                b[r * w + c] = kit.cell(kit.SINGLE, (r + c) % 3) if r < 3 else 0
    b[w // 2 - 1] = kit.cell(kit.SINGLE, 0)          # the neck is blocked
    b[(h - 1) * w] = kit.cell(kit.VIRUS, 2)
    game2.load_board(b, state="SPAWN")
    game2.run(200)
    lose_scene = codegen.reachable_scenes(game2.project).index(game2.scene["puzzle"]["lose"])
    check("a blocked neck goes to the game over scene", game2.hram("hScene") == lose_scene, f"scene {game2.hram('hScene')}")

    # ---- sound effects ----
    def heard(g, action):
        n = len(g.sounds)
        action()
        return [name for _, name, _ in g.sounds[n:]]
    sg = Game()
    triggers = []
    write = sg.m.write
    def logged(addr, val):
        if addr in (0xFF14, 0xFF19, 0xFF23) and val & 0x80:
            triggers.append(addr)
        write(addr, val)
    sg.m.write = logged
    sg.run(30)
    check("menu: down plays menu_move", heard(sg, lambda: sg.tap("down")) == ["menu_move"])
    check("menu: up plays menu_move", heard(sg, lambda: sg.tap("up")) == ["menu_move"])
    check("menu: A plays menu_confirm", heard(sg, lambda: (sg.tap("a"), sg.run(90))) == ["menu_confirm"])
    check("options: right plays option_change", heard(sg, lambda: sg.tap("right")) == ["option_change"])
    check("options: left at the end of a range is silent", heard(sg, lambda: [sg.tap("left") for _ in range(12)]).count("option_change") < 12)
    check("options: down plays menu_move", heard(sg, lambda: sg.tap("down")) == ["menu_move"])
    sg.tap("up")
    check("options: B plays menu_back", heard(sg, lambda: (sg.tap("b"), sg.run(90))) == ["menu_back"])
    sg.tap("a"); sg.run(90)
    check("options: Start plays menu_confirm", heard(sg, lambda: sg.tap("start")) == ["menu_confirm"])
    sg.wait_state({PZ["FALL"]}, 400)
    check("puzzle: left tap plays move", heard(sg, lambda: sg.tap("left", hold=1, after=1)) == ["move"])
    held = heard(sg, lambda: sg.run(40, ["right"]))
    check("puzzle: holding right repeats with move_held", held[:1] == ["move"] and "move_held" in held, str(held))
    check("puzzle: A plays rotate", heard(sg, lambda: sg.tap("a", hold=1, after=1)) == ["rotate"])
    landed = heard(sg, lambda: sg.wait_state({PZ["SPAWN"], PZ["CHECK"]}, 900))
    check("puzzle: a landing capsule plays land", "land" in landed, str(landed))
    check("pulse 1, pulse 2 and noise are all triggered", {0xFF14, 0xFF19, 0xFF23} <= set(triggers), str(set(triggers)))
    sg.run(120)
    idle = all(sg.m.read(sg.L["wSfx"] + v * 6 + k) == 0 for v in range(3) for k in (0, 1))
    check("every voice goes idle once its effect ends", idle)

    b = B()                 # row h-4 clears, then the yellow on top falls into a yellow column
    for c in range(2, 5):
        put(b, h - 1, c, kit.VIRUS, 2); put(b, h - 2, c, kit.SINGLE, 0)
        put(b, h - 3, c, kit.SINGLE, 2); put(b, h - 4, c, kit.SINGLE, 0)
    put(b, h - 1, 5, kit.VIRUS, 1); put(b, h - 2, 5, kit.SINGLE, 1); put(b, h - 3, 5, kit.SINGLE, 1)
    put(b, h - 4, 5, kit.SINGLE, 0); put(b, h - 5, 5, kit.SINGLE, 1)
    sg.set_hram("hPzChain", 0)
    n = len(sg.sounds)
    sg.load_board(b)
    sg.wait_state({PZ["SPAWN"]}, 900)
    clears = [t for _, name, t in sg.sounds[n:] if name == "clear"]
    check("a chain plays clear higher each step (0, +2)", clears == [0, 2], str(clears))
    check("cleared viruses play virus", "virus" in [name for _, name, _ in sg.sounds[n:]])

    b = B()
    for c in range(4):
        put(b, h - 1, c, kit.VIRUS, 1)
    n = len(sg.sounds)
    sg.load_board(b)
    sg.wait_state({PZ["END"]}, 600)
    check("clearing the last virus plays win", "win" in [name for _, name, _ in sg.sounds[n:]])
    check("game over plays lose", "lose" in [name for _, name, _ in game2.sounds])
    sg.run(200)
    check("sound effects: no hardware rule broken", not sg.m.violations, str(sg.m.violations[:2]))

    # ---- hardware limits over everything above ----
    # Stress boards (every line checked at once) are far heavier than real play, but must still fit.
    for name, gm in (("stress boards", game), ("game over test", game2)):
        check(f"{name}: no hardware rule broken", not gm.m.violations, str(gm.m.violations[:2]))
        check(f"{name}: no frame overruns ({gm.max_frame:,} of {FRAME:,} cycles)", gm.max_frame < FRAME)
        check(f"{name}: VBlank work fits ({gm.max_vblank:,} of {profiler.VBLANK_CYCLES:,} cycles)", gm.max_vblank <= profiler.VBLANK_CYCLES)

    passed = sum(results)
    log(f"\n{passed}/{len(results)} puzzle kit checks passed.")
    return passed == len(results)
