import * as M from './model.js';
import { DMG_SHADES, to8, from8, hex, parseHex, gbcScreen, rgbToHsv, hsvToRgb, sameColor } from './color.js';
import { initSystemCheck, loadBinjgb } from './syscheck.js';
import { Player, asOriginalGameBoy, audioContext } from './player.js';
import { capsuleClinic, CLINIC_VERSION } from './examples.js';
import { macVsJoe, MAC_VS_JOE_VERSION } from './mac-vs-joe.js';
import { readImage, importRival, importPlayer, rivalSheet, playerSheet, PLAYER_POSES, PW, PH, PLAYER_X } from './importer.js';

const $ = id => document.getElementById(id);
const STORAGE_KEY = 'gbstage.project';
const TOOL_NAMES = { pencil: 'Pencil', eraser: 'Eraser', fill: 'Fill', picker: 'Eyedropper', tilepal: 'Tile palette' };

// The font is shared with the code generator, so menu text here matches the ROM exactly.
try {
  M.setFont(await fetch('/api/font.txt').then(r => r.text()));
  M.setFont(await fetch('/api/font-bold.txt').then(r => r.text()), 'bold');
} catch {
  M.setFont('');
}

// The server's code fingerprint when this page loaded. If it changes, this page is running old code.
let codeStamp = null;
try {
  codeStamp = (await fetch('/api/status').then(r => r.json())).app.stamp;
  window.__stampLog = [['load', codeStamp]];
} catch {}

function checkStamp(res) {
  const stamp = res.headers.get('X-Gbstage-Stamp');
  window.__stampLog?.push(['header', stamp]);
  if (codeStamp && stamp && stamp !== codeStamp && $('staleBar').hidden) confirmStale();
  return res;
}

// Only say so once the server confirms it twice, two seconds apart, so a restart racing a request
// never raises a false alarm.
let confirming = false;
async function confirmStale() {
  if (confirming) return;
  confirming = true;
  try {
    const stamp = async () => (await fetch('/api/status').then(r => r.json())).app.stamp;
    const first = await stamp();
    await new Promise(r => setTimeout(r, 2000));
    const second = await stamp();
    if (first && first === second && second !== codeStamp) $('staleBar').hidden = false;
  } catch {
  } finally {
    confirming = false;
  }
}

const saved = loadSaved();
const state = {
  project: saved || M.newPressStartTemplate(),
  scene: 0,
  frame: 'normal',      // 'pressed' paints the flash area's second frame
  pose: 'idle',         // the fight rival's pose shown on the stage
  areaDraw: false,      // dragging on the stage sets the flash area
  areaDrag: null,       // {x0, y0, x1, y1} in tiles while dragging
  tool: 'pencil',
  palKind: 'bg',        // which palette the color picker edits: 'bg' or 'obj'
  pal: 0,
  slot: 3,
  objPal: 0,
  objSlot: 3,
  view: 'color',
  hover: null,          // {x, y}
  flashes: [],          // [{cell, until}] cells to highlight after a conflict
  undo: [],
  redo: [],
};

const scene = () => state.project.scenes[state.scene];
const pressArea = () => scene().pressStart?.area || null;
const editingPressed = () => state.frame === 'pressed' && !!pressArea();
const shownFrame = () => (editingPressed() ? 'pressed' : 'normal');

// What painting changes. In the Pressed frame only the flash area can change, and every tile keeps
// its palette, because the ROM flips tiles, not palettes.
function layer() {
  if (!editingPressed()) return M.layerOf(state.project, state.scene);
  return Object.assign(M.layerOf(state.project, state.scene, 'pressed'),
                       { lockPalettes: true, onlyCells: new Set(M.areaCells(pressArea())) });
}

// ---- persistence -----------------------------------------------------------

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? M.deserialize(JSON.parse(raw)) : null;
  } catch (err) {
    console.warn('Ignoring saved project:', err);
    return null;
  }
}

let saveTimer = 0;
function autosave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(M.serialize(state.project)));
  }, 400);
}

function download(name, data, type) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const fileBase = () => (state.project.name.trim() || 'untitled').replace(/[^\w\- ]+/g, '').replace(/\s+/g, '-');

// ---- undo ------------------------------------------------------------------

function pushUndo() {
  state.undo.push(M.snapshot(state.project));
  if (state.undo.length > 100) state.undo.shift();
  state.redo = [];
}

function undoRedo(from, to) {
  if (!from.length) return;
  to.push(M.snapshot(state.project));
  M.restore(state.project, from.pop());
  clampSelection();
  $('projectName').value = state.project.name;
  changed({ palettes: true, scenes: true });
}

function clampSelection() {
  const p = state.project;
  state.scene = Math.min(state.scene, p.scenes.length - 1);
  state.pal = Math.min(state.pal, p.palettes.length - 1);
  state.objPal = Math.max(0, Math.min(state.objPal, p.objPalettes.length - 1));
  if (state.palKind === 'obj' && !p.objPalettes.length) state.palKind = 'bg';
}

// Call after any change to the project. Panels with text inputs are only rebuilt when asked,
// so typing in them doesn't lose focus.
function changed({ palettes = false, scenes = false } = {}) {
  if (palettes) { renderPalettes(); renderSprites(); }
  if (scenes) renderScenes();
  renderStage();
  renderMeters();
  syncPicker();
  autosave();
  scheduleMeasure();
}

// ---- messages --------------------------------------------------------------

let messageTimer = 0;
function say(text, kind = 'info') {
  const el = $('message');
  el.textContent = text;
  el.className = kind;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => { el.textContent = ''; }, kind === 'warn' ? 9000 : 5000);
}

// ---- stage rendering -------------------------------------------------------

const stageCtx = $('stage').getContext('2d');
const stageImage = stageCtx.createImageData(M.W, M.H);
const overlay = $('overlay');
const octx = overlay.getContext('2d');

function displayColor(c, slot) {
  if (state.view === 'dmg') return DMG_SHADES[slot];
  if (state.view === 'screen') return gbcScreen(c);
  return to8(c);
}

function renderStage() {
  const p = state.project, sc = scene();
  const lut = p.palettes.map(pal => pal.colors.map((c, s) => displayColor(c, s)));
  const pose = sc.fight && sc.fight.rival.poses[state.pose] ? state.pose : 'idle';
  const px = M.composed(sc, sc.fight ? `pose:${pose}` : shownFrame());
  const cellPal = sc.fight ? sc.cellPal.slice() : sc.cellPal;
  if (sc.fight) for (const [c, palette] of M.rivalPoseCells(sc.fight, pose)) cellPal[c] = palette;
  const d = stageImage.data;
  for (let i = 0; i < M.W * M.H; i++) {
    const c = lut[cellPal[M.cellOf(i % M.W, (i / M.W) | 0)]][px[i]];
    d[i * 4] = c[0]; d[i * 4 + 1] = c[1]; d[i * 4 + 2] = c[2]; d[i * 4 + 3] = 255;
  }
  // Sprites, where the ROM puts them when the scene opens: the cursor and a slider marker.
  const sprite = (pixels, x0, y0) => {
    const colors = p.objPalettes[p.cursor.palette].colors;
    for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
      const v = pixels[y * 8 + x];
      const X = x0 + x, Y = y0 + y;
      if (!v || X < 0 || X >= M.W || Y < 0 || Y >= M.H) continue;
      const c = displayColor(colors[v], v), i = (Y * M.W + X) * 4;
      d[i] = c[0]; d[i + 1] = c[1]; d[i + 2] = c[2];
    }
  };
  if (sc.fight && p.objPalettes[sc.fight.player.palette]) {     // the player where the ROM puts him
    const colors = p.objPalettes[sc.fight.player.palette].colors, img = sc.fight.player.poses.idle;
    for (let y = 0; y < PH; y++) for (let x = 0; x < PW; x++) {
      const v = img.charCodeAt(y * PW + x) - 48, X = PLAYER_X + x, Y = M.H - PH + y;
      if (!v) continue;
      const c = displayColor(colors[v], v), i = (Y * M.W + X) * 4;
      d[i] = c[0]; d[i + 1] = c[1]; d[i + 2] = c[2];
    }
  }
  if (p.cursor && p.objPalettes[p.cursor.palette]) {
    if (sc.menu) sprite(p.cursor.pixels, sc.menu.x * 8 - 11, sc.menu.y * 8);
    if (sc.options?.rows.length) {
      const first = sc.options.rows[0];
      sprite(p.cursor.pixels, first.labelX * 8 - 11, first.labelY * 8);
      for (const row of sc.options.rows) if (row.slider) sprite(M.MARKER, M.sliderX(row), row.slider.y);
    }
  }
  stageCtx.putImageData(stageImage, 0, 0);
  renderOverlay();
}

