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
from .qatests import qa_decision, qa_grey, qa_hud, qa_mac, qa_perf, qa_reset, qa_sgb, qa_star  # noqa: F401  (career jobs too)

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
                if not passwords.HAVE:                   # (no NES code here, as on CI: its reading not checked)
                    lines.append(f"    ✓ {names[key_scene]}: pass key {''.join(map(str, digits))} (not read: no disassembly)")
                    continue
                want = passwords.decode(digits)
                good = special or (want is not None and want[:3] == rec)
                ok = ok and good
                lines.append(f"    {'✓' if good else '✗'} {names[key_scene]}: pass key {''.join(map(str, digits))}"
                             + ("" if special else f" (the NES reads it as {want})"))
        seen, held = set(), 0                   # then the ending, to its last screen: held there, Start or not (the NES's)
        for t in range(20000):
            seen.add(names[g.hram("hScene")])
            held = held + 1 if names[g.hram("hScene")] == "The end" else 0
            if held > 600:
                break
            g.hold(["start"] if t % 120 < 3 else [])
            g.tick(False)
        good = held > 600
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} the ending: {len([s for s in seen if s.startswith('Ending')])} portraits, THE END, held")
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


NES_REF = ROOT / "tests" / "nes_reference.json"     # what the NES does (tools/punchout_art/nes_reference.py)


def _boot(rom, redirect=None):
    """PyBoy on the ROM to the title, ready for keys; redirect: Glass Joe's challenger is that scene instead."""
    from pyboy import PyBoy
    from . import bot
    S, B = bot._symbols(rom)
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    if redirect is not None:
        done = []

        def jump(_):
            if pb.register_file.A == 1 and not done:
                pb.register_file.A = redirect
                done.append(1)
        pb.hook_register(B["LoadScene"], S["LoadScene"], jump, None)
    m, f = pb.memory, 0
    while (m[S["hScene"]] != 0 or f < 400) and f < 6000:
        pb.tick(1, False)
        f += 1
    pb.tick(240, False)
    return pb, S


def _tap(pb, b):
    pb.button_press(b); pb.tick(3, False); pb.button_release(b); pb.tick(5, False)


def _type_key(pb, digits, select=False, partial=None):
    """CONTINUE, the digits as a player types them (right to step one, A for the next; Select held on the last's
    A for the special keys), Start after a partial one."""
    _tap(pb, "down")
    pb.tick(20, False)
    _tap(pb, "right")
    for k, ch in enumerate(digits[:partial or 10]):
        for _ in range(int(ch)):
            _tap(pb, "right")
        if k == 9 and select:
            pb.button_press("select"); pb.tick(4, False)
            _tap(pb, "a")
            pb.button_release("select")
        else:
            _tap(pb, "a")
    if partial:
        _tap(pb, "start")


def _fighter(name):
    return "Joe" if name in ("Fight", "Challenger") else name.split(": ")[-1]


def nes_keys(rom):
    """The title's pass keys, every one the NES was tried with (valid, special, wrong, half typed): the same
    challenger and record, or the same back to NEW (busy signals after their beeps), or still waiting."""
    names, _ = _scenes()
    ref = json.loads(NES_REF.read_text())["pass_keys"]
    lines, ok = [], True
    for case in ref:
        pb, S = _boot(rom)
        m = pb.memory
        _type_key(pb, case["digits"], case["select"], case["partial"])
        pb.tick(900, False)
        scene = names[m[S["hScene"]]]
        if case["to"] == "credits":                     # (the staff credits: typed in, and they stay, Start or not)
            pb.tick(2400, False)
            for _ in range(3):
                pb.button_press("start"); pb.tick(4, False); pb.button_release("start"); pb.tick(120, False)
            scene = scene if names[m[S["hScene"]]] == scene else names[m[S["hScene"]]] + " (after Start)"
        rec = [m[S[n]] for n in ("wRecWins", "wRecLosses", "wRecKOs")]
        sel, shown, aw = m[S["hSel"]], m[S["wPkShown"]], m[S["wAw"]]
        pb.stop(save=False)
        want = case["to"]
        if want == "challenger":
            good = (scene.startswith("Challenger") and _fighter(scene).rstrip("2") == case["opponent"].rstrip("2")
                    and rec == case["record"] and aw == bool(case.get("another_world")))
            got = f"{scene}, {rec[0]}-{rec[1]} {rec[2]}KO"
        elif want == "title":
            good, got = scene == "Title" and sel == 0 and not shown, f"{scene}, item {sel}, key {'shown' if shown else 'hidden'}"
        elif want == "waiting":
            good, got = scene == "Title" and sel == 1 and shown, f"{scene}, still typing" if shown else scene
        else:                                           # (the credits: the NES's staff roll, held)
            good, got = scene == "Credits", scene
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} {case['name']}: {got}" + ("" if good else f" (the NES: {want})"))
    return ok, lines


