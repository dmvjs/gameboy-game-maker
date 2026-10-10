"""Fight kit tests: the Joe vs Mac ROM, run in the profiler's machine, checked against the rules in fight.py."""

import json
from pathlib import Path

from . import codegen, profiler
from . import fight as kit
from .build import build_rom
from .machine import FRAME, Machine

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "joe-vs-mac.gbstage.json"   # tools/punchout_art/build.py writes it
RV = {n: k for k, n in enumerate(["IDLE", "GUARD", "TELL", "STRIKE", "OPEN", "HIT", "TAUNT", "FALL", "DOWN", "GETUP",
                                   "CHEER", "CHARGE"])}
PL = {n: k for k, n in enumerate(["IDLE", "PUNCH", "DODGE", "BLOCK", "HIT", "STAR", "DOWN"])}


class Fight:
    def __init__(self, cgb=True):
        project = codegen.validate(json.loads(EXAMPLE.read_text()))
        self.project = project
        self.build = build_rom(codegen.generate_asm(project), "TEST", cgb=True)
        self.L = profiler.parse_sym(self.build.sym)
        keep = codegen.reachable_scenes(project)
        self.fight_scene = next(n for n, i in enumerate(keep) if project["scenes"][i].get("fight"))
        ft = next(project["scenes"][i]["fight"] for i in keep if project["scenes"][i].get("fight"))
        self.win_scene, self.lose_scene = keep.index(ft["win"]), keep.index(ft["lose"])
        self.m = Machine(self.build.rom, cgb)
        self.frames, self.busy, self.max_frame, self.loading = 0, 0, 0, None
        self.m.vblank_hook = self._vblank
        while self.m.cpu.pc != self.L["MainLoop"]:    # boot (waits for the screen) isn't game frame work
            self.m.step()

    def _vblank(self):
        self.frames += 1
        self.max_frame = max(self.max_frame, self.busy)
        self.busy = 0

    def run(self, n, buttons=()):
        self.m.buttons = set(buttons)
        target = self.frames + n
        load = self.L["LoadScene"]
        while self.frames < target:
            cpu = self.m.cpu
            if cpu.pc == load:                      # a scene load (screen off) isn't game frame work
                self.loading = cpu.sp + 2
            cycles, pc, halted = self.m.step()
            if self.loading is not None:
                if cpu.sp == self.loading and self.m.read(pc) in profiler.RETURNS:
                    self.loading = None
            elif not halted:
                self.busy += cycles
        self.m.buttons = set()

    def tap(self, button, after=20, also=()):
        self.run(2, [button, *also])
        self.run(after)

    def __getitem__(self, name):
        return self.m.read(self.L[name])

    def __setitem__(self, name, value):
        self.m.write(self.L[name], value & 0xFF)

    def to_fight(self):
        self.run(60)
        self.tap("a", 150)
        self.tap("start", 200)

    def wait(self, cond, limit=3000):
        for _ in range(limit):
            if cond():
                return True
            self.run(1)
        return False

    def ready(self):
        return self["wFtMatch"] == 0 and self["wRvState"] == RV["IDLE"] and self["wPlState"] == PL["IDLE"]


