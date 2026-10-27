"""Which of a rival's pictures likely comes next, as his fights show them (on the Joe vs Mac example's ROM: the bot's
fights, Color and the original, and Mac standing still, as qa_perf has him): per picture, by the pictures before it,
the one most often after it -- [next] alone, the one most often after it at all; [before, next] where the picture
before it says otherwise; [two before, before, next] where the one before that does too. The original Game Boy
loads it early, into its copy not shown, while the picture's up (its pictures stream slowly: a wrong guess, a frame
late).

His state rules come first, where his fights show them sure (STATE_SURE of the poses behind each): by his state
script's place as the NES has it at each frame (his state $90, its script's place $93, frames to go $92 up to 2;
the original: as it decides, at VBlank's end, the wanted picture up) -- [state, place, the one shown before, frames
to go, next] per picture shown, where they say other than [state, place, next] in general; the original asks each
frame, and changes its guess as his state goes on (the bot's fights, Color and the original; Mac still, the original).

  python pic_next.py -> out/pic-next.json, out/pic-state.json (build.py puts each rival's in his pictures as "next",
  "nextState")"""
import collections, json, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
STILL = 3000                            # (Mac still: qa_perf's frames)
STATE_SURE = 0.7                        # (a state rule kept: its next that share of the poses behind it, at least)


def _seq(args):
    """The wanted pictures' changes in a fight (None: the fight left, the corner between rounds); and per frame at
    VBlank's end, in the fight: the wanted picture, the one up, his state ($90), its place ($93), frames to go ($92)."""
    rom, scene, cgb, still = args
    from gbstage import bot
    seq, frames = [], []

    def look(g):
        if g.hram("hScene") == scene and g.hram("hFtActive") == 1:
            w = g.m[g.S["wRvPic"]]
            if not seq or seq[-1] != w:
                seq.append(w)
        elif seq and seq[-1] is not None:
            seq.append(None)

    def watch(g):                       # (each VBlank's end: as the original asks his guess)
        S, B = bot._symbols(rom)
        ov = g._vblank

        def done(_):
            ov(_)
            if g.hram("hScene") == scene and g.hram("hFtActive") == 1:
                w = g.m[S["wRvPic"]]
                n = S["wNes"]
                frames.append((w, w if cgb else g.m[S["wRvPicShown"]], g.m[n + 0x90], g.m[n + 0x93], g.m[n + 0x92]))
            elif frames and frames[-1] is not None:
                frames.append(None)
        g.pb.hook_deregister(B["VBlankDone"], S["VBlankDone"])
        g.pb.hook_register(B["VBlankDone"], S["VBlankDone"], done, None)
    if still:
        from gbstage import qatests
        g = qatests._game(rom, scene, cgb)
        watch(g)
        qatests._to_fight(g, scene)
        frames.clear()
        for _ in range(still):
            g.hold([])
            g.tick(False)
            look(g)
        g.stop()
        return scene, seq, frames
    S, B = bot._symbols(rom)
    oinit = bot.Game.__init__

    def init(self, *a, **k):
        oinit(self, *a, **k)
        if not cgb:                     # (as the original boots: A = $01)
            self.pb.hook_register(B["Start"], S["Start"], lambda _: setattr(self.pb.register_file, "A", 1), None)
        watch(self)
    bot.Game.__init__ = init
    otick = bot.Game.tick

    def tick(self, render=True):
        otick(self, render)
        if render:
            look(self)
    bot.Game.tick = tick
    try:
        bot.play(rom, scene, cgb=cgb)
    finally:                            # (a pool's process runs another fight next: as it was)
        bot.Game.__init__, bot.Game.tick = oinit, otick
    return scene, seq, frames


def _samples(frames):
    """Per frame with the wanted picture up: (the one up, the one up before it, state, place, frames to go up to 2,
    the next wanted, the change it's in)."""
    out, n = [], len(frames)
    nxt, cur = [None] * n, None
    for i in range(n - 1, -1, -1):
        if frames[i] is None:
            cur = None
            continue
        if i + 1 < n and frames[i + 1] is not None and frames[i + 1][0] != frames[i][0]:
            cur = frames[i + 1][0]
        nxt[i] = cur
    prev = last = None
    k = 0
    for i, f in enumerate(frames):
        if f is None:
            prev = last = None
            continue
        w, up, st, ix, t = f
        if i and frames[i - 1] is not None and frames[i - 1][0] != w:
            k += 1
        if up != last:
            if last is not None:
                prev = last
            last = up
        if nxt[i] is not None and up == w:
            out.append((up, prev, st, ix, min(t, 2), nxt[i], k))
    return out