function renderOverlay() {
  const rect = overlay.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (overlay.width !== Math.round(rect.width * dpr)) {
    overlay.width = Math.round(rect.width * dpr);
    overlay.height = Math.round(rect.height * dpr);
  }
  const s = overlay.width / M.W;     // device pixels per Game Boy pixel
  octx.clearRect(0, 0, overlay.width, overlay.height);
  const sc = scene();

  const now = performance.now();
  state.flashes = state.flashes.filter(f => f.until > now);
  // Conflicting tiles get a red outline and hatching, so they can't be mistaken for paint.
  for (const f of state.flashes) {
    const x = (f.cell % M.CW) * 8 * s, y = ((f.cell / M.CW) | 0) * 8 * s, size = 8 * s;
    octx.save();
    octx.beginPath();
    octx.rect(x, y, size, size);
    octx.clip();
    octx.strokeStyle = 'rgba(255, 40, 40, 0.9)';
    octx.lineWidth = Math.max(1, s / 3);
    for (let k = -size; k < size; k += s * 2) {
      octx.moveTo(x + k, y + size);
      octx.lineTo(x + k + size, y);
    }
    octx.stroke();
    octx.restore();
    octx.lineWidth = Math.max(2, s / 2);
    octx.strokeStyle = '#ff2828';
    octx.strokeRect(x + 1, y + 1, size - 2, size - 2);
  }

  // Pressed frame: everything outside the flash area is dimmed, since only the area changes.
  const area = sc.pressStart?.area;
  if (area && editingPressed()) {
    octx.fillStyle = 'rgba(0, 0, 0, 0.55)';
    const ax = area.x * 8 * s, ay = area.y * 8 * s, aw = area.w * 8 * s, ah = area.h * 8 * s;
    octx.fillRect(0, 0, overlay.width, ay);
    octx.fillRect(0, ay + ah, overlay.width, overlay.height - ay - ah);
    octx.fillRect(0, ay, ax, ah);
    octx.fillRect(ax + aw, ay, overlay.width - ax - aw, ah);
  }
  const drag = state.areaDrag;
  const box = drag ? normRect(drag) : area;
  if (box) {
    octx.lineWidth = Math.max(2, dpr * 1.5);
    octx.strokeStyle = drag && box.w * box.h > M.MAX_FLASH_TILES ? '#ff3b3b' : '#ff5ad1';
    octx.strokeRect(box.x * 8 * s + 1, box.y * 8 * s + 1, box.w * 8 * s - 2, box.h * 8 * s - 2);
    octx.font = `${Math.max(10, Math.round(3 * s))}px system-ui`;
    octx.fillStyle = octx.strokeStyle;
    octx.textBaseline = 'bottom';
    octx.fillText(`flash area ${box.w}×${box.h}`, box.x * 8 * s + 2, box.y * 8 * s - 2);
  }
  const prompt = sc.pressStart?.prompt;
  if (prompt) {
    octx.save();
    octx.setLineDash([3 * dpr, 3 * dpr]);
    octx.strokeStyle = 'rgba(255, 210, 80, 0.8)';
    octx.lineWidth = Math.max(1, dpr);
    octx.strokeRect(prompt.x * 8 * s + 0.5, prompt.y * 8 * s + 0.5, Math.max(1, prompt.label.length) * 8 * s - 1, 8 * s - 1);
    octx.restore();
  }

  if (sc.options) {
    octx.save();
    octx.setLineDash([3 * dpr, 3 * dpr]);
    octx.strokeStyle = 'rgba(255, 210, 80, 0.8)';
    octx.lineWidth = Math.max(1, dpr);
    for (const row of sc.options.rows) {
      octx.strokeRect(row.labelX * 8 * s + 0.5, row.labelY * 8 * s + 0.5, row.label.length * 8 * s - 1, 8 * s - 1);
      octx.strokeRect(row.valueX * 8 * s + 0.5, row.valueY * 8 * s + 0.5, M.optionWidth(row) * 8 * s - 1, 8 * s - 1);
    }
    octx.restore();
  }

  // Menu labels are drawn by the ROM on top of your painting; outline where they go.
  if (sc.menu) {
    octx.save();
    octx.setLineDash([3 * dpr, 3 * dpr]);
    octx.strokeStyle = 'rgba(255, 210, 80, 0.8)';
    octx.lineWidth = Math.max(1, dpr);
    sc.menu.items.forEach((it, n) => {
      const y = (sc.menu.y + n * sc.menu.spacing) * 8 * s;
      octx.strokeRect(sc.menu.x * 8 * s + 0.5, y + 0.5, Math.max(1, it.label.length) * 8 * s - 1, 8 * s - 1);
    });
    octx.restore();
  }

  if ($('palOverlay').checked) {
    octx.font = `${Math.round(3.2 * s)}px system-ui`;
    octx.textBaseline = 'top';
    for (let c = 0; c < M.CW * M.CH; c++) {
      const x = (c % M.CW) * 8 * s, y = ((c / M.CW) | 0) * 8 * s;
      const pal = sc.cellPal[c];
      octx.fillStyle = 'rgba(0,0,0,0.55)';
      octx.fillRect(x + s * 0.5, y + s * 0.5, 4 * s, 4 * s);
      octx.fillStyle = hex(state.project.palettes[pal].colors[1]);
      octx.fillText(String(pal + 1), x + s * 1.4, y + s * 0.9);
    }
  }

  if ($('gridToggle').checked) {
    octx.strokeStyle = 'rgba(128,128,128,0.35)';
    octx.lineWidth = 1;
    octx.beginPath();
    for (let x = 8; x < M.W; x += 8) { octx.moveTo(Math.round(x * s) + 0.5, 0); octx.lineTo(Math.round(x * s) + 0.5, overlay.height); }
    for (let y = 8; y < M.H; y += 8) { octx.moveTo(0, Math.round(y * s) + 0.5); octx.lineTo(overlay.width, Math.round(y * s) + 0.5); }
    octx.stroke();
  }

  if (state.hover) {
    const { x, y } = state.hover;
    octx.lineWidth = Math.max(1, dpr);
    if (state.tool === 'tilepal' || state.tool === 'fill') {
      octx.strokeStyle = 'rgba(255,255,255,0.8)';
      octx.strokeRect((x & ~7) * s + 0.5, (y & ~7) * s + 0.5, 8 * s - 1, 8 * s - 1);
    }
    octx.strokeStyle = 'rgba(255,255,255,0.9)';
    octx.strokeRect(x * s + 0.5, y * s + 0.5, s - 1, s - 1);
  }
  if (state.flashes.length) requestAnimationFrame(renderOverlay);
}

function flash(cells) {
  const until = performance.now() + 1500;
  for (const cell of cells) state.flashes.push({ cell, until });
  renderOverlay();
}

// ---- painting --------------------------------------------------------------

function eventPixel(e) {
  const r = overlay.getBoundingClientRect();
  return {
    x: Math.floor((e.clientX - r.left) / r.width * M.W),
    y: Math.floor((e.clientY - r.top) / r.height * M.H),
  };
}

const palName = i => state.project.palettes[i].name;

let stroke = null;   // {last, conflicts:Set, results:Set, force}

function applyAt(x, y) {
  const l = layer();
  if (x < 0 || y < 0 || x >= M.W || y >= M.H) return;
  if (state.tool === 'eraser') {
    stroke.results.add(M.erasePixel(l, x, y));
  } else if (state.tool === 'tilepal') {
    const c = M.cellOf(x, y);
    if (editingPressed()) { stroke.results.add('locked'); stroke.conflicts.add(c); return; }
    if (l.cellPal[c] !== state.pal) { M.setCellPalette(l, c, state.pal); stroke.results.add('painted'); }
  } else {
    const r = M.paintPixel(l, x, y, state.pal, state.slot, stroke.force);
    stroke.results.add(r);
    if (r === 'conflict' || r === 'locked') stroke.conflicts.add(M.cellOf(x, y));
  }
}

function lineTo(x1, y1) {
  let { x: x0, y: y0 } = stroke.last;
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    applyAt(x0, y0);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
  stroke.last = { x: x1, y: y1 };
}

function pickAt(x, y) {
  if (x < 0 || y < 0 || x >= M.W || y >= M.H) return;
  state.palKind = 'bg';
  state.pal = scene().cellPal[M.cellOf(x, y)];
  state.slot = M.composed(scene(), shownFrame())[y * M.W + x];
  renderPalettes();
  renderSprites();
  syncPicker();
}

function explainConflict(cells) {
  const cell = [...cells][0];
  const owner = palName(scene().cellPal[cell]);
  say(`Those 8×8 tiles use "${owner}", and a tile can only use one palette's 4 colors. ` +
      `Pick a color from "${owner}", or hold Alt (⌥) to repaint the tile with "${palName(state.pal)}".`, 'warn');
  flash(cells);
}

function explainOutside() {
  say('In the Pressed frame only the flash area changes. Switch to Normal to paint the rest of the screen.', 'warn');
}

function explainLocked(cells) {
  const owner = palName(scene().cellPal[[...cells][0]]);
  say(`In the Pressed frame every tile keeps its palette (the ROM swaps tiles, not palettes). ` +
      `Pick a color from "${owner}".`, 'warn');
  flash(cells);
}

function endStroke() {
  if (!stroke) return;
  const { results, conflicts } = stroke;
  const didChange = [...results].some(r => !['noop', 'conflict', 'locked', 'outside'].includes(r));
  if (!didChange) state.undo.pop();
  if (conflicts.size && editingPressed()) explainLocked(conflicts);
  else if (conflicts.size) explainConflict(conflicts);
  else if (results.has('outside') && !didChange) explainOutside();
  else if (results.has('switched')) say(`Tile switched to "${palName(state.pal)}". Each 8×8 tile uses one palette.`);
  else if (results.has('remapped')) say(`Tile moved to "${palName(state.pal)}". It had the same colors, so nothing changed visually.`);
  else if (results.has('forced')) say(`Tile repainted with "${palName(state.pal)}".`);
  stroke = null;
  if (didChange) changed({ palettes: true });
}

function normRect(d) {
  const x = Math.max(0, Math.min(d.x0, d.x1)), y = Math.max(0, Math.min(d.y0, d.y1));
  return { x, y, w: Math.min(M.CW, Math.max(d.x0, d.x1) + 1) - x, h: Math.min(M.CH, Math.max(d.y0, d.y1) + 1) - y };
}

function armAreaDraw(on) {
  state.areaDraw = on;
  overlay.style.cursor = on ? 'cell' : (state.tool === 'picker' ? 'copy' : 'crosshair');
  if (on) say(`Drag on the stage to set the flash area (up to ${M.MAX_FLASH_TILES} tiles). Esc cancels.`);
  renderSceneSettings();
}

function finishAreaDraw() {
  let r = normRect(state.areaDrag);
  state.areaDrag = null;
  if (r.w * r.h > M.MAX_FLASH_TILES) {
    r = { ...r, h: Math.max(1, Math.floor(M.MAX_FLASH_TILES / r.w)) };
    if (r.w * r.h > M.MAX_FLASH_TILES) r = { ...r, w: M.MAX_FLASH_TILES };
    say(`Flash areas can be up to ${M.MAX_FLASH_TILES} tiles, so it was trimmed to ${r.w}×${r.h}.`, 'warn');
  }
  pushUndo();
  M.setFlashArea(scene(), r);
  armAreaDraw(false);
  changed({ scenes: true });
}

overlay.addEventListener('contextmenu', e => e.preventDefault());

