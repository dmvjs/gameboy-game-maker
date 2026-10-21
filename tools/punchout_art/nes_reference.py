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


def main():
    print("pass keys:")
    keys = pass_keys()
    print("flows:")
    out = {"source": "Punch-Out!! (NES), played in cynes by tools/punchout_art/nes_reference.py", "pass_keys": keys,
           "flows": flows()}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
