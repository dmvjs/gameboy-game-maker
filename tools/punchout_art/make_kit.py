"""A zip of this project for someone to run the Joe vs Mac demo with their own copy of Punch-Out!!: all the
code (editor, gbstage, the tools here), none of Nintendo's data (the ROM's banks, the sprite sheets, anything
built from them). They unzip it, put their Punch-Out!! .nes and the two sprite sheets in the folder, and double-click Start.

    python3 tools/punchout_art/make_kit.py      -> joe-vs-mac-kit.zip"""
import subprocess, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Nintendo's data and what's made from it: never in the kit.
LEAVE_OUT = ("tools/punchout_art/rom/", "tools/punchout_art/sources/", "tools/punchout_art/out/",
             "editor/art/mac-vs-joe.js", "examples/joe-vs-mac.gbstage.json", "joe-vs-mac.gb")


def files():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.split()
    tools = [str(p.relative_to(ROOT)) for p in (ROOT / "tools" / "punchout_art").glob("*.py")] + \
            [str(p.relative_to(ROOT)) for p in (ROOT / "tools" / "punchout_art").glob("*.mjs")] + \
            [str(p.relative_to(ROOT)) for p in (ROOT / "editor").glob("mac-vs-joe.js")]
    for f in sorted(set(tracked + untracked + tools)):
        p = ROOT / f
        if p.is_file() and not f.startswith(LEAVE_OUT) and p.suffix.lower() not in (".gif", ".nes", ".gb", ".gbc"):
            yield f


if __name__ == "__main__":
    out = ROOT / "joe-vs-mac-kit.zip"
    names = list(files())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in names:
            z.write(ROOT / f, f"gameboy-game-maker/{f}")
    print(f"{out.name}: {len(names)} files, {out.stat().st_size // 1024} KB (no ROM data, no sprite sheets)")
