"""gbstage command line.

  python3 -m gbstage install [rgbds|emulator] [--version X]   install dependencies
  python3 -m gbstage doctor                                  check everything is hooked up
  python3 -m gbstage versions                                show installed RGBDS versions
  python3 -m gbstage use rgbds <version> | --path DIR | --auto
  python3 -m gbstage serve [--port N]                        start the editor
  python3 -m gbstage build PROJECT [-o OUT.gb] [--asm FILE]  build a project file and measure it
  python3 -m gbstage test [--update] [CASE...] [--cpu-roms DIR]  run the golden (and CPU) tests
"""

import argparse
import sys

from . import __version__, deps, doctor
from .install import InstallError, install_all, install_emulator, install_rgbds, use_rgbds

COLOR = sys.stdout.isatty()
MARKS = {"ok": ("✓", "32"), "warn": ("!", "33"), "error": ("✗", "31"), "skipped": ("-", "90")}


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def cmd_doctor(args):
    print(f"gbstage {__version__} doctor\n")
    checks = doctor.run_checks()
    for c in checks:
        mark, code = MARKS[c["status"]]
        lines = c["detail"].splitlines() or [""]
        print(f"  {paint(mark, code)} {c['label']:<15} {lines[0]}")
        for line in lines[1:]:
            print(f"    {'':<15} {line}")
        if c["fix"]:
            print(f"    {'':<15} {paint('fix: ' + c['fix'], code)}")
    result = doctor.overall(checks)
    print()
    if result == "ok":
        print(paint("All checks passed.", "32") + " The emulator itself runs in the browser: open the editor and click System check.")
    elif result == "warn":
        print(paint("Working, with warnings.", "33"))
    else:
        print(paint("Problems found. Run the fix commands above, then run doctor again.", "31"))
    return 1 if result == "error" else 0


def cmd_install(args):
    if args.what == "rgbds":
        install_rgbds(version=args.version, allow_unverified=args.allow_unverified)
    elif args.what == "emulator":
        install_emulator()
    else:
        if args.version:
            install_rgbds(version=args.version, allow_unverified=args.allow_unverified)
        install_all()
    print("\nNext: python3 -m gbstage doctor")
    return 0


def cmd_use(args):
    if args.auto:
        use_rgbds()
    elif args.path:
        use_rgbds(path=args.path)
    elif args.version:
        use_rgbds(version=args.version)
    else:
        print("Give a version, --path DIR, or --auto", file=sys.stderr)
        return 2
    return 0


def cmd_versions(args):
    info = deps.rgbds_info()
    active = info["version"] if info["found"] else None
    print(f"Supported RGBDS: {deps.supported_range_text()}   tested: {', '.join(deps.RGBDS_TESTED)}\n")
    installed = deps.managed_rgbds_versions()
    if installed:
        print(f"Installed in {deps.home() / 'rgbds'}:")
        for v in installed:
            mark = " (active)" if info["dir"] == str(deps.managed_rgbds_dir(v)) else ""
            print(f"  v{v}{mark}")
    else:
        print("No managed RGBDS installs.")
    print(f"\nActive: v{active} from {info['source']}" if active else f"\nActive: none ({info['error']})")
    return 0


def print_report(report):
    b = report["bytes"]
    print(f"  ROM    {b['rom_used']:,} of {b['rom_size']:,} bytes  (code {b['code']:,}, data {b['data']:,}, header {b['header']})")
    print(f"  RAM    {b['wram']} bytes WRAM, {b['hram']} bytes HRAM")
    for device in ("color", "original"):
        r = report.get(device)
        if not r:
            continue
        label = "Game Boy Color" if device == "color" else "Original"
        if "error" in r:
            print(f"  {label}: {paint('not measured: ' + r['error'], '33')}")
            continue
        print(f"  {label}:")
        print(f"    startup work    {r['startup_cycles']:,} cycles ({r['startup_cycles'] / 4194.304:.1f} ms)")
        print(f"    per frame       {r['frame_cycles_max']:,} of 70,224 cycles ({r['frame_load']}%)")
        print(f"    VBlank work     {r['vblank_work_cycles']:,} of {r['vblank_budget']:,} cycles")
        if r.get("scene_load_cycles"):
            print(f"    scene load      {r['scene_load_cycles']:,} cycles ({r['scene_load_cycles'] / 4194.304:.1f} ms, screen off)")
        for v in r["violations"]:
            print("    " + paint(f"✗ ${v['pc']:04X}: {v['message']}", "31"))