def _forced(rom, plan, redirect=None, key=None, select=False, frames=40000, settle=2500, start_after=False):
    """The fights in turn, each won (the NES's own result, $00 = $FC, as nes_reference.py does it) or lost (Mac's
    health held at 0), START between: each fight's fighter and Mac's record going in, and the scenes passed."""
    names, _ = _scenes()
    pb, S = _boot(rom, redirect)
    m, w = pb.memory, S["wNes"]
    if key:
        _type_key(pb, key, select)
    fights, seen, infight, t0, held, still, last = [], [], False, 0, False, 0, None
    for f in range(frames):
        sc = names[m[S["hScene"]]]
        if not seen or seen[-1] != sc:
            seen.append(sc)
            still = 0
        else:
            still += 1
        active = m[S["hFtActive"]] == 1
        if active and not infight:
            infight, t0 = True, f
            res = plan[len(fights)] if len(fights) < len(plan) else "W"
            fights.append({"opponent": _fighter(sc), "record": [m[S[n]] for n in ("wRecWins", "wRecLosses", "wRecKOs")],
                           "result": res})
        if infight:
            if res == "L":
                m[w + 0x391] = 0
            elif f - t0 == 200:
                m[w + 0x00] = 0xFC
            if not active and f - t0 > 210:
                infight = False
        if len(fights) > len(plan) or (len(fights) == len(plan) and not infight and still > settle):
            break
        press = not infight and f % 90 < 3 and len(fights) < len(plan)
        if press != held:
            (pb.button_press if press else pb.button_release)("start")
            held = press
        pb.tick(1, False)
    if start_after:                                     # (where it settled, Start pressed there: THE END stays)
        for _ in range(3):
            pb.button_press("start"); pb.tick(4, False); pb.button_release("start"); pb.tick(150, False)
        sc = names[m[S["hScene"]]]
        if sc != seen[-1]:
            seen.append(sc)
    aw = m[S["wAw"]]
    pb.stop(save=False)
    return fights[:len(plan)], seen, aw


def _same(gb, nes):
    """The fights alike: each's fighter (a rematch's, or the Another World Circuit's, by name) and record."""
    return len(gb) == len(nes) and all(g["opponent"].rstrip("2") == n["opponent"].rstrip("2") and g["record"] == n["record"]
                                       for g, n in zip(gb, nes))


def _fights(fs):
    return " > ".join(f"{f['opponent']} {f['record'][0]}-{f['record'][1]} {f['result']}" for f in fs)


