// Sprite sheets in and out: the fight's rival and player poses as PNGs an artist can edit.
//
// Rival sheet: 64x80 frames, left to right then top to bottom, in FIGHT_POSES order.
// Player sheet: 24x48 frames in PLAYER_POSES order, transparent background.
// Importing fits the art to the hardware: every color is snapped to what the Game Boy Color can
// show, each 8x8 tile gets one palette, and the rival's three palettes are chosen from the art.

import { FIGHT_W, FIGHT_H, FIGHT_POSES } from './model.js';
import { from8, to8, luminance } from './color.js';

export const PLAYER_POSES = ['idle', 'jab', 'jab_high', 'dodge', 'block', 'hit', 'star', 'down', 'win'];
const RW = FIGHT_W * 8, RH = FIGHT_H * 8;
export const PW = 24, PH = 48, PLAYER_X = 80 - PW / 2 - 8;   // as in gbstage/fight.py
const KINDS = ['s', 'g', 'h'];
const key = c => c.join(',');
const dist = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

export function readImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.width; c.height = img.height;
      const g = c.getContext('2d');
      g.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      resolve(g.getImageData(0, 0, img.width, img.height));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file isn't an image the browser can read.")); };
    img.src = url;
  });
}

function frames(img, fw, fh, count, what, need = count) {
  if (img.width % fw || img.height % fh) {
    throw new Error(`A ${what} sheet is made of ${fw}x${fh} frames; this image is ${img.width}x${img.height}.`);
  }
  const cols = img.width / fw, have = cols * (img.height / fh);
  if (have < need) throw new Error(`A ${what} sheet needs ${need} frames; this one has room for ${have}.`);
  count = Math.min(count, have);
  const out = [];
  for (let n = 0; n < count; n++) {
    const fx = (n % cols) * fw, fy = (n / cols | 0) * fh, px = [];
    for (let y = 0; y < fh; y++) for (let x = 0; x < fw; x++) {
      const i = ((fy + y) * img.width + fx + x) * 4, d = img.data;
      px.push(d[i + 3] < 128 ? null : from8([d[i], d[i + 1], d[i + 2]]));
    }
    out.push(px);
  }
  return out;
}

// ---- rival ----

// Returns { poses, palettes: [3 x 4 colors], changed } where changed counts tiles whose colors had to move.
export function importRival(img, mat) {
  const all = frames(img, RW, RH, FIGHT_POSES.length, 'rival', FIGHT_POSES.indexOf('guard_low'));   // older sheets: no low guard
  // The background: transparent pixels, or the color in each frame's top-left corner.
  const bg = all.map(px => px[0] && key(px[0]));
  const isBg = (n, c) => !c || key(c) === bg[n];
  // The outline is the darkest color used; slot 4 of every rival palette.
  let black = null;
  all.forEach((px, n) => px.forEach(c => { if (!isBg(n, c) && (!black || luminance(c) < luminance(black))) black = c; }));
  black = black || [0, 0, 0];
  // Per tile: the colors besides background and outline.
  const tiles = [];
  all.forEach((px, n) => {
    for (let cy = 0; cy < FIGHT_H; cy++) for (let cx = 0; cx < FIGHT_W; cx++) {
      const colors = new Map();
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
        const c = px[(cy * 8 + y) * RW + cx * 8 + x];
        if (!isBg(n, c) && key(c) !== key(black)) colors.set(key(c), (colors.get(key(c)) || 0) + 1);
      }
      tiles.push({ n, cx, cy, colors });
    }
  });
  // Choose up to 3 color pairs that cover the most tiles exactly.
  const pairs = new Map();
  for (const t of tiles) {
    if (!t.colors.size || t.colors.size > 2) continue;
    const k = [...t.colors.keys()].sort().join('|');
    pairs.set(k, (pairs.get(k) || 0) + 1);
  }
  const chosen = [];
  const covers = (pair, t) => [...t.colors.keys()].every(c => pair.includes(c));
  while (chosen.length < 3 && pairs.size) {
    let best = null, bestScore = -1;
    for (const k of pairs.keys()) {
      const pair = k.split('|');
      const score = tiles.filter(t => t.colors.size && covers(pair, t) && !chosen.some(p => covers(p, t))).length;
      if (score > bestScore) { best = pair; bestScore = score; }
    }
    if (bestScore <= 0) break;
    chosen.push(best);
    pairs.delete(best.slice().sort().join('|'));
  }
  // Two-color palettes; a one-color pick gets its own darker shade as the second color.
  const parse = k => k.split(',').map(Number);
  const palettes = chosen.map(pair => {
    const cs = pair.map(parse).sort((a, b) => luminance(b) - luminance(a));
    if (cs.length === 1) cs.push(cs[0].map(v => Math.max(0, v - 6)));
    return [mat, cs[0], cs[1], black];
  });
  while (palettes.length < 3) palettes.push(palettes[0] ? palettes[0].slice() : [mat, [31, 24, 18], [23, 14, 10], black]);
  // Paint every pose with the closest palette per tile.
  let changed = 0;
  const poses = {};
  all.forEach((px, n) => {
    const out = new Array(RW * RH).fill(0), kinds = [];
    for (let cy = 0; cy < FIGHT_H; cy++) for (let cx = 0; cx < FIGHT_W; cx++) {
      const cell = [];
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) cell.push((cy * 8 + y) * RW + cx * 8 + x);
      let bestP = 0, bestErr = Infinity;
      palettes.forEach((pal, pi) => {
        let err = 0;
        for (const i of cell) {
          const c = px[i];
          if (isBg(n, c)) continue;
          err += Math.min(...[1, 2, 3].map(s => dist(c, pal[s])));
        }
        if (err < bestErr) { bestErr = err; bestP = pi; }
      });
      if (bestErr > 0) changed++;
      const pal = palettes[bestP];
      for (const i of cell) {
        const c = px[i];
        if (isBg(n, c)) continue;
        let s = 1, e = Infinity;
        for (const k of [1, 2, 3]) { const d = dist(c, pal[k]); if (d < e) { e = d; s = k; } }
        out[i] = s;
      }
      kinds.push(KINDS[bestP]);
    }
    poses[FIGHT_POSES[n]] = { pixels: out.join(''), cells: kinds.join('') };
  });
  return { poses, palettes, changed };
}

