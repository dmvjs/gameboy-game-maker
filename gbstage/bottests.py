"""Every fighter goes down: the bot (bot.py, buttons only) fights each fight of the Joe vs Mac example and
must win it by knockout inside two rounds. Fights run side by side, one process each."""
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import codegen
from .build import build_rom

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
MAX_ROUND = 2


def _fight(args):
    rom, scene = args
    from . import bot
    return scene, bot.play(rom, scene)


def run(log=print, only=None):
    try:
        import pyboy  # noqa: F401
    except ImportError:
        log("  (skipped: needs PyBoy)")
        return True
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    fights = [(i, s.get("name", f"scene {i}")) for i, s in enumerate(project["scenes"]) if s.get("fight")]
    if only:
        fights = [f for f in fights if any(o.lower() in f[1].lower() for o in only)]
    build = build_rom(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    tmp = Path(tempfile.mkdtemp(prefix="gbstage-bot-"))
    rom = tmp / "fights.gbc"
    rom.write_bytes(build.rom)
    Path(str(rom) + ".sym").write_text(build.sym)
    names = dict(fights)
    ok = True
    with ProcessPoolExecutor() as pool:
        for scene, r in sorted(pool.map(_fight, [(str(rom), i) for i, _ in fights])):
            good = r["won"] and r["round"] <= MAX_ROUND
            ok = ok and good
            how = (f"won in round {r['round']}" if r["won"] else
                   "lost on points" if r["result"] == 0xFA else "lost" if r["result"] else "no result")
            log(("  ✓" if good else "  ✗") + f" {names[scene]}: {how}; Mac down {r['mac_knockdowns']}, "
                f"him down {r['his_knockdowns']} ({r['frames'] / 60:.0f}s of fight)")
    return ok