def state_rules(runs):
    """His state rules ({"spec": per picture [[state, place, before, frames to go, next]], "general": [[state, place,
    next]]}, as numbers: the pictures' own), from his fights' frames: each pose's same key counted once."""
    spec, gen = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for r, frames in enumerate(runs):
        seen = set()
        for up, prev, st, ix, t, nx, k in _samples(frames):
            for table, key in ((spec, (up, st, ix, prev, t)), (gen, (st, ix))):
                if (r, k, len(key), key) not in seen:
                    seen.add((r, k, len(key), key))
                    table[key][nx] += 1
    best = lambda c: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    sure = lambda c: best(c) if c[best(c)] >= STATE_SURE * sum(c.values()) else None
    general = {k: sure(c) for k, c in gen.items()}
    general = {k: v for k, v in general.items() if v is not None}
    out = collections.defaultdict(list)
    for (up, st, ix, prev, t), c in spec.items():
        b = sure(c)
        if b is not None and prev is not None and general.get((st, ix)) != b:
            out[up].append([st, ix, prev, t, b])
    return {"spec": {k: sorted(v) for k, v in out.items()}, "general": sorted([st, ix, nx] for (st, ix), nx in general.items())}


def _best(counter):
    """The most often, the lowest of a tie (the same table from the same fights, run to run)."""
    return min(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[0]


def rules(seqs):
    """Per picture its rules ([.., before, next], the longest first wins; [next] last), from the change sequences."""
    count = collections.defaultdict(collections.Counter)
    for s in seqs:
        for i in range(1, len(s)):
            for n in (1, 2, 3):
                ctx = tuple(s[max(0, i - n):i])
                if len(ctx) == n and None not in ctx and s[i] is not None:
                    count[ctx][s[i]] += 1
    out = {}
    for ctx in [c for c in count if len(c) == 1]:
        cur = ctx[0]
        nxt = _best(count[ctx])
        two = {c[0]: _best(count[c]) for c in count if len(c) == 2 and c[1] == cur}
        two = {b: p for b, p in two.items() if p != nxt}
        three = []
        for c in count:
            if len(c) == 3 and c[2] == cur:
                was = two.get(c[1], nxt)
                p = _best(count[c])
                if p != was and count[c][p] > count[c][was]:
                    three.append([c[0], c[1], p])
        out[cur] = sorted(three) + sorted([b, p] for b, p in two.items()) + [[nxt]]
    return out


def main():
    from gbstage import codegen
    from gbstage.build import build_rom
    project = codegen.validate(json.loads((ROOT / "examples" / "joe-vs-mac.gbstage.json").read_text()))
    build = build_rom(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    rom = Path(tempfile.mkdtemp(prefix="pic-next-")) / "game.gbc"
    rom.write_bytes(build.rom)
    Path(str(rom) + ".sym").write_text(build.sym)
    fights = [(i, s) for i, s in enumerate(project["scenes"]) if s.get("fight") and s.get("fight_pics")]
    seqs, runs, orders = collections.defaultdict(list), collections.defaultdict(list), {}
    jobs = [(str(rom), i, cgb, still) for i, _ in fights for cgb in (True, False) for still in (0, STILL)]
    with ProcessPoolExecutor() as pool:
        for (scene, seq, frames), (_, _, cgb, still) in zip(pool.map(_seq, jobs), jobs):
            s = project["scenes"][scene]
            name = s["name"].split(":")[-1].strip().lower().rstrip("0123456789") if ":" in s["name"] else "joe"
            order = s["fight_pics"]["order"]
            orders[name] = order
            seqs[name].append([None if k is None else order[k] if k < len(order) else None for k in seq])
            if not (still and cgb):     # (Mac still: the original's -- Color's the same course, a picture never late)
                runs[name].append(frames)
            print(s["name"], len(seq), "changes", flush=True)
    out = {name: rules(ss) for name, ss in seqs.items()}
    (HERE / "out" / "pic-next.json").write_text(json.dumps(out, indent=0, sort_keys=True))
    print("wrote out/pic-next.json:", {k: (len(v), sum(map(len, v.values()))) for k, v in out.items()})
    st = {}
    for name, rs in runs.items():
        r, o = state_rules(rs), orders[name]
        st[name] = {"spec": {o[k]: [[a, b, o[p], t, o[n]] for a, b, p, t, n in v] for k, v in sorted(r["spec"].items())},
                    "general": [[a, b, o[n]] for a, b, n in r["general"]]}
    (HERE / "out" / "pic-state.json").write_text(json.dumps(st, indent=0, sort_keys=True))
    print("wrote out/pic-state.json:", {k: (sum(map(len, v["spec"].values())), len(v["general"])) for k, v in st.items()})


if __name__ == "__main__":
    main()