def nes_flows(rom):
    """NEW and the Another World Circuit's start (to the fight itself); losing (rematches, down the ranks, game over
    and the record cleared); each circuit's title fight won (its training run or the paper, then the next); Mike
    Tyson beaten (the ending, held at THE END) -- each fight's fighter and record as the NES's."""
    names, _ = _scenes()
    ref = json.loads(NES_REF.read_text())["flows"]
    start = {"Joe": None, **{n.split(": ")[1]: i for i, n in enumerate(names) if n.startswith("Challenger: ")}}
    lines, ok = [], True
    for name, r in ref.items():
        if name == "the Another World Circuit won through":
            continue                                    # (its own test: another_world_won)
        first = r["fights"][0]["opponent"]
        plan = "".join(f["result"] for f in r["fights"])
        key = None
        if name == "Another World":
            import sys
            sys.path.insert(0, str(ROOT / "tools" / "punchout_art"))
            import passwords
            key = passwords.SPECIAL["another_world"]
        on = name in ("Piston Honda's title fight lost, then Von Kaiser's", "Bald Bull's title fight lost, then Great Tiger's")
        gb, seen, aw = _forced(rom, plan + ("W" if on else ""), None if key or first == "Joe" else start[first], key, bool(key),
                               settle=2500 if name == "Mike Tyson won" else 600, start_after=name == "Mike Tyson won")
        gb = gb[:len(plan)]                             # (on: one fight more, past its TITLE BOUT!! to the title bout)
        good = _same(gb, r["fights"])
        extra = ""
        if name == "Mike Tyson won":                    # (the ending, and THE END held: Start does nothing there)
            ends = [s for s in seen if s.startswith("Ending")]
            good = good and len(ends) == 10 and seen[-1] == "The end"
            extra = f"; {len(ends)} portraits, {seen[-1]}"
        between = seen[seen.index(next(s for s in seen if s.startswith("Fight"))) + 1:]
        between = [s for s in between if not s.startswith(("Bells", "First"))]
        want = {"Piston Honda's title fight won": ["Training: Honda", "Challenger: Don"],   # (the NES's, between)
                "Bald Bull's title fight won": ["Training: Bull", "Challenger: Honda2"],
                "Super Macho Man's title fight won": ["KO News", "The dream fight", "Challenger: Tyson"],
                "Piston Honda's title fight lost, then Von Kaiser's": ["Title bout: Honda", "Challenger: Honda"],
                "Bald Bull's title fight lost, then Great Tiger's": ["Title bout: Bull", "Challenger: Bull"]}.get(name)
        if want:
            k, hits = 0, []
            for sc in between:                          # (in that order, others between)
                if k < len(want) and sc == want[k]:
                    hits.append(sc)
                    k += 1
            good = good and k == len(want)
            extra = "; " + " > ".join(between)[:140]
        if name == "Another World":
            good = good and aw == 1
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} {name}: {_fights(gb)}{extra}" + ("" if good else f" (the NES: {_fights(r['fights'])})"))
    return ok, lines


def another_world_won(rom):
    """The Another World Circuit from 135 792 4680 (A+B+Select) through every fight to its ending: each next
    fighter and the record as the NES's, Mike Tyson's word with the fight's time, the portraits, THE END."""
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "punchout_art"))
    import passwords
    r = json.loads(NES_REF.read_text())["flows"]["the Another World Circuit won through"]
    plan = "".join(f["result"] for f in r["fights"])
    gb, seen, aw = _forced(rom, plan, key=passwords.SPECIAL["another_world"], select=True, frames=90000, settle=2500)
    ends = [s for s in seen if s.startswith("Ending")]
    good = _same(gb, r["fights"]) and aw == 1 and any(s.startswith("You win") and s.endswith("Tyson") for s in seen) \
        and len(ends) == 10 and seen[-1] == "The end" and "Title bout: Another World" in seen   # (its TITLE BOUT!!)
    return good, [f"    {'✓' if good else '✗'} {_fights(gb)}; {len(ends)} portraits, {seen[-1]}"
                  + ("" if good else f" (the NES: {_fights(r['fights'])})")]


def another_world_played(rom):
    """The Another World Circuit as a player plays it: 135 792 4680 typed with Select held on its last digit, then
    the bot (buttons only, the crowd's tells too) wins each of its nine fights in turn; the record and the next fight
    after each; Mike Tyson's word, the portraits, THE END."""
    from . import bot
    names, _ = _scenes()
    order = ["Hippo", "Tiger", "Honda2", "Soda", "Bull2", "Don2", "Sandman", "Macho", "Tyson"]
    g = bot.Game(rom, 2)                        # (no redirect: the title's own way in, by the key)
    g.stop = lambda: None
    pb, m, S = g.pb, g.m, g.S

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
    pb.tick(300, False)
    lines, ok, kos = [], m[S["wAw"]] == 1, 0
    lines.append(f"    {'✓' if ok else '✗'} 135 792 4680: {names[m[S['hScene']]]}, the circuit {'on' if m[S['wAw']] else 'off'}")
    game, bot.Game = bot.Game, lambda *a, **k: g
    try:
        for k, who in enumerate(order):
            scene = names.index(f"Fight: {who}")
            r = bot.play(rom, scene)
            kos += r["won"] and r["result"] in (0xFC, 0xFE)
            rec = _record(g)
            nxt = m[S["wRecNext"]]
            good = r["won"] and rec == (k + 1, 0, kos)
            ok = ok and good
            lines.append(f"    {'✓' if good else '✗'} {names[scene]}: {'won' if r['won'] else 'lost'}, record {rec[0]}-{rec[1]} "
                         f"{rec[2]}KO, next {names[nxt] if nxt < len(names) else nxt}")
            if not good:
                return False, lines
        seen, held = [], 0                      # then Mike Tyson's word with the time, the portraits, THE END held
        for t in range(20000):
            sc = names[g.hram("hScene")]
            if not seen or seen[-1] != sc:
                seen.append(sc)
            held = held + 1 if sc == "The end" else 0
            if held > 600:
                break
            g.hold(["start"] if t % 120 < 3 else [])
            g.tick(False)
        good = held > 600
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} the ending: {len([s for s in seen if s.startswith('Ending')])} portraits, THE END, held")
    finally:
        bot.Game = game
    return ok, lines