// ---- player ----

// Returns { poses, colors: [3 colors for slots 1-3], changed } (pixels whose color had to move).
export function importPlayer(img) {
  const all = frames(img, PW, PH, PLAYER_POSES.length, 'player');
  const bg = all.map(px => px[0] && key(px[0]));
  const isBg = (n, c) => !c || key(c) === bg[n];
  const count = new Map();
  all.forEach((px, n) => px.forEach(c => { if (!isBg(n, c)) count.set(key(c), (count.get(key(c)) || 0) + 1); }));
  const colors = [...count.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k]) => k.split(',').map(Number))
    .sort((a, b) => luminance(b) - luminance(a));
  while (colors.length < 3) colors.push([0, 0, 0]);
  let changed = 0;
  const poses = {};
  all.forEach((px, n) => {
    poses[PLAYER_POSES[n]] = px.map(c => {
      if (isBg(n, c)) return 0;
      let s = 1, e = Infinity;
      colors.forEach((pc, k) => { const d = dist(c, pc); if (d < e) { e = d; s = k + 1; } });
      if (e > 0) changed++;
      return s;
    }).join('');
  });
  return { poses, colors, changed };
}

// ---- sheets out ----

function sheetImage(fw, fh, names, paint) {
  const cols = 4, width = cols * fw, height = Math.ceil(names.length / cols) * fh;
  const data = new Uint8ClampedArray(width * height * 4);
  names.forEach((name, n) => {
    const fx = (n % cols) * fw, fy = (n / cols | 0) * fh;
    for (let y = 0; y < fh; y++) for (let x = 0; x < fw; x++) {
      const rgba = paint(name, x, y);
      if (rgba) data.set(rgba, ((fy + y) * width + fx + x) * 4);
    }
  });
  return { width, height, data };
}

export function rivalImage(fight, palettes) {
  return sheetImage(RW, RH, FIGHT_POSES, (name, x, y) => {
    const pose = fight.rival.poses[name];
    const kind = pose.cells[(y >> 3) * FIGHT_W + (x >> 3)];
    const slot = pose.pixels.charCodeAt(y * RW + x) - 48;
    return [...to8(palettes[fight.rival.palettes[kind]].colors[slot]), 255];
  });
}

export function playerImage(fight, colors) {
  return sheetImage(PW, PH, PLAYER_POSES, (name, x, y) => {
    const slot = fight.player.poses[name].charCodeAt(y * PW + x) - 48;
    return slot ? [...to8(colors[slot]), 255] : null;
  });
}

function png({ width, height, data }) {
  const c = document.createElement('canvas');
  c.width = width; c.height = height;
  c.getContext('2d').putImageData(new ImageData(data, width, height), 0, 0);
  return new Promise(resolve => c.toBlob(resolve, 'image/png'));
}

export const rivalSheet = (fight, palettes) => png(rivalImage(fight, palettes));
export const playerSheet = (fight, colors) => png(playerImage(fight, colors));
