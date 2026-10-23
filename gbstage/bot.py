"""A player for Punch-Out!!'s fights, for CI: does every fighter go down?

It plays with buttons only and never writes the game or rewinds it. What it knows is the game's own rules:
before it commits, it plays the moment forward on a copy (the way a player who knows the fighter's
pattern sees what's coming): if Mac stands still, when does his punch land; which of dodge, block or duck
stops it; will a punch of Mac's land, and land before he can answer. Then it presses the buttons for real.

  play(rom, scene) -> {"won", "result", "frames", "round", "mac_knockdowns", "his_knockdowns"}"""
import io

STOPPED = (1, 2, 4)                     # his punch's outcome ($98): 1 blocked, 2 ducked, 3 landed, 4 dodged
WIN, LOSS = (0xFC, 0xFE), (0xFB, 0xFD)
HAND = {"jab_r": "a", "body_r": "a", "jab_l": "b", "body_l": "b"}
PUNCHES = {"jab_r": ["up", "a"], "jab_l": ["up", "b"], "body_r": ["a"], "body_l": ["b"], "star": ["start"]}
BUSY = 44                               # frames a punch of Mac's can keep him from defending
LOOK = 72                               # frames looked ahead for his next punch
FREE = (1, 2, 3, 5, 7, 8, 0x0E)         # Mac's states a plan can start in (out of a dodge, block or duck's end too)
OUT_OF_DODGE = 22                       # frames a punch is held from a dodge: the game throws it as the dodge ends
DEBUG = None                            # (a list: think()'s choices, for looking into)
CHOICES = 1                             # defenses that work, compared by the combo each opens
CHAIN = 3                               # punches of a combo looked through
STAR = 20                               # a star earned, in damage
HORIZON = 60                            # frames a punch of Mac's is judged over
COMMIT = 4                              # frames ahead a plan's first press may be and still be made
STALL = 45                              # frames of nothing before Mac draws him out
DELAY = 20                              # frames ahead a punch is tried later, for a harder hit
DELAY_GAIN = 3                          # how much harder it must hit to be worth the wait


def _symbols(rom):
    S, B = {}, {}
    for line in open(str(rom) + ".sym"):
        p = line.split()
        if len(p) == 2 and ':' in p[0]:
            b, a = p[0].split(':'); S[p[1]] = int(a, 16); B[p[1]] = int(b, 16)
    return S, B


class Game:
    """The ROM in PyBoy, booted into a fight scene (the title's own way there, pointed at it)."""

    def __init__(self, rom, scene, cgb=True, sound=False):
        from pyboy import PyBoy
        self.S, B = _symbols(rom)
        self.sound = sound
        self.pb = PyBoy(str(rom), window="null", cgb=cgb, sound_emulated=sound)
        self.pb.set_emulation_speed(0)
        self.m = self.pb.memory
        self.w = self.S["wNes"]
        self.scene = scene
        self.held = set()

        def jump(_):
            if self.pb.register_file.A == 2:
                self.pb.register_file.A = scene
        self.pb.hook_register(B["LoadScene"], self.S["LoadScene"], jump, None)

    def nes(self, a):
        return self.m[self.w + a]

    def hram(self, name):
        return self.m[self.S[name]]

    def hold(self, buttons):
        buttons = set(buttons)
        for b in self.held - buttons:
            self.pb.button_release(b)
        for b in buttons - self.held:
            self.pb.button_press(b)
        self.held = buttons

    def tick(self, render=True):
        self.pb.tick(1, render, self.sound and render)     # (look-aheads: neither drawn nor heard)

    def save(self):
        f = io.BytesIO()
        self.pb.save_state(f)
        return f.getvalue(), set(self.held)

    def load(self, snap):
        data, held = snap
        self.pb.load_state(io.BytesIO(data))
        for b in ("up", "down", "left", "right", "a", "b", "start", "select"):
            self.pb.button_release(b)
        self.held = set()
        self.hold(held)

    def stop(self):
        self.pb.stop(save=False)


class Plan:
    """Buttons by frame from now: [(from, to, buttons)]."""

    def __init__(self, *steps):
        self.steps = list(steps)

    def at(self, k):
        out = []
        for a, b, btn in self.steps:
            if a <= k < b:
                out += btn
        return out

    def end(self):
        return max([b for _, b, _ in self.steps] + [0])


def dodge(at, side="left"):
    return Plan((at, at + 4, [side]))


def block(at, until):
    return Plan((at, until, ["down"]))


def duck(at):
    return Plan((at, at + 3, ["down"]), (at + 6, at + 9, ["down"]))


def punch(name, hold=4):
    return Plan((0, hold, PUNCHES[name]))


