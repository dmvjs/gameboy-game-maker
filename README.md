# gbstage

A Flash-style editor for making Game Boy games. It generates assembly and builds real `.gb` ROMs with [RGBDS](https://rgbds.gbdev.io).

## Joe vs Mac

Mike Tyson's Punch-Out!! on the Game Boy, built with gbstage: all 14 fights of the NES game, Glass Joe to Mike
Tyson, on Game Boy Color and the original Game Boy.

- **The NES game's own fight logic.** Each opponent's moves, tells, timing and AI run as the NES's do, so the
  patterns you know from the original work here.
- **Every frame as the NES draws it.** Each opponent's and Little Mac's frames are captured from the NES game
  itself and shown as they are, mirrored ones included. On the original Game Boy, each fighter gets his own grey
  shading.
- **The NES's music and sound effects**, played on the Game Boy's own sound channels, and the NES's own recorded
  crowd (its sample, streamed through the wave channel; in the fight on Color with the bass mixed in). Measured
  against the NES rendered by blargg's Nes_Apu (`tools/sound_ab.py`): every channel within about 1 dB of the NES's
  balance and 1 cent of its pitch.
- **The whole game around the fights**: title, challenger screens with the NES's full-size close-ups, the corner
  between rounds (Doc rubbing Mac's shoulder and the rival talking, each at the NES's own pace; Select there, once
  per fight, makes Doc rub faster and gives the NES's refill), knockdowns with the referee's count, TKOs, decisions on points, rematches, dropping down
  the ranks, and game over on the third loss, all by the NES's rules.
- **The NES's pass keys.** Mac's record is kept fight to fight, and the training runs show its pass key, worked out
  by the NES's own algorithm (ported, and checked against the original). Keys from the NES work on CONTINUE: try
  005 737 5423, or 007 373 5963 for Mike Tyson. The NES's secrets too: 135 792 4680 (hold Select as you enter the last
  digit) for the Another World Circuit, and the busy signals (075 541 6113).
- **Checked against real hardware timing.** Every fight runs in SameBoy with no video writes outside the time the
  hardware allows, on both machines. In the test suite, a bot that only presses buttons beats every fighter within
  two rounds, then plays the whole game from power-on to THE END; every opponent frame is compared with what the
  NES draws (`tools/punchout_art/frame_audit.py`).

It's a 4 MB MBC5 cartridge (`joe-vs-mac.gb`) that runs in any Game Boy emulator.

```sh
git clone https://github.com/dmvjs/gameboy-game-maker.git
cd gameboy-game-maker
npm i
npm start
```

`npm start` needs a Mike Tyson's Punch-Out!! (USA) `.nes` file and the Glass Joe and Little Mac sprite sheets (a
`.png` with `joe` / `mac` in its name) in the folder. It builds the ROM and opens the editor with the game loaded:
press **▶ Test** to play. The first build takes a few minutes. No Node? Double-click **Start.command** (Mac) or
**Start.bat** (Windows) instead. You need Python 3.9 or newer.

**Controls** (keyboard in **▶ Test**): **B** (Z) left punch, **A** (X) right punch, **Up** + punch to the face,
**Left/Right** dodge, hold **Down** to block, **Start** (Enter) star punch.

### Every fight, start to knockout