overlay.addEventListener('pointerdown', e => {
  const { x, y } = eventPixel(e);
  if (state.areaDraw && e.button === 0) {
    try { overlay.setPointerCapture(e.pointerId); } catch {}
    state.areaDrag = { x0: x >> 3, y0: y >> 3, x1: x >> 3, y1: y >> 3 };
    renderOverlay();
    return;
  }
  if (e.button === 2 || state.tool === 'picker') { pickAt(x, y); return; }
  if (e.button !== 0) return;
  if (state.palKind === 'obj') { state.palKind = 'bg'; renderPalettes(); renderSprites(); syncPicker(); }
  pushUndo();
  if (state.tool === 'fill') {
    if (editingPressed() && !new Set(M.areaCells(pressArea())).has(M.cellOf(x, y))) {
      state.undo.pop();
      explainOutside();
      return;
    }
    const r = M.fill(layer(), x, y, state.pal, state.slot, e.altKey);
    if (!r.painted && !r.conflictCells.size) state.undo.pop();
    if (r.conflictCells.size) editingPressed() ? explainLocked(r.conflictCells) : explainConflict(r.conflictCells);
    if (r.painted) changed({ palettes: true });
    return;
  }
  try { overlay.setPointerCapture(e.pointerId); } catch {}
  stroke = { last: { x, y }, results: new Set(), conflicts: new Set(), force: e.altKey };
  applyAt(x, y);
  renderStage();
});

overlay.addEventListener('pointermove', e => {
  const { x, y } = eventPixel(e);
  state.hover = { x, y };
  showCursor(x, y);
  if (state.areaDrag) {
    state.areaDrag.x1 = Math.max(0, Math.min(M.CW - 1, x >> 3));
    state.areaDrag.y1 = Math.max(0, Math.min(M.CH - 1, y >> 3));
    renderOverlay();
    return;
  }
  if (stroke) {
    stroke.force = stroke.force || e.altKey;
    lineTo(x, y);
    renderStage();
  } else {
    renderOverlay();
  }
});

overlay.addEventListener('pointerup', () => { if (state.areaDrag) finishAreaDraw(); else endStroke(); });
overlay.addEventListener('pointercancel', endStroke);
overlay.addEventListener('pointerleave', () => {
  state.hover = null;
  $('cursorInfo').textContent = '';
  renderOverlay();
});

function showCursor(x, y) {
  if (x < 0 || y < 0 || x >= M.W || y >= M.H) return;
  const c = M.cellOf(x, y);
  const pal = scene().cellPal[c];
  $('cursorInfo').textContent = `x ${x}, y ${y} · tile ${x >> 3},${y >> 3} · "${palName(pal)}" slot ${M.composed(scene(), shownFrame())[y * M.W + x] + 1}`;
}

// ---- palette rows (shared by background and sprite palettes) ----------------

function paletteRow({ pal, i, selected, isOn, onPick, usageText, canRemove, removeTitle, onRemove, problem, onFix, sprite }) {
  const row = document.createElement('div');
  row.className = 'pal-row' + (selected ? ' selected' : '');

  const name = document.createElement('input');
  name.className = 'pal-name';
  name.value = pal.name;
  name.spellcheck = false;
  let pushed = false;
  name.oninput = () => {
    if (!pushed) { pushUndo(); pushed = true; }
    pal.name = name.value;
    autosave();
  };

  const swatches = document.createElement('div');
  swatches.className = 'swatches';
  pal.colors.forEach((c, s) => {
    const b = document.createElement('button');
    b.className = 'sw' + (isOn(s) ? ' on' : '') + (sprite && s === 0 ? ' transparent' : '');
    b.style.background = hex(c);
    b.title = sprite && s === 0 ? 'Slot 1: transparent on sprites' :
      `Slot ${s + 1}: ${hex(c)}${!sprite && s === 0 ? ' (background color of tiles using this palette)' : ''}`;
    b.onclick = () => onPick(s);
    swatches.appendChild(b);
  });

  const grays = document.createElement('div');
  grays.className = 'grays';
  grays.title = 'How these slots look on an original Game Boy';
  DMG_SHADES.forEach((g, s) => {
    const span = document.createElement('span');
    span.style.background = sprite && s === 0 ? 'transparent' : `rgb(${g})`;
    grays.appendChild(span);
  });

  const usage = document.createElement('span');
  usage.className = 'usage dim';
  usage.textContent = usageText;

  const remove = document.createElement('button');
  remove.className = 'remove';
  remove.textContent = '×';
  remove.disabled = !canRemove;
  remove.title = removeTitle;
  remove.onclick = onRemove;

  row.append(name, swatches, grays, usage, remove);
  if (problem) {
    const warn = document.createElement('div');
    warn.className = 'pal-warn';
    warn.textContent = '⚠ ' + problem + ' ';
    const fix = document.createElement('button');
    fix.textContent = 'Fix order';
    fix.title = 'Sort lightest to darkest. Your picture stays the same.';
    fix.onclick = onFix;
    warn.appendChild(fix);
    row.appendChild(warn);
  }
  return row;
}

function renderPalettes() {
  const list = $('paletteList');
  list.innerHTML = '';
  const p = state.project;
  p.palettes.forEach((pal, i) => {
    const used = M.paletteUsage(p, i);
    const canRemove = used === 0 && p.palettes.length > 1;
    list.appendChild(paletteRow({
      pal, i,
      selected: state.palKind === 'bg' && i === state.pal,
      isOn: s => state.palKind === 'bg' && i === state.pal && s === state.slot,
      onPick: s => { state.palKind = 'bg'; state.pal = i; state.slot = s; renderPalettes(); renderSprites(); syncPicker(); },
      usageText: used ? `${used} tile${used === 1 ? '' : 's'}` : 'unused',
      canRemove,
      removeTitle: canRemove ? 'Remove palette' : used ? `Used by ${used} tiles. Repaint them first.` : 'A project needs at least one palette',
      onRemove: () => {
        pushUndo();
        M.removePalette(p, i);
        if (state.pal >= i && state.pal > 0) state.pal--;
        changed({ palettes: true });
      },
      problem: M.paletteOrderProblem(pal),
      onFix: () => {
        pushUndo();
        M.fixPaletteOrder(p, i);
        if (i === state.pal) state.slot = 0;
        say(`"${pal.name}" sorted lightest to darkest. Your picture didn't change.`);
        changed({ palettes: true });
      },
    }));
  });

  const add = $('addPalette');
  const full = p.palettes.length >= M.MAX_BG_PALETTES;
  add.disabled = full;
  add.innerHTML = `<option value="">${full ? `All ${M.MAX_BG_PALETTES} palettes in use` : '+ Add palette…'}</option>` +
    M.PRESETS.map((pr, k) => `<option value="${k}">${pr.name}</option>`).join('');
  renderMeters();
}

$('addPalette').onchange = e => {
  const k = e.target.value;
  if (k === '') return;
  pushUndo();
  if (M.addPalette(state.project, M.PRESETS[+k])) {
    state.palKind = 'bg';
    state.pal = state.project.palettes.length - 1;
    state.slot = 3;
  }
  changed({ palettes: true });
};

// ---- sprites panel -----------------------------------------------------------

const cursorCanvas = $('cursorCanvas');
const cursorCtx = cursorCanvas.getContext('2d');

function renderSprites() {
  const p = state.project;
  $('spritePanel').hidden = !p.objPalettes.length && !p.cursor;
  const list = $('objPaletteList');
  list.innerHTML = '';
  p.objPalettes.forEach((pal, i) => {
    const usedByCursor = p.cursor && p.cursor.palette === i;
    list.appendChild(paletteRow({
      pal, i, sprite: true,
      selected: state.palKind === 'obj' && i === state.objPal,
      isOn: s => state.palKind === 'obj' && i === state.objPal && s === state.objSlot,
      onPick: s => { state.palKind = 'obj'; state.objPal = i; state.objSlot = s; renderPalettes(); renderSprites(); syncPicker(); },
      usageText: usedByCursor ? 'cursor' : 'unused',
      canRemove: !usedByCursor,
      removeTitle: usedByCursor ? 'The cursor uses this palette' : 'Remove sprite palette',
      onRemove: () => {
        pushUndo();
        p.objPalettes.splice(i, 1);
        if (p.cursor && p.cursor.palette > i) p.cursor.palette--;
        clampSelection();
        changed({ palettes: true });
      },
      problem: M.paletteOrderProblem(pal, true),
      onFix: () => {
        pushUndo();
        M.fixSpritePaletteOrder(p, i);
        say(`"${pal.name}" sorted lightest to darkest. The cursor didn't change.`);
        changed({ palettes: true });
      },
    }));
  });
  drawCursorEditor();
}

function drawCursorEditor() {
  const p = state.project;
  cursorCtx.clearRect(0, 0, 8, 8);
  if (!p.cursor || !p.objPalettes[p.cursor.palette]) return;
  const colors = p.objPalettes[p.cursor.palette].colors;
  for (let i = 0; i < 64; i++) {
    const v = p.cursor.pixels[i];
    if (!v) continue;
    cursorCtx.fillStyle = `rgb(${displayColor(colors[v], v)})`;
    cursorCtx.fillRect(i % 8, (i / 8) | 0, 1, 1);
  }
}

let cursorStroke = false;
function paintCursor(e) {
  const p = state.project;
  if (!p.cursor) return;
  const r = cursorCanvas.getBoundingClientRect();
  const x = Math.floor((e.clientX - r.left) / r.width * 8), y = Math.floor((e.clientY - r.top) / r.height * 8);
  if (x < 0 || y < 0 || x > 7 || y > 7) return;
  const slot = e.buttons & 2 ? 0 : state.palKind === 'obj' ? state.objSlot : 3;
  if (state.palKind === 'obj' && p.cursor.palette !== state.objPal && slot) {
    p.cursor.palette = state.objPal;
    say(`The cursor now uses "${p.objPalettes[state.objPal].name}". A sprite uses one palette.`);
    renderSprites();
  }
  p.cursor.pixels[y * 8 + x] = slot;
  drawCursorEditor();
  renderStage();
}
cursorCanvas.addEventListener('contextmenu', e => e.preventDefault());
cursorCanvas.addEventListener('pointerdown', e => {
  pushUndo();
  cursorStroke = true;
  try { cursorCanvas.setPointerCapture(e.pointerId); } catch {}
  paintCursor(e);
});
cursorCanvas.addEventListener('pointermove', e => { if (cursorStroke) paintCursor(e); });
cursorCanvas.addEventListener('pointerup', () => { if (cursorStroke) { cursorStroke = false; changed(); } });

// ---- scenes panel ------------------------------------------------------------

function selectScene(i) {
  state.scene = i;
  state.frame = 'normal';
  state.areaDraw = false;
  renderScenes();
  renderStage();
  renderMeters();
}

