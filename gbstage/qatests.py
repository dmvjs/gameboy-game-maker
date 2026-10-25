"""Quality checks on the Joe vs Mac example's ROM, each a career job (careertests.py runs them): the fights' frame
budget (the crowd's sound never runs dry, his pictures up no later than they were), Mac's height as the NES's (low
from a round's first frame, low through a count, walked up by the NES's $70), the star's sparkle over his head when
the NES has no spot of its own for it, the original Game Boy's screens as they were (their words readable), and the
HUD's first frame each round (the NES's numbers, not the last round's). QA_UPDATE=1 writes the references instead."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
REF = ROOT / "tests" / "qa_reference.json"
GREY = ROOT / "tests" / "golden" / "grey-screens"
UPDATE = os.environ.get("QA_UPDATE") == "1"
LATE_MARGIN = 1.5                       # (picture-late %: the bot plays no part, but a picture's tiles can shift)
GREY_SCREENS = ["Title", "Challenger", "Challenger: Tyson", "You win", "Joe wins", "You win (TKO): Bull",
                "Title bout: Honda", "The dream fight", "Pass key", "Credits"]


def _project():
    return json.loads(EXAMPLE.read_text())


def _fights():
    return [(i, s["name"]) for i, s in enumerate(_project()["scenes"]) if s.get("fight")]


def _ref():
    return json.loads(REF.read_text()) if REF.exists() else {}


def _save_ref(key, value):
    ref = _ref()
    ref[key] = value
    REF.write_text(json.dumps(ref, indent=1, sort_keys=True) + "\n")


def _game(rom, scene, cgb):
    from . import bot
    g = bot.Game(rom, scene, cgb, False)
    if not cgb:                         # (as the original boots: A = $01; PyBoy gives $11)
        S, B = bot._symbols(rom)
        g.pb.hook_register(B["Start"], S["Start"], lambda _: setattr(g.pb.register_file, "A", 1), None)
    return g


def _to_fight(g, scene, limit=4000):
    t = 0
    while not (g.hram("hScene") == scene and g.hram("hFtActive") == 1) and t < limit:
        g.hold(["start"] if t % 50 < 3 else [])
        g.tick(False)
        t += 1
    return g.hram("hScene") == scene


def _passive(rom, scene, cgb, frames):
    """Mac standing still: the frames, the crowd's sound run dry, his pictures shown late."""
    from . import bot
    S, B = bot._symbols(rom)
    g = _game(rom, scene, cgb)
    st = {"under": 0}
    if "PcmMixOut.back" in S:
        g.pb.hook_register(B["PcmMixOut.back"], S["PcmMixOut.back"],
                           lambda _: st.__setitem__("under", st["under"] + (g.hram("hScene") == scene)), None)
    _to_fight(g, scene)
    n = behind = 0
    for _ in range(frames):
        g.hold([])
        g.tick(False)
        if g.hram("hScene") != scene:
            break
        if g.hram("hFtActive") == 1:
            n += 1
            behind += g.m[S["wRvPic"]] != g.m[S["wRvPicShown"]]
    g.stop()
    return n, st["under"], 100 * behind / max(1, n)


def qa_perf(rom):
    """Each fight, Color and the original, Mac still (3000 frames): the crowd's sound never runs dry; his pictures
    up late no more often than when last measured."""
    ref, out, lines, good = _ref().get("perf", {}), {}, [], True
    for scene, name in _fights():
        for cgb in (True, False):
            key = f"{name}|{'cgb' if cgb else 'dmg'}"
            n, under, late = _passive(rom, scene, cgb, 3000)
            out[key] = round(late, 2)
            ok = under == 0 and (UPDATE or late <= ref.get(key, 100) + LATE_MARGIN)
            good = good and ok
            if not ok or UPDATE:
                lines.append(f"    {'✓' if ok else '✗'} {key}: {n} frames, sound dry {under}, pictures late {late:.2f}%"
                             f" (was {ref.get(key, '-')})")
    if UPDATE:
        _save_ref("perf", out)
    lines.append(f"    {'✓' if good else '✗'} {len(out)} fights' frames within budget")
    return good, lines


