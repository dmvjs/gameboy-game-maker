"""Joe vs Mac: put your Punch-Out!! .nes file and the two sprite sheets in this folder, then run this
(double-click Start.command on a Mac, Start.bat on Windows, or: python3 start.py).

It finds them, builds everything on your machine and opens the editor with the game loaded."""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools" / "punchout_art"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT))


def find(patterns, suffix):
    """A file in this folder (or a subfolder one level down) whose name has any of these words."""
    places = [ROOT] + [p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith((".", "tools", "gbstage", "editor"))]
    for place in places:
        for f in sorted(place.glob(f"*{suffix}")):
            if any(w in f.name.lower() for w in patterns):
                return f


def fail(msg):
    print("\n" + msg)
    input("\nPress Enter to close.")
    sys.exit(1)


def main():
    if sys.version_info < (3, 9):
        fail("This needs Python 3.9 or newer (python.org).")
    import gamefiles

    print("Joe vs Mac\n")
    have_game = (TOOLS / "rom" / "original_files" / "PRG_BankDEF.bin").exists()
    rom = find(["punch", ""], ".nes")
    if rom:
        print("Your game:", rom.name)
        try:
            gamefiles.split_rom(rom)
        except SystemExit as e:
            fail(str(e))
    elif not have_game:
        fail("Put your Mike Tyson's Punch-Out!! (USA) .nes file in this folder, then run this again.")

    src = TOOLS / "sources"
    src.mkdir(exist_ok=True)
    for words, name in ((["joe"], "glass-joe.png"), (["mac"], "little-mac.png")):
        sheet = find(words, ".png")
        if sheet and sheet.resolve() != (src / name).resolve():
            shutil.copy(sheet, src / name)
            print("Sprite sheet:", sheet.name)
        if not (src / name).exists():
            fail(f"Put the {'Glass Joe' if 'joe' in name else 'Little Mac'} sprite sheet (a .png with "
                 f"'{words[0]}' in its name) in this folder, then run this again.")

    pack = ROOT / "editor" / "art" / "mac-vs-joe.js"
    inputs = [*(src).glob("*.png"), TOOLS / "rom" / "original_files" / "PRG_BankDEF.bin"]
    if not pack.exists() or any(f.stat().st_mtime > pack.stat().st_mtime for f in inputs if f.exists()):
        print("\nBuilding (the first time takes a few minutes: it plays the NES game in an emulator to draw it)...")
        r = subprocess.run([sys.executable, str(TOOLS / "build.py")], cwd=ROOT)
        if r.returncode:
            fail("The build stopped (see above).")

    from gbstage import deps
    if not deps.rgbds_info().get("found"):
        print("\nInstalling the Game Boy assembler (RGBDS)...")
        subprocess.run([sys.executable, "-m", "gbstage", "install", "rgbds"], cwd=ROOT)
    example = ROOT / "examples" / "joe-vs-mac.gbstage.json"
    if example.exists():
        subprocess.run([sys.executable, "-m", "gbstage", "build", str(example), "-o", str(ROOT / "joe-vs-mac.gb")],
                       cwd=ROOT, capture_output=True)
        if (ROOT / "joe-vs-mac.gb").exists():
            print("\njoe-vs-mac.gb is ready (it plays in any Game Boy emulator).")

    if "--no-editor" in sys.argv:
        return
    print("\nOpening the editor with Joe vs Mac. Press ▶ Test to play. (Close this window to stop.)")
    from gbstage.server import serve
    serve(page="?sample=mac-vs-joe")


if __name__ == "__main__":
    main()
