"""Which of a rival's pictures likely comes next, as his fights show them (on the Joe vs Mac example's ROM: the bot's
fights, Color and the original, and Mac standing still, as qa_perf has him): per picture, by the pictures before it,
the one most often after it -- [next] alone, the one most often after it at all; [before, next] where the picture
before it says otherwise; [two before, before, next] where the one before that does too. The original Game Boy
loads it early, into its copy not shown, while the picture's up (its pictures stream slowly: a wrong guess, a frame
late).

  python pic_next.py -> out/pic-next.json (build.py puts each rival's in his pictures as "next")"""
import collections, json, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
STILL = 3000                            # (Mac still: qa_perf's frames)


def _seq(args):
    """The wanted pictures' changes in a fight (None: the fight left, the corner between rounds)."""
    rom, scene, cgb, still = args
    from gbstage import bot
    seq = []

    def look(g):
        if g.hram("hScene") == scene and g.hram("hFtActive") == 1:
            w = g.m[g.S["wRvPic"]]
            if not seq or seq[-1] != w:
                seq.append(w)
        elif seq and seq[-1] is not None:
            seq.append(None)
    if still:
        from gbstage import qatests
        g = qatests._game(rom, scene, cgb)
        qatests._to_fight(g, scene)
        for _ in range(still):
            g.hold([])
            g.tick(False)
            look(g)
        g.stop()
        return scene, seq
    if not cgb:                         # (as the original boots: A = $01)
        S, B = bot._symbols(rom)
        oinit = bot.Game.__init__

        def init(self, *a, **k):
            oinit(self, *a, **k)
            self.pb.hook_register(B["Start"], S["Start"], lambda _: setattr(self.pb.register_file, "A", 1), None)
        bot.Game.__init__ = init
    otick = bot.Game.tick

    def tick(self, render=True):
        otick(self, render)
        if render:
            look(self)
    bot.Game.tick = tick
    bot.play(rom, scene, cgb=cgb)
    return scene, seq


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
    seqs = collections.defaultdict(list)
    jobs = [(str(rom), i, cgb, still) for i, _ in fights for cgb in (True, False) for still in (0, STILL)]
    with ProcessPoolExecutor() as pool:
        for scene, seq in pool.map(_seq, jobs):
            s = project["scenes"][scene]
            name = s["name"].split(":")[-1].strip().lower().rstrip("0123456789") if ":" in s["name"] else "joe"
            order = s["fight_pics"]["order"]
            seqs[name].append([None if k is None else order[k] if k < len(order) else None for k in seq])
            print(s["name"], len(seq), "changes", flush=True)
    out = {name: rules(ss) for name, ss in seqs.items()}
    (HERE / "out" / "pic-next.json").write_text(json.dumps(out, indent=0, sort_keys=True))
    print("wrote out/pic-next.json:", {k: (len(v), sum(map(len, v.values()))) for k, v in out.items()})


if __name__ == "__main__":
    main()
