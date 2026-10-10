// The project and the hardware rules it enforces. No DOM code, so it can be tested on its own.
//
// A project has scenes; each scene's background is one 160x144 screen. Every pixel stores a palette
// *slot* (0-3), and every 8x8 cell stores which palette it uses, exactly like Game Boy Color tile
// attributes. That makes it impossible to draw something the hardware can't show.
//
// Painting functions take a "layer": { palettes, pixels, cellPal } (see layerOf).

import { luminance, sameColor } from './color.js';

export const W = 160, H = 144, CELL = 8, CW = W / CELL, CH = H / CELL;
export const MAX_BG_PALETTES = 24;                 // in a project (same as gbstage/project.py)
export const SCENE_BG_PALETTES = 8;                // in one scene: what the hardware holds
export const MAX_OBJ_PALETTES = 8;
export const MAX_TILES = 256;
export const MAX_MENU_ITEMS = 6;
export const MAX_FLASH_TILES = 80;   // the flash area must flip within one VBlank
export const MAX_OPTION_ROWS = 6;
export const MAX_SCENES = 32;
export const FORMAT_VERSION = 2;

// Every preset is ordered lightest to darkest, so it works on the original Game Boy as is.
export const PRESETS = [
  { name: 'Sky', colors: [[31, 31, 31], [20, 26, 31], [8, 16, 28], [2, 4, 12]] },
  { name: 'Grass', colors: [[28, 31, 24], [17, 25, 10], [6, 15, 8], [1, 5, 4]] },
  { name: 'Brick', colors: [[31, 28, 22], [29, 17, 8], [17, 7, 4], [6, 2, 2]] },
  { name: 'Stone', colors: [[29, 29, 29], [19, 19, 21], [10, 10, 12], [2, 2, 3]] },
  { name: 'Water', colors: [[26, 31, 31], [10, 24, 30], [4, 12, 22], [1, 3, 10]] },
  { name: 'Sand', colors: [[31, 30, 24], [28, 24, 14], [20, 15, 6], [8, 5, 2]] },
  { name: 'Sunset', colors: [[31, 29, 20], [31, 18, 12], [20, 6, 14], [6, 2, 10]] },
  { name: 'Night', colors: [[24, 24, 31], [12, 12, 24], [5, 5, 14], [1, 1, 5]] },
];
// Sprite palettes: slot 0 is transparent, slots 1-3 go lightest to darkest.
export const OBJ_PRESETS = [
  { name: 'Cursor', colors: [[31, 31, 31], [31, 28, 10], [30, 16, 4], [8, 2, 0]] },
  { name: 'Hero', colors: [[31, 31, 31], [31, 24, 18], [10, 18, 31], [2, 2, 8]] },
];

const clonePalette = p => ({ name: p.name, colors: p.colors.map(c => [...c]) });

// ---- font (shared with the code generator: gbstage/font.txt) ---------------

let FONT = null;

export function parseFont(text) {
  const glyphs = { ' ': Array.from({ length: 8 }, () => new Array(8).fill(0)) };
  let ch = null, rows = [];
  const flush = () => {
    if (ch === null) return;
    const w = rows[0]?.length;                    // 5-wide glyphs sit one column in; 7-wide ones at the left edge
    if (rows.length !== 7 || ![5, 7].includes(w) || rows.some(r => !new RegExp(`^[#.]{${w}}$`).test(r))) {
      throw new Error(`font: glyph "${ch}" must be 7 rows of 5 or 7`);
    }
    const g = Array.from({ length: 8 }, () => new Array(8).fill(0));
    rows.forEach((row, y) => [...row].forEach((c, x) => { g[y][x + (w === 5 ? 1 : 0)] = c === '#' ? 1 : 0; }));
    glyphs[ch] = g;
  };
  for (const line of text.split('\n')) {
    if (line.startsWith('# ') || !line.trim()) continue;
    if (line.startsWith('= ')) { flush(); ch = line[2]; rows = []; } else rows.push(line);
  }
  flush();
  return glyphs;
}

const FONTS = {};
export function setFont(text, name = 'classic') { FONTS[name] = parseFont(text); FONT = FONTS.classic; }
export const FONT_NAMES = ['classic', 'bold'];
// Text draws in this font until the next call: each project picks one.
export function useFont(name) { FONT = FONTS[name] || FONTS.classic; }
export const fontHas = ch => !!FONT && ch in FONT;
export const cleanLabel = text => [...text.toUpperCase()].filter(fontHas).join('');

// Draw text into a layer's pixels with one slot (scale 1 or 2). Doesn't change tile palettes.
export function drawText(layer, text, x, y, slot, scale = 1) {
  [...text.toUpperCase()].forEach((ch, i) => {
    const g = FONT[ch] || FONT[' '];
    for (let gy = 0; gy < 8; gy++) for (let gx = 0; gx < 8; gx++) {
      if (!g[gy][gx]) continue;
      for (let sy = 0; sy < scale; sy++) for (let sx = 0; sx < scale; sx++) {
        const px = x + (i * 8 + gx) * scale + sx, py = y + gy * scale + sy;
        if (px >= 0 && py >= 0 && px < W && py < H) layer.pixels[py * W + px] = slot;
      }
    }
  });
}

// ---- projects and scenes ---------------------------------------------------

function blankScene(name, pal = 0) {
  return { name, pixels: new Uint8Array(W * H), cellPal: new Uint8Array(CW * CH).fill(pal), menu: null,
           pressStart: null, pressed: null, options: null, puzzle: null, back: null, notes: '' };
}

export function newProject() {
  useFont('classic');
  return {
    name: 'Untitled',
    palettes: PRESETS.slice(0, 3).map(clonePalette),
    objPalettes: [],
    cursor: null,
    scenes: [blankScene('Main')],
    start: 0,
    transition: null,
  };
}

// The slider marker sprite (same as the code generator's).
export const MARKER = [
  3, 3, 3, 3, 3, 3, 3, 3,
  3, 1, 1, 1, 1, 1, 1, 3,
  3, 1, 2, 2, 2, 2, 1, 3,
  3, 1, 2, 2, 2, 2, 1, 3,
  3, 1, 2, 2, 2, 2, 1, 3,
  3, 1, 2, 2, 2, 2, 1, 3,
  3, 1, 1, 1, 1, 1, 1, 3,
  3, 3, 3, 3, 3, 3, 3, 3,
];

export function sliderX(row) {
  const n = optionCount(row);
  return row.slider.x0 + Math.round((row.slider.x1 - row.slider.x0) * optionIndex(row) / (n - 1));
}

