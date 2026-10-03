"""Measure a built ROM: exact bytes from the linker map, exact cycles from running it.

Conventions the generated code follows so the profiler knows what it's looking at:
  Start          entry point after the header
  MainLoop       reached once startup work is done
  VBlankDone     reached each frame once everything that must happen during VBlank is done
  LoadScene      scene loads (screen off), measured separately from frames
  .waitX/.waitXDone  local labels around a busy-wait loop; cycles spent there are idle, not work
  "Code: ..." / "Data: ..."  section names, for the code vs data split
"""

import re

from .machine import FRAME, Machine
from .sm83 import Unsupported

VBLANK_CYCLES = 10 * 456          # time per frame when video memory is free to update
STARTUP_LIMIT = 60 * FRAME        # give up if startup takes over a second
RETURNS = {0xC0, 0xC8, 0xC9, 0xD0, 0xD8, 0xD9}


def parse_sym(text):
    labels = {}
    for line in text.splitlines():
        m = re.match(r"([0-9a-fA-F]+):([0-9a-fA-F]{4}) (\S+)", line)
        if m:
            labels[m.group(3)] = int(m.group(2), 16)
    return labels


def parse_map(text):
    """Sizes per memory region and per section from an rgblink map file."""
    regions, sections, region = {}, [], None
    for line in text.splitlines():
        m = re.match(r"(\w+) bank #\d+:", line)
        if m:
            region = m.group(1)
            continue
        m = re.match(r'\s*SECTION: \$([0-9a-f]+)(?:-\$([0-9a-f]+))? \(\$([0-9a-f]+) bytes?\) \["(.*)"\]', line)
        if m and region:
            size = int(m.group(3), 16)
            sections.append({"name": m.group(4), "region": region, "start": int(m.group(1), 16), "size": size})
            regions[region] = regions.get(region, 0) + size
    return regions, sections


def bytes_report(map_text, rom_size):
    regions, sections = parse_map(map_text)
    rom = [s for s in sections if s["region"] in ("ROM0", "ROMX")]
    kind = lambda s: "code" if s["name"].startswith("Code:") else "data" if s["name"].startswith("Data:") else "header"
    return {
        "rom_size": rom_size,
        "rom_used": sum(s["size"] for s in rom),
        "code": sum(s["size"] for s in rom if kind(s) == "code"),
        "data": sum(s["size"] for s in rom if kind(s) == "data"),
        "header": sum(s["size"] for s in rom if kind(s) == "header"),
        "wram": regions.get("WRAM0", 0) + regions.get("WRAMX", 0),
        "hram": regions.get("HRAM", 0),
        "sections": [{"name": s["name"], "size": s["size"]} for s in sections],
    }


def _idle_ranges(labels):
    return [(start, labels[name + "Done"]) for name, start in labels.items()
            if re.search(r"\.wait\w*$", name) and name + "Done" in labels]


