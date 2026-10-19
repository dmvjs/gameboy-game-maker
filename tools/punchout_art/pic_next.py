"""Which of a rival's pictures likely comes next, as the bot's fights show them (on the Joe vs Mac example's ROM):
per picture, the one most often after it, and one exception by the picture before it ([next, before, then next]).
The original Game Boy loads it early, into its copy not shown, while the picture's up (its pictures stream slowly).

  python pic_next.py -> out/pic-next.json (build.py puts each rival's in his pictures as "next")"""
import collections, json, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))


def _seq(args):
    rom, scene = args
    from gbstage import bot
    seq = []
    otick = bot.Game.tick

    def tick(self, render=True):
        otick(self, render)
        if render and self.hram("hFtActive") == 1:
            w = self.m[self.S["wRvPic"]]
            if not seq or seq[-1] != w:
                seq.append(w)
    bot.Game.tick = tick
    bot.play(rom, scene)
    return scene, seq


def main():
    from gbstage import codegen
    from gbstage.build import build_rom
    project = codegen.validate(json.loads((ROOT / "examples" / "joe-vs-mac.gbstage.json").read_text()))
    build = build_rom(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    rom = Path(tempfile.mkdtemp(prefix="pic-next-")) / "game.gbc"
    rom.write_bytes(build.rom)
    Path(str(rom) + ".sym").write_text(build.sym)
    fights = [(i, s) for i, s in enumerate(project["scenes"]) if s.get("fight") and s.get("fight_pics")]
    one = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    two = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    with ProcessPoolExecutor() as pool:
        for scene, seq in pool.map(_seq, [(str(rom), i) for i, _ in fights]):
            s = project["scenes"][scene]
            name = s["name"].split(":")[-1].strip().lower().rstrip("0123456789") if ":" in s["name"] else "joe"
            order = s["fight_pics"]["order"]
            keys = [order[k] if k < len(order) else None for k in seq]
            for a, b, c in zip(keys, keys[1:], keys[2:]):
                one[name][b][c] += 1
                two[name][(a, b)][c] += 1
            print(s["name"], len(seq), "changes", flush=True)
    out = {}
    for name, table in one.items():
        out[name] = {}
        for cur, nexts in table.items():
            if cur is None:
                continue
            nxt = nexts.most_common(1)[0][0]
            best = max(((two[name][(a, b)].most_common(1)[0][0], a, two[name][(a, b)].most_common(1)[0][1])
                        for (a, b) in two[name] if b == cur and a is not None), key=lambda t: t[2], default=None)
            exc = [best[1], best[0]] if best and best[0] != nxt else [nxt, nxt]
            out[name][cur] = [nxt] + exc
    (HERE / "out" / "pic-next.json").write_text(json.dumps(out, indent=0, sort_keys=True))
    print("wrote out/pic-next.json:", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