export const CURSOR_ARROW = [
  0, 0, 3, 0, 0, 0, 0, 0,
  0, 0, 3, 3, 0, 0, 0, 0,
  0, 0, 3, 1, 3, 0, 0, 0,
  0, 0, 3, 1, 2, 3, 0, 0,
  0, 0, 3, 1, 3, 0, 0, 0,
  0, 0, 3, 3, 0, 0, 0, 0,
  0, 0, 3, 0, 0, 0, 0, 0,
  0, 0, 0, 0, 0, 0, 0, 0,
];

// A night sky, a moon, a logo that flashes when you press Start, and a blinking prompt.
export function newPressStartTemplate() {
  useFont('classic');
  const starry = { name: 'Starry', colors: [[31, 31, 24], [18, 20, 31], [6, 7, 18], [1, 1, 6]] };
  const p = {
    name: 'My Game',
    palettes: [clonePalette(starry), clonePalette(PRESETS.find(pr => pr.name === 'Grass'))],
    objPalettes: [],
    cursor: null,
    scenes: [blankScene('Title'), blankScene('Game', 1)],
    start: 0,
    transition: { color: 'white', frames: 3 },
  };
  const title = layerOf(p, 0);
  title.pixels.fill(3);
  // Stars: a fixed scatter, so every new project looks the same.
  let seed = 7;
  const rand = n => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
  for (let k = 0; k < 40; k++) title.pixels[rand(112) * W + rand(W)] = k % 3 ? 1 : 0;
  // Moon with a darker crescent edge.
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const d = Math.hypot(x - 130, y - 22);
    if (d <= 11) title.pixels[y * W + x] = Math.hypot(x - 126, y - 19) <= 10 ? 0 : 1;
  }
  // Hills along the bottom.
  for (let x = 0; x < W; x++) {
    const top = 122 + Math.round(6 * Math.sin(x / 17) + 3 * Math.sin(x / 7));   // peaks stay below the prompt row
    for (let y = top; y < H; y++) title.pixels[y * W + x] = y === top ? 1 : 2;
  }
  drawText(title, 'MY GAME', 25, 41, 1, 2);
  drawText(title, 'MY GAME', 24, 40, 0, 2);
  const scene = p.scenes[0];
  scene.pressStart = {
    target: 1, flashes: 3,
    area: { x: 2, y: 5, w: 16, h: 3 },
    prompt: { label: 'PRESS START', x: 4, y: 13, textSlot: 0, blink: true },
  };
  // The pressed frame: the logo lights up like a sign: a bright panel with a thin border and the
  // logo in dark ink. Same tiles' palettes as the normal frame, only the slots change.
  scene.pressed = scene.pixels.slice();
  const lit = { palettes: p.palettes, pixels: scene.pressed, cellPal: scene.cellPal };
  const a = scene.pressStart.area;
  for (const i of areaPixels(a)) {
    const x = i % W, y = (i / W) | 0;
    const edge = x === a.x * 8 || x === (a.x + a.w) * 8 - 1 || y === a.y * 8 || y === (a.y + a.h) * 8 - 1;
    scene.pressed[i] = edge ? 1 : 0;
  }
  drawText(lit, 'MY GAME', 25, 41, 2, 2);
  drawText(lit, 'MY GAME', 24, 40, 3, 2);

  const game = layerOf(p, 1);
  game.pixels.fill(1);
  drawText(game, 'GAME', 48, 48, 3, 2);
  drawText(game, 'PRESS B', 52, 96, 3);
  p.scenes[1].back = 0;
  return p;
}

// The first experience: a title screen with a menu that leads to two scenes and back.
export function newTitleTemplate() {
  useFont('classic');
  const p = {
    name: 'My Game',
    palettes: ['Sky', 'Grass', 'Sand'].map(n => clonePalette(PRESETS.find(pr => pr.name === n))),
    objPalettes: [clonePalette(OBJ_PRESETS[0])],
    cursor: { palette: 0, pixels: Uint8Array.from(CURSOR_ARROW) },
    scenes: [blankScene('Title'), blankScene('Game', 1), blankScene('Options', 2)],
    start: 0,
    transition: { color: 'white', frames: 3 },
  };
  const [title, game, options] = p.scenes.map((_, i) => layerOf(p, i));

  // Title: sky with a big two-tone logo, grass along the bottom, and the menu.
  title.pixels.fill(1);
  for (let c = 15 * CW; c < CW * CH; c++) p.scenes[0].cellPal[c] = 1;
  // Grass uses a darker slot than the sky so the two stay distinct in gray on the original Game Boy.
  for (let y = 120; y < H; y++) for (let x = 0; x < W; x++) title.pixels[y * W + x] = y < 122 ? 3 : 2;
  drawText(title, 'MY GAME', 25, 25, 2, 2);
  drawText(title, 'MY GAME', 24, 24, 3, 2);
  p.scenes[0].menu = {
    x: 7, y: 10, spacing: 2, textSlot: 3, cursorAnimation: 'bob', blinks: 3,
    items: [{ label: 'START', target: 1 }, { label: 'OPTIONS', target: 2 }],
  };

  // Game and Options: placeholders that say how to get back.
  game.pixels.fill(1);
  drawText(game, 'GAME', 48, 48, 3, 2);
  drawText(game, 'PRESS B', 52, 96, 3);
  p.scenes[1].back = 0;
  options.pixels.fill(1);
  drawText(options, 'OPTIONS', 24, 48, 3, 2);
  drawText(options, 'PRESS B', 52, 96, 3);
  p.scenes[2].back = 0;
  return p;
}

// frame: 'normal', or 'pressed' for the flash area's second frame (it shares the tile palettes).
export const layerOf = (p, s, frame = 'normal') => ({
  palettes: p.palettes,
  pixels: frame === 'pressed' ? p.scenes[s].pressed : p.scenes[s].pixels,
  cellPal: p.scenes[s].cellPal,
});

export function* areaCells(area) {
  if (!area) return;
  for (let y = area.y; y < area.y + area.h; y++) for (let x = area.x; x < area.x + area.w; x++) yield y * CW + x;
}

export function* areaPixels(area) {
  for (const c of areaCells(area)) yield* cellPixels(c);
}

export function newPressStart(p, s) {
  const other = p.scenes.findIndex((_, i) => i !== s);
  return { target: other < 0 ? 0 : other, flashes: 3, area: null,
           prompt: { label: 'PRESS START', x: 4, y: 13, textSlot: 3, blink: true } };
}

// Move or resize the flash area. Cells that just joined it start with a pressed frame equal to the
// normal one; cells already in it keep what you painted.
export function setFlashArea(scene, area) {
  const before = new Set(areaCells(scene.pressStart.area));
  if (!scene.pressed) scene.pressed = scene.pixels.slice();
  for (const c of areaCells(area)) {
    if (!before.has(c)) for (const i of cellPixels(c)) scene.pressed[i] = scene.pixels[i];
  }
  scene.pressStart.area = area;
}