def qa_mac(rom):
    """Mac's height as the NES has it: low (its walk in's) from the round's first frame; through an opponent's
    count, low (his frames $81-$95 with the NES's $70 at 72); his walk up after, by $70 (MacWalkY)."""
    from . import bot, codegen
    project = codegen.validate(_project())
    fight = next(s for s in project["scenes"] if s["name"] == "Fight: Bull")
    nes = fight["fight"]["nes"]
    start_y = nes["mac_places"][0x48] & 0x7F
    from .project import MAC_LOW_SCALE
    walk = [min(63, round((84 - v) * 4 * MAC_LOW_SCALE)) for v in range(72, 85)]
    scene = next(i for i, s in _fights() if s == "Fight: Bull")
    S, _ = bot._symbols(rom)
    lines, good = [], True
    g = _game(rom, scene, True)         # the round's first frames, before his first pose: low
    _to_fight(g, scene)
    first = []
    for _ in range(15):
        first.append(g.m[S["wPlNesY"]] & 0x7F)
        g.tick(False)
    g.stop()
    ok = all(v == start_y for v in first[:5])
    good = good and ok
    lines.append(f"    {'✓' if ok else '✗'} low from the round's first frame ({first[:5]}, the NES's {start_y})")
    st = {"down": 0, "on": False, "count": [], "up": [], "n": 0}

    class Done(Exception):
        pass
    otick = bot.Game.tick

    def tick(self, render=True):        # the bot to his first knockdown, then the count and his getup
        otick(self, render)
        if self.hram("hScene") != scene:
            return
        d, f, y = self.nes(0x05), self.nes(0x61), self.m[S["wPlNesY"]] & 0x7F
        if d == 1 and st["down"] != 1:
            st["on"] = True
        st["down"] = d
        if st["on"]:
            st["n"] += 1
            if 0x81 <= f <= 0x95:
                v70 = self.nes(0x70)
                (st["count"] if v70 == 72 else st["up"]).append((v70, y))
            if st["n"] > 700 or (st["up"] and len(st["up"]) > 30):
                raise Done
    bot.Game.tick = tick
    try:
        bot.play(rom, scene, frames=9000, cgb=True)
    except Done:
        pass
    finally:
        bot.Game.tick = otick
    ok = bool(st["count"]) and all(y == walk[0] for _, y in st["count"])
    good = good and ok
    lines.append(f"    {'✓' if ok else '✗'} low through the count: {len(st['count'])} frames at {walk[0]}")
    ok = bool(st["up"]) and all(y == (walk[v - 72] if 72 <= v <= 84 else start_y) for v, y in st["up"])
    good = good and ok
    lines.append(f"    {'✓' if ok else '✗'} walked up by the NES's $70: {len(st['up'])} frames")
    return good, lines


def qa_star(rom):
    """A star earned, the NES with no spot of its own for its sparkle ($0344 = 1: it's in his picture, over his
    head): ours over his head too, following him -- never the right post's corner."""
    from . import bot, codegen
    from . import fight as kit
    project = codegen.validate(_project())
    lines, good = [], True
    for name in ("Fight: Bull", "Fight: Honda"):
        scene = next(i for i, s in _fights() if s == name)
        ft = project["scenes"][scene]["fight"]
        center = ft["x"] * 8 + kit.REGION_W * 4
        S, _ = bot._symbols(rom)
        seen = []

        class Done(Exception):
            pass
        otick = bot.Game.tick

        def tick(self, render=True, scene=scene, seen=seen):
            otick(self, render)
            if self.hram("hScene") != scene:
                return
            a = self.nes(0x343)
            if a and not a & 0x80 and self.nes(0x344) == 1:
                bx = self.hram("hFtBandX")
                bx = bx - 256 if bx > 127 else bx
                seen.append((self.m[S["wFtTwinkleX"]] - 8, center - bx))
                if len(seen) > 20:
                    raise Done
        bot.Game.tick = tick
        try:
            bot.play(rom, scene, frames=7000, cgb=True)
        except Done:
            pass
        finally:
            bot.Game.tick = otick
        ok = bool(seen) and all(abs(x - c) <= 20 for x, c in seen)
        good = good and ok
        lines.append(f"    {'✓' if ok else '✗'} {name}: {len(seen)} frames of its sparkle, over his head"
                     f" (x {sorted(set(x for x, _ in seen))[:4]}, his middle {sorted(set(c for _, c in seen))[:4]})")
    return good, lines


