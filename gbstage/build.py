"""Turn assembly source into a .gb ROM with the active RGBDS."""

import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path

from . import deps


class BuildError(Exception):
    def __init__(self, step, output):
        super().__init__(f"{step} failed")
        self.step = step
        self.output = output


def _run(step, cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise BuildError(step, (out.stdout + out.stderr).strip())


# rom: bytes. map/sym: RGBDS's section map and symbol file, used by the profiler.
Build = namedtuple("Build", "rom map sym")


def build_rom(asm_source, title, cgb=False, info=None):
    """Assemble, link and fix. cgb=True marks the ROM as Game Boy Color enhanced (dual mode). Returns a Build."""
    info = info or deps.rgbds_info()
    if not info["found"] or info["error"]:
        raise BuildError("RGBDS", info["error"] or "RGBDS not found. Run: python3 -m gbstage install")
    with tempfile.TemporaryDirectory() as tmp:
        src, obj, rom = Path(tmp) / "game.asm", Path(tmp) / "game.o", Path(tmp) / "game.gb"
        map_file, sym_file = Path(tmp) / "game.map", Path(tmp) / "game.sym"
        src.write_text(asm_source)
        _run("rgbasm", [deps.rgbds_tool(info, "rgbasm"), "-o", str(obj), str(src)])
        _run("rgblink", [deps.rgbds_tool(info, "rgblink"), "-t", "-m", str(map_file), "-n", str(sym_file), "-o", str(rom), str(obj)])   # -t: a plain 32 KB cartridge, all of it fixed
        fix = [deps.rgbds_tool(info, "rgbfix"), "-v", "-p", "0xFF", "-t", title]
        if cgb:
            fix.append("-c")
        _run("rgbfix", fix + [str(rom)])
        return Build(rom.read_bytes(), map_file.read_text(), sym_file.read_text())