def run(g, plan, frames, stop_on_arrival=False):
    """Play the plan forward from here; what came of it."""
    hp0, mac0, star0, inc0 = g.nes(0x398), g.nes(0x391), g.nes(0x342), g.nes(0x343) & 0x80
    o98 = g.nes(0x98)
    out = {"arrival": None, "outcome": None, "his_hp": 0, "mac_hp": 0, "his_kd": False, "mac_kd": False}
    for k in range(frames):
        g.hold(plan.at(k))
        g.tick(False)
        v = g.nes(0x98)
        if v and not v & 0x80 and v != o98 and out["arrival"] is None:
            out["arrival"], out["outcome"] = k, v
            if stop_on_arrival:
                break
        o98 = v
        kd = g.nes(0x05)
        out["his_kd"] |= kd == 1
        out["mac_kd"] |= kd == 2
        if g.hram("hFtActive") != 1 or kd:
            break
    out["his_hp"] = hp0 - g.nes(0x398)
    out["mac_hp"] = mac0 - g.nes(0x391)
    out["stars"] = max(0, g.nes(0x342) - star0) or int(bool(g.nes(0x343) & 0x80 and not inc0))  # (the star's
                                                    # flag, $0343: it's added a little after the punch)
    return out


def value(r):
    """What a plan did to him: a knockdown above all, then damage, a star earned worth a good punch."""
    return r["his_kd"] * 1000 + r["his_hp"] + STAR * r["stars"]


def first_hit(g, snap, plan, frames):
    """Frames to his first punch landing on Mac under this plan (None: none in sight)."""
    g.load(snap)
    o98 = g.nes(0x98)
    for k in range(frames):
        g.hold(plan.at(k))
        g.tick(False)
        v = g.nes(0x98)
        if v and not v & 0x80 and v != o98 and v == 3:
            return k
        o98 = v
        if g.hram("hFtActive") != 1 or g.nes(0x05):
            return None
    return None


def defenses(t):
    """Ways to meet a punch landing t frames from now, likeliest first."""
    return ([dodge(max(0, t - s)) for s in (11, 13, 9, 15, 7)] + [dodge(max(0, t - s), "right") for s in (11, 13, 9)] +
            [block(max(0, t - s), t + 3) for s in (12, 16, 8, 6)] + [duck(max(0, t - s)) for s in (7, 8, 6, 9)])


def stops(g, snap, plan, t):
    """Does this plan stop his punch due t frames from now (blocked, ducked, dodged)?"""
    g.load(snap)
    o98 = g.nes(0x98)
    for k in range(t + 6):
        g.hold(plan.at(k)); g.tick(False)
        v = g.nes(0x98)
        if v and not v & 0x80 and v != o98 and k >= t - 3:
            return v in STOPPED
        o98 = v
        if g.hram("hFtActive") != 1 or g.nes(0x05):
            return False
    return False


def defended(g, snap, base, frames, partial=False):
    """The base plan, with what stops each punch of his that would land: None if one can't be stopped
    (partial: as many as can be, from the first)."""
    plan = Plan(*base.steps)
    for _ in range(8):                  # (a flurry: each of its punches)
        t = first_hit(g, snap, plan, frames)
        if t is None:
            return plan
        good = []
        for d in defenses(t):
            trial = Plan(*(plan.steps + d.steps))
            if stops(g, snap, trial, t):
                good.append(trial)
                if len(good) >= (CHOICES if partial and not base.steps else 1):
                    break
        if not good:
            return plan if partial and plan.steps else None
        plan = good[0] if len(good) == 1 else max(good, key=lambda q: follow_up(g, snap, q))
    return plan if partial else None


def follow_up(g, snap, p, depth=CHAIN):
    """What the punch opens up: the combo after it, each next punch thrown as soon as Mac's free again
    (the best of each, greedily). Hippo's mouth, then his belly; a reeling fighter's flurry."""
    g.load(snap)
    end = p.end()
    for k in range(HORIZON):
        g.hold(p.at(k)); g.tick(False)
        st = g.nes(0x50) & 0x7F
        if k >= end and k > 6 and st in FREE and g.nes(0x76) != 0xFF:
            break
        if g.hram("hFtActive") != 1 or g.nes(0x05):
            return 0
    else:
        return 0
    total = 0
    for _ in range(depth):
        mid = g.save()
        best = None
        hold = 4 if (g.nes(0x50) & 0x7F) in (1, 2) else OUT_OF_DODGE
        for name in ("jab_r", "jab_l", "body_r", "body_l") + (("star",) if g.nes(0x342) else ()):
            g.load(mid)
            r = run(g, punch(name, hold), BUSY)
            if not (r["mac_hp"] or r["mac_kd"]) and value(r) > 0 and (best is None or value(r) > best[0]):
                best = (value(r), name)
        if best is None:
            break
        total += best[0]
        g.load(mid)
        q = punch(best[1], hold)
        for k in range(BUSY):
            g.hold(q.at(k)); g.tick(False)
            if k > 6 and (g.nes(0x50) & 0x7F) == 1:
                break
            if g.hram("hFtActive") != 1 or g.nes(0x05):
                return total
        else:
            break
    return total