function renderScenes() {
  const p = state.project;
  const list = $('sceneList');
  list.innerHTML = '';
  const reachable = M.reachableScenes(p);
  p.scenes.forEach((sc, i) => {
    const row = document.createElement('div');
    row.className = 'scene-row' + (i === state.scene ? ' selected' : '');
    row.onclick = e => { if (e.target === row || e.target.classList.contains('tag')) selectScene(i); };

    const star = document.createElement('button');
    star.className = 'star' + (p.start === i ? ' on' : '');
    star.textContent = p.start === i ? '★' : '☆';
    star.title = p.start === i ? 'The game starts here' : 'Start the game here';
    star.onclick = () => { pushUndo(); p.start = i; changed({ scenes: true }); };

    const name = document.createElement('input');
    name.value = sc.name;
    name.spellcheck = false;
    name.onfocus = () => { if (state.scene !== i) selectScene(i); };
    let pushed = false;
    name.oninput = () => { if (!pushed) { pushUndo(); pushed = true; } sc.name = name.value; autosave(); };
    name.onchange = () => renderSceneSettings();

    const tag = document.createElement('span');
    tag.className = 'tag dim';
    tag.textContent = !reachable.has(i) ? 'not reachable' : sc.menu ? 'menu' : sc.pressStart ? 'start' : sc.options ? 'options' : sc.back !== null ? 'B ↩' : '';
    if (!reachable.has(i)) tag.title = 'No menu item or B button leads here, so it\'s left out of the ROM. Add a menu item that goes here.';

    const remove = document.createElement('button');
    remove.className = 'remove';
    remove.textContent = '×';
    const refs = M.sceneReferences(p, i);
    remove.disabled = p.scenes.length <= 1 || refs.length > 0;
    remove.title = p.scenes.length <= 1 ? 'A project needs at least one scene' : refs.length ? `Can't remove: ${refs.join('; ')}` : 'Remove scene';
    remove.onclick = () => {
      pushUndo();
      if (M.removeScene(p, i)) { clampSelection(); changed({ scenes: true, palettes: true }); }
    };

    row.append(star, name, tag, remove);
    list.appendChild(row);
  });
  $('addScene').disabled = p.scenes.length >= M.MAX_SCENES;
  $('frameSeg').hidden = !pressArea();
  for (const b of $('frameSeg').children) b.classList.toggle('on', b.dataset.frame === shownFrame());
  renderSceneSettings();
}

$('addScene').onclick = () => {
  pushUndo();
  const i = M.addScene(state.project);
  if (i >= 0) { state.scene = i; changed({ scenes: true }); }
};

function el(tag, props = {}, ...children) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...children);
  return e;
}

function sceneOptions(select, value, { none = null, exclude = -1 } = {}) {
  select.innerHTML = '';
  if (none) select.append(el('option', { value: '', textContent: none }));
  state.project.scenes.forEach((sc, i) => {
    if (i !== exclude) select.append(el('option', { value: String(i), textContent: sc.name }));
  });
  select.value = value === null || value === undefined ? '' : String(value);
}

function numberField(label, value, min, max, onSet, title = '') {
  const input = el('input', { type: 'number', min, max, value, title });
  input.onchange = () => {
    const v = Math.max(min, Math.min(max, parseInt(input.value, 10) || min));
    input.value = v;
    pushUndo();
    onSet(v);
  };
  return el('label', { className: 'field' }, el('span', { textContent: label }), input);
}

function renderSceneSettings() {
  const box = $('sceneSettings');
  box.innerHTML = '';
  const p = state.project, sc = scene(), i = state.scene;

  const notes = el('textarea', { className: 'notes', value: sc.notes || '', placeholder: 'Notes about this scene (only for you; not in the ROM)',
                                 rows: Math.min(10, Math.max(2, (sc.notes || '').split('\n').length + 1)) });
  let pushed = false;
  notes.oninput = () => { if (!pushed) { pushUndo(); pushed = true; } sc.notes = notes.value; autosave(); };
  box.append(notes);

  const back = el('select');
  sceneOptions(back, sc.back, { none: 'does nothing', exclude: i });
  back.onchange = () => {
    pushUndo();
    sc.back = back.value === '' ? null : +back.value;
    if (sc.back !== null) M.ensureMenuSupport(p);
    changed({ scenes: true, palettes: true });
  };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'B button goes to' }), back));

  if (!sc.fight) {
    const slide = el('input', { type: 'checkbox', checked: !!sc.slideIn });
    slide.onchange = () => { pushUndo(); sc.slideIn = slide.checked; changed({ scenes: true }); };
    box.append(el('label', { className: 'field', title: 'The scene scrolls up from the bottom of the screen when it opens, ' +
      'over its background (about 2 seconds).' }, el('span', { textContent: 'Slides in' }), slide));
  }

  if (sc.menu) {
    renderMenuEditor(box, sc, i);
  } else if (sc.pressStart) {
    renderPressEditor(box, sc, i);
  } else if (sc.options) {
    renderOptionsEditor(box, sc, i);
  } else if (sc.fight) {
    renderFightEditor(box, sc, i);
  } else {
    const needOther = p.scenes.length < 2;
    const add = el('button', { className: 'wide', textContent: '+ Add a menu to this scene' });
    add.disabled = needOther;
    add.onclick = () => {
      pushUndo();
      M.ensureMenuSupport(p);
      sc.menu = M.newMenu(p, i);
      changed({ scenes: true, palettes: true });
    };
    const press = el('button', { className: 'wide', textContent: '+ Make this a press-start screen' });
    press.disabled = needOther;
    press.onclick = () => {
      pushUndo();
      if (!p.transition) p.transition = { color: 'white', frames: 3 };
      sc.pressStart = M.newPressStart(p, i);
      changed({ scenes: true });
    };
    const opts = el('button', { className: 'wide', textContent: '+ Make this an options screen' });
    opts.disabled = needOther;
    opts.onclick = () => {
      pushUndo();
      M.ensureMenuSupport(p);
      sc.options = M.newOptions(p, i);
      changed({ scenes: true, palettes: true });
    };
    if (needOther) add.title = press.title = opts.title = 'Add another scene first, for it to go to';
    box.append(add, press, opts);
  }

  renderTextsEditor(box, sc);

  if (p.transition) {
    box.append(el('h4', { textContent: 'Transitions (all scenes)' }));
    const color = el('select');
    color.append(el('option', { value: 'white', textContent: 'white' }), el('option', { value: 'black', textContent: 'black' }));
    color.value = p.transition.color;
    color.onchange = () => { pushUndo(); p.transition.color = color.value; changed(); };
    box.append(el('label', { className: 'field' }, el('span', { textContent: 'Fade to' }), color));
    box.append(numberField('Frames per fade step', p.transition.frames, 1, 30, v => { p.transition.frames = v; changed(); },
                           '4 steps per fade; 60 frames = 1 second'));
    if (p.transition.color === 'black') {
      box.append(el('p', { className: 'warn-text', textContent: 'The screen shows white for a moment while a scene loads, so fading to white looks smoother.' }));
    }
  }
}

// Free text labels in the built-in font, baked into the scene's tiles at build time.
function renderTextsEditor(box, sc) {
  const p = state.project;
  sc.texts = sc.texts || [];
  box.append(el('h4', { textContent: 'Text' }));
  sc.texts.forEach((t, n) => {
    const label = el('input', { value: t.label, maxLength: M.CW - t.x, spellcheck: false });
    let pushed = false;
    label.oninput = () => {
      if (!pushed) { pushUndo(); pushed = true; }
      const clean = M.cleanLabel(label.value).slice(0, M.CW - t.x);
      if (clean !== label.value) label.value = clean;
      t.label = clean || ' ';
      renderStage(); renderMeters(); autosave(); scheduleMeasure();
    };
    label.onchange = () => renderSceneSettings();
    const remove = el('button', { textContent: '×', title: 'Remove this text' });
    remove.onclick = () => { pushUndo(); sc.texts.splice(n, 1); changed({ scenes: true }); };
    box.append(el('div', { className: 'menu-items' }, el('div', { className: 'item' }, label, remove)));
    box.append(numberField('Column', t.x, 0, M.CW - t.label.length, v => { t.x = v; changed({ scenes: true }); }));
    box.append(numberField('Row', t.y, 0, M.CH - 1, v => { t.y = v; changed({ scenes: true }); }));
    const pal = p.palettes[sc.cellPal[t.y * M.CW + t.x]];
    box.append(el('div', { className: 'field' }, el('span', { textContent: 'Text color (slot)' }),
                  slotButtons(pal, t.textSlot, k => { pushUndo(); t.textSlot = k; changed({ scenes: true }); })));
  });
  const add = el('button', { className: 'wide', textContent: '+ Add text' });
  add.onclick = () => { pushUndo(); sc.texts.push({ label: 'TEXT', x: 1, y: 16, textSlot: 3 }); changed({ scenes: true }); };
  box.append(add);
}

function slotButtons(pal, current, onPick) {
  const slots = el('div', { className: 'slots' });
  for (let k = 0; k < 4; k++) {
    const b = el('button', { className: current === k ? 'on' : '', title: `Slot ${k + 1} of each tile's palette` });
    b.style.background = hex(pal.colors[k]);
    b.onclick = () => onPick(k);
    slots.append(b);
  }
  return slots;
}