def beat_mac(rom, only=None):
    """Each opponent beats Mac standing still, as the NES game's do (its, recorded: tests/nes_reference.json
    idle_losses): counted out ($FD), his states those of the NES's (taunts with them), on to the fight the NES goes
    to, and lost again there. Don Flamenco never attacks a still Mac."""
    names, _ = _scenes()
    ref = json.loads((ROOT / "tests" / "nes_reference.json").read_text())["idle_losses"]
    lines, ok = [], True
    for who, want in ref.items():
        if only and who not in only:
            continue
        entry = {"Honda": "Title bout: Honda", "Bull": "Title bout: Bull", "Macho": "Title bout: Macho",   # (the title
                 "Tyson": "The dream fight"}.get(who, "Challenger" if who == "Joe" else f"Challenger: {who}")  # fights' way in)
        pb, S = _boot(rom, names.index(entry))
        m, w = pb.memory, S["wNes"]

        def until_fight(limit=6000):
            left = m[S["hFtActive"]] != 1               # (the fight that ended first, then the next's start)
            for f in range(limit):
                if m[S["hFtActive"]] != 1:
                    left = True
                elif left:
                    return True
                (pb.button_press if f % 60 < 3 else pb.button_release)("start")
                pb.tick(1, False)
            return False
        pb.button_press("start"); pb.tick(3, False); pb.button_release("start")
        until_fight()
        pb.button_release("start")

        def lose(limit):
            states, down = set(), False
            for f in range(limit):
                pb.tick(1, False)
                if m[w + 0x00] == 1:
                    states.add(m[w + 0x90] & 0x7F)
                down = down or m[w + 0x05] == 2
                if m[w + 0x00] in (0xFB, 0xFC, 0xFD, 0xFE):
                    return m[w + 0x00], states, f, down
            return None, states, limit, down
        res, states, frames, down = lose(9000)
        if want["result"] is None:              # (Don Flamenco: waits for Mac to throw something)
            good = res is None and not down
            lines.append(f"    {'✓' if good else '✗'} {who}: never attacks a still Mac ({frames} frames, Mac {'down' if down else 'never down'})")
        else:
            nxt = None
            if res is not None and until_fight():
                nxt = _fighter(names[m[S["hScene"]]])
            again = lose(9000)[0] if nxt else None
            extra = sorted(states - set(want["states_used"]))
            good = res == want["result"] and not extra and nxt == want["next"] and again == want["result"]
            lines.append(f"    {'✓' if good else '✗'} {who}: ${res or 0:02X} after {frames} frames (the NES's ${want['result']:02X}, "
                         f"{want['frames']}), states {sorted(states)}{f' (not the NES: {extra})' if extra else ''}, "
                         f"then {nxt} (the NES's {want['next']}), lost again ${again or 0:02X}")
        ok = ok and good
        pb.stop(save=False)
    return ok, lines