export function addScene(p) {
  if (p.scenes.length >= MAX_SCENES) return -1;
  p.scenes.push(blankScene(`Scene ${p.scenes.length + 1}`));
  return p.scenes.length - 1;
}

// Scenes other scenes point at (menus, B button, start) can't be removed.
export function sceneReferences(p, s) {
  const refs = [];
  if (p.start === s) refs.push('it is the start scene');
  p.scenes.forEach((sc, i) => {
    if (sc.back === s) refs.push(`B on "${sc.name}" goes here`);
    sc.menu?.items.forEach(it => { if (it.target === s) refs.push(`"${it.label}" on "${sc.name}" goes here`); });
    if (sc.pressStart?.target === s) refs.push(`Start on "${sc.name}" goes here`);
    if (sc.options?.target === s) refs.push(`Start on "${sc.name}" goes here`);
    if (sc.passKey?.target === s) refs.push(`Start on "${sc.name}" goes here`);
    if (sc.puzzle?.win === s) refs.push(`winning on "${sc.name}" goes here`);
    if (sc.puzzle?.lose === s) refs.push(`game over on "${sc.name}" goes here`);
    if (sc.fight?.win === s) refs.push(`winning the fight on "${sc.name}" goes here`);
    if (sc.fight?.lose === s) refs.push(`losing the fight on "${sc.name}" goes here`);
    if (sc.fight?.corner === s) refs.push(`between rounds on "${sc.name}" goes here`);
  });
  return refs;
}

// Scenes the game can get to from the start scene. The ROM leaves the others out.
export function reachableScenes(p) {
  const seen = new Set(), todo = [p.start];
  while (todo.length) {
    const i = todo.pop();
    if (seen.has(i) || !p.scenes[i]) continue;
    seen.add(i);
    const sc = p.scenes[i];
    if (sc.back !== null) todo.push(sc.back);
    sc.menu?.items.forEach(it => todo.push(it.target));
    if (sc.pressStart) todo.push(sc.pressStart.target);
    if (sc.options) todo.push(sc.options.target);
    if (sc.passKey) todo.push(sc.passKey.target);
    if (sc.puzzle) todo.push(sc.puzzle.win, sc.puzzle.lose);
    if (sc.fight) todo.push(sc.fight.win, sc.fight.lose, ...(sc.fight.corner != null ? [sc.fight.corner] : []));
  }
  return seen;
}

export function removeScene(p, s) {
  if (p.scenes.length <= 1 || sceneReferences(p, s).length) return false;
  p.scenes.splice(s, 1);
  const fix = t => (t === null ? null : t > s ? t - 1 : t);
  if (p.start > s) p.start--;
  for (const sc of p.scenes) {
    sc.back = fix(sc.back);
    sc.menu?.items.forEach(it => { it.target = fix(it.target); });
    if (sc.pressStart) sc.pressStart.target = fix(sc.pressStart.target);
    if (sc.options) sc.options.target = fix(sc.options.target);
    if (sc.passKey) sc.passKey.target = fix(sc.passKey.target);
    if (sc.puzzle) { sc.puzzle.win = fix(sc.puzzle.win); sc.puzzle.lose = fix(sc.puzzle.lose); }
    if (sc.fight) { sc.fight.win = fix(sc.fight.win); sc.fight.lose = fix(sc.fight.lose); if (sc.fight.corner != null) sc.fight.corner = fix(sc.fight.corner); }
  }
  return true;
}

export function newMenu(p, s) {
  const other = p.scenes.findIndex((_, i) => i !== s);
  return { x: 7, y: 10, spacing: 2, textSlot: 3, cursorAnimation: 'bob', blinks: 3,
           items: [{ label: 'START', target: other < 0 ? 0 : other }] };
}

// Make sure the things menus need exist: a cursor sprite with a sprite palette, and a transition.
export function ensureMenuSupport(p) {
  if (!p.objPalettes.length) p.objPalettes.push(clonePalette(OBJ_PRESETS[0]));
  if (!p.cursor) p.cursor = { palette: 0, pixels: Uint8Array.from(CURSOR_ARROW) };
  if (!p.transition) p.transition = { color: 'white', frames: 3 };
}

// Where each menu label's ink goes: per item, a list of pixel indexes.
export function menuInk(menu) {
  return menu.items.map((item, n) => {
    const row = menu.y + n * menu.spacing, ink = [];
    [...item.label].forEach((ch, ci) => {
      const g = FONT[ch] || FONT[' '];
      for (let gy = 0; gy < 8; gy++) for (let gx = 0; gx < 8; gx++) {
        if (g[gy][gx]) ink.push((row * 8 + gy) * W + (menu.x + ci) * 8 + gx);
      }
    });
    return ink;
  });
}

export function textInk(label, x, y) {
  const ink = [];
  [...label].forEach((ch, ci) => {
    const g = FONT[ch] || FONT[' '];
    for (let gy = 0; gy < 8; gy++) for (let gx = 0; gx < 8; gx++) {
      if (g[gy][gx]) ink.push((y * 8 + gy) * W + (x + ci) * 8 + gx);
    }
  });
  return ink;
}

// ---- fight ------------------------------------------------------------------------
// Same layout as gbstage/fight.py: the rival is an 8x10-tile area; each pose is a full picture of it.
export const FIGHT_W = 8, FIGHT_H = 10;
export const FIGHT_POSES = ['idle', 'idle2', 'guard', 'hit_l', 'hit_r', 'hit_body', 'dazed',
                            'jab_tell', 'jab_mid', 'jab', 'hook_tell', 'hook_mid', 'hook', 'slip', 'idle3', 'hit_back',
                            'kd_stagger', 'kd_fall', 'kd_down', 'kd_kneel', 'taunt', 'arm_pop', 'guard_low'];
const FIGHT_HUD = { stars: 1, hearts: 2, points: 6, clock: 4, round: 1, playerBar: 6, rivalBar: 6 };

// Pixel index -> slot for one rival pose, placed in the scene.
export function rivalPosePixels(ft, pose) {
  const out = [], pw = FIGHT_W * CELL, px = ft.rival.poses[pose].pixels;
  for (let i = 0; i < px.length; i++) out.push([(ft.rival.y * CELL + (i / pw | 0)) * W + ft.rival.x * CELL + i % pw, px.charCodeAt(i) - 48]);
  return out;
}

// The palette each tile of a pose uses, as [cell, palette] pairs.
export function rivalPoseCells(ft, pose) {
  return [...ft.rival.poses[pose].cells].map((kind, k) =>
    [(ft.rival.y + (k / FIGHT_W | 0)) * CW + ft.rival.x + k % FIGHT_W, ft.rival.palettes[kind]]);
}

