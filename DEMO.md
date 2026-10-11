# Joe vs Mac

1. Get the project: `git clone git@github.com:dmvjs/gameboy-game-maker.git` (or download it as a zip).
2. Put these three files in it (next to `Start.command`):
   - your **Mike Tyson's Punch-Out!! (USA)** `.nes` file
   - the **Glass Joe** sprite sheet (a `.png` with "joe" in its name)
   - the **Little Mac** sprite sheet (a `.png` with "mac" in its name)
3. Double-click **Start.command** (Mac) or **Start.bat** (Windows).

The first time takes a few minutes. Then the editor opens with the game loaded: press **▶ Test** to play.
You also get `joe-vs-mac.gb`, which plays in any Game Boy emulator.

Controls: arrows move, **X** right punch, **Z** left punch, **Up + punch** to the face, **Enter** star punch.

You need Python 3.9 or newer (Macs have it; on Windows get it from python.org). On Windows or Linux, also
install Node.js (nodejs.org) to get the `.gb` file; the editor works without it.

The repo has no Nintendo data in it: everything is built on your machine from the game file you add.
Those files and what's built from them are git-ignored, so they never get committed.

## Quick start

```
git clone --recursive git@github.com:dmvjs/gameboy-game-maker.git
```

Then double-click **Start.command** (Mac) or **Start.bat** (Windows) and press **▶ Test**.