function renderPressEditor(box, sc, i) {
  const p = state.project, ps = sc.pressStart;
  box.append(el('h4', { textContent: 'Press-start screen' }));

  const target = el('select');
  sceneOptions(target, ps.target, { exclude: i });
  target.onchange = () => { pushUndo(); ps.target = +target.value; changed({ scenes: true }); };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'Start goes to' }), target));

  // Flash area
  const a = ps.area;
  box.append(el('div', { className: 'area-info', textContent: a
    ? `Flash area: ${a.w}×${a.h} tiles at column ${a.x}, row ${a.y} (${a.w * a.h}/${M.MAX_FLASH_TILES})`
    : 'No flash area yet. Draw one to make part of the screen flash when Start is pressed.' }));
  const draw = el('button', { textContent: state.areaDraw ? 'Drag on the stage…' : a ? 'Redraw area' : 'Draw flash area',
                              className: state.areaDraw ? 'armed' : '' });
  draw.onclick = () => armAreaDraw(!state.areaDraw);
  const buttons = el('div', { className: 'row-buttons' }, draw);
  if (a) {
    const editPressed = el('button', { textContent: state.frame === 'pressed' ? 'Back to Normal' : 'Paint Pressed frame' });
    editPressed.onclick = () => setFrame(state.frame === 'pressed' ? 'normal' : 'pressed');
    const clear = el('button', { textContent: 'Remove area' });
    clear.onclick = () => { pushUndo(); ps.area = null; setFrame('normal'); changed({ scenes: true }); };
    buttons.append(editPressed, clear);
  }
  box.append(buttons);
  if (a) box.append(numberField('Flashes', ps.flashes, 1, 8, v => { ps.flashes = v; changed(); }, 'How many times the area flips to Pressed (it ends Pressed)'));

  // Prompt
  const has = el('input', { type: 'checkbox', checked: !!ps.prompt });
  has.onchange = () => {
    pushUndo();
    ps.prompt = has.checked ? { label: 'PRESS START', x: 4, y: 13, textSlot: 3, blink: true } : null;
    changed({ scenes: true });
  };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'Prompt text' }), has));
  if (ps.prompt) {
    const pr = ps.prompt;
    const label = el('input', { value: pr.label, maxLength: M.CW - pr.x, spellcheck: false });
    let pushed = false;
    label.oninput = () => {
      if (!pushed) { pushUndo(); pushed = true; }
      const clean = M.cleanLabel(label.value).slice(0, M.CW - pr.x);
      if (clean !== label.value) label.value = clean;
      pr.label = clean || 'PRESS START';
      renderStage(); renderMeters(); autosave(); scheduleMeasure();
    };
    label.onchange = () => renderSceneSettings();
    box.append(el('div', { className: 'menu-items' }, el('div', { className: 'item' }, label)));
    box.append(numberField('Column', pr.x, 0, M.CW - pr.label.length, v => { pr.x = v; changed({ scenes: true }); }));
    box.append(numberField('Row', pr.y, 0, M.CH - 1, v => { pr.y = v; changed({ scenes: true }); }));
    const pal = p.palettes[sc.cellPal[pr.y * M.CW + pr.x]];
    box.append(el('div', { className: 'field' }, el('span', { textContent: 'Text color (slot)' }),
                  slotButtons(pal, pr.textSlot, k => { pushUndo(); pr.textSlot = k; changed({ scenes: true }); })));
    const blink = el('input', { type: 'checkbox', checked: pr.blink });
    blink.onchange = () => { pushUndo(); pr.blink = blink.checked; changed(); };
    box.append(el('label', { className: 'field' }, el('span', { textContent: 'Blink while waiting' }), blink));
  }

  for (const problem of M.pressStartProblems(p, i)) box.append(el('p', { className: 'warn-text', textContent: '⚠ ' + problem }));
  const remove = el('button', { className: 'wide', textContent: 'Remove press-start' });
  remove.onclick = () => { pushUndo(); sc.pressStart = null; setFrame('normal'); changed({ scenes: true }); };
  box.append(remove);
}

function renderFightEditor(box, sc, i) {
  const p = state.project, ft = sc.fight;
  box.append(el('h4', { textContent: 'Fight' }));
  for (const [key, label] of [['win', 'Winning goes to'], ['lose', 'Losing goes to']]) {
    const sel = el('select');
    sceneOptions(sel, ft[key], { exclude: i });
    sel.onchange = () => { pushUndo(); ft[key] = +sel.value; changed({ scenes: true }); };
    box.append(el('label', { className: 'field' }, el('span', { textContent: label }), sel));
  }
  const pose = el('select');
  for (const name of M.FIGHT_POSES) pose.append(el('option', { value: name, textContent: name.replace('_', ' ') }));
  pose.value = ft.rival.poses[state.pose] ? state.pose : 'idle';
  pose.onchange = () => { state.pose = pose.value; renderStage(); };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'Show rival pose' }), pose));

  box.append(el('p', { className: 'area-info', textContent:
    'Art: download a sheet, draw over it in any pixel editor (keep the frame size), and import it back. ' +
    `Rival frames are ${M.FIGHT_W * 8}x${M.FIGHT_H * 8} in this order: ${M.FIGHT_POSES.join(', ')}. ` +
    `Player frames are ${PW}x${PH} on a transparent background: ${PLAYER_POSES.join(', ')}.` }));
  const file = el('input', { type: 'file', accept: 'image/png,image/gif,image/bmp', hidden: true });
  let target = null;
  file.onchange = async () => {
    const f = file.files[0];
    file.value = '';
    if (!f) return;
    try {
      const img = await readImage(f);
      pushUndo();
      if (target === 'rival') {
        const mat = p.palettes[ft.rival.palettes.s].colors[0];
        const r = importRival(img, mat);
        ft.rival.poses = r.poses;
        ['s', 'g', 'h'].forEach((kind, k) => { p.palettes[ft.rival.palettes[kind]].colors = r.palettes[k].map(c => c.slice()); });
        say(`Imported ${M.FIGHT_POSES.length} rival poses with 3 palettes picked from the art` +
            (r.changed ? `; ${r.changed} tiles had a color moved to fit one palette per tile.` : '.'));
      } else {
        const r = importPlayer(img);
        ft.player.poses = r.poses;
        const pal = p.objPalettes[ft.player.palette];
        pal.colors = [pal.colors[0], ...r.colors.map(c => c.slice())];
        say(`Imported ${PLAYER_POSES.length} player poses` + (r.changed ? `; ${r.changed} pixels moved to the 3 sprite colors.` : '.'));
      }
      changed({ scenes: true, palettes: true });
    } catch (err) {
      say(err.message);
    }
  };
  const btn = (text, onclick) => { const b = el('button', { textContent: text }); b.onclick = onclick; return b; };
  const save = async (blob, name) => download(`${fileBase()}-${name}.png`, blob, 'image/png');
  box.append(el('div', { className: 'row-buttons' },
    btn('Download rival sheet', async () => save(await rivalSheet(ft, p.palettes), 'rival')),
    btn('Import rival sheet…', () => { target = 'rival'; file.click(); })));
  box.append(el('div', { className: 'row-buttons' },
    btn('Download player sheet', async () => save(await playerSheet(ft, p.objPalettes[ft.player.palette].colors), 'player')),
    btn('Import player sheet…', () => { target = 'player'; file.click(); })));
  box.append(file);
  for (const problem of M.fightProblems(p, i)) box.append(el('p', { className: 'warn-text', textContent: '⚠ ' + problem }));
}

function renderOptionsEditor(box, sc, i) {
  const p = state.project, o = sc.options;
  box.append(el('h4', { textContent: 'Options screen' }));
  box.append(el('p', { className: 'area-info', textContent: 'Up/down picks a row, left/right changes it (holding repeats), Start or A continues. Values stay in RAM for gameplay.' }));

  const target = el('select');
  sceneOptions(target, o.target, { exclude: i });
  target.onchange = () => { pushUndo(); o.target = +target.value; changed({ scenes: true }); };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'Start goes to' }), target));
  const firstCell = o.rows.length ? o.rows[0].labelY * M.CW + o.rows[0].labelX : 0;
  box.append(el('div', { className: 'field' }, el('span', { textContent: 'Text color (slot)' }),
                slotButtons(p.palettes[sc.cellPal[firstCell]], o.textSlot, k => { pushUndo(); o.textSlot = k; changed({ scenes: true }); })));

  o.rows.forEach((row, n) => {
    const head = el('div', { className: 'option-head' });
    const label = el('input', { value: row.label, spellcheck: false, title: 'Row label (also its name for gameplay)' });
    let pushed = false;
    label.oninput = () => {
      if (!pushed) { pushUndo(); pushed = true; }
      const clean = M.cleanLabel(label.value).slice(0, M.CW - row.labelX);
      if (clean !== label.value) label.value = clean;
      row.label = clean || 'OPTION';
      renderStage(); renderMeters(); autosave(); scheduleMeasure();
    };
    label.onchange = () => { const moved = M.fitOptionRow(row); if (moved) { say(moved); changed({ scenes: true }); } else renderSceneSettings(); };
    const kind = el('select');
    kind.append(el('option', { value: 'choice', textContent: 'choices' }), el('option', { value: 'number', textContent: 'number' }));
    kind.value = row.kind;
    kind.onchange = () => {
      pushUndo();
      if (kind.value === 'number') Object.assign(row, { kind: 'number', min: 0, max: 9, digits: 1, value: 0, choices: undefined });
      else Object.assign(row, { kind: 'choice', choices: ['ON', 'OFF'], value: 0, min: undefined, max: undefined, digits: undefined, slider: undefined });
      M.fitOptionRow(row);
      changed({ scenes: true });
    };
    const remove = el('button', { className: 'remove', textContent: '×', title: 'Remove row' });
    remove.disabled = o.rows.length <= 1;
    remove.onclick = () => { pushUndo(); o.rows.splice(n, 1); changed({ scenes: true }); };
    head.append(label, kind, remove);
    box.append(head);
    box.append(el('div', { className: 'area-info', textContent: `Gameplay reads it as ${M.optionSymbol(row.label)}` }));

    if (row.kind === 'choice') {
      const choices = el('input', { value: row.choices.join(', '), spellcheck: false, title: '2 to 6 choices, separated by commas' });
      choices.onchange = () => {
        const list = choices.value.split(',').map(c => M.cleanLabel(c.trim())).filter(Boolean).slice(0, 6);
        if (list.length < 2) { say('A choice row needs at least 2 choices, separated by commas.', 'warn'); renderSceneSettings(); return; }
        const width = list.reduce((n, c) => n + c.length, 0) + list.length - 1;
        if (width > M.CW) { say(`Those choices need ${width} characters in a row; a line holds ${M.CW}. Try shorter words.`, 'warn'); renderSceneSettings(); return; }
        pushUndo();
        row.choices = list;
        row.value = Math.min(row.value, list.length - 1);
        const moved = M.fitOptionRow(row);
        if (moved) say(moved);
        changed({ scenes: true });
      };
      box.append(el('label', { className: 'field' }, el('span', { textContent: 'Choices' }), choices));
      const def = el('select');
      row.choices.forEach((c, k) => def.append(el('option', { value: String(k), textContent: c })));
      def.value = String(row.value);
      def.onchange = () => { pushUndo(); row.value = +def.value; changed({ scenes: true }); };
      box.append(el('label', { className: 'field' }, el('span', { textContent: 'Starts at' }), def));
    } else {
      box.append(numberField('Smallest', row.min, 0, 98, v => { row.min = v; row.max = Math.max(row.max, v + 1); row.digits = row.max > 9 ? 2 : 1; row.value = Math.max(row.min, Math.min(row.max, row.value)); changed({ scenes: true }); }));
      box.append(numberField('Largest', row.max, 1, 99, v => { row.max = Math.max(v, row.min + 1); row.digits = row.max > 9 ? 2 : 1; row.value = Math.min(row.value, row.max); M.fitOptionRow(row); changed({ scenes: true }); }));
      box.append(numberField('Starts at', row.value, row.min, row.max, v => { row.value = v; changed({ scenes: true }); }));
      const slider = el('input', { type: 'checkbox', checked: !!row.slider });
      slider.onchange = () => {
        pushUndo();
        row.slider = slider.checked ? { x0: row.labelX * 8, x1: Math.min(M.W - 8, row.labelX * 8 + 100), y: Math.min(M.H - 8, (row.labelY + 2) * 8) } : undefined;
        changed({ scenes: true });
      };
      box.append(el('label', { className: 'field' }, el('span', { textContent: 'Slider marker' }), slider));
      if (row.slider) {
        box.append(numberField('Slider left (px)', row.slider.x0, 0, M.W - 9, v => { row.slider.x0 = v; row.slider.x1 = Math.max(row.slider.x1, v + 1); changed({ scenes: true }); }));
        box.append(numberField('Slider right (px)', row.slider.x1, 1, M.W - 8, v => { row.slider.x1 = Math.max(v, row.slider.x0 + 1); changed({ scenes: true }); }));
        box.append(numberField('Slider top (px)', row.slider.y, 0, M.H - 8, v => { row.slider.y = v; changed({ scenes: true }); }));
      }
    }
    box.append(el('div', { className: 'pos-grid' },
      numberField('Label column', row.labelX, 2, M.CW - row.label.length, v => { row.labelX = v; changed({ scenes: true }); }),
      numberField('Label row', row.labelY, 0, M.CH - 1, v => { row.labelY = v; changed({ scenes: true }); }),
      numberField('Values column', row.valueX, 0, M.CW - M.optionWidth(row), v => { row.valueX = v; changed({ scenes: true }); }),
      numberField('Values row', row.valueY, 0, M.CH - 1, v => { row.valueY = v; changed({ scenes: true }); })));
  });

  const add = el('button', { className: 'wide', textContent: '+ Add row' });
  add.disabled = o.rows.length >= M.MAX_OPTION_ROWS;
  add.onclick = () => {
    pushUndo();
    const last = o.rows[o.rows.length - 1];
    const y = Math.min(M.CH - 1, (last ? Math.max(last.labelY, last.valueY) : 2) + 2);
    let name = 'OPTION', k = 2;
    while (o.rows.some(r => r.label === name)) name = `OPTION ${k++}`;
    o.rows.push({ label: name, kind: 'choice', choices: ['ON', 'OFF'], value: 0, labelX: 3, labelY: y, valueX: 12, valueY: y });
    changed({ scenes: true });
  };
  box.append(add);
  for (const problem of M.optionsProblems(p, i)) box.append(el('p', { className: 'warn-text', textContent: '⚠ ' + problem }));
  const remove = el('button', { className: 'wide', textContent: 'Remove options screen' });
  remove.onclick = () => { pushUndo(); sc.options = null; changed({ scenes: true }); };
  box.append(remove);
}