function fightInto(out, scene, pose = 'idle') {
  const ft = scene.fight;
  for (const [i, v] of rivalPosePixels(ft, pose)) out[i] = v;
  const c = ft.hud.clock;
  for (const i of textInk(':', c.x + 1, c.y)) out[i] = ft.textSlot;
}

function fightTiles(scene, add) {
  const ft = scene.fight;
  for (const pose of FIGHT_POSES) {
    const img = scene.pixels.slice();
    fightInto(img, scene, pose);
    for (const [c] of rivalPoseCells(ft, pose)) add(img, c);
  }
  const digits = (spot, offsets) => {
    for (const k of offsets) for (let d = 0; d < 10; d++) {
      const img = scene.pixels.slice();
      for (const i of textInk(String(d), spot.x + k, spot.y)) img[i] = ft.textSlot;
      add(img, spot.y * CW + spot.x + k);
    }
  };
  digits(ft.hud.stars, [0]); digits(ft.hud.hearts, [0, 1]); digits(ft.hud.points, [0, 1, 2, 3, 4, 5]);
  digits(ft.hud.clock, [0, 2, 3]); digits(ft.hud.round, [0]);
  for (const bar of [ft.hud.playerBar, ft.hud.rivalBar]) for (let k = 0; k < 6; k++) for (let lv = 0; lv <= 8; lv++) {
    const img = scene.pixels.slice(), c = bar.y * CW + bar.x + k;
    for (let y = 2; y < 6; y++) for (let x = 0; x < lv; x++) img[(bar.y * CELL + y) * W + (bar.x + k) * CELL + x] = ft.barSlot;
    add(img, c);
  }
  const burst = ['...#....', '.#.#.#..', '..###...', '#######.', '..###...', '.#.#.#..', '...#....', '........'];
  const img = scene.pixels.slice(), row = ft.crowdRow || 0;     // a camera flash in the crowd
  burst.forEach((r, y) => [...r].forEach((ch, x) => { img[(row * CELL + y) * W + x] = ch === '#' ? 0 : 3; }));
  add(img, row * CW);
}

export function fightProblems(p, s) {
  const ft = p.scenes[s].fight, out = [];
  if (!ft) return out;
  for (const [key, w] of Object.entries(FIGHT_HUD)) {
    const spot = ft.hud[key];
    if (!spot || spot.x < 0 || spot.x + w > CW || spot.y < 0 || spot.y >= CH) out.push(`The HUD's ${key} is off screen.`);
  }
  return out;
}

// ---- puzzle grid ----------------------------------------------------------------
// Same shapes and rules as gbstage/puzzle.py. Cell colors are palette slots 1-3; slot 4 is the background.