def timed(g, snap, hold):
    """A punch thrown a few frames from now instead (a reeling fighter's stun ends on one frame: hit just
    then, it lands as a fresh hit, not a combo's little one; out of a dodge, a counter just as his punch is
    spent): its plan, if it beats the best now by DELAY_GAIN and every answer of his is still stopped. The
    delays are tried with one punch, then the others at the best of them (a state's load is what costs)."""
    names = ("jab_r", "jab_l", "body_r", "body_l") + (("star",) if g.nes(0x342) else ())

    def try_(name, d):
        g.load(snap)                    # (a press later: just then, 4 frames; out of a dodge too, as it ends)
        r = run(g, Plan((d, d + (hold if d == 0 else 4), PUNCHES[name])), d + 18)
        return -1 if r["mac_hp"] or r["mac_kd"] else value(r)

    now = max(try_(n, 0) for n in names)
    by_delay = sorted(((try_("jab_r", d), d) for d in range(1, DELAY + 1)), reverse=True)
    best = None
    for v, d in by_delay[:2]:
        for name in names:
            w = v if name == "jab_r" else try_(name, d)
            if best is None or w > best[0]:
                best = (w, name, d)
    if best is None or best[0] < max(now, 0) + DELAY_GAIN:
        return None
    _, name, d = best
    p = defended(g, snap, Plan((d, d + 4, PUNCHES[name])), HORIZON)
    if p is None:
        return None
    g.load(snap)
    r = run(g, p, HORIZON)
    return None if r["mac_kd"] or r["mac_hp"] else p


def think(g, idle_for, last_hand=None):
    """The plan for now: a punch that lands with every answer of his stopped; else the defense his next
    punch needs; else, if he's waiting on Mac, the safest punch to draw him out."""
    snap = g.save()
    scored = []
    hold = 4 if (g.nes(0x50) & 0x7F) in (1, 2) else OUT_OF_DODGE   # (out of a dodge: held, it comes at its end)
    for name in PUNCHES:
        if name == "star" and not g.nes(0x342):
            continue
        p = defended(g, snap, punch(name, hold), HORIZON)
        if p is None:                   # can't be kept safe: only if it puts him down
            p = punch(name, hold)
            g.load(snap)
            if not run(g, p, HORIZON)["his_kd"]:
                continue
        g.load(snap)
        r = run(g, p, HORIZON)
        if r["mac_kd"] or (r["mac_hp"] and not r["his_kd"]):   # (a hit taken is worth it to put him down)
            continue
        other = HAND.get(name) not in (None, last_hand)   # (as good either way: the other hand, left-right-left)
        scored.append((value(r) + follow_up(g, snap, p), name != "star", other, p))
    best = max(scored, key=lambda x: x[:3]) if scored else None
    later = (timed(g, snap, hold) if not (best and best[0] >= 1000) and (g.nes(0x90) & 0x7F) not in (0, 1)
             else None)                 # (he's waiting: no moment to wait for)
    if later is not None:               # (a punch a few frames from now hits harder: wait for it)
        g.load(snap)
        return later
    if DEBUG is not None:
        DEBUG.append((idle_for, [(v, n) for v, n, _, _ in scored]))
    if best and best[0] > 0:
        plan = best[3]
    else:
        plan = defended(g, snap, Plan(), LOOK, partial=True)
        if plan is not None and not plan.steps:
            plan = best[3] if best and idle_for > STALL else None
    g.load(snap)
    return plan


# Punch-Out!!'s crowd tells: frames from the cell lighting to his counter's right body blow. The NES's windows
# (tests/nes_reference.json "tells"), from the cue byte's frame: +8-12 for Bald Bull's charge and Piston Honda's
# rematch rush, +6-10 for Bald Bull's rematch; the cell shows a frame after it, so 8 lands in all three. The cue's
# kind ($05BE): 2 the camera, 6 the bearded man; 10 Super Macho Man's man in shades, a dodge's: his spin punch lands
# 28 frames into it, a dodge pressed from 4 to 20 frames in escapes it, so from the cell's lighting (a frame in)
# 10 is the window's middle.
TELL_DELAY = 8
DODGE_DELAY = 10