def run(log=print):
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        log(f"  {'✓' if ok else '✗'} {name}" + (f": {detail}" if detail and not ok else ""))
        return ok

    log("\nFight kit tests (Joe vs Mac ROM)\n")
    t = kit.TUNING
    g = Fight()
    g.to_fight()
    check("the menu and the tale of the tape lead into the fight", g["hScene"] == g.fight_scene, f"scene {g['hScene']}")
    ref = Fight()
    ref.run(60); ref.tap("a", 150); ref.tap("start", 60)
    said = []
    ref.wait(lambda: said.append((ref["wFtSay"], ref["wFtRefX"])) or ref["wFtMatch"] == 0, 300)
    check('the referee walks in and calls "FIGHT!" before the bell', any(sy == 3 and x == 118 for sy, x in said), str(said[-3:]))
    ref.run(40)
    check("then he steps out of the ring", ref["wFtRefX"] == 172, str(ref["wFtRefX"]))
    check("both start at full health", g["wPlHealth"] == kit.HEALTH and g["wRvHealth"] == kit.HEALTH)

    # guard: the covered target is blocked and costs a heart; the open one lands
    g.wait(g.ready)
    guard = g["wRvGuard"]
    covered, open_ = ((), ("up",)) if guard == 0 else (("up",), ())
    hp, hearts = g["wRvHealth"], g["wPlHearts"]
    g.tap("b", 24, covered)
    check("a punch where he's guarding is blocked and costs a heart",
          g["wRvHealth"] == hp and g["wPlHearts"] == hearts - 1, f"hp {hp}->{g['wRvHealth']} hearts {hearts}->{g['wPlHearts']}")
    def open_target():
        return ("up",) if g["wRvGuard"] == 0 else ()
    g.wait(g.ready)
    hp, target = g["wRvHealth"], open_target()
    g.tap("b", 24, target)
    dmg = t["DMG_HEAD"] if target else t["DMG_BODY"]
    check("a punch where he isn't guarding lands", g["wRvHealth"] == hp - dmg, f"hp {hp}->{g['wRvHealth']}")
    g.wait(g.ready)
    guard = g["wRvGuard"]
    g["wRvLanded"] = 0
    for _ in range(3):
        g.wait(g.ready)
        if g["wRvGuard"] != guard:
            break
        g.tap("b", 24, open_target())
    g.wait(g.ready)
    check("three clean hits and he switches guard", g["wRvGuard"] != guard)

    # his script: the taunt at 0:32 comes before any punch; then the shuffle-in hook
    g2 = Fight()
    g2.to_fight()
    first_tell = []
    def watch():
        if g2["wRvState"] in (RV["TELL"], RV["TAUNT"]) and not first_tell:
            first_tell.append((g2["wRvState"], g2["wFtMin"], g2["wFtSec"]))
        return bool(first_tell)
    g2.wait(watch, 4000)
    check("he does nothing until 0:40, then backs off to taunt (before any punch)", first_tell and first_tell[0] == (RV["TAUNT"], 0, 0x40),
          str(first_tell))
    g2.wait(lambda: g2["wRvState"] == RV["CHARGE"], 600)
    g2.wait(lambda: g2["wRvTimer"] <= kit.TUNING["CHARGE"] - 7, 30)     # past the KO window, mid-charge
    g2.run(2, ["b"]); g2.run(40)
    check("a punch as he shuffles back in knocks him down", g2["wRvDowns"] == 1 and g2["wRvGetupAt"] > 0,
          f"downs {g2['wRvDowns']} getup {g2['wRvGetupAt']}")
    g7 = Fight()
    g7.to_fight()
    g7.wait(lambda: g7["wRvState"] == RV["TAUNT"] and g7["wFtSwapHave"] == 2 and g7["wRvTimer"] == 4, 3000)
    g7.run(1, ["b"]); g7.run(40)                  # thrown just before he charges, it lands in the first frames
    check("caught in the first frames of the charge, he stays down (KO)", g7["wRvDowns"] == 1 and g7["wRvGetupAt"] == 0,
          f"downs {g7['wRvDowns']} getup {g7['wRvGetupAt']}")
    g8 = Fight()
    g8.to_fight()
    landed = 0
    while landed < 20:
        g8.wait(g8.ready)
        before = g8["wRvHealth"]
        g8.tap("b", 20, ("up",) if g8["wRvGuard"] == 0 else ())
        if g8["wRvHealth"] < before:
            landed += 1
        g8["wRvHealth"] = kit.HEALTH
        if landed == 19:
            stars19 = g8["wPlStars"]
    check("the 20th landed punch earns the first star", stars19 == 0 and g8["wPlStars"] == 1, f"{stars19} -> {g8['wPlStars']}")

    # dodging his punch leaves him open; getting hit costs health, hearts and stars
    g3 = Fight()
    g3.to_fight()
    g3.wait(lambda: g3["wRvState"] == RV["TELL"], 4000)
    g3.wait(lambda: g3["wRvTimer"] == 4, 100)
    g3.tap("left", 30)
    check("dodging his swing makes him miss and leaves him open", g3["wRvState"] == RV["OPEN"] and g3["wPlHealth"] == kit.HEALTH,
          f"state {g3['wRvState']} health {g3['wPlHealth']}")
    g3.wait(lambda: g3["wRvState"] == RV["TELL"], 4000)
    attack = g3["wRvAttack"]
    g3["wPlStars"] = 2
    hearts = g3["wPlHearts"]
    g3.wait(lambda: g3["wPlState"] == PL["HIT"], 200)
    check("standing still, his punch lands", g3["wPlHealth"] == kit.HEALTH - (t["DMG_HOOK"] if attack else t["DMG_JAB"]),
          f"health {g3['wPlHealth']}")
    check("getting hit costs hearts and every star", g3["wPlHearts"] == hearts - t["HEARTS_HIT"] and g3["wPlStars"] == 0)

    # worn out: no hearts left, the tired palette
    g3.wait(g3.ready)
    g3["wPlHearts"] = 1
    g3.tap("b", 20, () if g3["wRvGuard"] == 0 else ("up",))
    attrs = {g3.m.read(g3.L["wFtOAM"] + 4 * k + 3) & 7 for k in range(3)}
    tired_pal = g3.project["scenes"][2]["fight"]["player"]["tired_palette"]
    check("out of hearts, the player turns to the tired palette", g3["wPlTired"] > 0 and attrs == {tired_pal},
          f"tired {g3['wPlTired']} palettes {attrs}")
    g3["wPlTired"] = 1
    g3.run(4)
    # stars: a face punch during the hook's wind-up earns one; Start spends it
    g3.wait(lambda: g3["wRvState"] == RV["TELL"] and g3["wRvAttack"] == 1 and g3["wPlState"] == PL["IDLE"], 6000)
    g3.tap("b", 20, ("up",))
    check("a face punch during the hook's wind-up earns a star", g3["wPlStars"] == 1, f"stars {g3['wPlStars']}")
    g3.wait(g3.ready)
    hp = g3["wRvHealth"]
    g3.tap("start", 40)
    check("Start throws the star punch", g3["wPlStars"] == 0 and g3["wRvHealth"] <= hp - t["DMG_STAR"],
          f"stars {g3['wPlStars']} hp {hp}->{g3['wRvHealth']}")

    # his counter: every third right hand gets slipped and answered with a hook
    g6 = Fight()
    g6.to_fight()
    states = []
    for _ in range(3):
        g6.wait(g6.ready)
        g6.tap("a", 3)
        states.append(g6["wRvState"])
    g6.wait(lambda: g6["wRvState"] == RV["TELL"], 60)
    check("every third right hand, he slips it and counters with a hook", states[2] == 13 and g6["wRvAttack"] == 1,
          f"states {states} attack {g6['wRvAttack']}")
    # the arm pop: a star punch that doesn't drop him
    g6.wait(lambda: g6["wFtMatch"] == 0 and g6["wRvState"] in (RV["IDLE"],) and g6["wPlState"] == PL["IDLE"], 3000)
    g6["wPlStars"] = 1
    g6.tap("start", 30)
    popped = g6["wRvState"] == 12
    g6.wait(lambda: g6["wRvState"] != 12, 300)
    check("a star punch pops his arm out, and he snaps it back in", popped and g6["wFtSwapWant"] == 0, f"popped {popped}")

    # the end of a round: to the corner, Select refills once, Start goes back and the fight carries on
    g9 = Fight()
    g9.to_fight()
    g9.wait(g9.ready)
    g9["wFtMin"] = 2; g9["wFtSec"] = 0x59; g9["wFtSub"] = 19
    g9["wPlHealth"] = 40
    g9.run(200)
    corner = codegen.reachable_scenes(g9.project).index(g9.project["scenes"][2]["fight"]["corner"])
    at_corner = g9["hScene"] == corner
    hp = g9["wPlHealth"]
    g9.tap("select", 10); g9.tap("select", 10)
    refilled = g9["wPlHealth"] - hp
    g9.tap("start", 200)
    check("the round ends in the corner; Select refills once; Start resumes round 2",
          at_corner and refilled > 0 and g9["hScene"] == g9.fight_scene and g9["wFtRound"] == 2 and g9["wFtMatch"] in (0, 1),
          f"corner {at_corner} refill {refilled} scene {g9['hScene']} round {g9['wFtRound']}")

    # knockdowns, the count, getting up, KO
    g4 = Fight()
    g4.to_fight()
    counts, seen = [], set()
    kd = {kit.RIVAL_POSES.index(p) for p in kit.KD_POSES}
    for n in range(3):
        g4.wait(g4.ready)
        g4["wRvHealth"] = 1
        g4.tap("b", 30, ("up",) if g4["wRvGuard"] == 0 else ())
        g4.wait(lambda: seen.add(g4["wRvPose"]) or g4["wFtMatch"] == 0 or g4["wFtCount"] == 0xFF, 1200)
        counts.append(g4["wFtCount"] if n == 2 else g4["wRvHealth"])
        if n == 0:
            g4.wait(g4.ready)
            check("a knockdown plays the whole fall (stagger, fall, down, kneel) and swaps his tiles back",
                  kd <= seen and g4["wFtSwapHave"] == 0, f"seen {sorted(seen)} have {g4['wFtSwapHave']}")
    check("he gets up from knockdowns 1 and 2 (fully healed if the player is untouched early on)",
          counts[0] == kit.HEALTH and counts[1] == kit.HEALTH, str(counts))
    check("the third knockdown is a KO", counts[2] == 0xFF, str(counts))
    check("the referee waves off the KO", g4["wFtRefPose"] == 2 and g4["wFtSay"] == 2, f"pose {g4['wFtRefPose']} say {g4['wFtSay']}")
    g4.run(400)
    check("the KO goes to the win scene", g4["hScene"] == g4.win_scene, f"scene {g4['hScene']}")

    # the player down: mash to get up, or lose
    g5 = Fight()
    g5.to_fight()
    g5.wait(lambda: g5["wRvState"] == RV["STRIKE"], 4000)
    g5["wPlHealth"] = 1
    g5.wait(lambda: g5["wFtMatch"] == 3, 100)
    for _ in range(40):
        g5.tap("a", 3)
    check("mashing A gets the player back up", g5["wFtMatch"] == 0 and g5["wPlHealth"] > 0, f"match {g5['wFtMatch']}")
    g5.wait(lambda: g5["wRvState"] == RV["STRIKE"], 4000)
    g5["wPlHealth"] = 1
    g5.run(800)
    check("not getting up loses the fight", g5["hScene"] == g5.lose_scene, f"scene {g5['hScene']}")

    runs = (g, g2, g3, g4, g5, g6)
    check(f"every run: no hardware rule broken, busiest frame {max(x.max_frame for x in runs):,} of {FRAME:,} cycles",
          all(not x.m.violations and x.max_frame < FRAME for x in runs), str([x.m.violations[:1] for x in runs]))
    passed = sum(results)
    log(f"\n{passed}/{len(results)} fight kit checks passed.")
    return passed == len(results)