def cmd_build(args):
    import json
    from pathlib import Path
    from . import codegen, profiler
    from .build import BuildError, build_rom
    path = Path(args.project)
    try:
        project = codegen.validate(json.loads(path.read_text()))
        asm = codegen.generate_asm(project)
        build = build_rom(asm, codegen.rom_title(project["name"]), cgb=True)
    except codegen.ProjectError as e:
        for err in e.errors:
            print(paint("error: " + err, "31"), file=sys.stderr)
        return 1
    except BuildError as e:
        print(paint(f"error: {e.step} failed:\n{e.output}", "31"), file=sys.stderr)
        return 1
    out = Path(args.output or path.with_suffix("").with_suffix(".gb"))
    out.write_bytes(build.rom)
    if args.asm:
        Path(args.asm).write_text(asm)
    print(f"Built {out}")
    print_report(profiler.profile(build, codegen.auto_session(project)))
    return 0


def cmd_test(args):
    from . import goldens
    ok = goldens.run(update=args.update, only=args.cases)
    if not args.cases:
        from . import kittests
        print()
        ok = kittests.run() and ok
        from . import nestests
        print("\nNES opponent engine (the Game Boy port against the original code)\n")
        ok = nestests.run() and ok
    if args.cpu_roms:
        from . import cputests
        print()
        ok = cputests.run(args.cpu_roms) and ok
    return 0 if ok else 1


def cmd_serve(args):
    from .server import serve
    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="gbstage", description="Flash-style Game Boy game editor")
    p.add_argument("--version", action="version", version=f"gbstage {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check that RGBDS and the emulator are hooked up").set_defaults(fn=cmd_doctor)

    i = sub.add_parser("install", help="install RGBDS and/or the emulator")
    i.add_argument("what", nargs="?", choices=["rgbds", "emulator"], help="default: whatever is missing")
    i.add_argument("--version", help=f"RGBDS version (default {deps.RGBDS_RECOMMENDED}; 'latest' for newest supported)")
    i.add_argument("--allow-unverified", action="store_true", help="allow releases without a published checksum")
    i.set_defaults(fn=cmd_install)

    u = sub.add_parser("use", help="choose which RGBDS to use")
    u.add_argument("tool", choices=["rgbds"])
    u.add_argument("version", nargs="?")
    u.add_argument("--path", help="directory containing your own rgbasm/rgblink/rgbfix")
    u.add_argument("--auto", action="store_true", help="go back to automatic detection")
    u.set_defaults(fn=cmd_use)

    sub.add_parser("versions", help="list installed RGBDS versions").set_defaults(fn=cmd_versions)

    s = sub.add_parser("serve", help="start the editor")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)

    b = sub.add_parser("build", help="build a .gbstage.json project into a ROM and measure it")
    b.add_argument("project")
    b.add_argument("-o", "--output", help="ROM path (default: next to the project)")
    b.add_argument("--asm", help="also write the generated assembly here")
    b.set_defaults(fn=cmd_build)

    t = sub.add_parser("test", help="run the golden tests")
    t.add_argument("cases", nargs="*", help="only these cases")
    t.add_argument("--update", action="store_true", help="accept current output as the new expected results")
    t.add_argument("--cpu-roms", metavar="DIR", help="also run Blargg's CPU test ROMs from DIR against the profiler's CPU")
    t.set_defaults(fn=cmd_test)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (InstallError, RuntimeError) as e:
        print(paint(f"error: {e}", "31"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
