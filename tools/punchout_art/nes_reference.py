"""What Punch-Out!! (NES) does around its fights, played once in cynes (the real game) for gbstage/careertests.py:
the title's pass keys (valid, special, wrong), NEW and the Another World Circuit's start, losing (rematches, down
the ranks, game over), the circuits' title fights won (what comes next), Mike Tyson beaten, and the Another World
Circuit won through. Fights are won by the game's own result ($00 = $FC) and lost by Mac's health held at 0
($0391); START moves on between them. -> tests/nes_reference.json (CI checks the port against it; no NES ROM there).

  python nes_reference.py"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent.parent / "tests" / "nes_reference.json"
A, B, SEL, START, DOWN, RIGHT = 0x80, 0x40, 0x20, 0x10, 0x04, 0x01
OPP = ["Joe", "Kaiser", "Honda", "Don", "Hippo", "Tiger", "Bull", "Honda2", "Soda", "Bull2", "Don2", "Sandman",
       "Macho", "Tyson"]                                # (their $01; the port's scenes' names: "Fight: Kaiser", ...)
AW = ["Hippo", "Tiger", "Honda", "Soda", "Bull", "Don", "Sandman", "Macho", "Tyson"]    # ($01 $14-$1C)
SFX_CONFIRM, SFX_DIGIT = 0x18, 0x12


def _nes():
    import cynes_frames as C
    from cynes import NES
    return NES(C.rom_path())


def _run(nes, n, b=0, log=None):
    for _ in range(n):
        nes.controller = b
        nes.step()
        if log is not None and nes[0xF0] not in (0, 0x80):
            log.append(nes[0xF0])


def _key(nes, digits, select=False, partial=None, log=None):
    """The title, CONTINUE, the digits typed as a player types them (right to step one, A for the next; the last
    with A, B and Select held for the special keys)."""
    _run(nes, 700)                                      # (the title takes keys from about here)
    _run(nes, 4, DOWN); _run(nes, 26)
    _run(nes, 4, RIGHT); _run(nes, 16)
    for k, d in enumerate(digits[:partial or 10]):
        for _ in range(d):
            _run(nes, 4, RIGHT); _run(nes, 8)
        if k == 9 and select:
            _run(nes, 4, SEL); _run(nes, 40, SEL | A | B, log); _run(nes, 10, 0, log)
        else:
            _run(nes, 4, A, log); _run(nes, 16, 0, log)
    if partial:
        _run(nes, 4, START, log); _run(nes, 16, 0, log)


def _record(nes):
    r = [nes[0x170 + i] for i in range(6)]
    return [r[0] * 10 + r[1], r[2] * 10 + r[3], r[4] * 10 + r[5]]


def pass_keys():
    import passwords as P
    special = {k: [int(c) for c in v] for k, v in P.SPECIAL.items()}
    cases = [("3-0 3KO, the Minor Circuit's", P.encode(3, 0, 3, 0), False, None),
             ("7-1 5KO, the Major Circuit's", P.encode(7, 1, 5, 1), False, None),
             ("11-2 9KO, the World Circuit's", P.encode(11, 2, 9, 2), False, None),
             ("30-2 25KO, the World Circuit's", P.encode(30, 2, 25, 2), False, None),
             ("0-0 0KO, the Minor Circuit's (not one the NES takes)", P.encode(0, 0, 0, 0), False, None),
             ("Mike Tyson's", special["tyson"], False, None),
             ("the Another World Circuit's, A+B+Select", special["another_world"], True, None),
             ("the Another World Circuit's, without Select", special["another_world"], False, None),
             ("the credits', A+B+Select", special["credits"], True, None),
             ("the credits', without Select", special["credits"], False, None),
             ("busy signal 1", special["busy1"], False, None), ("busy signal 2", special["busy2"], False, None),
             ("busy signal 3", special["busy3"], False, None),
             ("1234567890", [1, 2, 3, 4, 5, 6, 7, 8, 9, 0], False, None), ("0000000000", [0] * 10, False, None),
             ("3-0 3KO's with a digit off", [(d + 1) % 10 if i == 4 else d for i, d in enumerate(P.encode(3, 0, 3, 0))],
              False, None),
             ("five digits, then Start", P.encode(3, 0, 3, 0), False, 5)]
    out = []
    for name, digits, select, partial in cases:
        nes, log = _nes(), []
        _key(nes, digits, select, partial, log)
        _run(nes, 600, 0, log)
        opp = nes[0x01]
        if digits == special["credits"] and select:
            result = {"to": "credits"}
        elif SFX_CONFIRM in log and opp < len(OPP):
            result = {"to": "challenger", "opponent": OPP[opp], "record": _record(nes)}
        elif SFX_CONFIRM in log and 0x14 <= opp <= 0x1C:
            result = {"to": "challenger", "opponent": AW[opp - 0x14], "another_world": True, "record": _record(nes)}
        elif partial:
            result = {"to": "waiting"}                  # (Start mid-way: the next digit, as A; no check)
        else:
            result = {"to": "title", "busy_beeps": log.count(SFX_DIGIT)}
        out.append({"name": name, "digits": "".join(map(str, digits)), "select": select, "partial": partial, **result})
        print(" ", name, result, flush=True)
    return out


def flow(nes, plan, frames, stop_after=2500):
    """The fights in turn as the plan has them (W or L, then W), START between: each fight's opponent (a name, its
    circuit's) and Mac's record going in; then where it settles (the last screen's $01)."""
    fights, infight, t, last, still, tf = [], False, 0, None, 0, 0
    while t < frames:
        mode = nes[0x00]
        if mode == 1 and not infight:
            infight, tf = True, t
            res = plan[len(fights)] if len(fights) < len(plan) else "W"
            o = nes[0x01]
            fights.append({"opponent": OPP[o] if o < len(OPP) else AW[o - 0x14], "record": _record(nes), "result": res})
        if infight:
            if res == "L":
                nes[0x391] = 0
            elif t - tf == 200:
                nes[0x00] = 0xFC
            if mode != 1 and t - tf > 210:
                infight = False
        nes.controller = START if not infight and t % 90 < 4 else 0
        f = nes.step()
        t += 1
        if t % 30 == 0 and not infight:
            h = hashlib.md5(bytes(f[::8, ::8, :3].tobytes())).hexdigest()
            still = 0 if h != last else still + 30
            last = h
            if still > stop_after and len(fights) >= len(plan):
                break
    return {"fights": fights, "settles": {"opponent": nes[0x01], "record": _record(nes)}}


def _start(opp=None, key=None, select=False):
    nes = _nes()
    if key:
        _key(nes, key, select)
        _run(nes, 200)
    else:
        _run(nes, 700); _run(nes, 4, START); _run(nes, 60)
        if opp is not None:
            nes[0x01] = opp
        _run(nes, 200)
    return nes


def flows():
    import passwords as P
    aw = [int(c) for c in P.SPECIAL["another_world"]]
    out = {}
    plans = {"NEW": (None, None, "W", 4000),
             "Another World": (None, aw, "W", 4000),
             "three losses to Glass Joe": (0, None, "LLLW", 20000),
             "Von Kaiser lost to, then his rematch": (1, None, "LLLW", 20000),
             "Don Flamenco won, King Hippo lost to twice": (3, None, "WLLW", 20000),
             "Piston Honda's title fight lost, then Von Kaiser's": (2, None, "LLW", 15000),
             "Bald Bull's title fight lost, then Great Tiger's": (6, None, "LLW", 15000),
             "Super Macho Man's title fight lost, then Don Flamenco's": (12, None, "LLW", 15000),
             "Piston Honda's title fight won": (2, None, "WW", 9000),
             "Bald Bull's title fight won": (6, None, "WW", 9000),
             "Super Macho Man's title fight won": (12, None, "WW", 9000),
             "Mike Tyson won": (13, None, "W", 9000),
             "the Another World Circuit won through": (None, aw, "W" * 9, 60000)}
    for name, (opp, key, plan, frames) in plans.items():
        r = flow(_start(opp, key, key is not None), plan, frames)
        r["fights"] = r["fights"][:len(plan)]
        out[name] = r
        print(" ", name, [(f["opponent"], f["record"], f["result"]) for f in r["fights"]], flush=True)
    return out


def dodge_tells():
    """Super Macho Man's crowd tell (his spin, state $19: a dodge's, the man in shades at NES cell row 9, column 24):
    his spin started from standing with Mac free, then left alone, and then hit (B, the frame after it starts):
    the frame the man first shows (0: the frame it starts) and for how many; hit, his state next (8: hit) and
    the man staying (through `window`): the NES never clears $46 then."""
    import numpy as np
    nes, t = _start(12), 0
    while True:
        nes[0x391] = 0x60
        nes.controller = START if nes[0x00] != 1 and t % 90 < 4 else 0
        f = nes.step()
        t += 1
        if nes[0x00] == 1 and t > 1400 and nes[0x90] & 0x7F == 1 and nes[0x50] == 1:
            break
    box = (slice(72, 80), slice(192, 200))
    rest, snap, window = f[box].copy(), nes.save(), 300
    out = {"opponent": 12, "state": 0x19, "window": window}
    for hit in (False, True):
        nes.load(snap)
        shown, states = [], []
        for k in range(window):
            nes[0x391] = 0x60
            nes.controller = B if hit and 1 <= k < 4 else 0
            if k == 0:
                nes[0x90] = 0x19 | 0x80
            shown.append(not np.array_equal(nes.step()[box], rest))
            states.append(nes[0x90] & 0x7F)
        first = shown.index(True)
        n = (shown[first:] + [False]).index(False)
        if hit:
            out["hit"] = {"button": "B", "at": 1, "his_state": next(v for v in states if v != 0x19), "shows_through": n == window - first}
        else:
            out["shows_after"], out["shows_for"] = first, n
    return {"Macho": out}


TAS_CLOCK_STOP = "https://tasvideos.org/6742S?handler=Download"     # (McHazard's "clock stop glitch" run, BizHawk)
OPP_KEYS = {8: "soda", 10: "don2", 12: "macho"}


def clock_stops():
    """The clock-stop glitch as the NES has it: TASVideos' clock-stop run (downloaded; its inputs a frame on from
    cynes' power-on), and each of its long clock holds (halted, no one down, not his own scripted pause $19/$1A,
    240 frames or more): the NES's RAM a while before (from where the clock last ran, his pause's own stop run too),
    the run's inputs from there, Mac's and his states each frame ($50, $90) to 30 past the hold's start, and how long
    the hold is. The port gets the RAM, the inputs, and
    has to hold the clock only briefly (gbstage/careertests.py glitches)."""
    import io, tempfile, urllib.request, zipfile
    data = urllib.request.urlopen(urllib.request.Request(TAS_CLOCK_STOP, headers={"User-Agent": "Mozilla/5.0"})).read()
    bk2 = zipfile.ZipFile(io.BytesIO(data))
    movie = zipfile.ZipFile(io.BytesIO(bk2.read(bk2.namelist()[0])))
    lines = [l for l in movie.read("Input Log.txt").decode().splitlines() if l.startswith("|..|")]
    bits = [0x08, 0x04, 0x02, 0x01, START, SEL, B, A]               # (its order: U D L R Start Select B A)
    inputs = [sum(b for b, c in zip(bits, l.split("|")[2]) if c != ".") for l in lines][1:]
    nes, run, hist, holds = _nes(), 0, [], []
    for t, b in enumerate(inputs):
        nes.controller = b
        nes.step()
        hist.append(nes[0x301] & 1)
        if nes[0x00] == 1 and nes[0x301] == 1 and nes[0x05] == 0 and nes[0x90] & 0x7F not in (0x19, 0x1A):
            run += 1
        else:
            if run >= 240 and nes[0x01] in OPP_KEYS:
                start = t - run
                ran = max(k for k in range(start) if not hist[k])       # (the clock last running before it)
                holds.append((start, start - ran + 40 if start - ran > 30 else 32))
            run = 0
    out = []
    for start, back in holds:
        nes = _nes()
        for t in range(start - back):
            nes.controller = inputs[t]
            nes.step()
        ram, opp = bytes(nes[a] for a in range(0x800)), nes[0x01]
        held, trace = 0, []
        for t in range(start - back, start + 600):
            nes.controller = inputs[t]
            nes.step()
            if t < start + 30:
                trace.append([nes[0x50], nes[0x90] & 0x7F])
            if t >= start:
                held = held + 1 if nes[0x301] & 1 and nes[0x05] == 0 else held
                if not nes[0x301] & 1:
                    break
        out.append({"opponent": OPP_KEYS[opp], "back": back, "held": held, "ram": ram.hex(),
                    "inputs": inputs[start - back:start + 200], "states": trace})
        print(" ", OPP_KEYS[opp], "hold at", start, "back", back, "held", held, flush=True)
    return out


RANDOM_OPPS = {0: "joe", 1: "kaiser", 2: "honda", 3: "don", 5: "tiger", 6: "bull", 7: "honda2", 8: "soda", 9: "bull2", 10: "don2", 12: "macho"}


def randoms(frames=1200, after=30):
    """The random byte ($18) as the NES has it: TASVideos' clock-stop run (as clock_stops), one stretch per opponent
    (RANDOM_OPPS) a while into his fight, mid-round, no one down: the NES's RAM at its start, the run's inputs from
    there, and each frame's $18 and $19 (its running sum), Mac's and his states ($50, $90), and what $18 is built from
    ($1E, $D0, $21) -- the port, given the RAM and the inputs, must build the same random bytes frame by frame."""
    import io, urllib.request, zipfile
    data = urllib.request.urlopen(urllib.request.Request(TAS_CLOCK_STOP, headers={"User-Agent": "Mozilla/5.0"})).read()
    bk2 = zipfile.ZipFile(io.BytesIO(data))
    movie = zipfile.ZipFile(io.BytesIO(bk2.read(bk2.namelist()[0])))
    lines = [l for l in movie.read("Input Log.txt").decode().splitlines() if l.startswith("|..|")]
    bits = [0x08, 0x04, 0x02, 0x01, START, SEL, B, A]
    inputs = [sum(b for b, c in zip(bits, l.split("|")[2]) if c != ".") for l in lines][1:]
    nes, run, starts = _nes(), {}, {}
    for t, b in enumerate(inputs):
        nes.controller = b
        nes.step()
        o = nes[0x01]
        live = nes[0x00] == 1 and nes[0x05] == 0 and nes[0x301] & 1
        run[o] = run.get(o, 0) + 1 if live else 0
        if o in RANDOM_OPPS and o not in starts and run[o] >= after:
            starts[o] = t
        if len(starts) == len(RANDOM_OPPS):
            break
    out = []
    for o, start in sorted(starts.items()):
        nes = _nes()
        for t in range(start + 1):
            nes.controller = inputs[t]
            nes.step()
        ram = bytes(nes[a] for a in range(0x800))
        trace = []
        for t in range(start + 1, start + 1 + frames):
            nes.controller = inputs[t]
            nes.step()
            trace.append([nes[0x18], nes[0x19], nes[0x50], nes[0x90] & 0x7F, nes[0x1E], nes[0xD0], nes[0x21]])
        out.append({"opponent": RANDOM_OPPS[o], "ram": ram.hex(), "inputs": inputs[start + 1:start + 2 + frames],
                    "trace": trace})
        print(" ", RANDOM_OPPS[o], "from", start, flush=True)
    return out


def main():
    if sys.argv[1:] == ["randoms"]:
        ref = json.loads(OUT.read_text())
        ref["randoms"] = randoms()
        ref["randoms_note"] = (
            "The random byte on the NES (cynes, TASVideos submission 6742's inputs): per opponent, the NES's RAM a while "
            "into his fight, the run's inputs from there, and each frame after: $18, $19, Mac's state, his state, $1E, $D0, $21.")
        OUT.write_text(json.dumps(ref, indent=1) + "\n")
        print("wrote", OUT, len(ref["randoms"]), "stretches")
        return
    if sys.argv[1:] == ["dodge_tells"]:             # (just these, into the reference as it stands)
        ref = json.loads(OUT.read_text())
        ref["dodge_tells"] = dodge_tells()
        OUT.write_text(json.dumps(ref, indent=1) + "\n")
        print("wrote", OUT, ref["dodge_tells"])
        return
    if sys.argv[1:] == ["clock_stops"]:
        ref = json.loads(OUT.read_text())
        ref["clock_stops"] = clock_stops()
        ref["clock_stops_note"] = (
            "The clock-stop glitch on the NES (cynes, TASVideos submission 6742's inputs): per long hold, the NES's RAM "
            "`back` frames before it starts, the run's inputs from there, and how long the NES holds the clock (frames, "
            "no one down; capped at 600). The port, given the RAM and inputs, must not hold it like that.")
        OUT.write_text(json.dumps(ref, indent=1) + "\n")
        print("wrote", OUT, len(ref["clock_stops"]), "holds")
        return
    print("pass keys:")
    keys = pass_keys()
    print("flows:")
    out = {"source": "Punch-Out!! (NES), played in cynes by tools/punchout_art/nes_reference.py", "pass_keys": keys,
           "flows": flows()}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
