"""Punch-Out!!'s whole game, as a player goes through it, on the Joe vs Mac example's ROM: the bot (bot.py, buttons
only) from power-on through every fight to THE END, Mac's record and the training runs' pass keys checked on the
way; losses (a rematch, down the ranks, game over and the title, the record cleared); and a pass key on the title
(its challenger, its record). The three run side by side, a process each."""
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import codegen
from .build import build_rom

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"


def _scenes():
    project = json.loads(EXAMPLE.read_text())
    return [s["name"] for s in project["scenes"]], [i for i, s in enumerate(project["scenes"]) if s.get("fight")]


def _record(g):
    return tuple(g.m[g.S[n]] for n in ("wRecWins", "wRecLosses", "wRecKOs"))


def career(rom):
    """Every fight in turn, won; the record after each; the pass keys the training runs show; the ending."""
    import sys
    from . import bot
    sys.path.insert(0, str(ROOT / "tools" / "punchout_art"))
    import passwords
    names, fights = _scenes()
    project = json.loads(EXAMPLE.read_text())
    g = bot.Game(rom, fights[0])
    g.stop = lambda: None
    game, bot.Game = bot.Game, lambda *a, **k: g
    lines, ok, kos = [], True, 0
    try:
        for k, scene in enumerate(fights):
            r = bot.play(rom, scene)
            kos += r["won"] and r["result"] in (0xFC, 0xFE)      # (a KO or TKO: no points decision in it)
            rec = _record(g)
            good = r["won"] and rec == (k + 1, 0, kos)
            ok = ok and good
            lines.append(f"    {'✓' if good else '✗'} {names[scene]}: {'won' if r['won'] else 'lost'}, record {rec[0]}-{rec[1]} {rec[2]}KO")
            if not good:
                return False, lines
            key_scene = next((j for j in range(scene + 1, len(names)) if names[j].startswith("Training")
                              and names[j].endswith(names[scene].split(": ")[-1])), None)
            if key_scene is not None:           # its training run: on to it, its key read off what it worked out
                for t in range(3000):
                    if g.hram("hScene") == key_scene:
                        break
                    g.hold(["start"] if t % 50 < 3 else [])
                    g.tick(False)
                for _ in range(120):
                    g.tick(False)
                box = ((project["scenes"][key_scene].get("cutscene") or {}).get("box") or {}).get("lines", [])
                fixed = next((l.replace(" ", "") for l in box if l.replace(" ", "") in passwords.SPECIAL.values()), None)
                digits = [int(c) for c in fixed] if fixed else [g.m[g.S["wPw"] + 0x10 + i] for i in range(10)]
                special = fixed is not None             # (a special one, as the game has it: the Tyson code)
                want = passwords.decode(digits)
                good = special or (want is not None and want[:3] == rec)
                ok = ok and good
                lines.append(f"    {'✓' if good else '✗'} {names[key_scene]}: pass key {''.join(map(str, digits))}"
                             + ("" if special else f" (the NES reads it as {want})"))
        seen = set()                            # then the ending, to its last screen and the title
        for t in range(20000):
            seen.add(names[g.hram("hScene")])
            if "The end" in seen and g.hram("hScene") == 0:
                break
            g.hold(["start"] if t % 120 < 3 else [])
            g.tick(False)
        good = "The end" in seen and g.hram("hScene") == 0
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} the ending: {len([s for s in seen if s.startswith('Ending')])} portraits, THE END, the title")
    finally:
        bot.Game = game
    return ok, lines


def losses(rom):
    """Three losses to Glass Joe (Mac's health gone each fight): a rematch each time (he's the circuit's first), then
    game over, the title, the record cleared."""
    from pyboy import PyBoy
    from . import bot
    names, fights = _scenes()
    S, _ = bot._symbols(rom)
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    m, w = pb.memory, S["wNes"]
    seq, held, last = [], False, None
    for f in range(40000):
        sc = m[S["hScene"]]
        if sc != last:
            seq.append((names[sc], m[S["wRecLosses"]]))
            last = sc
        if len(seq) > 3 and seq[-1][0] == names[1] and any(n == "Game over" for n, _ in seq):
            break
        if m[S["hFtActive"]] == 1:
            m[w + 0x391] = 0
        press = f % 50 < 3 and m[S["hFtActive"]] != 1
        if press != held:
            (pb.button_press if press else pb.button_release)("start")
            held = press
        pb.tick(1, False)
    pb.stop(save=False)
    flow = [n for n, _ in seq]
    after = flow[flow.index(names[fights[0]]):] if names[fights[0]] in flow else []
    want = ["Fight", "Joe wins", "Rematch", "Fight", "Joe wins", "Rematch", "Fight", "Joe wins", "Game over", "Title",
            names[1]]
    good = after[:len(want)] == want and seq[-1][1] == 0
    return good, [f"    {'✓' if good else '✗'} three losses to Glass Joe: {' > '.join(after[:len(want)])}"
                  + ("" if good else f" (wanted {' > '.join(want)})")]