def _cue(g):
    """(the tell's map cell, its tile at rest, the answer's delay, its buttons) for this fight, or None (none, or not
    the port): a counter's right body blow, or for a dodge's tell, the dodge."""
    S = getattr(g, "S", {})
    if "wFtCueCol" not in S or not hasattr(g, "pb") or not g.m[S["wFtCueTile"]] or g.nes(0x05BE) not in (2, 6, 10):
        return None
    cell = 0x9800 + 30 * 32 + g.m[S["wFtCueCol"]]
    if g.nes(0x05BE) == 10:
        return cell, g.m[0, cell], DODGE_DELAY, ["left"]
    return cell, g.m[0, cell], TELL_DELAY, ["a"]


def play(rom, scene, frames=60 * 60 * 15, log=None, cgb=True, sound=False):
    g = Game(rom, scene, cgb, sound)
    t = 0
    while not (g.hram("hScene") == scene and g.hram("hFtActive") == 1) and t < 20000:
        g.hold(["start"] if t % 50 < 3 else [])
        g.tick(); t += 1
    plan, k0 = None, 0
    cue = _cue(g)                           # Punch-Out!!'s crowd tell, read off the screen as a player reads it
    cue_on = False
    mode = result = None
    mac_kd = his_kd = last_kd = rnd_prev = mash = last_act = last_think = 0
    last_seen = None; due = 0; events = []; last_hand = None
    f = 0
    for f in range(frames):
        if g.hram("hScene") != scene:       # off the fight: its result, or the corner between rounds
            if mode in WIN + LOSS:
                result = mode
                break
            g.hold(["start"] if f % 40 < 3 else [])
            g.tick(); continue
        rnd = g.nes(0x06)
        if rnd and rnd < rnd_prev:          # the fight begun again: lost on points
            result = 0xFA
            break
        rnd_prev = rnd or rnd_prev
        mode = g.nes(0x00)
        if g.hram("hFtActive") != 1:
            g.hold(["start"] if f % 40 < 3 else [])
            g.tick(); continue
        kd = g.nes(0x05)
        if kd != last_kd:
            mac_kd += kd == 2; his_kd += kd == 1; last_kd = kd
            if kd in (1, 2):
                events.append((f, rnd, "him down" if kd == 1 else "Mac down"))
            plan = None
        if kd == 2:                         # Mac down: up, mashing
            mash += 1
            g.hold([["a"], [], ["b"], []][(mash // 3) % 4]); g.tick(); continue
        if kd:
            g.hold([]); g.tick(); continue
        if cue:                             # the tell: his counter's body blow (or the dodge), in the NES's window
            lit = g.m[0, cue[0]] != cue[1]
            if lit and not cue_on:
                plan, k0 = Plan((cue[2], cue[2] + 3, cue[3])), f
                events.append((f, rnd, "crowd tell"))
            cue_on = lit
        if plan is not None and f - k0 > plan.end() + 2:
            plan = None
        seen = (g.nes(0x90), g.nes(0xA1), g.nes(0x50), g.nes(0x398), g.nes(0x391), g.nes(0x342))
        if plan is None and (g.nes(0x50) & 0x7F) in FREE and g.nes(0x76) != 0xFF and (
                seen != last_seen or f >= due or f - last_think >= 8):
            plan = think(g, f - last_act, last_hand); k0 = f; last_think = f; last_seen = seen; due = 1 << 30
            if plan and min(a for a, _, _ in plan.steps) > COMMIT:
                due = f + min(a for a, _, _ in plan.steps) - COMMIT   # (not yet: think again then, or sooner
                plan = None                                           # if he shows something new)
            if plan:
                last_act = f
                pressed = {b for _, _, btn in plan.steps for b in btn}
                last_hand = "a" if "a" in pressed else "b" if "b" in pressed else last_hand
            if log and plan: log(f"{f}: plan {plan.steps} (Mac {g.nes(0x391)}, him {g.nes(0x398)})")
        g.hold(plan.at(f - k0) if plan else [])
        g.tick()
        if log and f % 1200 == 0:
            log(f"{f}: round {rnd} Mac {g.nes(0x391)} him {g.nes(0x398)} kd {mac_kd}/{his_kd}")
    out = {"won": result in WIN, "result": result, "frames": f, "round": rnd_prev,
           "mac_knockdowns": mac_kd, "his_knockdowns": his_kd, "events": events}
    g.stop()
    return out


if __name__ == "__main__":
    import sys
    print(play(sys.argv[1], int(sys.argv[2]), log=print if "-v" in sys.argv else None))
