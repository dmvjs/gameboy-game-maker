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
    titles = {"career": "The whole game, won (power-on to THE END)", "losses": "Losing", "pass_key": "CONTINUE"}
    with ProcessPoolExecutor() as pool:
        for name, (good, lines) in zip(titles, pool.map(_job, [(n, str(rom)) for n in titles])):
            log(f"  {titles[name]}:")
            for line in lines:
                log(line)
            ok = ok and good
    return ok