def _lose_from(rom, fight, losses, stop):
    """Straight into a fight (bot.Game's way in), Mac's health gone each time it runs: the scenes it goes on to,
    till one named stop (or `losses` losses)."""
    from . import bot
    names, _ = _scenes()
    g = bot.Game(rom, fight)
    S = g.S
    seq, lost, last = [], 0, None
    for f in range(30000):
        sc = g.hram("hScene")
        if sc != last:
            seq.append(names[sc])
            last = sc
            if names[sc].endswith("wins"):
                lost += 1
            if lost >= losses and names[sc] == stop:
                break
        if g.hram("hFtActive") == 1:
            g.m[g.w + 0x391] = 0
        g.hold(["start"] if f % 50 < 3 and g.hram("hFtActive") != 1 else [])
        g.tick(False)
    g.stop()
    return seq[seq.index(names[fight]):] if names[fight] in seq else seq


def routes(rom):
    """Losing as Punch-Out!!'s rules have it: a rematch lost (down a place), a title bout lost (down a place; in the
    World circuit two), the last fight lost (game over)."""
    cases = [("Kaiser: a rematch, then down to Glass Joe", 10, 2,
              ["Fight: Kaiser", "Kaiser wins", "Rematch: Kaiser", "Fight: Kaiser", "Kaiser wins", "Challenger"]),
             ("Honda (the Minor title): down to Von Kaiser", 17, 1,
              ["Fight: Honda", "Honda wins", "Challenger: Kaiser"]),
             ("Bald Bull (the Major title): down to Great Tiger", 45, 1,
              ["Fight: Bull", "Bull wins", "Challenger: Tiger"]),
             ("Super Macho Man (the World title): down two, to Don Flamenco", 87, 1,
              ["Fight: Macho", "Macho wins", "Challenger: Don2"]),
             ("Mike Tyson: game over", 94, 1, ["Fight: Tyson", "Tyson wins", "Game over"])]
    lines, ok = [], True
    for title, fight, losses, want in cases:
        seq = _lose_from(rom, fight, losses, want[-1])
        good = seq[:len(want)] == want
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} {title}: {' > '.join(seq[:len(want)])}"
                     + ("" if good else f" (wanted {' > '.join(want)})"))
    return ok, lines


def pass_key(rom):
    """005 737 5423 (3-0, 3 KOs, the Major Circuit's) typed on the title, as a player types it: Don Flamenco's
    challenger, Mac's record 3-0 3KO."""
    from pyboy import PyBoy
    from . import bot
    names, _ = _scenes()
    S, _ = bot._symbols(rom)
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    m = pb.memory

    def tap(b, n=1):
        for _ in range(n):
            pb.button_press(b); pb.tick(3, False); pb.button_release(b); pb.tick(5, False)
    f = 0
    while (m[S["hScene"]] != 0 or f < 400) and f < 6000:
        pb.tick(1, False)
        f += 1
    pb.tick(240, False)
    tap("down")
    pb.tick(20, False)
    tap("right")
    for ch in "0057375423":
        tap("right", int(ch))
        tap("a")
    pb.tick(600, False)
    scene, rec = m[S["hScene"]], tuple(m[S[n]] for n in ("wRecWins", "wRecLosses", "wRecKOs"))
    pb.stop(save=False)
    good = names[scene] == "Challenger: Don" and rec == (3, 0, 3)
    return good, [f"    {'✓' if good else '✗'} pass key 005 737 5423: {names[scene]}, record {rec[0]}-{rec[1]} {rec[2]}KO"]