export const PUZZLE_SHAPES = ['virus', 'single', 'left', 'right', 'top', 'bottom', 'pop'];
const SHAPE_ART = {
  virus: ['..####..', '.######.', '##.##.##', '##.##.##', '########', '.##..##.', '#.####.#', '.#....#.'],
  single: ['........', '..####..', '.######.', '.######.', '.######.', '.######.', '..####..', '........'],
  left: ['........', '..######', '.#######', '.#######', '.#######', '.#######', '..######', '........'],
  right: ['........', '######..', '#######.', '#######.', '#######.', '#######.', '######..', '........'],
  top: ['........', '..####..', '.######.', '.######.', '.######.', '.######.', '.######.', '.######.'],
  bottom: ['.######.', '.######.', '.######.', '.######.', '.######.', '.######.', '..####..', '........'],
  pop: ['........', '.#....#.', '..#..#..', '...##...', '...##...', '..#..#..', '.#....#.', '........'],
};
export const DEFAULT_PUZZLE_SHAPES = Object.fromEntries(Object.entries(SHAPE_ART).map(([k, rows]) => [k, rows.join('').replace(/#/g, '1').replace(/\./g, '0')]));

export function newPuzzle(p, s) {
  const other = p.scenes.findIndex((_, i) => i !== s);
  const t = other < 0 ? 0 : other;
  return { grid: { x: 3, y: 1, w: 8, h: 16 }, palette: 0, next: { x: 14, y: 2 }, score: { x: 13, y: 6 }, virusCount: { x: 15, y: 9 },
           level: null, textSlot: 3, speedOption: null, levelOption: null, win: t, lose: t, shapes: { ...DEFAULT_PUZZLE_SHAPES } };
}

export function puzzleCells(pz) {
  const cells = [];
  for (let r = 0; r < pz.grid.h; r++) for (let c = 0; c < pz.grid.w; c++) cells.push((pz.grid.y + r) * CW + pz.grid.x + c);
  return cells;
}
const spotCells = (spot, n) => (spot ? Array.from({ length: n }, (_, k) => spot.y * CW + spot.x + k) : []);
export const puzzleHud = pz => ({ next: spotCells(pz.next, 2), score: spotCells(pz.score, 6), virusCount: spotCells(pz.virusCount, 2), level: spotCells(pz.level, 2) });

// A cell's 64 slots: the shape in color slot c, background elsewhere.
export const puzzleTile = (pz, shape, c) => [...pz.shapes[shape]].map(b => (b === '1' ? c : 3));

// Give the grid and next-capsule tiles the piece palette (the build requires it).
export function applyPuzzlePalette(scene) {
  const pz = scene.puzzle;
  for (const c of [...puzzleCells(pz), ...puzzleHud(pz).next]) scene.cellPal[c] = pz.palette;
}

export function puzzleProblems(p, s) {
  const pz = p.scenes[s].puzzle, out = [];
  if (!pz) return out;
  const g = pz.grid;
  if (g.x + g.w > CW || g.y + g.h > CH) out.push('The grid runs off screen.');
  const taken = new Map(puzzleCells(pz).map(c => [c, 'the grid']));
  for (const [key, cells] of Object.entries(puzzleHud(pz))) {
    const name = { next: 'next capsule', score: 'score', virusCount: 'virus count', level: 'level' }[key];
    for (const c of cells) {
      if (c % CW < cells[0] % CW || c >= CW * CH) { out.push(`The ${name} runs off screen.`); break; }
      if (taken.has(c)) { out.push(`The ${name} overlaps ${taken.get(c)}.`); break; }
    }
    cells.forEach(c => taken.set(c, `the ${name}`));
  }
  for (const key of ['win', 'lose']) {
    if (!(pz[key] >= 0 && pz[key] < p.scenes.length) || pz[key] === s) out.push(`Choose a scene for ${key === 'win' ? 'winning' : 'game over'}.`);
  }
  if (p.scenes[s].back !== null) out.push('B rotates the capsule here, so "B button goes to" must be "does nothing".');
  return out;
}

// ---- options screens ----------------------------------------------------------

export const optionSymbol = label => 'OPT_' + (label.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'VALUE');
export const optionCount = row => (row.kind === 'number' ? row.max - row.min + 1 : row.choices.length);
export const optionWidth = row => (row.kind === 'number' ? row.digits : row.choices.reduce((n, c) => n + c.length, 0) + row.choices.length - 1);
export const optionValueCells = row => Array.from({ length: optionWidth(row) }, (_, k) => row.valueY * CW + row.valueX + k);
// Stored as 0..count-1, like the ROM does.
export const optionIndex = row => (row.kind === 'number' ? row.value - row.min : row.value);

export function newOptions(p, s) {
  const other = p.scenes.findIndex((_, i) => i !== s);
  return { target: other < 0 ? 0 : other, textSlot: 3, rows: [
    { label: 'SPEED', kind: 'choice', choices: ['LOW', 'MED', 'HI'], value: 1, labelX: 3, labelY: 4, valueX: 5, valueY: 5 },
  ] };
}

// Draw a row's value area for value index v into pixels; base holds the background without text.
export function drawOptionValue(pixels, base, row, v, slot) {
  for (const c of optionValueCells(row)) for (const i of cellPixels(c)) pixels[i] = base[i];
  if (row.kind === 'number') {
    for (const i of textInk(String(row.min + v).padStart(row.digits, '0'), row.valueX, row.valueY)) pixels[i] = slot;
    return;
  }
  let x = row.valueX;
  row.choices.forEach((choice, k) => {
    for (const i of textInk(choice, x, row.valueY)) pixels[i] = slot;
    if (k === v) for (let cx = x; cx < x + choice.length; cx++) for (const i of cellPixels(row.valueY * CW + cx)) pixels[i] = 3 - pixels[i];
    x += choice.length + 1;
  });
}

function optionLabelCells(row) {
  return Array.from({ length: row.label.length }, (_, k) => row.labelY * CW + row.labelX + k);
}

// Keep a row on screen after its text changes: slide the label or values left if they'd run off the
// right edge. Returns a note about what moved, or '' if nothing did.
export function fitOptionRow(row) {
  const notes = [];
  if (row.labelX + row.label.length > CW) { row.labelX = Math.max(2, CW - row.label.length); notes.push('Moved the label left so it fits.'); }
  const width = optionWidth(row);
  if (row.valueX + width > CW) {
    row.valueX = Math.max(0, CW - width);
    const hitsLabel = row.valueY === row.labelY && row.valueX < row.labelX + row.label.length + 1;
    if (hitsLabel && row.labelY + 1 < CH) {
      // No room beside the label: put the values on the line below, indented under it.
      row.valueY = row.labelY + 1;
      row.valueX = Math.max(0, Math.min(row.labelX + 2, CW - width));
      notes.push('Put the values on the line below the label so they fit.');
    } else {
      notes.push('Moved the values left so they fit.');
    }
  }
  return notes.length ? `"${row.label}": ${notes.join(' ')}` : '';
}

export function optionsProblems(p, s) {
  const o = p.scenes[s].options, out = [];
  if (!o) return out;
  if (!(o.target >= 0 && o.target < p.scenes.length) || o.target === s) out.push('Start needs a scene to go to.');
  const taken = new Map();
  const claim = (cells, what) => {
    for (const c of cells) {
      if (c < 0 || c >= CW * CH) { out.push(`${what} runs off screen.`); return; }
      if (taken.has(c)) { out.push(`${what[0].toUpperCase()}${what.slice(1)} and ${taken.get(c)} overlap; move one of them.`); return; }
    }
    for (const c of cells) taken.set(c, what);
  };
  o.rows.forEach(row => {
    if (row.labelX < 2) out.push(`"${row.label}" needs column 2 or more, for the cursor.`);
    if (row.labelX + row.label.length > CW) out.push(`"${row.label}" runs off the right edge.`);
    else claim(optionLabelCells(row), `"${row.label}"`);
    if (row.valueX + optionWidth(row) > CW) out.push(`The values of "${row.label}" run off the right edge.`);
    else claim(optionValueCells(row), `the values of "${row.label}"`);
  });
  const names = o.rows.map(r => optionSymbol(r.label));
  if (new Set(names).size !== names.length) out.push('Two rows have the same name.');
  return out;
}

// A pass key's digit cells, as gbstage/project.py lays them out: groups of 3, 4 and 3.
export const PASS_OFFSETS = [0, 1, 2, 4, 5, 6, 7, 9, 10, 11];
const clonePass = pk => pk && { x: pk.x, y: pk.y, textSlot: pk.textSlot ?? 0, target: pk.target };

// The scene's pixels with menu and prompt text baked in, exactly as the ROM shows them.
// frame 'pressed' shows the flash area's pressed frame.
export function composed(scene, frame = 'normal') {
  const pr = scene.pressStart?.prompt;
  if (!scene.menu && !pr && !scene.options && !scene.puzzle && !scene.fight && !scene.passKey && !scene.texts?.length && frame === 'normal') return scene.pixels;
  const out = scene.pixels.slice();
  if (scene.fight) fightInto(out, scene, typeof frame === 'string' && frame.startsWith('pose:') ? frame.slice(5) : 'idle');
  for (const t of scene.texts || []) for (const i of textInk(t.label, t.x, t.y)) out[i] = t.textSlot;
  if (scene.puzzle) {
    const pz = scene.puzzle, hud = puzzleHud(pz);
    for (const c of [...puzzleCells(pz), ...hud.next]) for (const i of cellPixels(c)) out[i] = 3;
    for (const [spot, text] of [[pz.score, '000000'], [pz.virusCount, '00'], [pz.level, '00']]) {
      if (spot) for (const i of textInk(text, spot.x, spot.y)) out[i] = pz.textSlot;
    }
  }
  if (scene.options) {
    const o = scene.options;
    for (const row of o.rows) for (const i of textInk(row.label, row.labelX, row.labelY)) out[i] = o.textSlot;
    for (const row of o.rows) {
      if (row.valueX + optionWidth(row) <= CW) drawOptionValue(out, out.slice(), row, optionIndex(row), o.textSlot);
    }
  }
  if (scene.menu) for (const ink of menuInk(scene.menu)) for (const i of ink) out[i] = scene.menu.textSlot;
  if (scene.passKey) for (const off of PASS_OFFSETS) for (const i of textInk('0', scene.passKey.x + off, scene.passKey.y)) out[i] = scene.passKey.textSlot;
  if (pr) for (const i of textInk(pr.label, pr.x, pr.y)) out[i] = pr.textSlot;
  if (frame === 'pressed' && scene.pressed) for (const i of areaPixels(scene.pressStart.area)) out[i] = scene.pressed[i];
  return out;
}

export function pressStartProblems(p, s) {
  const sc = p.scenes[s], ps = sc.pressStart, out = [];
  if (!ps) return out;
  if (!(ps.target >= 0 && ps.target < p.scenes.length) || ps.target === s) out.push('Start needs a scene to go to.');
  if (ps.area && ps.area.w * ps.area.h > MAX_FLASH_TILES) out.push(`The flash area is ${ps.area.w * ps.area.h} tiles; at most ${MAX_FLASH_TILES} can change in one frame.`);
  const pr = ps.prompt;
  if (pr) {
    if (pr.x + pr.label.length > CW) out.push('The prompt runs off the right edge.');
    if (ps.area && pr.y >= ps.area.y && pr.y < ps.area.y + ps.area.h &&
        pr.x < ps.area.x + ps.area.w && ps.area.x < pr.x + pr.label.length) out.push('The prompt and the flash area overlap; move one of them.');
  }
  return out;
}

export function menuProblems(p, s) {
  const m = p.scenes[s].menu, out = [];
  if (!m) return out;
  const last = m.y + (m.items.length - 1) * m.spacing;
  if (last >= CH) out.push('The menu runs off the bottom of the screen.');
  m.items.forEach((it, n) => {
    if (!it.label) out.push(`Item ${n + 1} needs a label.`);
    if (m.x + it.label.length > CW) out.push(`"${it.label}" runs off the right edge (${CW - m.x} characters fit).`);
    if (!(it.target >= 0 && it.target < p.scenes.length) || it.target === s) out.push(`"${it.label}" needs a scene to go to.`);
  });
  return out;
}

// ---- painting ----------------------------------------------------------------

export const cellOf = (x, y) => ((y / CELL) | 0) * CW + ((x / CELL) | 0);

function* cellPixels(c) {
  const x0 = (c % CW) * CELL, y0 = ((c / CW) | 0) * CELL;
  for (let y = y0; y < y0 + CELL; y++) for (let x = x0; x < x0 + CELL; x++) yield y * W + x;
}

export const colorAt = (p, i) => p.palettes[p.cellPal[cellOf(i % W, (i / W) | 0)]].colors[p.pixels[i]];

function usedSlots(p, c) {
  const used = new Set();
  for (const i of cellPixels(c)) used.add(p.pixels[i]);
  return used;
}

function isEmptyCell(p, c) {
  for (const i of cellPixels(c)) if (p.pixels[i] !== 0) return false;
  return true;
}

// Try to move cell c onto palette `to` without changing how it looks. Returns a slot map or null.
function remapFor(p, c, to) {
  const from = p.palettes[p.cellPal[c]].colors, target = p.palettes[to].colors;
  const map = [];
  for (const v of usedSlots(p, c)) {
    const w = sameColor(target[v], from[v]) ? v : target.findIndex(t => sameColor(t, from[v]));
    if (w < 0) return null;
    map[v] = w;
  }
  return map;
}

// Recolor a cell with another palette, keeping its slot pattern (the "tile palette" tool).
export function setCellPalette(p, c, pal) {
  p.cellPal[c] = pal;
}

/**
 * Paint one pixel with palette `pal`, slot `slot`.
 * Returns 'noop' | 'painted' | 'remapped' (cell moved palettes, image unchanged) |
 *         'switched' (empty cell took the new palette) | 'forced' | 'conflict' (nothing painted).
 */
export function paintPixel(p, x, y, pal, slot, force = false) {
  if (x < 0 || y < 0 || x >= W || y >= H) return 'noop';
  const i = y * W + x, c = cellOf(x, y);
  if (p.onlyCells && !p.onlyCells.has(c)) return 'outside';
  let result = 'painted';
  if (p.cellPal[c] !== pal && p.lockPalettes) return 'locked';
  if (p.cellPal[c] !== pal) {
    const map = remapFor(p, c, pal);
    if (map) {
      for (const j of cellPixels(c)) p.pixels[j] = map[p.pixels[j]];
      result = 'remapped';
    } else if (isEmptyCell(p, c)) {
      result = 'switched';
    } else if (force) {
      result = 'forced';
    } else {
      return 'conflict';
    }
    p.cellPal[c] = pal;
  } else if (p.pixels[i] === slot) {
    return 'noop';
  }
  p.pixels[i] = slot;
  return result;
}

// Erase = slot 0 of whatever palette the cell already uses. Never causes a conflict.
export function erasePixel(p, x, y) {
  if (x < 0 || y < 0 || x >= W || y >= H) return 'noop';
  if (p.onlyCells && !p.onlyCells.has(cellOf(x, y))) return 'outside';
  const i = y * W + x;
  if (p.pixels[i] === 0) return 'noop';
  p.pixels[i] = 0;
  return 'painted';
}

// Flood-fill the region of identical color under (x, y). Pixels in cells that can't take the
// palette are skipped and reported.
export function fill(p, x, y, pal, slot, force = false) {
  const start = y * W + x, target = colorAt(p, start);
  if (sameColor(target, p.palettes[pal].colors[slot]) && p.cellPal[cellOf(x, y)] === pal) {
    return { painted: 0, conflictCells: new Set() };
  }
  const region = [], seen = new Uint8Array(W * H), stack = [start];
  seen[start] = 1;
  while (stack.length) {
    const i = stack.pop();
    region.push(i);
    const px = i % W, py = (i / W) | 0;
    for (const [nx, ny] of [[px + 1, py], [px - 1, py], [px, py + 1], [px, py - 1]]) {
      if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
      const j = ny * W + nx;
      if (p.onlyCells && !p.onlyCells.has(cellOf(nx, ny))) continue;
      if (!seen[j] && sameColor(colorAt(p, j), target)) { seen[j] = 1; stack.push(j); }
    }
  }
  const conflictCells = new Set();
  for (const i of region) {
    const r = paintPixel(p, i % W, (i / W) | 0, pal, slot, force);
    if (r === 'conflict' || r === 'locked') conflictCells.add(cellOf(i % W, (i / W) | 0));
  }
  const want = p.palettes[pal].colors[slot];
  const painted = region.filter(i => sameColor(colorAt(p, i), want)).length;
  return { painted, conflictCells };
}

// ---- palettes ----------------------------------------------------------------

// The original Game Boy maps slots to white-to-black for every tile at once, so a palette only
// looks right in grayscale if its slots go from lightest to darkest. Sprite slot 0 is transparent.
export function paletteOrderProblem(palette, sprite = false) {
  const l = palette.colors.map(luminance);
  for (let s = sprite ? 2 : 1; s < 4; s++) {
    if (l[s] > l[s - 1] + 0.5) {
      return `Slot ${s + 1} is lighter than slot ${s}, so this palette's shading flips on the original Game Boy.`;
    }
  }
  return null;
}

// Sort a palette lightest to darkest and renumber the pixels that use it, so the picture is unchanged.
export function fixPaletteOrder(p, pal) {
  const colors = p.palettes[pal].colors;
  const order = [0, 1, 2, 3].sort((a, b) => luminance(colors[b]) - luminance(colors[a]));
  const newSlotOf = [];
  order.forEach((oldSlot, newSlot) => { newSlotOf[oldSlot] = newSlot; });
  p.palettes[pal].colors = order.map(s => colors[s]);
  for (const scene of p.scenes) {
    for (let c = 0; c < CW * CH; c++) {
      if (scene.cellPal[c] !== pal) continue;
      for (const i of cellPixels(c)) {
        scene.pixels[i] = newSlotOf[scene.pixels[i]];
        if (scene.pressed) scene.pressed[i] = newSlotOf[scene.pressed[i]];
      }
    }
  }
}

export function fixSpritePaletteOrder(p, pal) {
  const colors = p.objPalettes[pal].colors;
  const order = [1, 2, 3].sort((a, b) => luminance(colors[b]) - luminance(colors[a]));
  const newSlotOf = [0];
  order.forEach((oldSlot, k) => { newSlotOf[oldSlot] = k + 1; });
  p.objPalettes[pal].colors = [colors[0], ...order.map(s => colors[s])];
  if (p.cursor && p.cursor.palette === pal) p.cursor.pixels = p.cursor.pixels.map(v => newSlotOf[v]);
}

export function paletteUsage(p, pal) {
  return p.scenes.reduce((n, s) => n + s.cellPal.reduce((k, v) => k + (v === pal), 0), 0);
}

export function addPalette(p, preset) {
  if (p.palettes.length >= MAX_BG_PALETTES) return false;
  p.palettes.push(clonePalette(preset));
  return true;
}

export function removePalette(p, pal) {
  if (p.palettes.length <= 1 || paletteUsage(p, pal) > 0) return false;
  p.palettes.splice(pal, 1);
  for (const s of p.scenes) for (let c = 0; c < s.cellPal.length; c++) if (s.cellPal[c] > pal) s.cellPal[c]--;
  return true;
}

// ---- budgets -------------------------------------------------------------------

// Identical 8x8 patterns are stored once. Menu text and the blink frames (each item without its
// text) count too, exactly as the code generator builds them.
export function uniqueTileCount(scene) {
  const seen = new Set();
  const add = (pixels, c) => {
    let key = '';
    for (const i of cellPixels(c)) key += pixels[i];
    seen.add(key);
  };
  const shown = composed(scene);
  for (let c = 0; c < CW * CH; c++) add(shown, c);
  if (scene.menu) {
    scene.menu.items.forEach((it, n) => {
      const row = scene.menu.y + n * scene.menu.spacing;
      for (let k = 0; k < it.label.length; k++) add(scene.pixels, row * CW + scene.menu.x + k);
    });
  }
  if (scene.options) {
    const shownNow = composed(scene), base = shownNow.slice();
    for (const row of scene.options.rows) for (const c of optionValueCells(row)) for (const i of cellPixels(c)) base[i] = scene.pixels[i];
    for (const row of scene.options.rows) {
      if (row.valueX + optionWidth(row) > CW) continue;
      for (let v = 0; v < optionCount(row); v++) {
        const img = base.slice();
        drawOptionValue(img, base, row, v, scene.options.textSlot);
        for (const c of optionValueCells(row)) add(img, c);
      }
    }
  }
  if (scene.puzzle) {
    const pz = scene.puzzle;
    for (const shape of PUZZLE_SHAPES) for (let c = 0; c < 3; c++) seen.add(puzzleTile(pz, shape, c).join(''));
    seen.add(new Array(64).fill(3).join(''));
    for (const [spot, n] of [[pz.score, 6], [pz.virusCount, 2], [pz.level, 2]]) {
      if (!spot) continue;
      for (let k = 0; k < n; k++) for (let d = 0; d < 10; d++) {
        const img = scene.pixels.slice();
        for (const i of textInk(String(d), spot.x + k, spot.y)) img[i] = pz.textSlot;
        add(img, spot.y * CW + spot.x + k);
      }
    }
  }
  if (scene.fight) fightTiles(scene, add);
  const ps = scene.pressStart;
  if (ps?.prompt) for (let k = 0; k < ps.prompt.label.length; k++) add(scene.pixels, ps.prompt.y * CW + ps.prompt.x + k);
  if (ps?.area && scene.pressed) for (const c of areaCells(ps.area)) add(scene.pressed, c);
  return seen.size;
}

// ---- undo snapshots & files ------------------------------------------------------

const cloneMenu = m => m && { ...m, items: m.items.map(it => ({ ...it })) };
const clonePress = ps => ps && { ...ps, area: ps.area && { ...ps.area }, prompt: ps.prompt && { ...ps.prompt } };
const cloneTexts = t => (Array.isArray(t) ? t : []).map(x => ({ label: String(x.label), x: x.x, y: x.y, textSlot: x.textSlot }));
const clonePuzzle = pz => pz && JSON.parse(JSON.stringify(pz));
const POSE_FALLBACK = { idle2: 'idle', idle3: 'idle', hit_back: 'hit_l', slip: 'idle', jab_mid: 'jab_tell', hook_mid: 'hook_tell', kd_stagger: 'hit_body', kd_fall: 'fall',
                        kd_down: 'down', kd_kneel: 'fall', arm_pop: 'hit_body', guard_low: 'guard' };   // as in gbstage/fight.py: older projects borrow a pose
const cloneFight = ft => {
  if (!ft) return ft;
  const out = JSON.parse(JSON.stringify(ft));
  for (const [name, standIn] of Object.entries(POSE_FALLBACK)) {
    if (out.rival?.poses && !out.rival.poses[name] && out.rival.poses[standIn]) out.rival.poses[name] = { ...out.rival.poses[standIn] };
  }
  return out;
};
const cloneOptions = o => o && { ...o, rows: o.rows.map(r => ({ ...r, choices: r.choices && [...r.choices], slider: r.slider && { ...r.slider } })) };
const cloneScene = s => ({ name: s.name, pixels: s.pixels.slice(), cellPal: s.cellPal.slice(), menu: cloneMenu(s.menu),
                           pressStart: clonePress(s.pressStart), pressed: s.pressed && s.pressed.slice(), back: s.back,
                           options: cloneOptions(s.options), puzzle: clonePuzzle(s.puzzle),
                           fight: cloneFight(s.fight), passKey: clonePass(s.passKey || null), texts: cloneTexts(s.texts),
                           slideIn: !!s.slideIn, nesDmc: s.nesDmc || 0, notes: s.notes || '' });

export const snapshot = p => ({
  name: p.name, palettes: p.palettes.map(clonePalette), objPalettes: p.objPalettes.map(clonePalette),
  cursor: p.cursor && { palette: p.cursor.palette, pixels: p.cursor.pixels.slice() },
  scenes: p.scenes.map(cloneScene), start: p.start, transition: p.transition && { ...p.transition },
  sample: p.sample && { ...p.sample }, sound: p.sound || 'arcade', font: p.font || 'classic',
});
export const restore = (p, s) => Object.assign(p, snapshot(s));

export function serialize(p) {
  return {
    format: 'gbstage', version: FORMAT_VERSION, name: p.name,
    palettes: { bg: p.palettes.map(clonePalette), obj: p.objPalettes.map(clonePalette) },
    cursor: p.cursor && { palette: p.cursor.palette, pixels: p.cursor.pixels.join('') },
    scenes: p.scenes.map(s => ({
      name: s.name,
      background: { width: CW, height: CH, pixels: s.pixels.join(''), cellPalettes: [...s.cellPal] },
      menu: cloneMenu(s.menu),
      pressStart: clonePress(s.pressStart),
      pressed: s.pressStart?.area && s.pressed ? s.pressed.join('') : null,
      options: cloneOptions(s.options),
      puzzle: clonePuzzle(s.puzzle),
      ...(s.fight ? { fight: cloneFight(s.fight) } : {}),
      ...(s.passKey ? { passKey: clonePass(s.passKey) } : {}),
      back: s.back,
      ...(s.texts?.length ? { texts: cloneTexts(s.texts) } : {}),
      ...(s.slideIn ? { slideIn: true } : {}),
      ...(s.nesDmc ? { nesDmc: s.nesDmc } : {}),
      ...(s.notes ? { notes: s.notes } : {}),
    })),
    start: p.start,
    transition: p.transition && { ...p.transition },
    ...(p.sample ? { sample: { ...p.sample } } : {}),
    ...(p.sound && p.sound !== 'arcade' ? { sound: p.sound } : {}),
    ...(p.font && p.font !== 'classic' ? { font: p.font } : {}),
  };
}

function upgrade(data) {
  if (data.version === 1) {
    return {
      ...data, version: 2,
      palettes: { bg: data.palettes?.bg, obj: [] },
      scenes: [{ name: 'Main', background: data.background, menu: null, back: null }],
      start: 0, cursor: null, transition: null,
    };
  }
  return data;
}

export function deserialize(raw) {
  const fail = msg => { throw new Error(`Not a valid gbstage project: ${msg}`); };
  if (raw?.format !== 'gbstage') fail('missing format marker');
  if (raw.version > FORMAT_VERSION) fail(`made by a newer gbstage (format ${raw.version})`);
  const data = upgrade(raw);
  const goodColors = pal => Array.isArray(pal.colors) && pal.colors.length === 4 &&
    pal.colors.every(c => c.length === 3 && c.every(v => Number.isInteger(v) && v >= 0 && v <= 31));
  const bg = data.palettes?.bg, obj = data.palettes?.obj || [];
  if (!Array.isArray(bg) || bg.length < 1 || bg.length > MAX_BG_PALETTES) fail(`needs 1-${MAX_BG_PALETTES} background palettes`);
  if (obj.length > MAX_OBJ_PALETTES) fail('too many sprite palettes');
  for (const pal of [...bg, ...obj]) if (!goodColors(pal)) fail(`palette "${pal.name}" must have 4 colors with channels 0-31`);
  if (!Array.isArray(data.scenes) || !data.scenes.length) fail('needs at least one scene');
  const scenes = data.scenes.map((s, i) => {
    const b = s.background;
    if (b?.width !== CW || b?.height !== CH) fail(`scene ${i + 1}: background must be 20x18 tiles`);
    if (typeof b.pixels !== 'string' || !/^[0-3]*$/.test(b.pixels) || b.pixels.length !== W * H) fail(`scene ${i + 1}: bad pixel data`);
    if (b.cellPalettes?.length !== CW * CH || b.cellPalettes.some(v => !(v >= 0 && v < bg.length))) fail(`scene ${i + 1}: bad tile palettes`);
    return {
      name: String(s.name || `Scene ${i + 1}`),
      pixels: Uint8Array.from(b.pixels, ch => ch.charCodeAt(0) - 48),
      cellPal: Uint8Array.from(b.cellPalettes),
      menu: cloneMenu(s.menu || null),
      pressStart: clonePress(s.pressStart || null),
      options: cloneOptions(s.options || null),
      puzzle: clonePuzzle(s.puzzle || null),
      fight: cloneFight(s.fight || null),
      passKey: clonePass(s.passKey || null),
      pressed: typeof s.pressed === 'string' && s.pressed.length === W * H && /^[0-3]*$/.test(s.pressed)
        ? Uint8Array.from(s.pressed, ch => ch.charCodeAt(0) - 48) : null,
      back: Number.isInteger(s.back) ? s.back : null,
      texts: cloneTexts(s.texts),
      slideIn: s.slideIn === true && !s.fight,
      nesDmc: Number.isInteger(s.nesDmc) ? s.nesDmc : 0,
      notes: typeof s.notes === 'string' ? s.notes.slice(0, 2000) : '',
    };
  });
  const c = data.cursor;
  return {
    name: String(data.name || 'Untitled'),
    palettes: bg.map(pal => ({ name: String(pal.name || 'Palette'), colors: pal.colors.map(x => [...x]) })),
    objPalettes: obj.map(pal => ({ name: String(pal.name || 'Sprite palette'), colors: pal.colors.map(x => [...x]) })),
    cursor: c && typeof c.pixels === 'string' && c.pixels.length === 64
      ? { palette: c.palette | 0, pixels: Uint8Array.from(c.pixels, ch => ch.charCodeAt(0) - 48) } : null,
    scenes,
    start: Number.isInteger(data.start) && data.start < scenes.length ? data.start : 0,
    transition: data.transition ? { color: data.transition.color === 'black' ? 'black' : 'white',
                                    frames: Math.min(30, Math.max(1, data.transition.frames | 0)) } : null,
    sample: data.sample && typeof data.sample.id === 'string' ? { id: data.sample.id, version: data.sample.version | 0 } : null,
    sound: ['arcade', 'boxing'].includes(data.sound) ? data.sound : 'arcade',
    font: FONT_NAMES.includes(data.font) ? data.font : 'classic',
  };
}
