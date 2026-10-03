// Example projects, drawn with the same model functions the editor uses, so they follow every rule.

import * as M from './model.js';

const pal = (name, colors) => ({ name, colors });

function fillRect(layer, x, y, w, h, slot) {
  for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) {
    if (i >= 0 && j >= 0 && i < M.W && j < M.H) layer.pixels[j * M.W + i] = slot;
  }
}

// A box with a 2-pixel border, in pixels.
function box(layer, x, y, w, h, fill, border) {
  fillRect(layer, x, y, w, h, border);
  fillRect(layer, x + 2, y + 2, w - 4, h - 4, fill);
}

function checker(layer, a, b, size = 4) {
  for (let y = 0; y < M.H; y++) for (let x = 0; x < M.W; x++) {
    layer.pixels[y * M.W + x] = ((x / size | 0) + (y / size | 0)) % 2 ? a : b;
  }
}

function cellPalettes(scene, cx, cy, cw, ch, palette) {
  for (let y = cy; y < cy + ch; y++) for (let x = cx; x < cx + cw; x++) scene.cellPal[y * M.CW + x] = palette;
}

// 8x8 art from strings: '.' keeps the pixel, digits are slots.
function stamp(layer, x0, y0, rows) {
  rows.forEach((row, y) => [...row].forEach((ch, x) => {
    if (ch !== '.') layer.pixels[(y0 + y) * M.W + x0 + x] = +ch;
  }));
}

const VIRUS = (s) => [
  `..${s}${s}${s}${s}..`,
  `.${s}${s}${s}${s}${s}${s}.`,
  `${s}${s}0${s}${s}0${s}${s}`,
  `${s}${s}0${s}${s}0${s}${s}`,
  `${s}${s}${s}${s}${s}${s}${s}${s}`,
  `.${s}${s}00${s}${s}.`,
  `${s}.${s}${s}${s}${s}.${s}`,
  `.${s}....${s}.`,
];
const PILL_LEFT = (s) => [`........`, `..${s}${s}${s}${s}${s}${s}`, `.${s}0${s}${s}${s}${s}${s}`, `.${s}${s}${s}${s}${s}${s}${s}`,
  `.${s}${s}${s}${s}${s}${s}${s}`, `..${s}${s}${s}${s}${s}${s}`, `........`, `........`];
const PILL_RIGHT = (s) => [`........`, `${s}${s}${s}${s}${s}${s}..`, `${s}${s}${s}${s}${s}0${s}.`, `${s}${s}${s}${s}${s}${s}${s}.`,
  `${s}${s}${s}${s}${s}${s}${s}.`, `${s}${s}${s}${s}${s}${s}..`, `........`, `........`];

// How each scene is built, shown in the editor so the sample can be taken apart.
const NOTES = {
  'Title': `A menu scene: the labels and the cursor are added by the ROM, so they're outlined, not painted.
• "CLINIC" is red because those tiles use the Pills palette. Turn on "Tile palettes" to see which tiles use which. Pills slot 1 is the same cream as Clinic slot 1, so the panel looks seamless.
• The checkerboard is one tile repeated over and over. Repeats are free: the whole screen is 65 unique tiles.
• Try it: rename a menu item, or point it at another scene. Then check the Original Game Boy view: the red becomes a gray that still reads.`,
  'Settings': `An options screen: up/down picks a row, left/right changes it (hold to repeat), Start or A goes to the Playfield, B goes back.
• The ROM draws the labels and values; the chosen word is shown inverted. Every value's tiles are precomputed, so a change is one small patch during VBlank.
• VIRUS LEVEL is a number from 0 to 20 with a slider: the marker is a sprite sliding along the bar you painted.
• The values stay in RAM between scenes, as OPT_VIRUS_LEVEL, OPT_SPEED and OPT_MUSIC, ready for gameplay to read.`,
  'Playfield': `A puzzle grid: the game itself. Arrows move, A and B rotate, Down drops faster. Line up 4 of a color to clear them; clear every virus to win.
• The bottle's inside is the 8x16 grid. Each cell is one tile, picked from the shapes (virus, pill halves, pop) in one of 3 colors.
• The colors are slots 1-3 of the Pills palette, so they stay apart in gray on the original Game Boy (light, mid, dark); slot 4 is the background.
• Speed and level come from the Settings screen (OPT_SPEED, OPT_VIRUS_LEVEL). Winning goes to "Stage clear", topping out goes to "Game over".
• The ROM redraws only the rows that changed, during VBlank, so moving a capsule costs a few hundred cycles.`,
  'Stage clear': `A press-start screen with no flash area: the prompt blinks and Start goes back to Settings for the next round.`,
  'Game over': `A press-start screen with no flash area: Start goes back to the Title.`,
  'How to play': `Plain text drawn into the background with the built-in font, at 11-pixel line spacing instead of the 8-pixel tile grid.
• Text that isn't tile-aligned costs more unique tiles (110 here) but reads better. Still far under the 256 limit.
• B goes back to the Title (set under "B button goes to").`,
};