function renderMenuEditor(box, sc, i) {
  const p = state.project, m = sc.menu;
  box.append(el('h4', { textContent: 'Menu' }));

  const items = el('div', { className: 'menu-items' });
  m.items.forEach((it, n) => {
    const label = el('input', { value: it.label, maxLength: M.CW - m.x, spellcheck: false, title: 'Uppercase letters, digits and . , ! ? - : \' / ( ) & +' });
    let pushed = false;
    label.oninput = () => {
      if (!pushed) { pushUndo(); pushed = true; }
      const clean = M.cleanLabel(label.value).slice(0, M.CW - m.x);
      if (clean !== label.value) label.value = clean;
      it.label = clean;
      renderStage(); renderMeters(); autosave(); scheduleMeasure();
    };
    label.onchange = () => renderSceneSettings();
    const target = el('select', { title: 'Scene this item goes to' });
    sceneOptions(target, it.target, { exclude: i });
    target.onchange = () => { pushUndo(); it.target = +target.value; changed({ scenes: true }); };
    const remove = el('button', { className: 'remove', textContent: '×', title: 'Remove item' });
    remove.disabled = m.items.length <= 1;
    remove.onclick = () => { pushUndo(); m.items.splice(n, 1); changed({ scenes: true }); };
    items.append(el('div', { className: 'item' }, label, target, remove));
  });
  box.append(items);
  const addItem = el('button', { className: 'wide', textContent: '+ Add item' });
  addItem.disabled = m.items.length >= M.MAX_MENU_ITEMS || m.y + m.items.length * m.spacing >= M.CH;
  addItem.title = addItem.disabled ? 'No more room on screen' : '';
  addItem.onclick = () => {
    pushUndo();
    const other = p.scenes.findIndex((_, k) => k !== i);
    m.items.push({ label: 'ITEM', target: other });
    changed({ scenes: true });
  };
  box.append(addItem);

  const longest = Math.max(1, ...m.items.map(it => it.label.length));
  box.append(numberField('Column', m.x, 2, M.CW - longest, v => { m.x = v; changed({ scenes: true }); }, 'Tile column of the labels; the cursor sits to the left'));
  box.append(numberField('Row', m.y, 0, M.CH - 1 - (m.items.length - 1) * m.spacing, v => { m.y = v; changed({ scenes: true }); }));
  box.append(numberField('Spacing', m.spacing, 1, Math.max(1, Math.min(4, Math.floor((M.CH - 1 - m.y) / Math.max(1, m.items.length - 1)))),
                         v => { m.spacing = v; changed({ scenes: true }); }, 'Rows between items'));

  // Text color: a slot, so it's valid whatever palette each tile uses.
  const firstCell = m.y * M.CW + m.x;
  const pal = p.palettes[sc.cellPal[firstCell]];
  const slots = el('div', { className: 'slots' });
  for (let s = 0; s < 4; s++) {
    const b = el('button', { className: m.textSlot === s ? 'on' : '', title: `Slot ${s + 1} of each tile's palette` });
    b.style.background = hex(pal.colors[s]);
    b.onclick = () => { pushUndo(); m.textSlot = s; changed({ scenes: true }); };
    slots.append(b);
  }
  box.append(el('div', { className: 'field' }, el('span', { textContent: 'Text color (slot)' }), slots));

  const anim = el('select');
  anim.append(el('option', { value: 'bob', textContent: 'bob' }), el('option', { value: 'none', textContent: 'still' }));
  anim.value = m.cursorAnimation;
  anim.onchange = () => { pushUndo(); m.cursorAnimation = anim.value; changed(); };
  box.append(el('label', { className: 'field' }, el('span', { textContent: 'Cursor' }), anim));
  box.append(numberField('Blinks when chosen', m.blinks, 0, 8, v => { m.blinks = v; changed(); }));

  for (const problem of M.menuProblems(p, i)) box.append(el('p', { className: 'warn-text', textContent: '⚠ ' + problem }));

  const remove = el('button', { className: 'wide', textContent: 'Remove menu' });
  remove.onclick = () => { pushUndo(); sc.menu = null; changed({ scenes: true }); };
  box.append(remove);
}

// ---- meters ----------------------------------------------------------------

function meter(el, label, n, max) {
  el.textContent = `${label} ${n}/${max}`;
  el.className = 'meter ' + (n > max ? 'error' : n >= max * 0.85 ? 'warn' : 'ok');
}

function renderMeters() {
  const p = state.project;
  meter($('palMeter'), `"${scene().name}" BG palettes`, new Set(scene().cellPal).size, M.SCENE_BG_PALETTES);
  $('palMeter').title = `Background palettes this scene uses: the hardware holds ${M.SCENE_BG_PALETTES} at once. ` +
    `The project has ${p.palettes.length} of ${M.MAX_BG_PALETTES}. A fight or puzzle scene uses palettes 1-8 only.`;
  meter($('objMeter'), 'Sprite palettes', p.objPalettes.length, M.MAX_OBJ_PALETTES);
  meter($('sceneMeter'), 'Scenes', p.scenes.length, M.MAX_SCENES);
  const tiles = M.uniqueTileCount(scene());
  meter($('tileMeter'), `"${scene().name}" tiles`, tiles, M.MAX_TILES);
  $('tileMeter').title = 'Unique 8×8 tiles in this scene, including menu text and its blink frames. ' +
    'Identical patterns are stored once, even with different palettes, so repeating patterns is free.';
}

// ---- color picker ----------------------------------------------------------

const sv = $('svPick'), hue = $('huePick');
const svCtx = sv.getContext('2d'), hueCtx = hue.getContext('2d');
let hsv = [0, 0, 1];
let editing = false;

function currentPalette() {
  return state.palKind === 'obj' ? state.project.objPalettes[state.objPal] : state.project.palettes[state.pal];
}
const currentSlot = () => (state.palKind === 'obj' ? state.objSlot : state.slot);
const currentColor = () => currentPalette().colors[currentSlot()];

function setCurrentColor(c5, fromHsv = false) {
  const pal = currentPalette();
  if (sameColor(pal.colors[currentSlot()], c5) && fromHsv) { drawPicker(); return; }
  pal.colors[currentSlot()] = c5;
  if (!fromHsv) hsv = rgbToHsv(to8(c5));
  renderPalettes();
  renderSprites();
  renderStage();
  syncPicker(fromHsv);
  autosave();
}

function syncPicker(keepHsv = false) {
  const c = currentColor();
  if (!keepHsv) hsv = rgbToHsv(to8(c));
  const slot = currentSlot();
  $('pickerTitle').textContent = state.palKind === 'obj'
    ? `Sprite "${currentPalette().name}" · slot ${slot + 1}${slot === 0 ? ' (transparent, color unused)' : ''}`
    : `"${palName(state.pal)}" · slot ${slot + 1}`;
  for (const [id, v] of [['inR', c[0]], ['inG', c[1]], ['inB', c[2]]]) {
    if (document.activeElement !== $(id)) $(id).value = v;
  }
  if (document.activeElement !== $('inHex')) $('inHex').value = hex(c);
  $('pvColor').style.background = hex(c);
  $('pvScreen').style.background = `rgb(${gbcScreen(c)})`;
  $('pvDmg').style.background = `rgb(${DMG_SHADES[slot]})`;
  drawPicker();
}