def run_profile(rom, labels, cgb, frames=8, presses=(), checkpoints=None):
    """Run the ROM as a Game Boy Color (cgb=True) or original Game Boy and measure it.

    presses: [(first frame, last frame, {"down", ...})] buttons held over a range of frames.
    checkpoints: {name: frame} screens to capture; each shows what was on screen when that frame began.
    Frames are counted from the first VBlank after MainLoop is reached, starting at 0.
    """
    for needed in ("Start", "MainLoop"):
        if needed not in labels:
            raise Unsupported(f"the program has no {needed} label to measure from")
    m = Machine(rom, cgb)
    cpu = m.cpu
    idle = _idle_ranges(labels)
    is_idle = lambda pc: any(a <= pc < b for a, b in idle)
    main_loop = labels["MainLoop"]
    load_entry = labels.get("LoadScene")
    vblank_done = labels.get("VBlankDone")
    checkpoints = dict(checkpoints or {})
    frames = max([frames] + [f + 1 for f in checkpoints.values()] + [b + 1 for _, b, _ in presses])

    # Startup: entry until MainLoop, not counting busy-waits.
    work = 0
    while cpu.pc != main_loop:
        cycles, pc, halted = m.step()
        if not halted and not is_idle(pc):
            work += cycles
        if m.cycles > STARTUP_LIMIT:
            raise Unsupported("startup didn't reach MainLoop within one second")

    # Frames run from one VBlank to the next. VBlank work is the time from the start of VBlank until the
    # program reaches VBlankDone (everything that touches video memory must be done by then). Scene loads
    # run with the screen off, so they're reported on their own instead of as frame time.
    st = {"frame": -1, "busy": [], "vblank": [], "vb_start": None, "load": None, "loads": [], "screens": {}}

    def on_vblank():
        st["frame"] += 1
        f = st["frame"]
        st["busy"].append(0)
        st["vb_start"] = m.cycles
        m.buttons = set().union(*[b for first, last, b in presses if first <= f <= last])
        for name, at in checkpoints.items():
            if at == f:
                st["screens"][name] = (m.render_background(), m.render_background(sprites=False))

    m.vblank_hook = on_vblank
    limit = m.cycles + (frames + 30) * FRAME
    while st["frame"] < frames:
        if cpu.halted and not m.pending_interrupts():
            # Fast-forward an idle HALT to the next scanline (or a timer tick) instead of 4 cycles at a time.
            chunk = 16 if m.io[0x07] & 4 else (456 - m.lcd_dots % 456 if m.lcd_on() else 456)
            m.advance(chunk)
        else:
            if cpu.pc == vblank_done and st["vb_start"] is not None:
                st["vblank"].append(m.cycles - st["vb_start"])
                st["vb_start"] = None
            if cpu.pc == load_entry and st["load"] is None:
                st["load"] = [0, cpu.sp + 2]
            cycles, pc, halted = m.step()
            busy = not halted and not is_idle(pc)
            if st["load"] is not None:
                if busy:
                    st["load"][0] += cycles
                if cpu.sp == st["load"][1] and m.read(pc) in RETURNS:
                    st["loads"].append(st["load"][0])
                    st["load"] = None
            elif st["busy"] and busy:
                st["busy"][-1] += cycles
        if m.cycles > limit:
            raise Unsupported("frames stopped arriving (the screen never reached VBlank)")

    busy = st["busy"][1:frames + 1] or [0]
    return {
        "startup_cycles": work,
        "frame_cycles_max": max(busy),
        "frame_cycles_avg": round(sum(busy) / len(busy)),
        "frame_load": round(max(busy) / FRAME * 100, 2),
        "vblank_work_cycles": max(st["vblank"]) if st["vblank"] else 0,
        "vblank_budget": VBLANK_CYCLES,
        "scene_load_cycles": max(st["loads"]) if st["loads"] else None,
        "violations": m.violations,
        "screens": st["screens"],
        "machine": m,
    }


DEFAULT_SESSION = {"frames": 8, "presses": [], "checkpoints": {"screen": 8}}


def profile(build, session=None):
    """Full report for a Build: bytes plus cycles on both devices, over an optional input session."""
    session = session or DEFAULT_SESSION
    labels = parse_sym(build.sym)
    report = {"bytes": bytes_report(build.map, len(build.rom))}
    dual = build.rom[0x143] & 0x80
    for name, cgb in (("color", True), ("original", False)):
        if name == "color" and not dual:
            continue
        try:
            r = run_profile(build.rom, labels, cgb, session["frames"], session_presses(session), {})
            r.pop("machine")
            r.pop("screens")
            report[name] = r
        except Unsupported as e:
            report[name] = {"error": str(e)}
    return report


def session_presses(session):
    return [(p["frame"], p["frame"] + p.get("hold", 1) - 1, set(p["buttons"])) for p in session.get("presses", [])]


def screens(build, cgb, session=None):
    """Capture the session's checkpoints: {name: (full screen, background only)}, plus the run's report."""
    session = session or DEFAULT_SESSION
    r = run_profile(build.rom, parse_sym(build.sym), cgb, session["frames"], session_presses(session),
                    session["checkpoints"])
    return r["screens"], r
