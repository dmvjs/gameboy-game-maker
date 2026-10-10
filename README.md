# gbstage

A Flash-style editor for making Game Boy games. It generates assembly and builds real `.gb` ROMs with [RGBDS](https://rgbds.gbdev.io).

## Getting started

You need Python 3.9 or newer. Nothing else is required up front.

```sh
python3 -m gbstage install    # downloads RGBDS and the browser emulator, verifying checksums
python3 -m gbstage doctor     # checks that everything is hooked up
python3 -m gbstage serve      # opens the editor at http://localhost:8765
```

In the editor, the top bar shows the RGBDS version and emulator in use. Click **System check** to rerun every
check, including booting a test ROM in the browser emulator. Problems come with a fix, and missing pieces can be
installed from there.

## Templates and scenes

**New** offers three starting points, all tuned and working out of the box:

- **Press Start** (the default for a first project): title art with a blinking PRESS START. Pressing Start
  flashes a **flash area** you choose, then fades into the game. Draw the area on the stage (up to 80 tiles, so it
  always changes within one frame) and paint its **Pressed** frame with the Normal / Pressed switch above the stage.
  In the Pressed frame only the area can change, and every tile keeps its palette, so it can't break the rules.
- **Title + Options**: a menu with a cursor sprite that slides and bobs, the chosen item blinking, fades, two
  scenes to go to, and B to come back.
- **Blank**: one empty scene.

Under **Examples**, **Capsule Clinic** is a complete, playable falling-capsule puzzle game: title menu, settings
(virus level, speed), playfield, how to play, and win / game over screens.

**Joe vs Mac** is a boxing game against one scripted rival, seen from behind the player: guard switching,
counters, star punches, a timed taunt and charge, knockdowns with a referee's count, three rounds with a corner
scene between them (Select there for a once-per-match refill), and a decision on points. It's built from the boxing
template (`editor/boxing.js`) and a fighter pack: swap the pack's names, text, poses and portraits for a new game on
the same engine. Its art is Little Mac and Glass Joe from Punch-Out!! (NES), so it stays on this machine
(`tools/punchout_art/build.py` makes it; `.git/info/exclude` keeps it out of git). The rival's poses swap in and
out of video memory in sets (attack, knockdown, special) so he can have more of them than fit at once. Its fight
scene's art comes in and out as sprite sheets: **Download rival sheet** / **Import rival sheet…** (64x80 frames)
and the same for the player (24x48 frames, transparent background). Importing snaps colors to the hardware and picks
the rival's three palettes from the art. Games larger than 32 KB are built as MBC5 cartridges automatically.

Scenes are listed in the side panel. ★ marks where the game starts. A scene can have a menu, an options screen
(choices, numbers, sliders), a press-start prompt or a puzzle grid, and can send B back to another scene. Scenes nothing leads to are tagged "not reachable" and left out
of the ROM. Text (menu labels, prompts) uses the built-in font (`gbstage/font.txt`) in one palette slot, so it
always follows the one-palette-per-tile rule.

In **▶ Test**: arrows = d-pad, X = A, Z = B, Enter = Start, Shift = Select. **Sound** toggles audio.

Sound effects are built in and on by default: menu moves, confirm, back, option changes, Start, and in the puzzle
moving, rotating, landing, clears (rising with each chain step), virus pops, and win / lose. They play on the
Game Boy's own sound channels. Music is not supported yet.

The generated engine includes only what a project uses. Interrupts stay off: HALT wakes at VBlank and that
frame's video work runs straight away, with no handler. Changes to the tile map (blinks, flashes) are
generated as unrolled routines for their exact shape.

## Painting with color

Projects are **dual mode**: full color on a Game Boy Color, automatic grayscale on an original Game Boy.
The editor enforces the hardware rules as you work, so anything you can draw will build:

- You paint with **palette slots**, not loose colors. Change a palette color and everything using it updates.
- Each 8×8 tile uses one palette (up to 8 background palettes). Painting a different palette's color into a tile
  moves the tile to that palette when that doesn't change how it looks, or claims the tile if it's empty.
  Otherwise the tile is highlighted and the status bar explains what to do. Hold **Alt (⌥)** to repaint the tile anyway.
- The color picker only offers colors the hardware can show (32 levels per channel).
- Every palette must go lightest to darkest so it reads correctly in grayscale. If one doesn't, it's flagged and
  **Fix order** sorts it without changing your picture.
- **Game Boy Color / Color screen / Original Game Boy** switch the stage between what each device shows.
  "Color screen" simulates the Game Boy Color's darker, less saturated display.
- Meters track palettes (8 max) and unique tiles (256 max; repeated 8×8 patterns are free).
- **▶ Test** (⌘/Ctrl+Enter) builds the ROM and runs it in the emulator as either device. **Export .gb** downloads it.

| Key | Action |
|---|---|
| B / E / G / I / T | Pencil, eraser, fill, eyedropper, tile palette |
| Right-click | Eyedropper with any tool |
| 1–4 | Choose slot in the current palette |
| [ / ] | Previous / next palette |
| ⌘Z / ⇧⌘Z | Undo / redo |

Your work autosaves in the browser. **Save** downloads a `.gbstage.json` project file, and **Open** loads one.

## Measuring the output

Every build is run through gbstage's own cycle-exact Game Boy CPU emulator (`gbstage/sm83.py`), which reports:

- **ROM and RAM bytes**, split into code and data, from the linker map.
- **Startup work**: cycles from power-on to the main loop, not counting busy-waits for the screen.
- **Per-frame CPU**: cycles used out of the 70,224 in each frame, on both Game Boy Color and original.
- **VBlank work**: cycles used out of the 4,560 when video memory can be updated.
- **Scene loads**: cycles to load a scene with the screen off.
- **Hardware-rule violations** that fail silently on real hardware, like writing video memory while the screen draws.

The editor shows ROM and CPU meters that update a moment after each edit, and the full report in **▶ Test**.
From the terminal, `python3 -m gbstage build my-game.gbstage.json` builds a ROM and prints the same report.

If a program uses hardware the emulator doesn't model yet, it reports "not measured" and never guesses.
The CPU passes all of Blargg's `cpu_instrs` and `instr_timing` tests, and its cycle counts match PyBoy exactly.

## Golden tests

`tests/golden/` holds known projects with their exact expected assembly, ROM hash, byte and cycle counts, and
screen images. Every case's screen must also match the project pixel for pixel on both devices.

```sh
python3 -m gbstage test                      # run all golden cases and the puzzle and fight kit checks
python3 -m gbstage test --update             # accept new output after reviewing it (check the git diff and PNGs)
python3 -m gbstage test --cpu-roms DIR       # also run Blargg's test ROMs (from github.com/retrio/gb-test-roms)
```

Any change to generated code shows up as a precise difference, such as `cycles.color.startup_cycles: 35216 → 35220 (+4)`,
with the assembly diff.

## Dependencies

gbstage doesn't bundle its dependencies. They're installed per user in `~/.gbstage` (override with `GBSTAGE_HOME`).

| Dependency | Version policy |
|---|---|
| RGBDS | Supported: `>=0.9.0, <2.0.0`. Tested: 0.9.4, 1.0.4. Recommended: 1.0.4. Downloads are checked against the SHA-256 that GitHub publishes. |
| binjgb (browser emulator) | Pinned to commit `4fd2ad0`. Every file is checked against a pinned SHA-256. |

RGBDS is looked up in this order:

1. `GBSTAGE_RGBDS` environment variable (a directory containing `rgbasm`, `rgblink`, `rgbfix`)
2. `python3 -m gbstage use rgbds --path DIR` (your own build or package-manager install)
3. `python3 -m gbstage use rgbds 1.0.4` (a specific managed install)
4. The newest supported managed install
5. Your `PATH`

Other commands:

```sh
python3 -m gbstage install rgbds --version latest   # newest release in the supported range
python3 -m gbstage versions                         # installed versions and which one is active
python3 -m gbstage use rgbds --auto                 # back to automatic detection
```

`doctor` exits with code 1 if anything is broken, so it also works in scripts and CI.