def tells(rom):
    """Punch-Out!!'s crowd tells used as a player uses them: the bot (bot.py) watches the tell's cell on the screen and
    throws his counter in the NES's window (tests/nes_reference.json "tells"): in a real fight it knocks him down; from
    the tell's frame, the body blow at the bot's delay knocks him down and one straight away, or 20 frames late,
    doesn't."""
    from . import bot
    names, _ = _scenes()
    ref = json.loads((ROOT / "tests" / "nes_reference.json").read_text())["tells"]
    lines, ok = [], True
    for who in ref:
        scene = names.index(f"Fight: {who}")
        trials, tried, orig = {}, [], bot.Game.tick       # (a tell Mac can't answer, mid-hit: the next, up to 3)

        state, live, due = ref[who]["state"], [0], [1200]

        def tick(self, render=True, _orig=orig):
            _orig(self, render)
            if not render or trials.get("bot's") or len(tried) >= 3 or not hasattr(self, "_cue_cell"):
                return
            live[0] += self.hram("hFtActive") == 1 and self.nes(0x05) == 0
            if live[0] >= due[0] and self.nes(0x90) & 0x7F in (1, 2):   # (not reached by now: his move forced, from
                self.m[self.w + 0x90] = state | 0x80                    # standing, as the NES's script has it; again
                due[0] = live[0] + 600                                  # in a while if it can't be answered)
            lit = self.m[0, self._cue_cell[0]] != self._cue_cell[1]
            first, self._was_lit = lit and not getattr(self, "_was_lit", False), lit
            if first:                                                # (the tell's first frame on screen)
                snap = self.save()
                for name, at in (("early", 0), ("bot's", self._cue_cell[2]), ("late", 20)):
                    self.load(snap)
                    down = False
                    for k in range(at + 60):
                        self.hold(["a"] if at <= k < at + 3 else [])
                        _orig(self, False)
                        self.m[self.w + 0x391] = 0x60
                        if self.nes(0x05) == 1:
                            down = True
                            break
                    trials[name] = down
                tried.append(dict(trials))
                self.load(snap)
        cue_of = bot._cue

        def cue(g, _cue=cue_of):
            c = _cue(g)
            if c:
                g._cue_cell = c
            return c
        bot.Game.tick, bot._cue = tick, cue
        try:
            r = bot.play(rom, scene, frames=20000)
        finally:
            bot.Game.tick, bot._cue = orig, cue_of
        ev = r["events"]
        countered = any(e[2] == "him down" and any(t[2] == "crowd tell" and 0 < e[0] - t[0] < 40 for t in ev) for e in ev)
        good = countered and trials == {"early": False, "bot's": True, "late": False}
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} {who}: {sum(e[2] == 'crowd tell' for e in ev)} tells, countered into a knockdown: "
                     f"{'yes' if countered else 'no'}; from the tell: {trials}")
    dodge = json.loads((ROOT / "tests" / "nes_reference.json").read_text())["dodge_tells"]
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    for who, want in dodge.items():
        for grey in (False, True):
            got = _dodge_tell(rom, names.index(f"Fight: {who}"), project, want, grey)
            dodged = got.pop("bot's dodge")
            fixed = dict(want["hit"], shows_through=False)     # (the NES's crowd freeze, not ours: kit_nes.asm NesCueOwner)
            good = got == {k: want[k] for k in ("shows_after", "shows_for")} | {"hit": fixed} and dodged
            ok = ok and good
            lines.append(f"    {'✓' if good else '✗'} {who} ({'grey' if grey else 'Color'}): his tell (a dodge's) {got}; "
                         f"the bot's dodge from it escapes his punch: {'yes' if dodged else 'no'}"
                         + ("" if good else f" (the NES: {want})"))
    return ok, lines