function drawPicker() {
  const w = sv.width, h = sv.height;
  const img = svCtx.createImageData(w, h);
  // Draw the square already snapped to Game Boy Color colors, so what you see is what you get.
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const c = to8(from8(hsvToRgb([hsv[0], x / (w - 1), 1 - y / (h - 1)])));
      const i = (y * w + x) * 4;
      img.data[i] = c[0]; img.data[i + 1] = c[1]; img.data[i + 2] = c[2]; img.data[i + 3] = 255;
    }
  }
  svCtx.putImageData(img, 0, 0);
  const mx = hsv[1] * (w - 1), my = (1 - hsv[2]) * (h - 1);
  svCtx.strokeStyle = hsv[2] > 0.5 ? '#000' : '#fff';
  svCtx.lineWidth = 2;
  svCtx.beginPath(); svCtx.arc(mx, my, 5, 0, Math.PI * 2); svCtx.stroke();

  for (let x = 0; x < hue.width; x++) {
    hueCtx.fillStyle = `rgb(${hsvToRgb([x / hue.width * 360, 1, 1])})`;
    hueCtx.fillRect(x, 0, 1, hue.height);
  }
  const hx = hsv[0] / 360 * hue.width;
  hueCtx.fillStyle = '#fff';
  hueCtx.fillRect(hx - 1, 0, 3, hue.height);
}

function beginEdit() {
  if (!editing) { pushUndo(); editing = true; }
}
function endEdit() {
  if (editing) { editing = false; scheduleMeasure(); }
}

function dragOn(canvas, onPoint) {
  canvas.addEventListener('pointerdown', e => {
    beginEdit();
    try { canvas.setPointerCapture(e.pointerId); } catch {}
    onPoint(e);
    const move = ev => onPoint(ev);
    const up = () => {
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      endEdit();
    };
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
  });
}

const clamp01 = v => Math.min(1, Math.max(0, v));
dragOn(sv, e => {
  const r = sv.getBoundingClientRect();
  hsv = [hsv[0], clamp01((e.clientX - r.left) / r.width), 1 - clamp01((e.clientY - r.top) / r.height)];
  setCurrentColor(from8(hsvToRgb(hsv)), true);
});
dragOn(hue, e => {
  const r = hue.getBoundingClientRect();
  hsv = [clamp01((e.clientX - r.left) / r.width) * 359.9, hsv[1], hsv[2]];
  setCurrentColor(from8(hsvToRgb(hsv)), true);
});

for (const [id, ch] of [['inR', 0], ['inG', 1], ['inB', 2]]) {
  $(id).addEventListener('focus', beginEdit);
  $(id).addEventListener('blur', endEdit);
  $(id).addEventListener('input', () => {
    const v = parseInt($(id).value, 10);
    if (!(v >= 0 && v <= 31)) return;
    const c = [...currentColor()];
    c[ch] = v;
    setCurrentColor(c);
  });
}
$('inHex').addEventListener('focus', beginEdit);
$('inHex').addEventListener('blur', () => { endEdit(); syncPicker(); });
$('inHex').addEventListener('change', () => {
  const c = parseHex($('inHex').value);
  if (c) setCurrentColor(c);
  else say('That isn\'t a hex color. Try something like #4080ff.', 'warn');
  syncPicker();
});

// ---- tools, views, keyboard ------------------------------------------------

function setTool(tool) {
  state.tool = tool;
  for (const b of $('tools').children) b.classList.toggle('on', b.dataset.tool === tool);
  $('toolName').textContent = TOOL_NAMES[tool];
  overlay.style.cursor = tool === 'picker' ? 'copy' : 'crosshair';
  renderOverlay();
}
$('tools').onclick = e => { const b = e.target.closest('button'); if (b) setTool(b.dataset.tool); };

function setFrame(frame) {
  state.frame = frame;
  const seg = $('frameSeg');
  seg.hidden = !pressArea();
  for (const b of seg.children) b.classList.toggle('on', b.dataset.frame === shownFrame());
  if (frame === 'pressed' && pressArea()) say('Painting the Pressed frame: only the flash area, and each tile keeps its palette.');
  renderStage();
  renderSceneSettings();
}
$('frameSeg').onclick = e => { const b = e.target.closest('button'); if (b) setFrame(b.dataset.frame); };

function setView(view) {
  state.view = view;
  for (const b of $('viewSeg').children) b.classList.toggle('on', b.dataset.view === view);
  renderStage();
  drawCursorEditor();
}
$('viewSeg').onclick = e => { const b = e.target.closest('button'); if (b) setView(b.dataset.view); };
$('gridToggle').onchange = renderOverlay;
$('palOverlay').onchange = renderOverlay;
window.addEventListener('resize', renderOverlay);

const TEST_KEYS = {
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
  x: 'A', X: 'A', z: 'B', Z: 'B', Enter: 'start', Shift: 'select',
};

document.addEventListener('keydown', e => {
  if ($('testDialog').open && player && TEST_KEYS[e.key] && !(e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    audioContext();
    player.setButton(TEST_KEYS[e.key], true);
    return;
  }
  if (e.key === 'Escape' && state.areaDraw) { state.areaDrag = null; armAreaDraw(false); renderOverlay(); return; }
  const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName);
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 'Enter') { e.preventDefault(); audioContext(); openTest(); return; }
  if (typing || document.querySelector('dialog[open]')) return;
  if (mod && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    e.shiftKey ? undoRedo(state.redo, state.undo) : undoRedo(state.undo, state.redo);
    return;
  }
  if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); undoRedo(state.redo, state.undo); return; }
  if (mod) return;
  const tools = { b: 'pencil', e: 'eraser', g: 'fill', i: 'picker', t: 'tilepal' };
  const k = e.key.toLowerCase();
  if (tools[k]) setTool(tools[k]);
  else if ('1234'.includes(e.key)) { state.palKind = 'bg'; state.slot = +e.key - 1; renderPalettes(); renderSprites(); syncPicker(); }
  else if (e.key === '[' || e.key === ']') {
    const n = state.project.palettes.length;
    state.palKind = 'bg';
    state.pal = (state.pal + (e.key === ']' ? 1 : n - 1)) % n;
    renderPalettes(); renderSprites(); syncPicker();
  }
});

document.addEventListener('keyup', e => {
  if (player && TEST_KEYS[e.key]) player.setButton(TEST_KEYS[e.key], false);
});

// ---- files -----------------------------------------------------------------

let renaming = false;
$('projectName').addEventListener('blur', () => { renaming = false; });
$('projectName').addEventListener('input', e => {
  if (!renaming) { pushUndo(); renaming = true; }
  state.project.name = e.target.value;
  autosave();
});

function loadProject(p) {
  M.useFont(p.font || 'classic');
  state.project = p;
  state.scene = p.start;
  state.palKind = 'bg';
  state.pal = 0;
  state.slot = 3;
  state.objPal = 0;
  state.objSlot = 3;
  state.undo = [];
  state.redo = [];
  state.frame = 'normal';
  state.areaDraw = false;
  $('projectName').value = p.name;
  changed({ palettes: true, scenes: true });
  checkSampleVersion();
}

$('newBtn').onclick = () => $('newDialog').showModal();
$('newCancel').onclick = () => $('newDialog').close();
$('newPressStart').onclick = () => {
  $('newDialog').close();
  loadProject(M.newPressStartTemplate());
  say('Press Start template ready. Press ▶ Test to try it, then paint your own title and Pressed frame.');
};
$('newTemplate').onclick = () => {
  $('newDialog').close();
  loadProject(M.newTitleTemplate());
  say('Title + Options template ready. Press ▶ Test to try it, then paint your own title.');
};
$('newBlank').onclick = () => { $('newDialog').close(); loadProject(M.newProject()); };
$('newClinic').onclick = () => {
  $('newDialog').close();
  loadProject(capsuleClinic());
  say('Capsule Clinic loaded. Each scene has notes on how it was built: click through the scenes on the right.');
};
$('newMacJoe').onclick = () => {
  $('newDialog').close();
  loadProject(macVsJoe());
  say('Joe vs Mac loaded. Press ▶ Test to fight. The Fight scene\'s notes explain how Joe works.');
};
$('saveBtn').onclick = () => {
  download(`${fileBase()}.gbstage.json`, JSON.stringify(M.serialize(state.project)), 'application/json');
  say('Project file downloaded.');
};
$('openBtn').onclick = () => $('openFile').click();
$('openFile').onchange = async e => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  try {
    loadProject(M.deserialize(JSON.parse(await file.text())));
    say(`Opened ${file.name}.`);
  } catch (err) {
    say(`Couldn't open ${file.name}: ${err.message}`, 'warn');
  }
};

async function buildRom() {
  let res;
  try {
    res = await fetch('/api/build', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gbstage': '1' },
      body: JSON.stringify(M.serialize(state.project)),
    }).then(checkStamp).then(r => r.json());
  } catch {
    throw Object.assign(new Error('build failed'), { errors: ["Can't reach the gbstage server. Is `python3 -m gbstage serve` running?"] });
  }
  if (!res.ok) throw Object.assign(new Error('build failed'), { errors: res.errors });
  const build = { rom: Uint8Array.from(atob(res.rom), ch => ch.charCodeAt(0)), asm: res.asm, stats: res.stats, report: res.report };
  showMeasurements(build.report);
  return build;
}

// ---- measurements ----------------------------------------------------------

// Rebuild quietly a moment after editing stops, so the ROM and CPU meters always describe the current project.
let measureTimer = 0;
let measureSeq = 0;
function scheduleMeasure() {
  clearTimeout(measureTimer);
  measureTimer = setTimeout(async () => {
    const seq = ++measureSeq;
    try {
      const res = await fetch('/api/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Gbstage': '1' },
        body: JSON.stringify(M.serialize(state.project)),
      }).then(checkStamp).then(r => r.json());
      if (seq !== measureSeq) return;
      if (res.ok) showMeasurements(res.report);
      else showBuildProblem(res.errors);
    } catch {
      // Server unreachable; the System check chip already says so.
    }
  }, 900);
}

