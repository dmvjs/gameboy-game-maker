"""The "is everything hooked up?" checks, shared by the CLI and the web UI."""

import subprocess
from pathlib import Path

from . import deps
from .build import BuildError, build_rom

SELFTEST_ASM = Path(__file__).with_name("selftest.asm")
SELFTEST_TITLE = "GBSTAGE TEST"
INSTALL_HINT = "python3 -m gbstage install"

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCC6EE6DDDDD999BBBB67636E0EECCCDDDC999FBBB9333E")


def build_selftest(info):
    """Assemble, link and fix the self-test ROM. Returns the ROM bytes."""
    return build_rom(SELFTEST_ASM.read_text(), SELFTEST_TITLE, info=info).rom


def validate_rom(rom):
    """Check the cartridge header the way real hardware and emulators will. Returns a list of problems."""
    problems = []
    if len(rom) < 0x8000 or len(rom) % 0x4000:
        problems.append(f"size is {len(rom)} bytes, not a multiple of 16 KB")
        return problems
    if rom[0x104:0x134] != NINTENDO_LOGO:
        problems.append("Nintendo logo bytes are wrong (a real Game Boy would refuse to boot it)")
    x = 0
    for b in rom[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    if x != rom[0x14D]:
        problems.append(f"header checksum is {rom[0x14D]:#04x}, should be {x:#04x}")
    total = (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF
    if total != (rom[0x14E] << 8 | rom[0x14F]):
        problems.append("global checksum is wrong")
    if 0x8000 << rom[0x148] != len(rom):
        problems.append(f"header says {0x8000 << rom[0x148]} bytes but file is {len(rom)}")
    title = rom[0x134:0x144].rstrip(b"\0").decode("ascii", "replace")
    if title != SELFTEST_TITLE:
        problems.append(f"title is '{title}', expected '{SELFTEST_TITLE}'")
    return problems


def _check(id, label, status, detail, fix=None):
    return {"id": id, "label": label, "status": status, "detail": detail, "fix": fix}


def run_checks():
    """Return a list of check results. status is 'ok', 'warn', 'error', or 'skipped'."""
    checks = []

    py = deps.python_info()
    checks.append(_check("python", "Python", "ok" if py["ok"] else "error",
                         f"Python {py['version']}" + ("" if py["ok"] else f" (need {py['required']}+)"),
                         None if py["ok"] else f"Install Python {py['required']} or newer"))

    try:
        info = deps.rgbds_info()
    except RuntimeError as e:
        checks.append(_check("rgbds", "RGBDS", "error", str(e), "Fix or delete the config file"))
        info = None

    if info is not None:
        if not info["found"]:
            checks.append(_check("rgbds", "RGBDS found", "error", info["error"] or "not found", INSTALL_HINT))
        else:
            checks.append(_check("rgbds", "RGBDS found", "ok", f"{info['dir']}  ({info['source']})"))
            if info["error"]:
                checks.append(_check("rgbds-version", "RGBDS version", "error", info["error"],
                                     "python3 -m gbstage install rgbds"))
            else:
                checks.append(_check("rgbds-version", "RGBDS version", "ok",
                                     f"v{info['version']} (rgbasm, rgblink and rgbfix agree)"))
                status = {"tested": "ok", "untested": "warn", "unsupported": "error"}[info["compat"]]
                fix = None if status == "ok" else f"python3 -m gbstage install rgbds --version {deps.RGBDS_RECOMMENDED}"
                detail = info["compat_message"]
                if info["compat"] != "unsupported":
                    detail += f" (supported: {info['supported']})"
                checks.append(_check("rgbds-compat", "Compatibility", status, detail, fix))

    usable = info is not None and info["found"] and not info["error"] and info["compat"] != "unsupported"
    if usable:
        try:
            rom = build_selftest(info)
            checks.append(_check("build", "Test build", "ok", f"assembled, linked and fixed a {len(rom) // 1024} KB test ROM"))
            problems = validate_rom(rom)
            checks.append(_check("rom", "ROM header", "error" if problems else "ok",
                                 "; ".join(problems) or "logo, header checksum and global checksum are valid",
                                 "RGBDS produced a bad ROM; try the recommended version" if problems else None))
        except BuildError as e:
            checks.append(_check("build", "Test build", "error", f"{e.step} failed:\n{e.output}",
                                 f"Try the recommended version: python3 -m gbstage install rgbds --version {deps.RGBDS_RECOMMENDED}"))
        except (OSError, subprocess.TimeoutExpired) as e:
            checks.append(_check("build", "Test build", "error", f"couldn't run RGBDS: {e}", INSTALL_HINT))
    else:
        checks.append(_check("build", "Test build", "skipped", "needs a working RGBDS"))

    emu = deps.emulator_info()
    checks.append(_check("emulator", "Emulator files", "ok" if emu["installed"] else "error",
                         f"{emu['name']} @ {emu['commit']} (hashes verified)" if emu["installed"] else emu["error"],
                         None if emu["installed"] else INSTALL_HINT))
    return checks


def overall(checks):
    statuses = {c["status"] for c in checks}
    return "error" if "error" in statuses else "warn" if "warn" in statuses else "ok"
