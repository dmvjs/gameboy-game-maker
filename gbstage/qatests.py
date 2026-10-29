"""Quality checks on the Joe vs Mac example's ROM, each a career job (careertests.py runs them): the fights' frame
budget (the crowd's sound never runs dry, his pictures up no later than they were), Mac's height as the NES's (low
from a round's first frame, low through a count, walked up by the NES's $70), the star's sparkle over his head when
the NES has no spot of its own for it, the original Game Boy's screens as they were (their words readable), and the
HUD's first frame each round (the NES's numbers, not the last round's), the Super Game Boy's packets. QA_UPDATE=1 writes the references instead."""
import io
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
REF = ROOT / "tests" / "qa_reference.json"
GREY = ROOT / "tests" / "golden" / "grey-screens"
UPDATE = os.environ.get("QA_UPDATE") == "1"
LATE_MARGIN = 1.5                       # (picture-late %: the bot plays no part, but a picture's tiles can shift)
LATE_MARGIN_CGB = 0.5                   # (Color: his pictures up the frame the NES asks, the big ones too)
LAG_MARGIN = 1.0                        # (his poses up later on the original than on Color, % of them: Mac still, the
                                        #  same poses at the same frames on both, run to run; a frame's work can shift a few)
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


def crowd_watch(g, rom, scene, cgb):
    """The crowd's recording (kit_pcm.asm), each restart of the wave channel in the fight: {"under": the Color ring
    short of the 16 bytes (and as many as the restart's late) it reads, "wrap": a restart so much later than the
    one before that the channel ran past its buffer (its 32nd step: back to its first, a click)}."""
    from . import bot
    S, B = bot._symbols(rom)
    st, prev, cps = {"under": 0, "wrap": 0}, [None], 3 if cgb else 6     # (the timer's counts a step)

    def tick(_):
        m = g.pb.memory
        if g.hram("hScene") != scene or g.hram("hFtActive") != 1:
            prev[0] = None
            return
        d = (m[0xFF05] - m[0xFF06]) & 0xFF              # (the timer's counts since it overflowed: how late)
        if m[S["wPcmMix"]]:
            q = m[S["hPcmQ"]]
            if (m[S["wMixHead"]] - m[S["hPcmPtr"]]) & 0xFF < (d + q // 2) // q + 16:
                st["under"] += 1
        if prev[0] is not None and (256 - m[0xFF06]) + d - prev[0] >= 32 * cps:
            st["wrap"] += 1
        prev[0] = d

    def restart(_):
        prev[0] = None
    g.pb.hook_register(B["PcmTick"], S["PcmTick"], tick, None)
    for n in ("PcmMaybeFar", "PcmResume", "PcmStop"):
        g.pb.hook_register(B[n], S[n], restart, None)
    return st


def _passive(rom, scene, cgb, frames):
    """Mac standing still: the frames, the crowd's sound run dry or broken, his pictures shown late (% of frames); per
    VBlank the picture wanted and the one up after it; frames lost (their work run into VBlank: MainLoop's .late)."""
    from . import bot
    S, B = bot._symbols(rom)
    g = _game(rom, scene, cgb)
    st = crowd_watch(g, rom, scene, cgb)
    st.update({"lost": set(), "t": 0})
    shown = []
    vblank = g._vblank

    def done(_):                        # (VBlank's work done: the picture the NES wants, the one this frame shows)
        vblank(_)
        live = g.hram("hScene") == scene and g.hram("hFtActive") == 1
        shown.append((g.m[S["wRvPic"]], g.m[S["wRvPicShown"]]) if live else None)
    g.pb.hook_deregister(B["VBlankDone"], S["VBlankDone"])
    g.pb.hook_register(B["VBlankDone"], S["VBlankDone"], done, None)
    g.pb.hook_register(B["MainLoop.late"], S["MainLoop.late"], lambda _: st["lost"].add(st["t"]), None)
    _to_fight(g, scene)
    shown.clear()
    st["lost"].clear()
    n = behind = 0
    for t in range(frames):
        st["t"] = t
        g.hold([])
        g.tick(False)
        if g.hram("hScene") != scene:
            break
        if g.hram("hFtActive") == 1:
            n += 1
            behind += g.m[S["wRvPic"]] != g.m[S["wRvPicShown"]]
    if cgb and g.m[S["wPcmLoaded"]]:    # (and the recording, in WRAMX's first bank, as the ROM has it: the Color
        data = Path(rom).read_bytes()   #  ring, in its second, never over it)
        at = B["CrowdPcm"] * 0x4000 + S["CrowdPcm"] - 0x4000
        st["wrap"] += bytes(g.pb.memory[1, S["wPcm"]:S["wPcm"] + 512]) != data[at:at + 512]
    g.stop()
    return n, st["under"] + st["wrap"], 100 * behind / max(1, n), shown, len(st["lost"])


def _pose_delays(shown):
    """Per change of the picture wanted: the VBlanks till it's up (0: at the first, as wanted; 99: never, another
    wanted first)."""
    out, pend, prev = [], None, None
    for i, x in enumerate(shown):
        if x is None:
            pend = prev = None
            continue
        want, up = x
        if pend is not None and up == pend[0]:
            out[pend[1]] = i - pend[2]
            pend = None
        if prev is not None and want != prev:
            if pend is not None:
                out[pend[1]] = 99
            out.append(0 if want == up else 99)
            pend = None if want == up else (want, len(out) - 1, i)
        prev = want
    return out


def qa_perf(rom):
    """Each fight, Color and the original, Mac still (3000 frames): the crowd's sound never runs dry or skips; his
    pictures up late no more often than when last measured; on the original no frame lost, and his poses up later than on
    Color (the same poses at the same frames: Mac still) no more often than when last measured."""
    ref, out, lines, good = _ref().get("perf", {}), {}, [], True
    lag_ref, lag_out, lag_n, lag_later = _ref().get("lag", {}), {}, 0, 0
    for scene, name in _fights():
        delays, lost = {}, 0
        for cgb in (True, False):
            key = f"{name}|{'cgb' if cgb else 'dmg'}"
            n, under, late, shown, frames_lost = _passive(rom, scene, cgb, 3000)
            delays[cgb] = _pose_delays(shown)
            lost = lost if cgb else frames_lost
            out[key] = round(late, 2)
            ok = under == 0 and (UPDATE or late <= ref.get(key, 100) + (LATE_MARGIN_CGB if cgb else LATE_MARGIN))
            good = good and ok
            if not ok or UPDATE:
                lines.append(f"    {'✓' if ok else '✗'} {key}: {n} frames, crowd sound dry or broken {under}, pictures late {late:.2f}%"
                             f" (was {ref.get(key, '-')})")
        poses = min(len(delays[True]), len(delays[False]))
        later = sum(1 for d, c in zip(delays[False], delays[True]) if d > c)
        pct = round(100 * later / max(1, poses), 2)
        lag_out[name], lag_n, lag_later = pct, lag_n + poses, lag_later + later
        ok = lost == 0 and (UPDATE or pct <= lag_ref.get(name, 0) + LAG_MARGIN)
        good = good and ok
        if not ok or UPDATE:
            lines.append(f"    {'✓' if ok else '✗'} {name}|dmg: {poses} poses, {later} up later than on Color ({pct:.2f}%,"
                         f" was {lag_ref.get(name, '-')}), frames lost {lost}")
    if UPDATE:
        _save_ref("perf", out)
        _save_ref("lag", lag_out)
    lines.append(f"    {'✓' if good else '✗'} {len(out)} fights' frames within budget; the original's poses up later than"
                 f" Color's: {lag_later} of {lag_n} ({100 * lag_later / max(1, lag_n):.1f}%)")
    return good, lines


OFF_SCENES = ["Bells", "First screen", "Title", "Challenger", "You win", "Joe wins", "Pass key", "Corner", "Rematch",
              "You win (TKO)", "Challenger: Bull", "Corner: Bull", "KO News", "Game over", "Credits",
              "Title bout: Honda", "The dream fight"]


def _off_frames(rom, cgb, scene, frames, every):
    """Booted into SCENE (the first LoadScene's), FRAMES on, start pressed every EVERY frames (0: never): off the fight
    (its screen on, no scene loading), each VBlank (line 144's start: lines counted on from frame to frame) and the
    main loop's VBlank work (VBlankDone) -- {"n": VBlanks counted, "lost": one that found the loop waiting for it and
    had no work run in it, "twice": two works begun in one VBlank, "crowd": counted with the crowd's recording playing
    (its timer's interrupt on)}. A VBlank that came with the frame's own work still running (from VBlankDone to its
    return to MainLoop) isn't the loop's to lose: not counted."""
    from . import bot
    from pyboy import PyBoy
    S, B = bot._symbols(rom)
    pb = PyBoy(str(rom), window="null", cgb=cgb, sound_emulated=False)
    pb.set_emulation_speed(0)
    m = pb.memory
    if not cgb:                         # (as the original boots: A = $01; PyBoy gives $11)
        pb.hook_register(B["Start"], S["Start"], lambda _: setattr(pb.register_file, "A", 1), None)
    st = {"first": True, "loading": True, "line": 0, "ly": 0, "frame": -154}
    events = []                         # (line, "work" | "wait" | "load" | "frame", off the fight, the crowd's timer on)

    def at(kind):                       # (the line count on, by LY: a frame's end each 154 lines at least)
        ly = m[0xFF44]
        st["line"] += (ly - st["ly"]) % 154
        st["ly"] = ly
        if kind == "frame":
            if st["line"] - st["frame"] < 77 and m[0xFF40] & 0x80:
                st["line"] += 154       # (a whole frame between two ends, no event in it)
            st["frame"] = st["line"]
        events.append((st["line"], kind, not st["loading"] and m[S["hFtActive"]] == 0 and bool(m[0xFF40] & 0x80),
                       bool(m[0xFFFF] & 4)))

    def load(_):
        if st["first"]:
            st["first"] = False
            pb.register_file.A = scene
        st["loading"] = True
        at("load")

    def done(_):
        st["loading"] = False
        at("work")
    pb.hook_register(B["LoadScene"], S["LoadScene"], load, None)
    pb.hook_register(B["VBlankDone"], S["VBlankDone"], done, None)
    pb.hook_register(B["MainLoop"], S["MainLoop"], lambda _: at("wait"), None)
    held = False
    for t in range(frames):
        if every and (t % every < 3) != held:
            held = not held
            (pb.button_press if held else pb.button_release)("start")
        pb.tick(1, False, False)
        at("frame")
    pb.stop(save=False)
    out = {"n": 0, "lost": 0, "twice": 0, "crowd": 0}
    first = (144 - events[0][0]) % 154 + events[0][0]
    i, state = 0, None
    for v in range(first, events[-1][0] - 154, 154):
        while i < len(events) and events[i][0] < v:
            if events[i][1] in ("work", "wait", "load"):
                state = events[i]
            i += 1
        near = [e for e in events[max(0, i - 400):i + 400] if v - 154 <= e[0] < v + 154]
        if not all(e[2] for e in near) or state is None:
            continue                    # (a fight, a scene loading, the screen off near it)
        out["n"] += 1
        out["crowd"] += events[i - 1][3]
        works = [e[0] for e in events[i:i + 400] if e[1] == "work" and e[0] < v + 154]
        out["twice"] += sum(1 for w in works if w < v + 10) >= 2
        if state[1] == "wait" and not any(w < v + 77 for w in works):
            out["lost"] += 1
    return out


FIGHT_START_FRAMES = 600


def _fight_start(rom, scene, cgb, frames=FIGHT_START_FRAMES):
    """A fight's start, Mac still: from its load (the title's way there, pointed at it) to FRAMES VBlanks past the
    first one its frame's work ran in (the screen's first: its load before it on Color behind the faded-out black, on
    the original with the screen off) -- the fade in, his walk in, the round's first seconds. Per VBlank (line 144 to
    the next one's) the main loop's VBlank work (VBlankDone): {"load": VBlanks from its LoadScene to that first one,
    "lost": VBlanks with none, "twice": with two, "first": the first few of them (VBlanks from the first)}. (A VBlank
    with its work's MainLoop.late isn't one lost: a short frame's logic, the fade's, done in the VBlank it began in,
    waits for the next.)"""
    from . import bot
    S, B = bot._symbols(rom)
    g = _game(rom, scene, cgb)
    m = g.pb.memory
    st = {"t": -1, "on": False, "load": None}
    hits = []                           # (frame, LY) at each VBlankDone; PyBoy's frames end at line 0

    def load(_):                        # (Game's own, pointing the title's way at the fight; and its load noted)
        if g.pb.register_file.A == 2:
            g.pb.register_file.A = scene
        if g.pb.register_file.A == scene and not st["on"]:
            st["on"], st["load"] = True, st["t"]

    def done(_):
        g._vblank(_)
        hits.append((st["t"], m[0xFF44]))
    for label, fn in (("LoadScene", load), ("VBlankDone", done)):
        g.pb.hook_deregister(B[label], S[label])
        g.pb.hook_register(B[label], S[label], fn, None)
    t = 0
    while not st["on"] and t < 20000:
        st["t"] = t
        g.hold(["start"] if t % 50 < 3 else [])
        g.tick(False)
        t += 1
    g.hold([])
    hits.clear()
    first, out = None, {"load": None, "lost": 0, "twice": 0, "first": []}
    bad_edge = 0
    for t in range(st["t"] + 1, st["t"] + 2000):
        st["t"] = t
        g.tick(False)
        bad_edge += m[0xFF44] >= 144 and bool(m[0xFF40] & 0x80)
        if first is None and m[S["hFtActive"]] == 1 and m[0xFF40] & 0x80 and any(f == t and ly >= 144 for f, ly in hits):
            first = t
        if first is not None and t > first + frames:
            break
    g.stop()
    if first is None or bad_edge:
        out["lost"] = frames             # (never shown, or PyBoy's frames not ending where counted: a failure)
        return out
    out["load"] = first - st["load"] if st["load"] is not None else None
    per = {}
    for f, ly in hits:                  # (the VBlank a work's in: from line 144 of frame f to line 143 of the next)
        w = f if ly >= 144 else f - 1
        per[w] = per.get(w, 0) + 1
    for w in range(first, first + frames):
        n = per.get(w, 0)
        if n != 1:
            out["lost" if n == 0 else "twice"] += 1
            if len(out["first"]) < 6:
                out["first"].append(w - first)
    return out


def qa_frames(rom):
    """Off the fight, both machines (the boot, the title, the challengers, the corner, the results, idle and pressed
    on): every VBlank's work run -- none lost to the crowd's timer interrupt returning just as VBlank begins, none
    run twice in one VBlank (a screen's work can be short). Each fight's start, both machines: from its load through
    its first FIGHT_START_FRAMES VBlanks (the fade in, his walk in), none lost, none run twice."""
    names = {n: i for i, n in enumerate(s["name"] for s in _project()["scenes"])}
    lines, good = [], True
    for cgb in (True, False):
        loads, bad = [], []
        for scene, name in _fights():
            r = _fight_start(rom, scene, cgb)
            loads.append(r["load"])
            if r["lost"] or r["twice"]:
                bad.append(f"{name}: lost {r['lost']}, twice {r['twice']} (VBlanks {r['first']} from the first)")
        ok = not bad
        good = good and ok
        known = [x for x in loads if x is not None] or [0]
        lines.append(f"    {'✓' if ok else '✗'} {'Color' if cgb else 'the original'}: {len(loads)} fights' starts, "
                     f"{FIGHT_START_FRAMES} VBlanks each from the first shown (their loads {min(known)}-{max(known)}"
                     f" VBlanks before it): {len(bad)} with one lost or worked twice")
        lines += [f"      ✗ {b}" for b in bad]
    for cgb in (True, False):
        tot = {"n": 0, "lost": 0, "twice": 0, "crowd": 0}
        bad = []
        for name in OFF_SCENES:
            for every in (0, 150):
                r = _off_frames(rom, cgb, names[name], 4000, every)
                for k in tot:
                    tot[k] += r[k]
                if r["lost"] or r["twice"]:
                    bad.append(f"{name}{' (pressed)' if every else ''}: lost {r['lost']}, twice {r['twice']}")
        ok = tot["lost"] == 0 and tot["twice"] == 0 and tot["n"] > 0
        good = good and ok
        lines.append(f"    {'✓' if ok else '✗'} {'Color' if cgb else 'the original'}: {tot['n']} VBlanks off the fight"
                     f" ({tot['crowd']} with the crowd's timer on), lost {tot['lost']}, worked twice {tot['twice']}")
        lines += [f"      ✗ {b}" for b in bad]
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


SCREENS = ROOT / "tests" / "golden" / "fight-screens"
SCREENS_WALK = 150          # (his walk in: this many frames before the bell)
SCREENS_TELL = 24           # (the punch that lands first: its wind-up, this many frames before Mac's hearts drop)
SCREENS_LIMIT = 2500        # (frames past the bell, a knockdown not come)
SCREENS_CARDS = [("Corner: Don", "Fight: Don", (60, 240)), ("Title bout: Honda", None, (90,))]


def _slug(name):
    return name.replace(":", "").replace(" ", "-").replace("(", "").replace(")", "").lower()


def _fight_screens(rom, scene, cgb):
    """A fight, Mac still, from its first frame (hFtActive): {moment: RGB screen}. The moments: "intro" (40 frames
    in: the fade in done, the opponent idle in the ring), "walk-in" (SCREENS_WALK before the bell), "bell" (30 after
    it, wFtSec first 1), "idle" (300 after), "tell" and "hit" (the first punch that lands: SCREENS_TELL before Mac's
    hearts drop, and 4 after), "down" (Mac down, the count at 3) -- each only if it comes within SCREENS_LIMIT."""
    from collections import deque
    g = _game(rom, scene, cgb)
    S = g.S
    _to_fight(g, scene)
    back, shots = deque(maxlen=SCREENS_WALK + 2), {}
    bell = hit = None
    hearts = g.m[S["wPlHearts"]]
    for t in range(SCREENS_LIMIT + 2000):
        g.hold([])
        g.pb.tick(1, True, False)
        if g.hram("hScene") != scene or g.hram("hFtActive") != 1:
            break
        px = g.pb.screen.ndarray[:, :, :3].copy()
        back.append((t, px))
        if t == 40:
            shots["intro"] = px
        if bell is None and g.m[S["wFtSec"]] == 1:
            bell = t
            shots["walk-in"] = next(p for u, p in back if u == t - SCREENS_WALK)
        if bell is not None:
            if t in (bell + 30, bell + 300):
                shots["bell" if t == bell + 30 else "idle"] = px
            if hit is None and g.m[S["wPlHearts"]] < hearts:
                hit = t
                shots["tell"] = next((p for u, p in back if u == t - SCREENS_TELL), None)
            if hit is not None and t == hit + 4:
                shots["hit"] = px
            if "down" not in shots and g.m[S["wFtCount"]] == 3:
                shots["down"] = px
            if "down" in shots and "idle" in shots and (hit is None or "hit" in shots) or t > bell + SCREENS_LIMIT:
                break
    g.stop()
    return {k: v for k, v in shots.items() if v is not None}


def _card_screens(rom, scene, fight, frames, cgb):
    """A screen between fights: reached from FIGHT (Mac still: the round over, his corner) or, with none, loaded
    straight from the title; FRAMES on from its first frame, each an RGB screen."""
    names = [s["name"] for s in _project()["scenes"]]
    target = names.index(scene)
    g = _game(rom, names.index(fight) if fight else target, cgb)
    if fight:
        _to_fight(g, names.index(fight))
    at, out = None, {}
    for t in range(12000):
        g.hold(["start"] if at is None and not fight and t % 60 < 3 else [])
        here = g.hram("hScene") == target
        g.pb.tick(1, True, False)
        if here and at is None:
            at = t
        if at is not None and t - at in frames:
            out[t - at] = g.pb.screen.ndarray[:, :, :3].copy()
            if len(out) == len(frames):
                break
    g.stop()
    return out


def _save_png(path, px):
    """A screen as an indexed PNG (its own few colors: small, exact)."""
    import numpy
    from PIL import Image
    colors, idx = numpy.unique(px.reshape(-1, 3), axis=0, return_inverse=True)
    im = Image.fromarray(idx.reshape(px.shape[:2]).astype("uint8"), "P")
    im.putpalette(colors.astype("uint8").flatten().tolist())
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def qa_screens(rom):
    """Every fight's screens, Color and the original, pixel for pixel as saved (tests/golden/fight-screens/cgb|dmg):
    Mac still from the fight's first frame, the intro (the fade in done), his walk in, the bell, a pose later, the first
    punch that lands (its wind-up and Mac hit) and Mac down at the count of 3, each at the same frame every run
    (_fight_screens); and the corner (after Don's first round, Mac still) and a title bout's card. A mismatch: the
    pixels that differ, the screen and a diff (red where they differ) saved under $QA_DIFF_DIR (default: the temp
    directory's gbstage-fight-screens).
    Regenerate (after the fighters' art or placement changes, then look the PNGs over before committing):
        QA_UPDATE=1 python -m gbstage test --stage career --career qa_screens"""
    import tempfile
    import numpy
    from PIL import Image
    diff_dir = Path(os.environ.get("QA_DIFF_DIR") or Path(tempfile.gettempdir()) / "gbstage-fight-screens")
    lines, good, seen, n = [], True, set(), 0
    shots = []
    for cgb in (True, False):
        machine = "cgb" if cgb else "dmg"
        for scene, name in _fights():
            fighter = "joe" if name == "Fight" else _slug(name.replace("Fight: ", ""))
            for moment, px in _fight_screens(rom, scene, cgb).items():
                shots.append((f"{machine}/{fighter}-{moment}.png", px))
        for scene, fight, frames in SCREENS_CARDS:
            for f, px in _card_screens(rom, scene, fight, frames, cgb).items():
                shots.append((f"{machine}/{_slug(scene)}-{f}.png", px))
    for rel, px in shots:
        path = SCREENS / rel
        seen.add(path)
        n += 1
        if UPDATE:
            _save_png(path, px)
            continue
        if not path.exists():
            good = False
            lines.append(f"    ✗ {rel}: no saved screen")
            continue
        want = numpy.array(Image.open(path).convert("RGB"))
        bad = (want != px).any(axis=2)
        if bad.any():
            good = False
            diff_dir.joinpath(rel).parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(px).save(diff_dir / rel)
            mark = (px // 3 + 128).astype("uint8")
            mark[bad] = (255, 0, 0)
            Image.fromarray(mark).save(diff_dir / rel.replace(".png", "-diff.png"))
            lines.append(f"    ✗ {rel}: {int(bad.sum())} pixels differ (now and the diff: {diff_dir / rel})")
    gone = sorted(p for p in SCREENS.rglob("*.png") if p not in seen)
    if UPDATE:
        for p in gone:
            p.unlink()
        lines.append(f"    ✓ {n} screens saved ({len(gone)} no longer made removed)")
        return True, lines
    for p in gone:
        good = False
        lines.append(f"    ✗ {p.relative_to(SCREENS)}: saved, not reached now")
    lines.append(f"    {'✓' if good else '✗'} {n} fight screens as saved")
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


def qa_reset(rom):
    """The soft reset, Color and the original: A, B, Select and Start together mid-fight start the game over (as
    from power on, the same machine), and a fight can be reached again after."""
    lines, good = [], True
    first = _fights()[0][0]
    for cgb in (True, False):
        g = _game(rom, first, cgb)
        fought = _to_fight(g, first)
        for _ in range(120):
            g.hold([])
            g.tick(False)
        g.hold(["a", "b", "select", "start"])
        for _ in range(4):
            g.tick(False)
        g.hold([])
        t = 0
        while g.hram("hScene") != 0 and t < 600:
            g.tick(False)
            t += 1
        reset = g.hram("hScene") == 0 and bool(g.hram("hIsCGB")) == cgb
        again = _to_fight(g, first)
        g.stop()
        ok = fought and reset and again
        good = good and ok
        if not ok:
            lines.append(f"    ✗ {'cgb' if cgb else 'dmg'}: fight {fought}, reset {reset}, fight again {again}")
    lines.append(f"    {'✓' if good else '✗'} A+B+Select+Start mid-fight: the game over from the start, both machines")
    return good, lines


def _sgb_boot(rom, c, cgb=False, frames=150):
    """Power-on with the boot ROM's C as given ($14: a Super Game Boy's), A as the original's: the packets the ROM
    sends through P1 (each from its bits, as SgbSend puts them out), the frame each starts on, and VRAM as each
    transfer shows it (the screen's tiles, its map rows, LCDC, BGP)."""
    from pyboy import PyBoy
    from . import bot
    S, B = bot._symbols(rom)
    pb = PyBoy(str(rom), window="null", cgb=cgb, sound_emulated=False)
    st = {"bits": None, "packets": [], "shown": [], "t": 0, "at": 0}

    def start(_):
        pb.register_file.C = c
        if not cgb:
            pb.register_file.A = 1

    def done():
        b = st["bits"][:128]
        st["packets"].append((st["at"], bytes(sum(b[i * 8 + k] << k for k in range(8)) for i in range(16))))
        st["bits"] = None

    def packet(_):
        if st["bits"] is not None and len(st["bits"]) >= 128:
            done()
        st["bits"], st["at"] = [], st["t"]

    def bit(_):
        st["bits"].append(pb.register_file.A == 0x10)

    def shown(_):                       # (a transfer's packet sent: its VRAM on show)
        m = pb.memory
        st["shown"].append({"tiles": bytes(m[0x8000:0x9000]), "lcdc": m[0xFF40], "bgp": m[0xFF47],
                            "map": [bytes(m[0x9800 + 32 * r:0x9800 + 32 * r + 20]) for r in range(13)]})
    pb.hook_register(B["Start"], S["Start"], start, None)
    if "SgbSend" in S:
        pb.hook_register(B["SgbSend.packet"], S["SgbSend.packet"], packet, None)
        pb.hook_register(B["SgbSend.one"], S["SgbSend.one"], bit, None)
        pb.hook_register(B["SgbTransfer.shown"], S["SgbTransfer.shown"], shown, None)
    for t in range(frames):
        st["t"] = t
        pb.tick(1, False)
    if st["bits"] is not None and len(st["bits"]) >= 128:
        done()
    up = pb.memory[S["hScene"]] == _project()["start"]
    pb.stop(save=False)
    return st["packets"], st["shown"], up


def qa_sgb(rom):
    """The Super Game Boy (PyBoy has none: the packets the ROM puts out, read off its own sender): the header's SGB
    flag and old licensee $33; on an SGB, at boot, the screen held (MASK_EN), the border's tiles (CHR_TRN, both
    halves) and map with its palette (PCT_TRN) each shown as the SGB reads them, the grey look's colors (PAL01), the
    screen shown again; four frames between packets; nothing sent on a Game Boy or a Color."""
    from . import codegen
    lines, good = [], True
    data = Path(rom).read_bytes()

    def check(ok, what):
        nonlocal good
        good = good and ok
        lines.append(f"    {'✓' if ok else '✗'} {what}")
    check(data[0x146] == 0x03 and data[0x14B] == 0x33,
          f"header: SGB flag ${data[0x146]:02X}, old licensee ${data[0x14B]:02X}")
    border = bytes.fromhex(codegen.SGB_BORDER.read_text())
    packets, shown, up = _sgb_boot(rom, 0x14)
    heads = [p[0] for _, p in packets]
    want = [0xB9, 0x99, 0x99, 0xA1, 0x01, 0xB9]
    check(heads == want, "packets in turn: MASK_EN, CHR_TRN x2, PCT_TRN, PAL01, MASK_EN"
          + ("" if heads == want else f" (sent: {' '.join(f'${h:02X}' for h in heads)})"))
    if heads == want:
        p = [q for _, q in packets]
        check(p[0][1] == 1 and p[5][1] == 0, "the screen held through the transfers, shown after")
        check(p[1][1] == 0 and p[2][1] == 1, "CHR_TRN: tiles 0-127, then 128-255")
        g = codegen.SGB_GREENS
        col = lambda c: (c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10
        pal = [int.from_bytes(p[4][1 + 2 * k:3 + 2 * k], "little") for k in range(7)]
        check(pal == [col(x) for x in g + g[1:]], "PAL01: the grey look's four greens")
        gaps = [b[0] - a[0] for a, b in zip(packets, packets[1:])]
        check(all(d >= 4 for d in gaps), f"four frames between packets (frames apart: {gaps})")
    if len(shown) == 3:
        seq = all(m == bytes((r * 20 + x) & 0xFF for x in range(20)) for s in shown for r, m in enumerate(s["map"]))
        check(seq and all(s["lcdc"] == 0x91 and s["bgp"] == 0xE4 for s in shown),
              "each transfer's VRAM on show: tiles 0-255 in order, BGP $E4, LCDC $91")
        check(shown[0]["tiles"] == border[:0x1000] and shown[1]["tiles"] == border[0x1000:0x2000],
              "the border's tiles as made (sgb_border.hex)")
        check(shown[2]["tiles"][:0x700] == border[0x2000:0x2700]
              and shown[2]["tiles"][0x800:0x820] == border[0x2700:0x2720], "the border's map and palette as made")
    else:
        check(False, f"three transfers shown ({len(shown)})")
    check(up, "the first scene up after")
    for c, cgb, what in ((0x13, False, "a Game Boy"), (0x00, True, "a Color")):
        packets, shown, up = _sgb_boot(rom, c, cgb)
        check(not packets and not shown and up, f"nothing sent on {what}")
    return good, lines


def qa_decision(rom):
    """A fight gone the distance, Color and the original: the last round's bell to the NES's decision, on points
    ($03E8 against his mark, $05C8): Mac ahead, his win screen; behind, his loss."""
    from . import bot
    lines, good = [], True
    first = _fights()[0][0]
    names = [s["name"] for s in _project()["scenes"]]
    for cgb in (True, False):
        for ahead in (True, False):
            g = _game(rom, first, cgb)
            S, _ = bot._symbols(rom)
            reached = _to_fight(g, first)
            for _ in range(60):
                g.hold([])
                g.tick(False)
            g.m[S["wFtRound"]] = 3
            g.m[g.w + 0x06] = 3
            g.m[g.w + 0x0302], g.m[g.w + 0x0304], g.m[g.w + 0x0305] = 2, 5, 8
            end = None
            for _ in range(1500):
                g.m[g.w + 0x03E8] = 9 if ahead else 0
                g.hold([])
                g.tick(False)
                if g.hram("hScene") != first:
                    end = names[g.hram("hScene")]
                    break
            g.stop()
            ok = reached and end is not None and end.endswith("wins") != ahead
            good = good and ok
            if not ok:
                lines.append(f"    ✗ {'cgb' if cgb else 'dmg'}, Mac {'ahead' if ahead else 'behind'}: {end}")
    lines.append(f"    {'✓' if good else '✗'} a decision after round 3, both ways, both machines")
    return good, lines


SAVE_TAG = b"PO!!\x01"                  # (kit_save.asm: its tag and format)
TIME_CENTS = (0, 0, 2, 5, 4, 8, 6, 1, 8, 2, 9, 7, 9, 9)    # (kit_fight.asm's TimeCents: the hundredths' digits)


def _save_block(sram, fights):
    """The battery's block (kit_save.asm), from cartridge RAM: (good, the career's scene, its record, each fight's best)."""
    n = 11 + 6 * fights
    good = sram[:5] == SAVE_TAG and int.from_bytes(sram[n:n + 2], "little") == sum(sram[:n]) & 0xFFFF
    return good, sram[5], list(sram[6:11]), [list(sram[11 + 6 * k:17 + 6 * k]) for k in range(fights)]


def _save_sum(sram, fights):
    """The block again, its check worked out (a test's own edit to it)."""
    n = 11 + 6 * fights
    return sram[:n] + (sum(sram[:n]) & 0xFFFF).to_bytes(2, "little") + sram[n + 2:]


class _Cart:
    """The ROM in PyBoy from power-on to the title, the cartridge's RAM what its battery kept (PyBoy's ram_file);
    off() powers it down, keeping it again. time: the fight's clock as its result is kept (round, M, S, S, the
    hundredths' step), so its best is known."""

    def __init__(self, rom, cgb, sram):
        from pyboy import PyBoy
        from . import bot
        self.S, self.B = bot._symbols(rom)
        self.rom = open(rom, "rb").read()
        self.pb = PyBoy(str(rom), window="null", cgb=cgb, sound_emulated=False, ram_file=io.BytesIO(sram))
        self.pb.set_emulation_speed(0)
        self.m = self.pb.memory
        if not cgb:                     # (as the original boots: A = $01; PyBoy gives $11)
            self.pb.hook_register(self.B["Start"], self.S["Start"], lambda _: setattr(self.pb.register_file, "A", 1), None)
        self.time = self.fight = None
        self.pb.hook_register(self.B["LoadScene"], self.S["LoadScene"], self._clock, None)
        self.wait(lambda: self.scene() == 0 and self.t >= 400, 6000)
        self.ticks(240)

    def _clock(self, _):
        if self.time and self.scene() == self.fight:      # (leaving the fight: its result loading)
            w = self.S["wNes"]
            r, mn, s10, s1, step = self.time
            self.m[w + 0x06], self.m[w + 0x302], self.m[w + 0x304], self.m[w + 0x305], self.m[w + 0x306] = r, mn, s10, s1, step << 4

    def scene(self):
        return self.m[self.S["hScene"]]

    def ticks(self, n):
        self.pb.tick(n, False)

    def wait(self, done, limit, start_every=0):
        self.t = 0
        while not done() and self.t < limit:
            press = start_every and self.t % start_every < 3
            (self.pb.button_press if press else self.pb.button_release)("start")
            self.pb.tick(1, False)
            self.t += 1
        self.pb.button_release("start")
        return done()

    def tap(self, b):
        self.pb.button_press(b)
        self.ticks(3)
        self.pb.button_release(b)
        self.ticks(20)

    def win(self, fight, time):
        """On (Start) into the fight, won there by a KO (the NES's own result, as careertests._forced has it) at this
        time; its result screen up."""
        self.time, self.fight = time, fight
        self.wait(lambda: self.scene() == fight and self.m[self.S["hFtActive"]] == 1, 4000, 90)
        self.ticks(200)
        self.m[self.S["wNes"]] = 0xFC
        self.wait(lambda: self.scene() != fight, 3000)
        self.ticks(120)
        return self.m[self.S["wFtCount"]] >= 0xFE

    def sram(self):
        return bytes(self.m[0, 0xA000:0xA200])

    def ram_on(self):
        return self.m[0xA000] != 0xFF or self.m[0xA001] != 0xFF       # (the RAM off: $FF read back)

    def best_line(self, time):
        """The win screen up, its best's line: "NEW RECORD!", "BEST" (this time, as its glyphs in the ROM write it:
        BEST, a space, M, ":", S, S, ".", C, C, ",", R, N) or "something else"."""
        scene = self.scene()
        t = next(t for t in _project()["scenes"][scene]["texts"] if t.get("bestTime"))
        new = self._rom(f"Scene{scene}NewBest", 0, 64)
        if all(self.m[0, new[1 + 3 * k] | new[2 + 3 * k] << 8] == new[3 + 3 * k] for k in range(new[0])):
            return "NEW RECORD!"
        g = self._rom(f"Scene{scene}Best0", 0, 69)
        r, mn, s10, s1, step = time
        c10, c1 = TIME_CENTS[2 * step:2 * step + 2]
        want = bytes(list(g[:5]) + [g[5 + mn], g[15], g[16 + s10], g[26 + s1], g[36], g[37 + c10], g[47 + c1], g[57], g[58], g[59 + r]])
        at = 0x9800 + 32 * t["y"] + t["x"]
        return "BEST" if bytes(self.m[0, at:at + 15]) == want else "something else"

    def _rom(self, label, at, n):
        a = self.B[label] * 0x4000 + self.S[label] - (0x4000 if self.B[label] else 0) + at
        return self.rom[a:a + n]

    def off(self):
        f = io.BytesIO()
        self.pb.stop(save=True, ram_file=f)
        return f.getvalue()




def qa_save(rom):
    """Punch-Out!!'s battery save (kit_save.asm), Color and the original: a KO kept as its result screen comes up (the
    career's next scene, Mac's record, his best for that fight, the block's check), the RAM off again, NEW RECORD! on
    the win screen; powered off and on, CONTINUE's Start goes on at the next challenger, the record as it was; NEW
    keeps the bests: a slower KO shows his BEST and keeps it, a faster one NEW RECORD!; a corrupt save, or another
    format's, is none."""
    names = [s["name"] for s in _project()["scenes"]]
    fights = [i for i, _ in _fights()]
    kaiser = names.index("Challenger: Kaiser")
    first, slower, faster = (1, 1, 3, 0, 2), (2, 0, 1, 0, 0), (1, 0, 4, 5, 1)     # (R1 1:30.48, R2 0:10.00, R1 0:45.25)
    best = lambda t: list(t[:4]) + list(TIME_CENTS[2 * t[4]:2 * t[4] + 2])
    none = [0xFF] * 6
    lines, good = [], True

    def check(ok, what):
        nonlocal good
        good = good and ok
        lines.append(f"    {'✓' if ok else '✗'} {what}")

    def kept(c, ko, best_time, shown, what):
        ok, scene, rec, bests = _save_block(c.sram(), len(fights))
        line = c.best_line(best_time)
        check(ko and ok and scene == kaiser and rec == [1, 0, 1, 0, 0] and bests == [best(best_time)] + [none] * (len(fights) - 1)
              and not c.ram_on() and line == shown,
              f"{what}: {'KO' if ko else 'no KO'}, {'good' if ok else 'bad'} block, on at {names[scene] if scene < len(names) else scene}"
              f", record {rec}, best {bests[0]}, RAM {'on' if c.ram_on() else 'off'}, the win screen: {line}")

    for cgb in (True, False):
        m = "cgb" if cgb else "dmg"
        c = _Cart(rom, cgb, bytes(0x2000))                 # a new cartridge: NEW, Glass Joe KO'd
        kept(c, c.win(fights[0], first), first, "NEW RECORD!", f"{m}: a new cartridge, Glass Joe KO'd")
        sram = c.off()
        c = _Cart(rom, cgb, sram)                          # on again: CONTINUE, Start
        c.tap("down")
        c.tap("start")
        c.wait(lambda: c.scene() != 0, 600)
        c.ticks(120)
        rec = [c.m[c.S[n]] for n in ("wRecWins", "wRecLosses", "wRecKOs")]
        check(c.scene() == kaiser and rec == [1, 0, 1] and not c.ram_on(),
              f"{m}: on again, CONTINUE's Start: {names[c.scene()]}, {rec[0]}-{rec[1]} {rec[2]}KO")
        c.off()
        c = _Cart(rom, cgb, sram)                          # NEW: a slower KO, his best kept and shown
        kept(c, c.win(fights[0], slower), first, "BEST", f"{m}: NEW, a slower KO")
        sram = c.off()
        c = _Cart(rom, cgb, sram)                          # a faster one replaces it
        kept(c, c.win(fights[0], faster), faster, "NEW RECORD!", f"{m}: a faster KO")
        sram = c.off()
        flipped = bytearray(sram)
        flipped[11 + 6 * 5] ^= 1
        old = bytearray(sram)
        old[4] = SAVE_TAG[4] + 1
        for what, bad in (("a byte flipped", bytes(flipped)), ("another format", _save_sum(bytes(old), len(fights)))):
            c = _Cart(rom, cgb, bad)                       # none: CONTINUE's Start does nothing; a KO's a new record
            c.tap("down")
            c.tap("start")
            c.ticks(300)
            stays = c.scene() == 0
            check(stays, f"{m}: {what}: CONTINUE's Start {'stays on the title' if stays else 'went on'}")
            c.tap("up")
            kept(c, c.win(fights[0], slower), slower, "NEW RECORD!", f"{m}: {what}: a new save")
            c.off()
    return good, lines