const devices = report => ['color', 'original'].filter(d => report[d] && !report[d].error);
const fmt = n => (typeof n === 'number' ? n.toLocaleString() : '–');   // a missing measurement shows as a dash, never an error

function showMeasurements(report) {
  const rom = $('romMeter'), cpu = $('cpuMeter');
  const b = report.bytes;
  rom.hidden = cpu.hidden = false;
  meter(rom, 'ROM', b.rom_used, b.rom_size);   // sets the color; the text is replaced below
  rom.textContent = `ROM ${(b.rom_used / 1024).toFixed(1)}/${b.rom_size / 1024} KB`;
  rom.title = `${fmt(b.rom_used)} bytes used: code ${fmt(b.code)}, data ${fmt(b.data)}, header ${b.header}`;

  const measured = devices(report);
  const violations = measured.flatMap(d => report[d].violations);
  const unmeasured = ['color', 'original'].filter(d => report[d]?.error);
  if (violations.length) {
    cpu.textContent = `⚠ ${violations.length} hardware issue${violations.length === 1 ? '' : 's'}`;
    cpu.className = 'meter error';
    cpu.title = violations.map(v => v.message).join('\n');
    return;
  }
  if (unmeasured.length) {
    cpu.textContent = 'CPU not measured';
    cpu.className = 'meter warn';
    cpu.title = unmeasured.map(d => report[d].error).join('\n');
    return;
  }
  const load = Math.max(...measured.map(d => report[d].frame_load));
  cpu.textContent = `CPU ${load < 1 ? load.toFixed(2) : load.toFixed(0)}% per frame`;
  cpu.className = 'meter ' + (load > 100 ? 'error' : load > 85 ? 'warn' : 'ok');
  cpu.title = measured.map(d => `${d === 'color' ? 'Game Boy Color' : 'Original'}: ` +
    `${fmt(report[d].frame_cycles_max)} of 70,224 cycles in the busiest frame, startup ${fmt(report[d].startup_cycles)} cycles`).join('\n');
}

function showBuildProblem(errors) {
  const cpu = $('cpuMeter');
  cpu.hidden = false;
  cpu.textContent = '⚠ won\'t build';
  cpu.className = 'meter error';
  cpu.title = errors.join('\n');
}

function renderReport(report) {
  const t = $('report');
  const measured = devices(report);
  const b = report.bytes;
  const ms = c => `${(c / 4194.304).toFixed(1)} ms`;
  const row = (label, cells, note = '') =>
    `<tr><td>${label}</td>${cells.map(c => `<td class="num">${c}</td>`).join('')}</tr>` +
    (note ? `<tr><td colspan="${cells.length + 1}" class="note">${note}</td></tr>` : '');
  let html = `<tr><th colspan="3">ROM</th></tr>` +
    row('Used', [`${fmt(b.rom_used)} B`, `of ${fmt(b.rom_size)}`]) +
    row('Code', [`${fmt(b.code)} B`, '']) + row('Data', [`${fmt(b.data)} B`, '']) +
    row('RAM', [`${fmt(b.wram + b.hram)} B`, '']);
  if (measured.length) {
    html += `<tr><th>CPU (cycles)</th>${measured.map(d => `<th class="num">${d === 'color' ? 'Color' : 'Original'}</th>`).join('')}</tr>` +
      row('Startup work', measured.map(d => fmt(report[d].startup_cycles)),
          `${measured.map(d => ms(report[d].startup_cycles)).join(' / ')}, not counting waits for the screen`) +
      row('Busiest frame', measured.map(d => `${fmt(report[d].frame_cycles_max)} (${report[d].frame_load}%)`), 'out of 70,224 cycles per frame') +
      row('VBlank work', measured.map(d => fmt(report[d].vblank_work_cycles)), 'out of 4,560 cycles while video memory is free');
    if (measured.some(d => report[d].scene_load_cycles)) {
      html += row('Scene load', measured.map(d => fmt(report[d].scene_load_cycles || 0)),
                  `${measured.map(d => ms(report[d].scene_load_cycles || 0)).join(' / ')} with the screen off`);
    }
  }
  for (const d of ['color', 'original']) {
    const r = report[d];
    if (r?.error) html += `<tr><td colspan="3" class="bad">${d}: not measured (${r.error})</td></tr>`;
    for (const v of r?.violations || []) html += `<tr><td colspan="3" class="bad">⚠ ${v.message} at $${v.pc.toString(16).padStart(4, '0')}</td></tr>`;
  }
  t.innerHTML = html;
}

$('exportBtn').onclick = async () => {
  try {
    const { rom, stats } = await buildRom();
    download(`${fileBase()}.gb`, rom, 'application/octet-stream');
    say(`Exported ${fileBase()}.gb (${stats.bytes / 1024} KB, ${stats.scenes} scene${stats.scenes === 1 ? '' : 's'}). It runs in color on a Game Boy Color and in gray on an original.`);
  } catch (err) {
    openTest(err.errors);
  }
};

// ---- test ------------------------------------------------------------------

let player = null;
let testBuild = null;
let testDevice = 'color';

// For automated checks of the Test window (keyboard -> emulator).
window.gbstageDebug = { get player() { return player; } };

function stopPlayer() {
  if (player) { player.destroy(); player = null; }
}

async function startPlayer() {
  stopPlayer();
  for (const b of $('testSeg').children) b.classList.toggle('on', b.dataset.device === testDevice);
  if (!testBuild) return;
  try {
    const Binjgb = await loadBinjgb();
    const rom = testDevice === 'dmg' ? asOriginalGameBoy(testBuild.rom) : testBuild.rom;
    player = await Player.create(Binjgb, rom, $('testScreen'), { colorCurve: testDevice === 'screen' ? 2 : 0 });
    player.start();
  } catch (err) {
    showTestErrors([`The emulator couldn't start: ${err.message}. Run System check for details.`]);
  }
}

function showTestErrors(errors) {
  const box = $('testErrors');
  box.hidden = !errors;
  box.innerHTML = '';
  for (const msg of errors || []) {
    const p = document.createElement('p');
    p.textContent = msg;
    box.appendChild(p);
  }
  $('testScreen').hidden = !!errors;
}

async function openTest(knownErrors) {
  if (!$('testDialog').open) $('testDialog').showModal();
  testBuild = null;
  $('asmView').textContent = '';
  $('report').innerHTML = '';
  $('testInfo').textContent = 'building…';
  showTestErrors(knownErrors || null);
  if (knownErrors) { $('testInfo').textContent = 'build failed'; return; }
  try {
    testBuild = await buildRom();
    const s = testBuild.stats;
    $('testInfo').textContent = `${s.bytes / 1024} KB ROM · ${s.scenes} scene${s.scenes === 1 ? '' : 's'} · ${s.palettes} palettes`;
    $('asmView').textContent = testBuild.asm;
    renderReport(testBuild.report);
    await startPlayer();
    $('testScreen').focus();   // keys go to the game, not to a dialog button
  } catch (err) {
    $('testInfo').textContent = 'build failed';
    showTestErrors(err.errors || [String(err)]);
  }
}

$('testBtn').onclick = () => { audioContext(); openTest(); };   // start audio inside the click
$('testSound').checked = !Player.muted;
$('testSound').onchange = e => {
  Player.muted = !e.target.checked;
  localStorage.setItem('gbstage.muted', Player.muted ? '1' : '0');
  if (player) player.setMuted(Player.muted);
  $('testScreen').focus();
};
$('testSeg').onclick = e => {
  const b = e.target.closest('button');
  if (b) { testDevice = b.dataset.device; startPlayer(); b.blur(); }
};
$('testClose').onclick = () => $('testDialog').close();
$('testDialog').addEventListener('close', stopPlayer);

// ---- samples -----------------------------------------------------------------

const SAMPLES = { 'capsule-clinic': capsuleClinic, 'mac-vs-joe': macVsJoe };
const SAMPLE_VERSIONS = { 'capsule-clinic': CLINIC_VERSION, 'mac-vs-joe': MAC_VS_JOE_VERSION };
const SAMPLE_NAMES = { 'capsule-clinic': 'Capsule Clinic', 'mac-vs-joe': 'Joe vs Mac' };

// An older copy of a sample can't do what the notes describe: offer the current one.
function checkSampleVersion() {
  // Copies opened before samples carried a version are version 1.
  if (!state.project.sample && state.project.name === 'Capsule Clinic') state.project.sample = { id: 'capsule-clinic', version: 1 };
  const s = state.project.sample;
  const bar = $('sampleBar');
  bar.hidden = !(s && SAMPLE_VERSIONS[s.id] && s.version < SAMPLE_VERSIONS[s.id]);
  if (!bar.hidden) $('sampleBarText').textContent = `This is an older copy of the ${SAMPLE_NAMES[s.id]} sample. The new version has more working parts.`;
}
$('sampleUpdate').onclick = () => {
  const s = state.project.sample;
  if (!s || !SAMPLES[s.id]) { $('sampleBar').hidden = true; return; }
  loadProject(SAMPLES[s.id]());
  say('Sample updated. Each scene has notes on how it was built.');
};

// ?sample=capsule-clinic opens a sample project. If you have work in progress, it asks first.
function openSampleFromUrl() {
  const url = new URL(location.href);
  const name = url.searchParams.get('sample');
  if (!name) return false;
  url.searchParams.delete('sample');
  history.replaceState(null, '', url.pathname + url.search);
  const make = SAMPLES[name];
  if (!make) { say(`There's no sample called "${name}".`, 'warn'); return false; }
  if (saved && !confirm(`Open the "${name}" sample? It replaces your current project in the editor. ` +
                        'Save your project first (Save button) if you want to keep it.')) return false;
  loadProject(make());
  say('Sample loaded. Each scene has notes on how it was built: click through the scenes on the right.');
  return true;
}

// ---- start -----------------------------------------------------------------

$('reloadBtn').onclick = () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(M.serialize(state.project)));
  location.reload();
};

$('projectName').value = state.project.name;
state.scene = state.project.start;
setTool('pencil');
setView('color');
changed({ palettes: true, scenes: true });
initSystemCheck();
checkSampleVersion();
if (!openSampleFromUrl() && !saved) {
  say('Welcome! This is the Press Start template. Press ▶ Test to play it, then make it yours. New has more templates.');
}