def another_world(rom):
    """Punch-Out!!'s Another World Circuit: 135 792 4680 typed with Select held on its last digit (the NES's A, B
    and Select): King Hippo's challenger, the circuit on, 0-0; won there, on to its next (Piston Honda, not Bald
    Bull); its rematch lost, down its ranks (Great Tiger)."""
    from pyboy import PyBoy
    from . import bot
    names, _ = _scenes()
    S, _ = bot._symbols(rom)
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    m = pb.memory

    def tap(b):
        pb.button_press(b); pb.tick(3, False); pb.button_release(b); pb.tick(5, False)
    f = 0
    while (m[S["hScene"]] != 0 or f < 400) and f < 6000:
        pb.tick(1, False)
        f += 1
    pb.tick(240, False)
    tap("down")
    pb.tick(20, False)
    tap("right")
    for k, ch in enumerate("1357924680"):
        for _ in range(int(ch)):
            tap("right")
        if k == 9:
            pb.button_press("select"); pb.tick(4, False)
        tap("a")
    pb.button_release("select")
    pb.tick(600, False)
    scene, on = names[m[S["hScene"]]], m[S["wAw"]]
    pb.stop(save=False)
    good = scene == "Challenger: Hippo" and on == 1
    lines = [f"    {'✓' if good else '✗'} 135 792 4680: {scene}, the circuit {'on' if on else 'off'}"]

    def aw_on(g, fight):
        tick = g.tick

        def t(*a, **k):
            if g.hram("hScene") == fight:
                g.m[g.S["wAw"]] = 1
            return tick(*a, **k)
        g.tick = t
    fight = names.index("Fight: Tiger")                 # won there
    g = bot.Game(rom, fight)
    aw_on(g, fight)
    g.stop = lambda: None
    game, bot.Game = bot.Game, lambda *a, **k: g
    try:
        r = bot.play(rom, fight)
    finally:
        bot.Game = game
    nxt = g.m[g.S["wRecNext"]]
    win = r["won"] and nxt < len(names) and names[nxt] == "Challenger: Honda2"
    lines.append(f"    {'✓' if win else '✗'} Great Tiger beaten there: on to {names[nxt] if nxt < len(names) else nxt}")
    fight = names.index("Fight: Honda2")                # lost twice there
    g = bot.Game(rom, fight)
    aw_on(g, fight)
    seq, lost, last = [], 0, None
    for f in range(30000):
        sc = g.hram("hScene")
        if sc != last:
            seq.append(names[sc])
            last = sc
            lost += names[sc].endswith("wins")
            if lost >= 2 and names[sc].startswith("Challenger"):
                break
        if g.hram("hFtActive") == 1:
            g.m[g.w + 0x391] = 0
        g.hold(["start"] if f % 50 < 3 and g.hram("hFtActive") != 1 else [])
        g.tick(False)
    g.stop()
    seq = seq[seq.index("Fight: Honda2"):] if "Fight: Honda2" in seq else seq
    want = ["Fight: Honda2", "Honda2 wins", "Rematch: Honda2", "Fight: Honda2", "Honda2 wins", "Challenger: Tiger"]
    drop = seq[:len(want)] == want
    lines.append(f"    {'✓' if drop else '✗'} Piston Honda's rematch lost there: {' > '.join(seq[:len(want)])}")
    return good and win and drop, lines


def original_flow(rom):
    """The original Game Boy, as a player goes in: NEW, Glass Joe's challenger (the recorded crowd playing), the
    fight (its load with that crowd's interrupts stopped), round 1's end, the corner (Doc moving; Select taken once),
    back in the fight. Every scene a real one, the stack where it belongs."""
    from . import bot
    names, fights = _scenes()
    g = bot.Game(rom, fights[0], False)
    S0, B0 = bot._symbols(rom)
    g.pb.hook_register(B0["Start"], S0["Start"], lambda _: setattr(g.pb.register_file, "A", 1), None)
    corner = next(i for i, n in enumerate(names) if n == "Corner")
    seen, crowd, bad, docs, f = [], False, None, set(), 0
    for f in range(9000):
        sc = g.hram("hScene")
        if f > 300 and (sc >= len(names) or not 0xC000 <= g.pb.register_file.SP < 0xE000):
            bad = f"frame {f}: scene {sc}, SP ${g.pb.register_file.SP:04X}"
            break
        if not seen or seen[-1] != names[sc]:
            seen.append(names[sc])
            if names[sc] == "Fight" and seen.count("Fight") == 1:
                for _ in range(300):
                    g.tick(False)
                g.m[g.w + 0x302], g.m[g.w + 0x304], g.m[g.w + 0x305] = 2, 5, 8     # (round 1's end, soon)
        crowd = crowd or g.m[g.S["wPcmOn"]] == 1
        if sc == corner:
            docs.add(g.m[g.S["wDocState"]])
        g.hold(["select"] if sc == corner and f % 200 == 100 else ["start"] if f % 40 < 3 and g.hram("hFtActive") != 1 else [])
        g.tick(False)
        if seen.count("Fight") >= 2 and len(docs) >= 3:
            break
    used = g.m[g.w + 0x3D8]
    g.stop()
    good = bad is None and crowd and "Corner" in seen and seen.count("Fight") >= 2 and len(docs) >= 3 and used == 1
    return good, [f"    {'✓' if good else '✗'} {' > '.join(seen[:8])}: the crowd recorded {'yes' if crowd else 'no'}, Doc in "
                  f"{len(docs)} states, Select {'taken' if used == 1 else 'not taken'}" + (f" ({bad})" if bad else "")]


def _job(args):
    name, rom = args
    return globals()[name](rom)


def run(log=print):
    try:
        import pyboy  # noqa: F401
    except ImportError:
        log("  (skipped: needs PyBoy)")
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    build = build_rom(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    rom = Path(tempfile.mkdtemp(prefix="gbstage-career-")) / "game.gbc"
    rom.write_bytes(build.rom)
    Path(str(rom) + ".sym").write_text(build.sym)
    ok = True
    titles = {"career": "The whole game, won (power-on to THE END)", "losses": "Losing", "routes": "Down the ranks",
              "pass_key": "CONTINUE", "another_world": "The Another World Circuit",
              "original_flow": "The original Game Boy, into the fight and the corner"}
    with ProcessPoolExecutor() as pool:
        for name, (good, lines) in zip(titles, pool.map(_job, [(n, str(rom)) for n in titles])):
            log(f"  {titles[name]}:")
            for line in lines:
                log(line)
            ok = ok and good
    return ok