// Bump when the sample changes, so editors holding an older copy offer the new one.
export const CLINIC_VERSION = 3;

// Capsule Clinic: the screens of a falling-pill puzzle game. Title with a menu, a settings screen
// where Start begins, the playfield, and a how-to-play page.
export function capsuleClinic() {
  const p = {
    name: 'Capsule Clinic',
    palettes: [
      pal('Clinic', [[31, 31, 28], [22, 26, 22], [10, 16, 12], [2, 5, 4]]),
      pal('Pills', [[20, 31, 31], [31, 24, 6], [28, 6, 6], [1, 3, 10]]),   // the 3 capsule colors + the bottle's dark blue
      pal('Glass', [[26, 31, 31], [14, 24, 30], [4, 12, 22], [1, 3, 10]]),
      pal('Logo', [[31, 31, 28], [22, 26, 22], [28, 6, 6], [2, 5, 4]]),
    ],
    objPalettes: [], cursor: null,
    scenes: ['Title', 'Settings', 'Playfield', 'How to play', 'Stage clear', 'Game over'].map(name => ({
      name, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH),
      menu: null, pressStart: null, pressed: null, options: null, puzzle: null, back: null, notes: NOTES[name],
    })),
    start: 0,
    transition: { color: 'white', frames: 3 },
    sample: { id: 'capsule-clinic', version: CLINIC_VERSION },
  };
  M.ensureMenuSupport(p);
  const [title, settings, field, howto, clear, over] = p.scenes.map((_, i) => M.layerOf(p, i));

  // ---- Title ----
  checker(title, 1, 2);
  box(title, 16, 14, 128, 52, 0, 3);
  M.drawText(title, 'CAPSULE', 24, 20, 3, 2);
  M.drawText(title, 'CLINIC', 33, 41, 3, 2);
  M.drawText(title, 'CLINIC', 32, 40, 2, 2);
  cellPalettes(p.scenes[0], 4, 5, 13, 2, 3);          // "CLINIC" in red: the Logo palette (its shadow included)
  box(title, 24, 76, 128, 44, 0, 3);
  fillRect(title, 0, 128, 160, 8, 0);
  M.drawText(title, '(C) 2026 YOU', 32, 128, 3);
  p.scenes[0].menu = {
    x: 5, y: 11, spacing: 2, textSlot: 3, cursorAnimation: 'bob', blinks: 3,
    items: [{ label: '1 PLAYER GAME', target: 1 }, { label: 'HOW TO PLAY', target: 3 }],
  };

  // ---- Settings: an options screen ----
  checker(settings, 1, 2);
  box(settings, 4, 8, 152, 128, 0, 3);
  M.drawText(settings, '1 PLAYER GAME', 28, 16, 2);
  fillRect(settings, 24, 51, 112, 2, 2);                    // the level bar: the marker sprite slides along it
  for (let k = 0; k <= 20; k += 5) fillRect(settings, 24 + Math.round(k * 5.5), 48, 2, 8, 2);
  M.drawText(settings, 'START: PLAY', 36, 120, 2);
  const s1 = p.scenes[1];
  s1.options = {
    target: 2, textSlot: 3,
    rows: [
      { label: 'VIRUS LEVEL', kind: 'number', min: 0, max: 20, digits: 2, value: 5,
        labelX: 3, labelY: 4, valueX: 16, valueY: 4, slider: { x0: 21, x1: 131, y: 48 } },
      { label: 'SPEED', kind: 'choice', choices: ['LOW', 'MED', 'HI'], value: 1, labelX: 3, labelY: 9, valueX: 9, valueY: 9 },
      { label: 'MUSIC', kind: 'choice', choices: ['A', 'B', 'OFF'], value: 0, labelX: 3, labelY: 12, valueX: 9, valueY: 12 },
    ],
  };
  s1.back = 0;

  // ---- Playfield: the puzzle grid ----
  checker(field, 1, 2);
  const f = p.scenes[2];
  // The bottle: walls in Glass, the 8x16-cell inside in Pills (the same dark blue in both).
  cellPalettes(f, 2, 0, 10, 18, 2);
  cellPalettes(f, 3, 1, 8, 16, 1);
  fillRect(field, 16, 0, 80, 144, 0);
  fillRect(field, 21, 5, 70, 139, 1);
  fillRect(field, 23, 7, 66, 137, 2);
  fillRect(field, 24, 8, 64, 128, 3);
  fillRect(field, 40, 0, 32, 8, 3);                         // the neck
  fillRect(field, 38, 0, 2, 8, 1);
  fillRect(field, 72, 0, 2, 8, 1);
  fillRect(field, 24, 136, 64, 8, 2);
  // Panels on the right; the ROM writes the numbers and the next capsule.
  box(field, 96, 8, 64, 32, 0, 3);
  M.drawText(field, 'SCORE', 104, 12, 3);
  box(field, 96, 48, 64, 32, 0, 3);
  M.drawText(field, 'NEXT', 104, 52, 3);
  fillRect(field, 118, 62, 20, 12, 3);                      // a dark window for the next capsule
  box(field, 96, 88, 64, 48, 0, 3);
  M.drawText(field, 'LEVEL', 104, 94, 3);
  M.drawText(field, 'VIRUS', 104, 112, 3);
  f.puzzle = {
    grid: { x: 3, y: 1, w: 8, h: 16 }, palette: 1, textSlot: 3,
    next: { x: 15, y: 8 }, score: { x: 13, y: 3 }, level: { x: 17, y: 13 }, virusCount: { x: 17, y: 15 },
    speedOption: 'OPT_SPEED', levelOption: 'OPT_VIRUS_LEVEL', win: 4, lose: 5,
    shapes: { ...M.DEFAULT_PUZZLE_SHAPES },
  };
  M.applyPuzzlePalette(f);

  // ---- How to play ----
  checker(howto, 1, 2);
  box(howto, 8, 0, 144, 144, 0, 3);
  M.drawText(howto, 'HOW TO PLAY', 36, 10, 2);
  fillRect(howto, 24, 22, 112, 1, 1);
  // 11-pixel line spacing, with a gap between paragraphs.
  const lines = [[30, 'LINE UP 4 OF'], [41, 'ONE COLOR TO'], [52, 'CLEAR THEM.'],
                 [70, 'CLEAR EVERY'], [81, 'VIRUS TO WIN!'],
                 [99, 'ARROWS: MOVE'], [110, 'A / B: TURN']];
  for (const [y, text] of lines) M.drawText(howto, text, 24, y, 3);
  M.drawText(howto, 'B: BACK', 52, 128, 2);
  p.scenes[3].back = 0;

  // ---- Stage clear and Game over: press-start screens ----
  for (const [layer, scene, text, x, target] of [[clear, p.scenes[4], 'CLEAR!', 32, 1], [over, p.scenes[5], 'GAME OVER', 8, 0]]) {
    checker(layer, 1, 2);
    box(layer, 4, 32, 152, 72, 0, 3);
    M.drawText(layer, text, x + 1, 49, 1, 2);
    M.drawText(layer, text, x, 48, 3, 2);
    scene.pressStart = { target, flashes: 1, area: null, prompt: { label: 'PRESS START', x: 4, y: 10, textSlot: 3, blink: true } };
  }
  return p;
}
