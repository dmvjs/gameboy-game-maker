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
        banked = "ROMX" in asm_source       # data in switchable banks: an MBC5 cartridge; otherwise a plain 32 KB one
        link = [deps.rgbds_tool(info, "rgblink")] + ([] if banked else ["-t"])
        _run("rgblink", link + ["-m", str(map_file), "-n", str(sym_file), "-o", str(rom), str(obj)])
        if rom.stat().st_size > 256 * 0x4000:   # (every switch writes $2000 only, the bank's low 8 bits: past 255,
            raise BuildError("rgblink", "ROM past 4 MB: banks over 255 need MBC5's ninth bank bit ($3000)")  # the wrong one)
        fix = [deps.rgbds_tool(info, "rgbfix"), "-v", "-p", "0xFF", "-t", title] + (["-m", "0x19"] if banked else [])
        if "DEF SAVE_SRAM EQU 1" in asm_source:     # a battery save: MBC5+RAM+BATTERY, its 8 KB of RAM
            fix += ["-m", "0x1B", "-r", "0x02"]
        if cgb:
            fix.append("-c")
        if "DEF SGB_SUPPORT EQU 1" in asm_source:   # Super Game Boy functions: the SGB flag and old licensee $33
            fix += ["-s", "-l", "0x33", "-k", "00"]  # (which the SGB wants; the new licensee code left "00")
        _run("rgbfix", fix + [str(rom)])
        return Build(rom.read_bytes(), map_file.read_text(), sym_file.read_text())