def _grey_screen(rom, scene):
    """The original Game Boy's screen, 90 frames into a scene (its four greys, 0-3)."""
    import numpy
    g = _game(rom, scene, False)
    at, left = None, scene != 0         # (the title: once the first screen's gone by -- power-on is scene 0 too)
    for t in range(1500):
        left = left or g.hram("hScene") != 0
        here = left and g.hram("hScene") == scene
        g.hold(["start"] if at is None and scene != 0 and t % 60 < 3 else [])
        g.tick(False)
        if here and at is None:
            at = t
        if at is not None and t - at == 90:
            break
    g.tick(True)
    px = g.pb.screen.ndarray[:, :, :3].astype("uint16").sum(axis=2)
    ok = g.hram("hScene") == scene
    g.stop()
    return ok, ((px < 600).astype("uint8") + (px < 380) + (px < 150)).astype("uint8")


def qa_grey(rom):
    """The original Game Boy's screens between the fights, as they were: each the same, pixel for pixel, as its
    saved one (their words readable: light on black, as the NES's on navy)."""
    import numpy
    from PIL import Image
    names = [s["name"] for s in _project()["scenes"]]
    lines, good = [], True
    GREY.mkdir(parents=True, exist_ok=True)
    for name in GREY_SCREENS:
        if name not in names:
            continue
        reached, px = _grey_screen(rom, names.index(name))
        path = GREY / (name.replace(":", "").replace(" ", "-").replace("(", "").replace(")", "").lower() + ".png")
        if UPDATE:
            Image.fromarray(255 - px * 85).save(path, optimize=True)
            lines.append(f"    ✓ {name}: saved")
            continue
        want = ((255 - numpy.array(Image.open(path))) // 85).astype("uint8") if path.exists() else None
        diff = None if want is None else int((want != px).sum())
        ok = reached and diff == 0
        good = good and ok
        if not ok:
            lines.append(f"    ✗ {name}: {'not reached' if not reached else 'no saved screen' if diff is None else f'{diff} pixels differ'}")
    lines.append(f"    {'✓' if good else '✗'} {len(GREY_SCREENS)} screens as saved")
    return good, lines


def qa_hud(rom):
    """Each fight's first frame, Color and the original: Mac's hearts the NES's he starts with, the clock and points
    the NES's (not the last fight's or round's)."""
    from . import bot, codegen
    S, _ = bot._symbols(rom)
    lines, good = [], True
    for scene, name in _fights():
        for cgb in (True, False):
            g = _game(rom, scene, cgb)
            _to_fight(g, scene)
            hearts, sec, mn = g.m[S["wPlHearts"]], g.m[S["wFtSec"]], g.m[S["wFtMin"]]
            g.stop()
            want = codegen.NES_START_HEARTS.get(name)
            ok = (want is None or hearts == want) and (mn, sec) == (0, 0)
            good = good and ok
            if not ok:
                lines.append(f"    ✗ {name} {'cgb' if cgb else 'dmg'}: hearts {hearts} (the NES's {want}), clock {mn}:{sec:02X}")
    lines.append(f"    {'✓' if good else '✗'} every fight's HUD right from its first frame")
    return good, lines