The bot plays each fight on the ROM this repo builds, buttons only, on Game Boy Color and the original Game Boy.
CI renders the videos on every change ([fight-videos.yml](.github/workflows/fight-videos.yml)). Click a preview for
the whole fight with sound, or [watch them all](https://dmvjs.github.io/gameboy-game-maker/).

| | Game Boy Color | Game Boy |
|---|---|---|
| **Great Tiger** | [<img src="https://dmvjs.github.io/gameboy-game-maker/tiger-color.gif" width="320" alt="Great Tiger, Game Boy Color">](https://dmvjs.github.io/gameboy-game-maker/#tiger) | [<img src="https://dmvjs.github.io/gameboy-game-maker/tiger-grey.gif" width="320" alt="Great Tiger, Game Boy">](https://dmvjs.github.io/gameboy-game-maker/#tiger) |
| **Bald Bull** | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull-color.gif" width="320" alt="Bald Bull, Game Boy Color">](https://dmvjs.github.io/gameboy-game-maker/#bull) | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull-grey.gif" width="320" alt="Bald Bull, Game Boy">](https://dmvjs.github.io/gameboy-game-maker/#bull) |
| **Mike Tyson** | [<img src="https://dmvjs.github.io/gameboy-game-maker/tyson-color.gif" width="320" alt="Mike Tyson, Game Boy Color">](https://dmvjs.github.io/gameboy-game-maker/#tyson) | [<img src="https://dmvjs.github.io/gameboy-game-maker/tyson-grey.gif" width="320" alt="Mike Tyson, Game Boy">](https://dmvjs.github.io/gameboy-game-maker/#tyson) |

<details><summary>All 14 fights</summary>

| | Game Boy Color | Game Boy |
|---|---|---|
| Glass Joe | [<img src="https://dmvjs.github.io/gameboy-game-maker/joe-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#joe) | [<img src="https://dmvjs.github.io/gameboy-game-maker/joe-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#joe) |
| Von Kaiser | [<img src="https://dmvjs.github.io/gameboy-game-maker/kaiser-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#kaiser) | [<img src="https://dmvjs.github.io/gameboy-game-maker/kaiser-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#kaiser) |
| Piston Honda | [<img src="https://dmvjs.github.io/gameboy-game-maker/honda-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#honda) | [<img src="https://dmvjs.github.io/gameboy-game-maker/honda-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#honda) |
| Don Flamenco | [<img src="https://dmvjs.github.io/gameboy-game-maker/don-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#don) | [<img src="https://dmvjs.github.io/gameboy-game-maker/don-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#don) |
| King Hippo | [<img src="https://dmvjs.github.io/gameboy-game-maker/hippo-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#hippo) | [<img src="https://dmvjs.github.io/gameboy-game-maker/hippo-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#hippo) |
| Great Tiger | [<img src="https://dmvjs.github.io/gameboy-game-maker/tiger-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#tiger) | [<img src="https://dmvjs.github.io/gameboy-game-maker/tiger-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#tiger) |
| Bald Bull | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#bull) | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#bull) |
| Piston Honda II | [<img src="https://dmvjs.github.io/gameboy-game-maker/honda2-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#honda2) | [<img src="https://dmvjs.github.io/gameboy-game-maker/honda2-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#honda2) |
| Soda Popinski | [<img src="https://dmvjs.github.io/gameboy-game-maker/soda-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#soda) | [<img src="https://dmvjs.github.io/gameboy-game-maker/soda-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#soda) |
| Bald Bull II | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull2-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#bull2) | [<img src="https://dmvjs.github.io/gameboy-game-maker/bull2-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#bull2) |
| Don Flamenco II | [<img src="https://dmvjs.github.io/gameboy-game-maker/don2-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#don2) | [<img src="https://dmvjs.github.io/gameboy-game-maker/don2-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#don2) |
| Mr. Sandman | [<img src="https://dmvjs.github.io/gameboy-game-maker/sandman-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#sandman) | [<img src="https://dmvjs.github.io/gameboy-game-maker/sandman-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#sandman) |
| Super Macho Man | [<img src="https://dmvjs.github.io/gameboy-game-maker/macho-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#macho) | [<img src="https://dmvjs.github.io/gameboy-game-maker/macho-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#macho) |
| Mike Tyson | [<img src="https://dmvjs.github.io/gameboy-game-maker/tyson-color.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#tyson) | [<img src="https://dmvjs.github.io/gameboy-game-maker/tyson-grey.gif" width="160" alt="">](https://dmvjs.github.io/gameboy-game-maker/#tyson) |

</details>

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

**Joe vs Mac** (above) is built from the boxing template (`editor/boxing.js`) and a fighter pack
(`editor/art/mac-vs-joe.js`, made from the NES game by `tools/punchout_art/build.py`). Swap the pack's names, text,
poses and portraits for a new game on the same engine. A fight scene's art comes in and out as sprite sheets:
**Download rival sheet** / **Import rival sheet…** (64x80 frames) and the same for the player (24x48 frames,
transparent background). Importing snaps colors to the hardware and picks the rival's three palettes from the art.
Games larger than 32 KB are built as MBC5 cartridges automatically.

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
