"""Joe vs Mac from your own copy of Punch-Out!!, in one command:

    python3 tools/punchout_art/demo.py --rom "Mike Tyson's Punch-Out!! (USA).nes" \\
        --joe-sheet glass-joe.png --mac-sheet little-mac.png

It checks the ROM is the version the port matches, splits it into the banks the tools read (rom/), takes the
two sprite sheets, builds the art pack and the example project, builds joe-vs-mac.gb, and runs the checks that
the Game Boy's engine matches the NES game. Then: python3 -m gbstage serve, and New > Examples > Joe vs Mac.
Nothing it writes leaves your machine; none of it goes in git (.git/info/exclude)."""
import argparse, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def step(msg):
    print(f"\n== {msg}")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--rom", type=Path, help="your Mike Tyson's Punch-Out!! (USA) .nes file")
    a.add_argument("--joe-sheet", type=Path, help="the Glass Joe sprite sheet (glass-joe.png)")
    a.add_argument("--mac-sheet", type=Path, help="the Little Mac sprite sheet (little-mac.png)")
    a.add_argument("--skip-tests", action="store_true", help="don't run the NES comparison tests (a few minutes)")
    args = a.parse_args()
    sys.path.insert(0, str(HERE))
    import gamefiles

    step("Python and RGBDS")
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 or newer is needed.")
    r = subprocess.run([sys.executable, "-m", "gbstage", "doctor"], cwd=ROOT, capture_output=True, text=True)
    if "RGBDS" in r.stdout and ("not found" in r.stdout.lower() or r.returncode):
        print("Installing RGBDS (the Game Boy assembler)...")
        subprocess.run([sys.executable, "-m", "gbstage", "install", "rgbds"], cwd=ROOT, check=True)
    print("ok")

    step("Your copy of the game")
    if args.rom:
        print("ROM checked and split into", gamefiles.split_rom(args.rom))
    else:
        print("using", gamefiles.banks())

    step("The sprite sheets")
    src = HERE / "sources"
    src.mkdir(exist_ok=True)
    for sheet, name in ((args.joe_sheet, "glass-joe.png"), (args.mac_sheet, "little-mac.png")):
        if sheet:
            shutil.copy(sheet, src / name)
        if not (src / name).exists():
            sys.exit(f"Missing {name}: pass it with --{'joe' if 'joe' in name else 'mac'}-sheet.")
    print("ok")

    step("The art pack and the example project")
    subprocess.run([sys.executable, str(HERE / "build.py")], cwd=ROOT, check=True)

    step("The ROM")
    rom = ROOT / "joe-vs-mac.gb"
    subprocess.run([sys.executable, "-m", "gbstage", "build", "examples/joe-vs-mac.gbstage.json", "-o", str(rom)],
                   cwd=ROOT, check=True)

    if not args.skip_tests:
        step("Checks: the Game Boy engine against the NES game's own code, byte for byte")
        subprocess.run([sys.executable, "-m", "gbstage", "test"], cwd=ROOT, check=True)

    print(f"""
Done. {rom.name} plays in any Game Boy (Color) emulator. To work on it in the editor:
    python3 -m gbstage serve
then New > Examples > Joe vs Mac.""")


if __name__ == "__main__":
    main()
