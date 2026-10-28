"""The hardware-timing check: every fight of the Joe vs Mac example on SameBoy (cycle-accurate where PyBoy is only
frame-accurate), Color (CGB-E) and the original (DMG-B), each from power-on (SameBoy's own open-source boot ROMs,
built from source -- never Nintendo's) into the fight: start tapped every 50 frames through the first START_FRAMES
(the screens before it, the fight's first seconds), then a seeded masher (the same buttons every run: punches,
dodges, blocks, stars -- the fight on, won or lost, and the screens after), FRAMES video frames in all. Fails on anything real hardware does that a forgiving emulator doesn't show:
  - a VRAM write while the screen draws it (mode 3), an OAM write during OAM scan or drawing (modes 2-3), a Color
    palette write during drawing -- the hardware drops each;
  - a GDMA (general-purpose VRAM DMA, the CPU stopped) over a line's drawing: mode 3 somewhere between its start
    and its end (in VBlank, or in a line's HBlank and the next line's OAM scan, it's fine);
  - a fight VBlank with no frame's work run in it (a frame lost: VBlankDone, once a VBlank) or with two.
Each is listed with its frame, line, mode, the routine it's in (the ROM's symbols) and the scene.

    python tools/sameboy/check.py                 # fetch + build SameBoy (once, cached), build the ROM, check all
    python tools/sameboy/check.py --fight Joe --model dmg --frames 3000
SameBoy is checked out at SAMEBOY_COMMIT under $SAMEBOY (default ~/.gbstage/sameboy/<commit>) and built with
tools/sameboy/Makefile (its core, headless; its boot ROMs with RGBDS); sbreplay.c is the checker itself."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
EXAMPLE = ROOT / "examples" / "joe-vs-mac.gbstage.json"
SAMEBOY_REPO = "https://github.com/LIJI32/SameBoy.git"
SAMEBOY_COMMIT = "26a56bd6a122a6318a456abd80558408742d5adf"     # (SameBoy's master, 2026-10-13)
START_FRAMES = 900          # (the recording: start tapped every 50 game frames, through the screens to the fight)
sys.path.insert(0, str(ROOT))


def sameboy_dir():
    return Path(os.environ.get("SAMEBOY") or Path.home() / ".gbstage" / "sameboy" / SAMEBOY_COMMIT[:12])


def build_tools(log=print):
    """SameBoy at the pinned commit, its core and boot ROMs and sbreplay built (make: only what's missing)."""
    from gbstage import deps
    sb = sameboy_dir()
    if not (sb / "Core" / "gb.c").exists():
        log(f"fetching SameBoy {SAMEBOY_COMMIT[:12]} into {sb}")
        sb.mkdir(parents=True, exist_ok=True)
        for cmd in (["git", "init", "-q"], ["git", "remote", "add", "origin", SAMEBOY_REPO],
                    ["git", "fetch", "-q", "--depth", "1", "origin", SAMEBOY_COMMIT], ["git", "checkout", "-q", "FETCH_HEAD"]):
            subprocess.run(cmd, cwd=sb, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sb, capture_output=True, text=True).stdout.strip()
    if head != SAMEBOY_COMMIT:
        raise SystemExit(f"{sb} is at {head or '?'}, not {SAMEBOY_COMMIT}: remove it (or point $SAMEBOY elsewhere)")
    rgbds = deps._locate_rgbds()[0]
    subprocess.run(["make", "-s", "-C", str(HERE), f"-j{os.cpu_count() or 2}", f"SAMEBOY={sb}",
                    f"RGBDS={str(rgbds) + '/' if rgbds else ''}"], check=True)
    return sb / "build" / "sbcheck" / "sbreplay", sb / "build" / "bin" / "BootROMs"


def build_rom(out):
    from gbstage import codegen
    from gbstage.build import build_rom as build
    project = codegen.validate(json.loads(EXAMPLE.read_text()))
    b = build(codegen.generate_asm(project), codegen.rom_title(project["name"]), cgb=True)
    out.write_bytes(b.rom)
    Path(str(out) + ".sym").write_text(b.sym)
    return out


def symbols(rom):
    """{name: (bank, address)} and per bank a sorted [(address, name)] (for naming where a write came from)."""
    named, by_bank = {}, {}
    for line in Path(str(rom) + ".sym").read_text().splitlines():
        if not line or line[0] == ";" or ":" not in line.split()[0]:
            continue
        loc, name = line.split()[:2]
        bank, addr = (int(x, 16) for x in loc.split(":"))
        named[name] = (bank, addr)
        if addr < 0x8000:
            by_bank.setdefault(0 if addr < 0x4000 else bank, []).append((addr, name))
    for v in by_bank.values():
        v.sort()
    return named, by_bank


def where(by_bank, pc, bank):
    """The label at or before PC (in the bank mapped then, for $4000-$7FFF)."""
    if pc >= 0x8000:
        return "RAM" if pc < 0xFF80 else "HRAM"
    best = None
    for addr, name in by_bank.get(0 if pc < 0x4000 else bank, []):
        if addr > pc:
            break
        best = (addr, name)
    return f"{best[1]}+${pc - best[0]:X}" if best else "?"


def scene_names():
    return [s["name"] for s in json.loads(EXAMPLE.read_text())["scenes"]]


def fights():
    project = json.loads(EXAMPLE.read_text())
    return [(i, s["name"].replace("Fight: ", "") if s["name"] != "Fight" else "Joe")
            for i, s in enumerate(project["scenes"]) if s.get("fight")]


def check_one(tools, rom, syms, scene, name, model, frames, work):
    sbreplay, boot = tools
    named, by_bank = syms
    out = work / f"{name}-{model}"
    out.mkdir(parents=True, exist_ok=True)
    inputs = work / "start.bin"
    env = dict(os.environ, SB_DONE=hex(named["VBlankDone"][1]), SB_ACTIVE=hex(named["hFtActive"][1]), SB_STRICT="1")
    cmd = [str(sbreplay), model, str(boot / f"{model}_boot.bin"), str(rom), str(inputs), str(out),
           hex(named["hFrame"][1]), hex(named["LoadScene"][1]), str(scene), str(frames), "0",
           hex(named["hScene"][1]), hex(named["hFtActive"][1])]
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=max(120, frames // 20))
        crashed = r.returncode not in (0, 2) and f"exit {r.returncode}: {r.stderr.strip()[-200:]}"
    except subprocess.TimeoutExpired:
        crashed = "timed out"
    fought, at = 0, {}
    ram = out / "ram.txt"
    if ram.exists():
        for line in ram.read_text().splitlines():
            f = line.split()
            fought += f[-2] == str(scene) and f[-1] == "1"
            at[f[0]] = int(f[-2])
    names = scene_names()
    bad, summary = [], "no summary"
    hw = out / "hardware.txt"
    for line in (hw.read_text().splitlines() if hw.exists() else []):
        if line.startswith("SUMMARY"):
            summary = line[8:]
        elif line.startswith("frame "):
            f = line.split()
            pc = "PC" in f and f.index("PC") or "(PC" in f and f.index("(PC")
            if pc:                              # (a write's or a GDMA's: PC xxxx bank B)
                addr, bank = int(f[pc + 1], 16), int(f[f.index("bank") + 1].rstrip(")"))
                line += f"  [{where(by_bank, addr, bank)}]"
            sc = at.get(f[1])                   # (its scene, at that frame's end)
            if sc is not None and sc < len(names):
                line += f"  ({names[sc]})"
            bad.append(line)
    ok = not crashed and fought > 0 and not bad
    return ok, name, model, fought, summary, grouped(bad), crashed


def grouped(bad):
    """A burst of dropped writes (one routine, one frame) as one line: its count, lines and addresses."""
    out, runs = [], {}
    for line in bad:
        m = re.match(r"frame (\d+) LY (\d+) STAT (\d) PC \w+ bank \d+ (.+) dropped (\w+) \(stack top (\w+)\)  (.*)", line)
        if not m:
            out.append(line)
            continue
        key = (m[1], m[4], m[7], m[6])
        if key not in runs:
            runs[key] = [len(out), [], [], set()]
            out.append(None)
        runs[key][1].append(int(m[2]))
        runs[key][2].append(m[5])
        runs[key][3].add(m[3])
    for (frame, what, rest, top), (i, lys, addrs, modes) in runs.items():
        def span(v):
            return str(v[0]) if v[0] == v[-1] else f"{v[0]}-{v[-1]}"
        out[i] = (f"frame {frame} LY {span(lys)} mode {'/'.join(sorted(modes))}: {len(addrs)} {what}s dropped "
                  f"{span(addrs)} (stack top {top})  {rest}")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--rom", help="a built ROM (its .sym beside it); default: build the example's")
    p.add_argument("--frames", type=int, default=6000, help="video frames each run, from power-on (default 6000)")
    p.add_argument("--fight", action="append", help="only this opponent (repeatable): Joe, Kaiser, ... Tyson")
    p.add_argument("--model", action="append", choices=("cgb", "dmg"))
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    p.add_argument("--work", help="where each run's ram.txt/hardware.txt go (default: a temporary directory)")
    p.add_argument("--build-only", action="store_true", help="fetch and build SameBoy and sbreplay, then stop")
    a = p.parse_args(argv)
    tools = build_tools()
    if a.build_only:
        return 0
    work = Path(a.work or tempfile.mkdtemp(prefix="sbcheck-"))
    work.mkdir(parents=True, exist_ok=True)
    rom = Path(a.rom) if a.rom else build_rom(work / "game.gbc")
    syms = symbols(rom)
    (work / "start.bin").write_bytes(bytes(0x80 if t % 50 < 3 else 0 for t in range(START_FRAMES)))
    runs = [(s, n, m) for s, n in fights() if not a.fight or n in a.fight for m in (a.model or ("cgb", "dmg"))]
    if not runs:
        raise SystemExit("no such fight")
    good = True
    with ThreadPoolExecutor(a.jobs) as pool:
        for ok, name, model, fought, summary, bad, crashed in pool.map(
                lambda r: check_one(tools, rom, syms, *r, a.frames, work), runs):
            good = good and ok
            print(f"{'✓' if ok else '✗'} {name} {model}: {fought} fight frames; {summary}"
                  + (f"; {crashed}" if crashed else "") + ("" if fought else "; the fight never reached"), flush=True)
            for line in bad[:20]:
                print("    " + line)
            if len(bad) > 20:
                print(f"    ... {len(bad) - 20} more ({work / f'{name}-{model}' / 'hardware.txt'})")
    print(f"{'✓' if good else '✗'} {len(runs)} runs, {a.frames} frames each: "
          + ("no hardware-rule violations" if good else "hardware-rule violations (above)"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
