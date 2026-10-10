"""Golden tests: known projects with their exact expected output.

Each case in tests/golden/<name>/ has:
  project.json     the input
  expected.asm     exact generated assembly
  expected.json    ROM hash, byte and cycle metrics, screen hashes (or the expected validation errors)
  screen-*.png     what each device shows, for humans reviewing a change

Beyond matching the stored results, every case must show exactly what the project says: each pixel's
palette color on Game Boy Color, and its slot's gray on an original Game Boy.
"""

import difflib
import hashlib
import json
import struct
import zlib
from pathlib import Path

from . import codegen, deps, profiler
from .project import CW, W
from .build import build_rom

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "tests" / "golden"
DEVICES = {"color": True, "original": False}
DMG_GRAYS = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]
METRICS = ["startup_cycles", "frame_cycles_max", "vblank_work_cycles", "scene_load_cycles"]


def write_png(path, pixels, w=160, h=144):
    raw = b"".join(b"\0" + bytes(c for p in pixels[y * w:(y + 1) * w] for c in p) for y in range(h))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                          + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def expected_variants(project, scene, frame="normal", values=None):
    """The slot pictures a settled screen may show. A blinking prompt may be either on or off; the
    pressed frame always has the prompt on. values: {OPT_NAME: number or choice index} for options
    that should show something other than their default."""
    s = project["scenes"][scene]
    shown = list(s["composed"])
    if values and s.get("options"):
        from .project import draw_option_value, option_value_cells, using_font
        for r in s["options"]["rows"]:
            if r["symbol"] not in values:
                continue
            v = values[r["symbol"]] - (r["min"] if r["kind"] == "number" else 0)
            base = list(shown)
            for c in option_value_cells(r):
                x0, y0 = (c % CW) * 8, (c // CW) * 8
                for y in range(8):
                    for x in range(8):
                        base[(y0 + y) * W + x0 + x] = s["pixels"][(y0 + y) * W + x0 + x]
            with using_font(project.get("font", "classic")):
                draw_option_value(shown, base, r, v, s["options"]["text_slot"])
    press = s.get("press")
    if frame == "pressed":
        for row in s["area_cells"]:
            for c, _, _ in row:
                x0, y0 = (c % CW) * 8, (c // CW) * 8
                for y in range(8):
                    for x in range(8):
                        i = (y0 + y) * W + x0 + x
                        shown[i] = press["pressed"][i]
        return [shown]
    variants = [shown]
    if press and press["prompt"] and press["prompt"]["blink"]:
        hidden = list(shown)
        for c, _, _ in s["prompt_cells"]:
            x0, y0 = (c % CW) * 8, (c // CW) * 8
            for y in range(8):
                for x in range(8):
                    i = (y0 + y) * W + x0 + x
                    hidden[i] = s["pixels"][i]
        variants.append(hidden)
    return variants


def to_rgb(project, scene, slots, cgb):
    expand = lambda v: (v << 3) | (v >> 2)
    s = project["scenes"][scene]
    if not cgb:
        return [DMG_GRAYS[v] for v in slots]
    return [tuple(expand(c) for c in project["palettes"][s["cell_pal"][(i // W // 8) * CW + (i % W) // 8]][v])
            for i, v in enumerate(slots)]


def expected_pixels(project, cgb, scene=None, frame="normal"):
    """What the background must show, computed straight from the project (text included)."""
    scene = project["start"] if scene is None else scene
    return to_rgb(project, scene, expected_variants(project, scene, frame)[0], cgb)


def screen_hash(pixels):
    return hashlib.sha256(bytes(c for p in pixels for c in p)).hexdigest()


def evaluate(case_dir):
    """Build and measure one case. Returns (results dict, asm or None, screens dict, problems list)."""
    data = json.loads((case_dir / "project.json").read_text())
    session_file = case_dir / "session.json"
    session = json.loads(session_file.read_text()) if session_file.exists() else dict(
        profiler.DEFAULT_SESSION, settled={"screen": None})
    try:
        project = codegen.validate(data)
    except codegen.ProjectError as e:
        return {"errors": e.errors}, None, {}, []
    asm = codegen.generate_asm(project)
    build = build_rom(asm, codegen.rom_title(project["name"]), cgb=True)
    b = profiler.bytes_report(build.map, len(build.rom))
    results = {
        "rom_sha256": hashlib.sha256(build.rom).hexdigest(),
        "bytes": {k: b[k] for k in ("rom_used", "code", "data", "wram", "hram")},
        "cycles": {},
        "screens": {},
    }
    problems, shots = [], {}
    for device, cgb in DEVICES.items():
        try:
            captured, r = profiler.screens(build, cgb, session)
        except profiler.Unsupported as e:
            problems.append(f"{device}: profiler couldn't run it: {e}")
            continue
        results["cycles"][device] = {k: r[k] for k in METRICS if r.get(k) is not None}
        for v in r["violations"]:
            problems.append(f"{device}: hardware rule broken at ${v['pc']:04X}: {v['message']}")
        if r["frame_cycles_max"] > profiler.FRAME:
            problems.append(f"{device}: a frame needs {r['frame_cycles_max']} cycles; only {profiler.FRAME} exist")
        if r["vblank_work_cycles"] > profiler.VBLANK_CYCLES:
            problems.append(f"{device}: VBlank work needs {r['vblank_work_cycles']} cycles; "
                            f"VBlank lasts {profiler.VBLANK_CYCLES}")
        results["screens"][device] = {}
        for name, (full, background) in sorted(captured.items()):
            shots[(device, name)] = full
            results["screens"][device][name] = screen_hash(full)
        for name, spec in session.get("settled", {}).items():
            if name not in captured:
                problems.append(f"{device}: checkpoint {name} was never reached")
                continue
            spec = spec if isinstance(spec, list) else [spec]
            scene, frame, values = (spec + ["normal", None])[:3]
            scene = project["start"] if scene is None else scene
            got = captured[name][1]
            options = [to_rgb(project, scene, v, cgb) for v in expected_variants(project, scene, frame, values)]
            want = next((o for o in options if o == got), options[0])
            if got != want:
                bad = next(i for i, (a, w) in enumerate(zip(got, want)) if a != w)
                count = sum(a != w for a, w in zip(got, want))
                problems.append(f"{device} {name}: background doesn't match the project at x={bad % 160}, "
                                f"y={bad // 160} (shows {got[bad]}, should be {want[bad]}; {count} pixels differ)")
    return results, asm, shots, problems


def _compare(expected, actual, path=""):
    """Readable differences between two nested dicts, with +/- for numbers."""
    diffs = []
    for key in sorted(set(expected) | set(actual)):
        e, a, p = expected.get(key), actual.get(key), f"{path}{key}"
        if isinstance(e, dict) and isinstance(a, dict):
            diffs += _compare(e, a, p + ".")
        elif e != a:
            if isinstance(e, int) and isinstance(a, int):
                diffs.append(f"{p}: {e} → {a} ({a - e:+d})")
            else:
                diffs.append(f"{p}: {str(e)[:70]} → {str(a)[:70]}")
    return diffs


def run(update=False, only=None, log=print):
    cases = sorted(d for d in GOLDEN_DIR.iterdir() if (d / "project.json").exists()) if GOLDEN_DIR.exists() else []
    if only:
        cases = [d for d in cases if d.name in only]
        missing = set(only) - {d.name for d in cases}
        if missing:
            log(f"No such golden case: {', '.join(sorted(missing))}")
            return False
    if not cases:
        log(f"No golden cases in {GOLDEN_DIR}")
        return False
    info = deps.rgbds_info()
    log(f"Golden tests with RGBDS v{info['version']}\n")
    failed = 0
    for case in cases:
        results, asm, screens, problems = evaluate(case)
        exp_json = case / "expected.json"
        exp_asm = case / "expected.asm"
        if update:
            exp_json.write_text(json.dumps(results, indent=2) + "\n")
            if asm is not None:
                exp_asm.write_text(asm)
                for old_png in case.glob("*.png"):
                    old_png.unlink()
                for (device, name), pixels in screens.items():
                    write_png(case / (f"screen-{device}.png" if name == "screen" else f"{name}-{device}.png"), pixels)
            elif exp_asm.exists():
                exp_asm.unlink()
        diffs = list(problems)
        if not update:
            if not exp_json.exists():
                diffs.append("no expected.json yet (run with --update after checking the output)")
            else:
                diffs += _compare(json.loads(exp_json.read_text()), results)
            if asm is not None and exp_asm.exists() and exp_asm.read_text() != asm:
                d = list(difflib.unified_diff(exp_asm.read_text().splitlines(), asm.splitlines(),
                                              "expected.asm", "generated", lineterm="", n=1))
                diffs.append("assembly changed:\n      " + "\n      ".join(d[:40]) + ("\n      ..." if len(d) > 40 else ""))
        summary = _summary(results)
        if diffs:
            failed += 1
            log(f"  ✗ {case.name:16} {summary}")
            for d in diffs:
                log(f"      {d}")
        else:
            log(f"  {'↻' if update else '✓'} {case.name:16} {summary}")
    log("")
    if update:
        log(f"Updated {len(cases)} golden case(s). Review the changes (git diff, screen PNGs) before committing.")
    else:
        log(f"{len(cases) - failed}/{len(cases)} golden case(s) passed.")
    return failed == 0


def _summary(results):
    if "errors" in results:
        return "rejected: " + results["errors"][0][:70]
    c = results["cycles"]
    parts = [f"{results['bytes']['rom_used']} B"]
    for device in ("color", "original"):
        if device in c:
            parts.append(f"{device} startup {c[device]['startup_cycles']:,} cy, frame {c[device]['frame_cycles_max']} cy")
    return " · ".join(parts)