def _dodge_tell(rom, scene, project, want, grey):
    """A dodge's crowd tell as the NES's (tests/nes_reference.json "dodge_tells"): his move started from standing
    with Mac free, the tell's cell watched on the screen (its rope row shows over his area's first row): left alone,
    the frame it first shows and for how many; hit in the move, his state next and whether the cell stays (the NES's
    crowd freeze: punched in his tell he's out of it and it never comes down; here it does); and the bot's
    answer (bot._cue's buttons, its delay from the cell's first showing) leaving Mac untouched by the move."""
    import numpy as np
    from . import bot
    g = bot.Game(rom, scene, cgb=not grey)
    if grey:                                    # (as a real one boots: A = $01)
        S, B = bot._symbols(rom)
        g.pb.hook_register(B["Start"], S["Start"], lambda _: setattr(g.pb.register_file, "A", 1), None)
    t = 0
    while t < 20000:
        on = g.hram("hScene") == scene and g.hram("hFtActive") == 1
        g.hold(["start"] if not on and t % 50 < 3 else [])
        g.tick()
        t += 1
        if on:
            g.m[g.w + 0x391] = 0x60
            if g.nes(0x00) == 1 and t > 1400 and g.nes(0x90) & 0x7F == 1 and g.nes(0x50) == 1:
                break
    y = project["scenes"][scene]["fight"]["y"] * 8
    x = g.m[g.S["wFtCueCol"]] * 8
    screen = lambda: g.pb.screen.ndarray[y:y + 8, x:x + 8, :3].copy()
    rest, snap, out = screen(), g.save(), {}
    cue = None
    for hit in (False, True):
        g.load(snap)
        shown, states = [], []
        for k in range(want["window"]):
            g.m[g.w + 0x391] = 0x60
            g.hold([want["hit"]["button"].lower()] if hit and want["hit"]["at"] <= k < want["hit"]["at"] + 3 else [])
            if k == 0:
                g.m[g.w + 0x90] = want["state"] | 0x80
            g.tick()
            shown.append(not np.array_equal(screen(), rest))
            states.append(g.nes(0x90) & 0x7F)
        first = shown.index(True) if True in shown else -1
        n = (shown[first:] + [False]).index(False) if first >= 0 else 0
        if hit:
            out["hit"] = {"button": want["hit"]["button"], "at": want["hit"]["at"],
                          "his_state": next((v for v in states if v != want["state"]), None),
                          "shows_through": first >= 0 and n == want["window"] - first}
        else:
            out["shows_after"], out["shows_for"] = first, n
            cue = bot._cue(g)
    g.load(snap)
    hurt = False
    for k in range(want["window"] // 2):        # (the bot's dodge: Mac's health untouched through the move)
        g.hold(cue[3] if cue and first >= 0 and first + cue[2] <= k < first + cue[2] + 3 else [])
        if k == 0:
            g.m[g.w + 0x90] = want["state"] | 0x80
        g.tick()
        hurt = hurt or g.nes(0x391) < 0x60
        if g.nes(0x90) & 0x7F not in (want["state"], 0x01) and k > 0:
            break                               # (the move over: what follows is another)
    out["bot's dodge"] = cue is not None and not hurt
    g.stop()
    return out


def glitches(rom):
    """The NES game's glitches, not ours. The clock stop (tests/nes_reference.json "clock_stops": TASVideos' clock-stop
    run's long holds, from cynes): the NES's RAM put in the port's fight (its script pointers' high bytes as the port
    keeps them, $40 down; the sound's aside), the run's inputs fed (a frame early: the harness's button reaches the
    port a frame after cynes'), Mac's and his states following the NES's to the hold, and the clock held there briefly,
    not the NES's hundreds of frames. Mr. Sandman's midget ($80 and $10's sprite size left 8x8 by a cut-off script: the
    NES draws him in strips): the port's screen the same either way."""
    import numpy as np
    from . import bot
    names, _ = _scenes()
    ref = json.loads((ROOT / "tests" / "nes_reference.json").read_text())["clock_stops"]
    ptr = (0x32, 0x34, 0x3C, 0x55, 0x7F, 0x95, 0x9F)
    keys = [(0x08, "up"), (0x04, "down"), (0x02, "left"), (0x01, "right"), (0x10, "start"), (0x20, "select"),
            (0x40, "b"), (0x80, "a")]
    lines, ok, games = [], True, {}

    def fight(who):
        if who not in games:
            scene = names.index(f"Fight: {who.capitalize() if who[-1] != '2' else who[:-1].capitalize() + '2'}")
            g = bot.Game(rom, scene)
            t = 0
            while t < 20000:
                on = g.hram("hScene") == scene and g.hram("hFtActive") == 1
                g.hold(["start"] if not on and t % 50 < 3 else [])
                g.tick(False)
                t += 1
                if on and g.nes(0x00) == 1 and g.nes(0x90) & 0x7F == 1 and g.nes(0x50) == 1 and t > 1400:
                    break
            games[who] = (g, g.save())
        return games[who]
    for c in ref:
        g, snap = fight(c["opponent"])
        g.load(snap)
        ram = bytes.fromhex(c["ram"])
        for a in range(0x800):
            if not (0xF0 <= a < 0x100 or a >= 0x700):
                g.m[g.w + a] = ram[a] - 0x40 if a in ptr and 0x80 <= ram[a] < 0xA0 else ram[a]
        back, follows, held = c["back"], None, 0
        for k in range(back + 199):
            b = c["inputs"][k + 1]
            g.hold([n for bit, n in keys if b & bit])
            g.tick(False)
            if follows is None and (k >= len(c["states"]) or [g.nes(0x50), g.nes(0x90) & 0x7F] != c["states"][k]):
                follows = k
            if k >= back:
                if not g.nes(0x301) & 1:
                    break
                held += g.nes(0x05) == 0
        follows = k + 1 if follows is None else follows     # (followed all the way)
        good = follows >= back and held < 100 <= c["held"]
        ok = ok and good
        lines.append(f"    {'✓' if good else '✗'} the clock stop, {c['opponent']}: the NES's run followed {follows} frames "
                     f"(to the hold: {back}); the clock held {held} frames (the NES: {c['held']})")
    for g, _ in games.values():
        g.stop()
    g = bot.Game(rom, names.index("Fight: Sandman"))
    t, prev = 0, 0
    while t < 20000:                                # (his first punch: in a script that sets them)
        on = g.hram("hScene") == g.scene and g.hram("hFtActive") == 1
        g.hold(["start"] if not on and t % 50 < 3 else [])
        g.tick(False)
        t += 1
        if on:
            g.m[g.w + 0x391] = 0x60
            if g.nes(0x97) and not prev and g.nes(0x05) == 0:
                break
            prev = g.nes(0x97)
    snap, shots = g.save(), {}
    for v in (0x10, 8):
        g.load(snap)
        frames = []
        for k in range(120):
            g.m[g.w + 0x391] = 0x60
            g.m[g.w + 0x80] = v
            g.m[g.w + 0x10] = (g.m[g.w + 0x10] & 0xDF) | (0x20 if v == 0x10 else 0)
            g.hold([])
            g.tick(True)
            frames.append(g.pb.screen.ndarray[:, :, :3].copy())
        shots[v] = frames
    g.stop()
    same = all(np.array_equal(a, b) for a, b in zip(shots[0x10], shots[8]))
    ok = ok and same
    lines.append(f"    {'✓' if same else '✗'} the midget Sandman: his screen with the NES's 8x8 sprites left on "
                 f"{'the same' if same else 'changed'} over 120 frames")
    return ok, lines


def random(rom):
    """The random byte ($18) as the NES builds it, on the NES's own frames (cynes: tests/nes_reference.json's
    "randoms"), the port's builder fed what the NES's was: nestests.randoms (no disassembly needed)."""
    from . import nestests
    lines = []
    good = nestests.randoms(lambda line: lines.append("  " + line.strip() if not line.startswith("    ") else line),
                            "the random byte, built as the NES builds it, on its own frames")
    return good, lines


def _job(args):
    name, rom = args
    return globals()[name](rom)


def run(log=print, only=None):
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
              "original_flow": "The original Game Boy, into the fight and the corner",
              "nes_keys": "The title's pass keys, as the NES takes them", "nes_flows": "Starts, losses, title fights, the ending, as the NES's",
              "another_world_won": "The Another World Circuit won through, as the NES's",
              "another_world_played": "The Another World Circuit, played through by the bot",
              "beat_mac": "Every opponent beats a still Mac, as the NES's",
              "tells": "The crowd's tells, used by the bot as the NES's",
              "glitches": "The NES game's glitches, fixed: the clock stop, the midget Sandman",
              "random": "The random byte, as the NES's",
              "qa_perf": "Each fight's frames within budget (the crowd's sound, his pictures, the original's poses as Color's)",
              "qa_mac": "Mac's height as the NES's (a round's start, a count, his walk up)",
              "qa_star": "A star's sparkle over his head, as the NES's",
              "qa_grey": "The original Game Boy's screens as saved",
              "qa_hud": "Every fight's HUD from its first frame",
              "qa_reset": "The soft reset, both machines",
              "qa_sgb": "The Super Game Boy: its packets, the border",
              "qa_decision": "A decision after the last round"}
    if only:
        titles = {k: v for k, v in titles.items() if k in only}
    with ProcessPoolExecutor() as pool:
        for name, (good, lines) in zip(titles, pool.map(_job, [(n, str(rom)) for n in titles])):
            log(f"  {titles[name]}:")
            for line in lines:
                log(line)
            ok = ok and good
    return ok
