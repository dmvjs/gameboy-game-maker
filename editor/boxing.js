// The boxing game template: a fight against one rival, seen from behind the player, with a title menu, a
// challenger screen, endings, help and a corner between rounds. Everything that makes it one particular game
// (names, text, colors, poses, portraits) comes from a fighter pack, so new art makes a new game on the same
// engine. Joe vs Mac (mac-vs-joe.js) is a pack.
//
// A fighter pack:
//   id, name, credit       sample id, project name, the title's credit line
//   referee?               { poses (24x32: 1-3, 4 in its shirt palette), colors, shirtColors } instead of the kit's
//   title                  [{ text, x, y, scale, slot, shadow? }] drawn on the title screen (slots of textPalette,
//                            or of titleLogo's colors when there's a logo)
//   titleLogo?             { w: 160, h, y, pixels (slots), colors: 4 } a full-width band across the title
//   titlePunch?            what choosing on the title plays first: { sprite: { w, h, x, y, pixels }, steps: [{ frames,
//                            colors (3, or null: hidden), front, logo (4 colors), backdrop }] } (see Punch-Out!!'s)
//   circuit                the challenger screen's first line (up to 12 wide)
//   textPalette            4 colors: 0 light text, 1 and 2 accents, 3 the background of every menu screen
//   portraitPalettes?      palettes of the portraits' own (up to 10; a scene shows 8 palettes at once)
//   rival                  { short, hud, name, rank, lines (up to 5, 11 wide), palettes (skin, gloves, hair:
//                            4 colors each, slot 0 becomes the mat), poses (64x80), portrait, hurtPortrait? }
//   player                 { name, hud, rank, lines (up to 5, 12 wide; name and rank too), colors (sprite slots 1-3), tiredColors, downColors?,
//                            poses (24x48), portrait }
//   win, lose              lines under the ending screens' headlines
//   corner                 { rival: his lines, coach: up to 4 lines of advice }
//   effects?               { stars, sweat, spark }: sprite effects over the art, on unless set false
//   rival.nes?             a Punch-Out!! fighter bank to drive him (see gbstage/kit_nes.asm): { bank (base64),
//                            offset, frames: {NES frame (hex): pose}, home: [x, y], scale }
// Portraits are 56x56: pixels are slots, cells each tile's palette: s/g/h the rival's, t text, or a digit k for
// portraitPalettes[k].

import * as M from './model.js';
import { REF_POSES } from './art/referee.js';

export const BOXING_VERSION = 32;

const pal = (name, colors, greys) => ({ name, colors, ...(greys ? { greys } : {}) });   // (greys: the original's, if not as is)
export const MAT = [26, 28, 31];
export const PORTRAIT = 56;                            // portraits are 56x56 (7x7 tiles)
const PT = PORTRAIT / 8;

function fillRect(layer, x, y, w, h, slot) {
  for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) {
    if (i >= 0 && j >= 0 && i < M.W && j < M.H) layer.pixels[j * M.W + i] = slot;
  }
}

function cellPalettes(scene, cx, cy, cw, ch, palette) {
  for (let y = cy; y < cy + ch; y++) for (let x = cx; x < cx + cw; x++) scene.cellPal[y * M.CW + x] = palette;
}

// Small 8x8 icons for the HUD, slots as digits.
const STAR = ['...1....', '...1....', '..111...', '1111111.', '.11111..', '..1.1...', '.1...1..', '........'];
const HEART = ['.22.22..', '2222222.', '2222222.', '.22222..', '..222...', '...2....', '........', '........'];
function icon(layer, cx, cy, rows) {
  rows.forEach((r, y) => [...r].forEach((ch, x) => { if (ch !== '.') layer.pixels[(cy * 8 + y) * M.W + cx * 8 + x] = +ch; }));
}

const notes = rival => ({
  'Title': `A menu, as Punch-Out!!'s: Select or up/down moves, Start (or A) chooses. NEW goes to the challenger
screen, CONTINUE to the pass key.
• The cursor is a little glove in the player's sprite palette.`,
  'Pass key': `A pass key: left/right picks a digit, up/down changes it, Start goes on to the challenger screen
(the key isn't checked yet), B back to the title. The digits stay as entered.`,
  'Challenger': `A press-start screen that slides up from the bottom (Slides in, under the scene's settings). Every line of text is a text label: click one under "Text" to change a name, hometown or record.`,
  'Fight': `The fight. B = left punch, A = right punch, Up + punch = to the face. Left/Right dodge, hold Down to block, Start throws a star punch.
• ${rival} stands guarding his body (gloves low) or his face (gloves high). Hit where he isn't guarding. Three clean hits and he switches.
• His punches start with a wind-up: dodge or block. Hit his face while he winds up the hook to earn a star.
• He does nothing for the first 40 seconds: learn his guard. At 0:40 (0:30 in rounds 2 and 3) he backs off, taunts, then charges in with a hook. Catch him in the first frames of the charge and he's out; a little later, he's down.
• Throw too many rights and he slips one (every third) and counters with a hook to the body.
• A star punch that doesn't drop him pops his arm out of its socket. He snaps it back in with a click.
• ${rival} is an 8x10-tile area of the map. His tiles stay in video memory, and a pose change rewrites that area during VBlank. While he's down, the tiles only his attack poses use are swapped for the knockdown set.
• The player is sprites. The HUD's digits and bars are tiles picked from per-cell tables.`,
  'You win': `A press-start screen: Punch-Out!!'s "GREAT FIGHTING" with its glove (when the pack has one). Start goes back to the title.`,
  'You win (TKO)': `The same, after a TKO ("YOU WON BY TKO!").`,
  [`${rival} wins`]: `A press-start screen: Punch-Out!!'s "DON'T CRY, MAC!" with its glove (when the pack has one). Start goes on to the rematch.`,
  'Rematch': `The challenger screen again after a loss, as Punch-Out!!'s: REMATCH under the circuit, the player's record with the loss.`,
  'Corner': `Between rounds the fight fades to this corner screen, then Start goes back to the ring and the fight carries on where it was.
• Select, once per match, gets the coach working faster: a random chunk of health comes back.`,
});

const centered = (text, scale = 1) => (M.W - text.length * 8 * scale) >> 1;

export function boxingGame(pack) {
  M.useFont('bold');
  const R = pack.rival, P = pack.player;
  const ringOf = rv => rv.ring || pack.ring;              // his ring's colors (Punch-Out!!'s change by circuit)
  const circuitOf = rv => rv.circuit || pack.circuit;     // his circuit's name
  const nesText = l => l.replace(/^(\d+)-(\d+) (\d+)KO$/, (_, w, l2, k) => `${w.padStart(2)}-${l2.padStart(2)} ${k.padStart(2)}KO`)
    .replace(/^RANKED NO\.(\d+)$/, 'RANKED: #$1');      // (a record and a rank as the NES writes them: "12- 1 10KO")
  const titleX = l => /^"/.test(l) || l === 'TITLE-' ? 1 : l === 'HOLDER' ? 2 : 0;   // (Mac's titles: indented, the NES's)
  const matOf = rv => ringOf(rv)?.mat || MAT;
  const ROLE = { s: 3, g: 4, h: 5, t: 6 };               // portrait cells: these letters, or a digit k for portraitPalettes[k]
  const portraitPal = [];                                // portraitPalettes[k]'s palette (one with the same colors shared)
  const role = r => ROLE[r] ?? portraitPal[/[A-Z]/.test(r) ? r.charCodeAt(0) - 55 : r >= '\u00C0' ? r.charCodeAt(0) - 0xC0 + 36 : +r];   // (0-9, A-Z, À on)
  const p = {
    name: pack.name,
    palettes: [
      pal('HUD', [[31, 31, 31], [31, 26, 6], [28, 6, 6], [3, 4, 10]]),
      pal('Crowd', [[31, 31, 31], [18, 16, 24], [26, 6, 8], [4, 4, 10]]),
      pal('Mat', [matOf(R), [20, 22, 28], [8, 12, 24], [3, 3, 6]]),
      ...['skin', 'gloves', 'hair'].map((part, k) => pal(`${R.short} ${part}`, [matOf(R), ...R.palettes[k].slice(1)])),
      pal('Text', pack.textPalette, [0, 1, 1, 3]),        // (the original: its green as light as its orange, over black)
      ...(pack.titleLogo ? [pal('Title logo', pack.titleLogo.colors, [3, 2, 0, 1])] : []),
    ],
    objPalettes: [pal('Player', [[0, 0, 0], ...P.colors]),
                  pal('Referee', [[0, 0, 0], ...(pack.referee?.colors || [[31, 24, 18], [26, 29, 31], [3, 3, 6]])]),
                  pal('Player tired', [[0, 0, 0], ...P.tiredColors]),
                  ...(P.downColors ? [pal('Player down', [[0, 0, 0], ...P.downColors])] : []),
                  ...(pack.referee?.shirtColors ? [pal('Referee shirt', [[0, 0, 0], ...pack.referee.shirtColors.slice(0, 2), [4, 4, 10]])] : [])],   // (its dark the crowd's: the side ropes' outside, as over the mat)
    cursor: { palette: 0, pixels: Uint8Array.from(
      '00333000' + '03313300' + '33133330' + '33333330' + '33333330' + '03333300' + '00222000' + '00000000', ch => +ch) },
    scenes: ['Title', 'Challenger', 'Fight', 'You win', `${R.short} wins`, 'Pass key', 'Corner', 'Rematch',
             'You win (TKO)'].map(name => ({
      name, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH),
      menu: null, pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [],
      notes: notes(R.short)[name],
    })),
    start: 0,
    transition: { color: 'black', frames: 2 },
    sound: 'boxing',
    font: 'bold',
    sample: { id: pack.id, version: BOXING_VERSION },
  };
  const [title, passKey] = [M.layerOf(p, 0), M.layerOf(p, 5)];
  const LOGO = p.palettes.length - 1;                    // the title logo's palette (when there is one)
  const NAME = pack.titleLogo ? p.palettes.push(pal('Title name', pack.titleLogo.colors, [3, 0, 2, 3])) - 1 : LOGO;   // (its name
                                                         //  over it: on the original, white on black)
  (pack.portraitPalettes || []).forEach((colors, k) => {
    const greys = pack.portraitGreys?.[k];               // (the original Game Boy's greys for its slots, if not as is)
    const at = p.palettes.findIndex(q => JSON.stringify(q.colors) === JSON.stringify(colors) && JSON.stringify(q.greys) === JSON.stringify(greys || undefined));
    portraitPal.push(at >= 7 ? at : p.palettes.push({ ...pal(`Portrait ${k + 1}`, colors), ...(greys ? { greys } : {}) }) - 1);
  });
  const S = p.scenes;

  // A 48x48 portrait into a scene at tile (cx, cy).
  function portrait(scene, layer, face, cx, cy) {
    const w = face.w || PORTRAIT, h = face.h || PORTRAIT, cols = w / 8;
    for (let i = 0; i < w * h; i++) {
      layer.pixels[(cy * 8 + (i / w | 0)) * M.W + cx * 8 + i % w] = +face.pixels[i];
    }
    [...face.cells].forEach((r, k) => { scene.cellPal[(cy + (k / cols | 0)) * M.CW + cx + k % cols] = role(r); });
  }
  // A close-up's colors past its background palettes (Color: the NES's sprites over it), state k's, placed at its
  // cell (cx, cy): sprites with their palettes in the scene's list (overlay.pals), added there as needed.
  function overlaySprites(scene, face, k, cx, cy, dmg) {
    const o = face.overlay;
    if (dmg) return (o?.dmg?.[k] || []).map(([x, y, pixels, pal]) => ({ x: cx * 8 + x, y: cy * 8 + y, pixels, pal }));   // (the original's greys)
    if (!o || !o.states[k]) return [];
    scene.overlay = scene.overlay || { pals: [], sprites: [] };
    const at = o.pals.map(c => {
      const n = scene.overlay.pals.findIndex(q => JSON.stringify(q) === JSON.stringify(c));
      return n >= 0 ? n : scene.overlay.pals.push(c) - 1;
    });
    return o.states[k].map(([x, y, pixels, pal]) => ({ x: cx * 8 + x, y: cy * 8 + y, pixels, pal: at[pal] }));
  }
  // Words re-wrapped to a width (the NES's own breaks kept where they fit; a blank line kept as a gap).
  function rewrap(lines, width) {
    const out = [];
    for (const line of lines) {
      if (!line) { out.push(''); continue; }
      let cur = '';
      for (const word of line.split(' ').filter(w => w)) {
        if (!cur) cur = word;
        else if (cur.length + 1 + word.length <= width) cur += ' ' + word;
        else { out.push(cur); cur = word; }
      }
      if (cur) out.push(cur);
    }
    return out;
  }

  // Text palette slots: 0 light, 1 and 2 accents, 3 the background.
  cellPalettes(S[0], 0, 0, M.CW, M.CH, ROLE.t);

  // ---- Title: Punch-Out!!'s, a name over the logo band, NEW and CONTINUE ----
  fillRect(title, 0, 0, M.W, M.H, 3);
  const logo = pack.titleLogo;
  if (logo) {
    for (let i = 0; i < logo.w * logo.h; i++) title.pixels[(logo.y + (i / logo.w | 0)) * M.W + i % logo.w] = +logo.pixels[i];
    cellPalettes(S[0], 0, logo.y >> 3, M.CW, logo.h >> 3, LOGO);
  } else {
    fillRect(title, 0, 52, M.W, 4, 2);
    portrait(S[0], title, R.portrait, M.CW - PT, 8);
  }
  for (const t of pack.title) {
    if (logo) {                                          // in the logo's colors: its black (slot 0) behind
      cellPalettes(S[0], 0, t.y >> 3, M.CW, t.scale, NAME);
      fillRect(title, 0, t.y & ~7, M.W, 8 * t.scale, 0);
    }
    if (t.shadow !== undefined) M.drawText(title, t.text, t.x + 1, t.y + 1, t.shadow, t.scale);
    M.drawText(title, t.text, t.x, t.y, t.slot, t.scale);
  }
  S[0].menu = { x: 6, y: logo ? 11 : 10, spacing: 2, textSlot: 0, cursorAnimation: 'bob', blinks: 3, selectMoves: true,
                items: [{ label: 'NEW', target: 1 }, { label: 'CONTINUE', target: 5 }] };
  const gl = logo && pack.titleGloves;
  if (gl) {                                              // Punch-Out!!'s: a glove either side of the chosen item, NEW
    const m = S[0].menu, x0 = m.x * 8, x1 = x0 + 'CONTINUE'.length * 8;   // centered over CONTINUE
    m.items[0].label = '  NEW';
    m.cursorAnimation = 'none';
    m.gloves = { pixels: gl.pixels, colors: gl.colors, left: x0 - gl.gap - gl.w, right: x1 + gl.gap, dy: gl.dy };
  }
  if (logo) {                                            // Punch-Out!!'s: the pass key right under CONTINUE (the
    S[0].menu.passKey = { item: 1, label: 'PASS KEY', labelY: 15, y: 16, textSlot: 2,   // credit makes way; green);
                          codes: pack.passKeys || [] };   // a code's ten digits take you to its scene
  }
  const punch = logo && pack.titlePunch;
  if (punch) {                                           // the glove: behind the logo's mesh, then punching out
    const text = pack.textPalette;
    S[0].menu.confirm = {
      sprite: { ...punch.sprite }, faded: true,
      steps: punch.steps.map(st => ({ frames: st.frames, colors: st.colors, front: st.front, nesSfx: st.nesSfx || 0,
                                      bg: { [LOGO]: st.logo, [NAME]: st.logo, [ROLE.t]: [text[0], text[1], text[2], st.backdrop] } })),
    };
  }
  S[0].texts = [{ label: pack.credit, x: centered(pack.credit) >> 3, y: 16, textSlot: 0 }];

  // ---- Endings and help ----
  // Punch-Out!!'s screens after the fight: blue, the W.V.B.A. header, a word for Mac, the big glove, the next
  // challenge. LOSS and its glove's palette, then each screen's lines (rows; the glove covers the one at row 10).
  let LOSS = null;
  function nesScreen(scene, layer, lines, gloveAt, gloveX, circuit = pack.circuit) {   // (gloveX: the glove's own place)
    if (LOSS === null) {
      LOSS = p.palettes.length;
      p.palettes.push(pal('Loss', [[1, 2, 18], [7, 22, 25], [29, 29, 29], [0, 0, 0]], [3, 1, 0, 3]),   // NES $02, $2C, $30 (the original: light on black)
                      pal('Loss glove', [[1, 2, 18], [19, 4, 4], [29, 13, 12], [0, 0, 0]], [3, 2, 1, 3]),   // $16, $26
                      pal('Loss glove, letters', [[1, 2, 18], [19, 4, 4], [29, 29, 29], [0, 0, 0]], [3, 2, 0, 3]));   // (where they meet)
    }
    cellPalettes(scene, 0, 0, M.CW, M.CH, LOSS);
    fillRect(layer, 0, 0, M.W, M.H, 0);
    const line = (text, y, slot) => M.drawText(layer, text, centered(text) >> 3 << 3, y, slot);   // (on whole tiles, as the NES's)
    line('THE W.V.B.A.', 8, 1); line(circuit, 16, 1);
    for (let x = 0; x < M.W; x += 8) fillRect(layer, x + 1, 27, 5, 1, 1);
    for (const [text, y, x] of lines) x === undefined ? line(text, y, 2) : M.drawText(layer, text, x, y, 2);
    const g = pack.loseGlove, gx = gloveX ?? (centered(gloveAt) >> 3 << 3) + 5 * 8, gy = 8 * 8;
    const lettered = new Set();                          // behind the letters, as the NES has it (its glove's
    for (let i = 0; i < g.w * g.h; i++) {               // sprites under the background): the tiles where they meet
      const x = gx + i % g.w, y = gy + (i / g.w | 0);   // take the glove's dark red, white and black
      if (+g.pixels[i] && layer.pixels[y * M.W + x]) lettered.add((y >> 3) * M.CW + (x >> 3));
    }
    for (let i = 0; i < g.w * g.h; i++) {
      const v = +g.pixels[i], x = gx + i % g.w, y = gy + (i / g.w | 0), cell = (y >> 3) * M.CW + (x >> 3);
      if (!v) continue;
      if (lettered.has(cell)) {
        scene.cellPal[cell] = LOSS + 2;
        if (!layer.pixels[y * M.W + x]) layer.pixels[y * M.W + x] = v === 2 ? 1 : v;   // (its light red: dark here)
      } else { layer.pixels[y * M.W + x] = v; scene.cellPal[cell] = LOSS + 1; }
    }
  }
  const NEXT = [['ARE YOU READY', 104], ['FOR THE', 114], ['NEXT CHALLENGE ?', 124]];

  // Punch-Out!!'s round card: after Start on the challenger screen (and the corner) the screen scrolls up and
  // it comes up from below: ROUND (FINAL ROUND for the third) over the round's digit, lit dots on a dark grid.
  const DIGITS = {
    1: ['', '', '     ##', '    ###', '   # ##', ...Array(8).fill('     ##'), '   ######', '', ''],
    2: ['', '', '    ####', '   ##  ##', '  ##    ##', '  ##    ##', '       ###', '      ###', '    ###', '   ##',
        '  ##', '  ##', '  ########', '  ########', '', ''],
    3: ['', '', '    ####', '   ##  ##', '  ##    ##', '  ##    ##', '       ##', '     ###', '       ##', '        ##',
        '  ##    ##', '  ##    ##', '   ##  ##', '    ####', '', ''],
  };
  const dots = n => DIGITS[n].map(r => r.padEnd(12, ' ').replace(/ /g, '.'));
  const CARD = pack.roundCard ? p.palettes.length : null;
  if (pack.roundCard) p.palettes.push(pal('Round card', [[29, 29, 29], [12, 3, 1], [12, 3, 1], [0, 0, 0]]));   // NES $30, $07 (as it looks on a TV)
  const card = variants => ({ variants, palette: CARD, textPalette: ROLE.t, textSlot: 1, hold: 100 });

  // ---- Each rival: his challenger screen, his ring, the screens after (won, won on a TKO, lost), his corner and
  // the rematch. The first rival's are scenes 1-4, 6-8; the next ones' come after, seven each. ----
  const rivals = pack.rivals || [R];
  const SCENE_NAMES = ['Challenger', 'Fight', 'You win', 'wins', 'Corner', 'Rematch', 'You win (TKO)'];
  const ids = rivals.map((rv, k) => {
    if (k === 0) return { challenger: 1, fight: 2, win: 3, lose: 4, corner: 6, rematch: 7, winTko: 8 };
    const at = p.scenes.length;
    for (const name of SCENE_NAMES) {
      const full = name === 'wins' ? `${rv.short} wins` : `${name}: ${rv.short}`;
      p.scenes.push({ name: full, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH),
        menu: null, pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null,
        texts: [], notes: notes(rv.short)[name === 'wins' ? `${rv.short} wins` : name] });
    }
    return { challenger: at, fight: at + 1, win: at + 2, lose: at + 3, corner: at + 4, rematch: at + 5, winTko: at + 6 };
  });
  const layer = i => M.layerOf(p, i);
  // ---- Punch-Out!!'s training run, after a circuit's title (the rival with `training`): New York scrolling by,
  // Doc on his bike, Mac running; then the pass key in a box ----
  const im = pack.intermission;
  const trainIds = {};                                      // per circuit champion (a rival with `training`): his run
  if (im && rivals.some(rv => rv.training)) {
    const bg0 = p.palettes.length;
    im.palettes.forEach((colors, k) => p.palettes.push({ ...pal(`Training ${k + 1}`, colors),   // (the original's greys:
                                                         ...(im.greys ? { greys: im.greys[k] } : {}) }));   // the picture's)
    const sky = im.palettes[+im.cells[0]][+im.pixels[0]];
    const boxPal = p.palettes.length;
    p.palettes.push({ ...pal('Training box', [sky, [31, 31, 31], [20, 20, 20], [0, 0, 0]]), ...(im.boxGreys ? { greys: im.boxGreys } : {}) });
    const ob0 = p.objPalettes.length;
    im.objPalettes.forEach((colors, k) => p.objPalettes.push(pal(`Training sprites ${k + 1}`, [[0, 0, 0], ...colors])));
    rivals.forEach((rv, k) => {
      if (!rv.training) return;
      trainIds[k] = p.scenes.length;
      const scene = { name: `Training: ${rv.short}`, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH),
        menu: null, pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null,
        texts: [], notes: 'Punch-Out!!\'s training run between circuits: the city scrolls by (the whole map, 256 wide, goes round), Doc and Mac run, then the pass key comes up in a box. Start goes on once it\'s written.' };
      for (let y = 0; y < M.H; y++) for (let x = 0; x < M.W; x++) scene.pixels[y * M.W + x] = +im.pixels[y * 256 + x];
      for (let cy = 0; cy < M.CH; cy++) for (let cx = 0; cx < M.CW; cx++) scene.cellPal[cy * M.CW + cx] = bg0 + +im.cells[cy * 32 + cx];
      scene.cutscene = {
        pixels: im.pixels, cells: [...im.cells].map(c => bg0 + +c), music: 0x1A, dmgDarkOdd: true,
        // Punch-Out!!'s parallax, as the NES's (256ths of a pixel a frame: half its, the map half as wide): the
        // skyline an eighth of a pixel, the water's far edge a quarter, everything from the water down (posts,
        // trees, sidewalk, road) a pixel and a half; each from where the NES's starts to where it stops as the box
        // comes up, the NES's screen centred in ours (the statue)
        bands: [[48, 16, 17], [92, 32, 0], [96, 192, 3]].map(([y, speed, endX]) => ({ y, speed, endX })),
        actors: im.actors.map(a => ({ x: a.x, y: a.y, w: a.w, h: a.h, every: 6,
          frames: a.frames.map(f => ({ pixels: f.pixels, cells: [...f.cells].map(c => ob0 + +c) })) })),
        box: { x: 3, y: 1, lines: ['PASS KEY IS', rv.trainingKey || '000 000 0000', 'PUSH START!'],
               palette: boxPal, textSlot: 1, bgSlot: 3, after: 1536, every: 4 },   // (as the NES's: 25 s, a letter
                                                                                       // every 4 frames)
      };
      scene.pressStart = { target: 0, flashes: 1, area: null, prompt: null, quiet: true };   // (Start stops its song)
      p.scenes.push(scene);
    });
  }
  // A palette by its colors: one already in the project if it has them (a rematch's are his first fight's)
  const addPal = (name, colors, greys) => {
    const k = p.palettes.findIndex(q => JSON.stringify(q.colors) === JSON.stringify(colors) && JSON.stringify(q.greys) === JSON.stringify(greys));
    return k >= 0 ? k : p.palettes.push(pal(name, colors, greys)) - 1;
  };
  // ---- Punch-Out!!'s screens between fights that aren't a fighter's (the game's, at 5/8 its size, the words in our
  // font): NEXT IS ... TITLE BOUT!! before a circuit's title bout, the KO News page after the World Circuit's (its
  // paper creeping up into place, his pass key in it), then THE DREAM FIGHT!!; the big letters' colors in turn ----
  const NS = pack.screens, tbIds = {};
  let newsId = null, dreamId = null, awTbId = null;
  const plain = name => ({ name, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH), menu: null,
    pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [] });
  if (NS && pack.loseGlove) {
    const big = addPal('Title bout', [NS.navy, NS.cyan, NS.orange, [0, 0, 0]], [3, 1, 0, 3]);
    const gl = addPal('Title bout glove', [NS.navy, NS.glove[0], NS.glove[1], [0, 0, 0]], [3, 2, 1, 3]);
    const gll = addPal('Title bout glove, letters', [NS.navy, NS.glove[0], NS.orange, [0, 0, 0]], [3, 2, 0, 3]);
    const bigScreen = (name, spec, lines, linesY, lettersY, gloveAt, target, note) => {
      const sc = plain(name), L = spec.letters, lx = (M.W - L.w) >> 1, front = new Set();
      sc.cellPal.fill(big);
      for (let i = 0; i < L.w * L.h; i++) {
        if (!+L.pixels[i]) continue;
        const k = (lettersY + (i / L.w | 0)) * M.W + lx + i % L.w;
        sc.pixels[k] = 2; front.add(k);
      }
      const lettered = new Set([...front].map(k => ((k / M.W | 0) >> 3) * M.CW + ((k % M.W) >> 3)));
      const g = pack.loseGlove, gx = lx + gloveAt[0], gy = lettersY + gloveAt[1];   // (behind the letters, as the NES's)
      for (let i = 0; i < g.w * g.h; i++) {
        const v = +g.pixels[i], x = gx + i % g.w, y = gy + (i / g.w | 0), k = y * M.W + x, cell = (y >> 3) * M.CW + (x >> 3);
        if (!v || front.has(k)) continue;
        if (lettered.has(cell)) { sc.cellPal[cell] = gll; sc.pixels[k] = v === 2 ? 1 : v; }   // (its light red: dark here)
        else { sc.cellPal[cell] = gl; sc.pixels[k] = v; }
      }
      sc.texts = lines.map((label, n) => ({ label, x: centered(label) >> 3, y: linesY + n, textSlot: 1 }));
      sc.cycle = { palettes: [big, gll], slot: 2, colors: NS.cycleColors, after: spec.after, every: spec.every, loops: spec.loops };
      sc.pressStart = { target, flashes: 1, area: null, quiet: true,
                        auto: spec.after + spec.loops * NS.cycleColors.length * spec.every + spec.hold };
      sc.nesMusic = spec.music;
      sc.notes = note;
      return p.scenes.push(sc) - 1;
    };
    const tbLines = circuit => ['NEXT', 'IS', 'THE W.V.B.A.', circuit.replace(/ CIRCUIT$/, ''), 'CIRCUIT'];
    const tbNote = 'Punch-Out!!\'s TITLE BOUT!! before a circuit\'s title bout: its letters\' colors in turn, then on by itself.';
    rivals.forEach((rv, k) => {
      if (k > 0 && rv.titleBout && !rivals[k - 1].news) {
        const sc = bigScreen(`Title bout: ${rv.short}`, NS.titleBout, tbLines(circuitOf(rv)), 1, 56, [28, 5], ids[k].challenger, tbNote);
        p.scenes[sc].announce = true;
        tbIds[k] = sc;
      }
    });
    const aw = pack.anotherWorld || [], awLast = rivals.findIndex(rv => rv.short === aw[aw.length - 1]);
    if (aw.length && awLast >= 0) {
      awTbId = bigScreen('Title bout: Another World', NS.titleBout, tbLines('ANOTHER WORLD CIRCUIT'), 1, 56, [28, 5],
                         ids[awLast].challenger, tbNote);
      p.scenes[awTbId].announce = true;
    }
    const macho = rivals.findIndex(rv => rv.news);
    if (macho >= 0 && macho + 1 < rivals.length) {
      dreamId = bigScreen('The dream fight', NS.dreamFight, NS.dreamFight.lines, 13, 8, [33, 40], ids[macho + 1].challenger,
                          'Punch-Out!!\'s THE DREAM FIGHT!!, after the KO News page: its letters\' colors in turn, then on by itself to Mike Tyson.');
      const N = NS.news, sc = plain('KO News'), newsPal = addPal('KO News', N.colors);
      sc.cellPal.fill(newsPal);
      sc.pixels.fill(1);                                    // (the paper)
      const blit = (pc, x0, y0) => {
        for (let i = 0; i < pc.w * pc.h; i++) {
          const x = x0 + i % pc.w, y = y0 + (i / pc.w | 0);
          if (x >= 0 && x < M.W && y >= 0 && y < M.H) sc.pixels[y * M.W + x] = +pc.pixels[i];
        }
      };
      blit(N.masthead, (M.W - N.masthead.w) >> 1, 0);
      for (const y of [22, 33]) for (let x = 0; x < M.W; x++) sc.pixels[y * M.W + x] = 3;
      blit(N.photo, -2, 35);
      blit(N.headline, 56 + ((M.W - 56 - N.headline.w) >> 1), 35);
      blit(N.macho, M.W - N.macho.w, M.H - N.macho.w);
      const right = ['THE W.V.B.A.', 'WORLD CIRCUIT', 'LAST NIGHT,WE', 'FOUND A SMALL', 'BUT GREAT', 'CHAMP HIS', 'NAME IS', '"LITTLE MAC"'];
      sc.texts = [{ label: 'APRIL 1,1987', x: 0, y: 3, textSlot: 3 },
                  ...right.map((label, n) => ({ label, x: 7, y: 6 + n, textSlot: 3 })),
                  { label: 'PUSH START FOR', x: 0, y: 14, textSlot: 3 }, { label: 'THE DREAM FIGHT', x: 0, y: 15, textSlot: 3 },
                  { label: 'I FOUND A KEY:', x: 0, y: 16, textSlot: 3 },
                  { label: '000 000 0000', x: 1, y: 17, textSlot: 3, passKey: 2 }];   // (his, the World Circuit's, as it stands)
      sc.slideIn = { from: Math.round(N.from * 5 / 8), every: Math.round(N.every * 8 / 5), fillSlot: 3 };   // (as long as
      sc.pressStart = { target: dreamId, flashes: 1, area: null, quiet: true };                            //  the NES's)
      sc.nesMusic = N.music;
      sc.notes = 'Punch-Out!!\'s KO News, after the World Circuit\'s title: his pass key in it. Start goes on to THE DREAM FIGHT!!.';
      newsId = p.scenes.push(sc) - 1;
    }
  }
  rivals.forEach((rv, k) => {
    const id = ids[k], after = k + 1 < rivals.length ? ids[k + 1].challenger : 0;
    const next = trainIds[k] ?? (rv.news && newsId !== null ? newsId : tbIds[k + 1] ?? after);   // (a circuit's title: the
                                                            // training run first; before one, its TITLE BOUT!!)
    if (trainIds[k] !== undefined) S[trainIds[k]].pressStart.target = after;
    const rivalPals = k === 0 ? { s: 3, g: 4, h: 5 } : (() => {   // his own three, past the first rival's
      const set = [0, 1, 2].map(j => [matOf(rv), ...rv.palettes[j].slice(1)]);   // (the three apart, as his fight has them:
      const same = (i, j) => JSON.stringify(p.palettes[i + j]?.colors) === JSON.stringify(set[j]);   // reused only together)
      let at = p.palettes.findIndex((_, i) => [0, 1, 2].every(j => same(i, j)));
      if (at < 0) {
        at = p.palettes.length;
        ['skin', 'gloves', 'hair'].forEach((part, j) => p.palettes.push(pal(`${rv.short} ${part}`, set[j])));
      }
      return { s: at, g: at + 1, h: at + 2 };
    })();
    for (const sc of [id.challenger, id.rematch, id.corner]) cellPalettes(S[sc], 0, 0, M.CW, M.CH, ROLE.t);
    for (const sc of [id.win, id.lose, id.winTko]) cellPalettes(S[sc], 0, 0, M.CW, M.CH, ROLE.t);

    // ---- Challenger: his rank, name and portrait top right with your record beside it; your name and portrait
    // bottom left with his record beside it ----
    // ---- The same screens with the NES's close-ups at their own size (80x72: his top right, Doc and Mac bottom
    // left), the words around them in what's left: Mac's above his, the rival's under his (10 wide, the NES's
    // breaks kept where they fit). A bio too long for its rows (King Hippo's) moves his close-up up a row. ----
    const FW = 10, FH = 9;
    const wordsTo = (q, width) => rewrap(q, width);
    function bioOf() {
      return [nesText(rv.lines[0]), ...wordsTo(rv.lines.slice(1), FW)];
    }
    function fullChallenger(scene, lay, rematch) {
      fillRect(lay, 0, 0, M.W, M.H, 3);
      const bio = bioOf(), compact = bio.length > 6;
      portrait(scene, lay, rv.portraitFull, M.CW - FW, compact ? 2 : 3);
      portrait(scene, lay, P.portraitFull, 0, M.CH - FH);
      const over = [...overlaySprites(scene, rv.portraitFull, 0, M.CW - FW, compact ? 2 : 3),
                    ...overlaySprites(scene, P.portraitFull, 0, 0, M.CH - FH)];
      if (scene.overlay) Object.assign(scene.overlay, { sprites: over, dmg: [
        ...overlaySprites(scene, rv.portraitFull, 0, M.CW - FW, compact ? 2 : 3, true), ...overlaySprites(scene, P.portraitFull, 0, 0, M.CH - FH, true)] });
      const right = (text, y, textSlot) => {
        const label = nesText(text);
        return { label, x: M.CW - label.length, y, textSlot };
      };
      const lines = rv.playerLines || P.lines;
      const record = rematch ? lines.map(l => l.replace(/^(\d+)-(\d+) /, (_, w, l2) => `${w}-${+l2 + 1} `)) : lines;
      const circuit = circuitOf(rv), tag = rematch ? 'REMATCH' : rv.titleBout ? 'TITLE BOUT' : null;
      const header = compact
        ? [{ label: circuit, x: 0, y: 0, textSlot: 1 },
           ...(tag && circuit.length + 1 + tag.length <= M.CW ? [right(tag, 0, 1)] : []),
           { label: nesText(rv.name), x: 0, y: 2, textSlot: 0 }, right(rv.rank, 1, 2)]
        : [{ label: circuit, x: 0, y: 0, textSlot: 1 }, ...(tag ? [{ label: tag, x: 0, y: 1, textSlot: 1 }] : []),
           right(rv.rank, 1, 2), right(rv.name, 2, 0)];
      const top = compact ? 11 : 12;
      const his = !compact && bio.length < 6 ? [bio[0], '"PROFILE"', ...bio.slice(1)] : bio;
      scene.texts = [
        ...header,
        ...record.map((label, n) => ({ label: nesText(label), y: 8 - record.length + n, textSlot: 0,
                                       x: /^FROM /.test(record[n - 1] || '') && !label.includes(':')
                                         ? record[n - 1].length - label.length : titleX(label),
                                       ...(/^\d+-\d+ \d+KO$/.test(label) ? { record: true } : {}) }))
              .filter(t => t.label),
        { label: nesText(rv.playerRank || P.rank), x: 0, y: 8, textSlot: 2 },
        ...his.map((label, n) => right(label, top + n, 0)),
      ];
      const aw = (pack.anotherWorld || []).indexOf(rv.short);   // (the Another World Circuit's words: as the other)
      if (aw >= 0) {
        const last = aw === pack.anotherWorld.length - 1, n = pack.anotherWorld.length;
        const awTag = rematch ? 'REMATCH' : last ? 'TITLE BOUT' : null;   // (in CIRCUIT's place: no room for both)
        const low = !compact && nesText(rv.name).length >= 13 ? 3 : 2;   // (a long name over row 2: Mac's lines a row down)
        scene.awTexts = [
          { label: 'ANOTHER WORLD', x: 0, y: 0, textSlot: 1 },
          compact ? { label: nesText(rv.name), x: 0, y: 1, textSlot: 0 } : { label: awTag || 'CIRCUIT', x: 0, y: 1, textSlot: 1 },
          ...scene.texts.filter(t => t.y > 1 && !(t.x <= 2 && t.y >= 2 && t.y <= 8) && !(last && t.label === nesText(rv.name))),
          right(last ? 'ANOTHER' : `RANKED: #${n - 1 - aw}`, 1, 2),   // (the champion: the NES's own slip, CHAMPION
          ...(last ? [right('MCHAMPIONN', 2, 0)] : []),               //  over his name's MIKE TYSON, its ends left)
          ...['"WORLD"', '"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER'].map((label, j) => ({ label, x: j < 4 ? 1 : 2, y: low + j, textSlot: 0 })),
          { label: nesText('0-0 0KO'), x: 0, y: low + 5, textSlot: 0, record: true },
          ...(low === 2 ? [{ label: nesText(`RANKED: #${n - aw}`), x: 0, y: 8, textSlot: 2 }] : []),
        ];
      }
      scene.pressStart = { target: id.fight, flashes: 3, area: null, prompt: null,   // (no room left for PUSH START!)
                           ...(rv.nes?.sound ? { nesDmc: 1 } : {}),
                           ...(CARD !== null ? { card: card([{ label: 'ROUND', dots: dots(1) }]) }
                                             : rv.nes?.sound ? { hold: 160 } : {}) };
      scene.slideIn = true;
      if (rv.nes?.sound) scene.nesDmc = 1;
    }
    function challenger(scene, lay, rematch) {
      if (rv.portraitFull && P.portraitFull) return fullChallenger(scene, lay, rematch);
      fillRect(lay, 0, 0, M.W, M.H, 3);
      portrait(scene, lay, rv.portrait, M.CW - PT, 3);
      portrait(scene, lay, P.portrait, 0, 10);
      const right = (text, y, textSlot) => {
        const label = nesText(text);
        return { label, x: M.CW - label.length, y, textSlot };
      };
      const lines = rv.playerLines || P.lines;          // (your record as it stands by then)
      const record = rematch ? lines.map(l => l.replace(/^(\d+)-(\d+) /, (_, w, l2) => `${w}-${+l2 + 1} `)) : lines;
      scene.texts = [
        { label: circuitOf(rv), x: 0, y: 0, textSlot: 1 },
        ...(rematch ? [{ label: 'REMATCH', x: 0, y: 1, textSlot: 1 }] : rv.titleBout ? [{ label: 'TITLE BOUT', x: 1, y: 1, textSlot: 1 }] : []),
        right(rv.rank, 1, 2), right(rv.name, 2, 0),
        ...record.map((label, n) => ({ label: nesText(label), y: 8 - record.length + n, textSlot: 0,   // (your record: as it
                                       x: /^FROM /.test(record[n - 1] || '') && !label.includes(':')    // stands, live; a
                                         ? record[n - 1].length - label.length : titleX(label),        // place under its
                                       ...(/^\d+-\d+ \d+KO$/.test(label) ? { record: true } : {}) }))   // FROM, its end's)
              .filter(t => t.label),
        { label: nesText(rv.playerRank || P.rank), x: 0, y: 8, textSlot: 2 }, { label: P.name, x: 0, y: 9, textSlot: 0 },
        { label: 'VS.', x: PT + 1, y: 10, textSlot: 1 },
        ...(rv.lines.length < 6 ? [rv.lines[0], '"PROFILE"', ...rv.lines.slice(1)] : rv.lines)   // ("PROFILE", the NES's,
          .map((label, n) => right(label, 11 + n, 0)),                                          // where it fits)
      ];
      const aw = (pack.anotherWorld || []).indexOf(rv.short);   // Punch-Out!!'s Another World Circuit: the same
      if (aw >= 0) {                                       // screen with its words (shown when that circuit's on)
        const last = aw === pack.anotherWorld.length - 1, n = pack.anotherWorld.length;
        const rank = scene.texts.find(t => t.label === nesText(rv.rank) && t.y === 1);
        scene.awTexts = [
          { label: 'ANOTHER WORLD', x: 0, y: 0, textSlot: 1 }, { label: 'CIRCUIT', x: 0, y: 1, textSlot: 1 },
          ...(rematch ? [{ label: 'REMATCH', x: 0, y: 2, textSlot: 1 }] : last ? [{ label: 'TITLE BOUT', x: 0, y: 2, textSlot: 1 }] : []),
          ...scene.texts.filter(t => t.y > 1 && !(t.x === 0 && t.y >= 3 && t.y <= 8)),
          ...(rank ? [right(last ? 'CHAMPION' : `RANKED: #${n - 1 - aw}`, 1, 2)] : []),
          ...(rematch || last ? ['"WORLD"', '"MAJOR"', '"MINOR"', 'TITLE-HOLDER'].map((label, j) => ({ label, x: j < 3 ? 1 : 0, y: 3 + j, textSlot: 0 }))
                              : ['"WORLD"', '"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER'].map((label, j) =>   // (the NES's: its
                                  ({ label, x: j < 4 ? 1 : 2, y: 2 + j, textSlot: 0 }))),          // lines indented)
          { label: nesText('0-0 0KO'), x: 0, y: 7, textSlot: 0, record: true },
          { label: nesText(`RANKED: #${n - aw}`), x: 0, y: 8, textSlot: 2 },
        ];
      }
      scene.pressStart = { target: id.fight, flashes: 3, area: null, prompt: { label: 'PUSH START!', x: 9, y: 17, textSlot: 1, blink: true },
                           ...(rv.nes?.sound ? { nesDmc: 1 } : {}),      // Start sets the crowd off, as in Punch-Out!!,
                           ...(CARD !== null ? { card: card([{ label: 'ROUND', dots: dots(1) }]) }   // and the round card
                                             : rv.nes?.sound ? { hold: 160 } : {}) };      // comes up (or it holds)
      scene.slideIn = true;
      if (rv.nes?.sound) scene.nesDmc = 1;               // the crowd as it comes up, on into the fight
    }
    // Punch-Out!!'s between rounds: the challenger screen's two portraits and records, Doc's word to Mac typed
    // out (after round 1 his tip for this fight, after round 2 one of his sayings), then the rival's (one of
    // his lines), then PUSH START!. Its letters tick as the NES's (Doc's and the rival's apart).
    function nesCorner(scene, lay) {
      const full = rv.portraitFull && P.portraitFull;   // (the NES's close-ups at their size: Doc's hand and mouth
      if (full) {                                        // moving, faster once Select's pressed)
        const talk = rv.portraitFull.talk;              // (the rival talking: his two states in turn, the NES's frames)
        portrait(scene, lay, talk ? { ...rv.portraitFull, pixels: talk.states[0] } : rv.portraitFull, M.CW - FW, 3);
        portrait(scene, lay, P.portraitFull, 0, M.CH - FH);
        if (P.portraitFull.states) scene.docAnim = { x: 0, y: M.CH - FH, w: FW, h: FH, states: P.portraitFull.states,
                                                     sprites: [0, 1, 2, 3].map(k => overlaySprites(scene, P.portraitFull, k, 0, M.CH - FH)),
                                                     dmgSprites: [0, 1, 2, 3].map(k => overlaySprites(scene, P.portraitFull, k, 0, M.CH - FH, true)) };
        if (talk) scene.rivalAnim = { x: M.CW - FW, y: 3, w: FW, h: FH, states: talk.states, time: talk.time,
                                      sprites: [1, 2].map(k => overlaySprites(scene, rv.portraitFull, k, M.CW - FW, 3)),
                                      dmgSprites: [1, 2].map(k => overlaySprites(scene, rv.portraitFull, k, M.CW - FW, 3, true)) };
        const still = talk ? [] : overlaySprites(scene, rv.portraitFull, 0, M.CW - FW, 3);
        if (scene.overlay) Object.assign(scene.overlay, { sprites: still, dmg: talk ? [] : overlaySprites(scene, rv.portraitFull, 0, M.CW - FW, 3, true) });
      } else {
      portrait(scene, lay, rv.portrait, M.CW - PT, 3);   // his top right, Mac's bottom left
      portrait(scene, lay, P.portrait, 0, M.CH - PT);
      }
      const right = (text, y, textSlot) => {             // (a record too wide beside his name: kept short)
        const label = /^\d+-\d+ \d+KO$/.test(text) && nesText(text).length + P.name.length >= M.CW ? text : nesText(text);
        return { label, x: M.CW - label.length, y, textSlot };
      };
      const playerRecord = nesText((rv.playerLines || P.lines).at(-1));
      scene.texts = full ? [
        { label: circuitOf(rv), x: 0, y: 0, textSlot: 1 },
        ...(rv.titleBout ? [{ label: 'TITLE BOUT', x: 0, y: 1, textSlot: 1 }] : []),
        right(rv.rank, 1, 2), right(rv.name, 2, 0),
        { label: playerRecord, x: 0, y: 8, textSlot: 0, record: true },          // Mac's record over him, the rival's
        { ...right(rv.lines[0], 12, 0), label: nesText(rv.lines[0]), x: M.CW - nesText(rv.lines[0]).length },   // under his
      ] : [
        { label: circuitOf(rv), x: 0, y: 0, textSlot: 1 },
        ...(rv.titleBout ? [{ label: 'TITLE BOUT', x: 1, y: 1, textSlot: 1 }] : []),
        right(rv.rank, 1, 2), right(rv.name, 2, 0),
        { label: playerRecord, x: 0, y: 9, textSlot: 0, record: true },                       // Mac's record and name over
        { label: P.name, x: 0, y: 10, textSlot: 2 }, right(rv.lines[0], 10, 0),   // him, the rival's record
      ];                                                                        // under his portrait
      const DOC = full ? { x: 0, y: 3, w: FW, h: 5 } : { x: 0, y: 3, w: M.CW - PT, h: 6 };
      const RIVAL = full ? { x: M.CW - FW, y: 13, w: FW, h: 3 } : { x: PT + 1, y: M.CH - PT, w: M.CW - PT - 1, h: 6 };
      const said = (lines, h) => {                       // "...", the lines after the first one in; blank lines
        let ls = lines.length > h ? lines.filter(l => l) : lines;   // go if it's too long
        ls = ls.map((l, n) => (n ? ' ' : '"') + l);
        ls[ls.length - 1] += '"';
        return ls;
      };
      const quotedPages = (lines, box) => {              // (the close-ups' size: re-wrapped to the box, paged by it;
        const room = box.w - 1;                          // its marks at the quote's ends; a word too long, hyphenated)
        const words = lines.map(l => l.split(' ').filter(w => w));
        let ls = [];
        for (const ws of words) {
          if (!ws.length) { ls.push(''); continue; }
          let cur = '';
          for (let w of ws) {
            while (w.length > room) { if (cur) { ls.push(cur); cur = ''; } ls.push(w.slice(0, room - 1) + '-'); w = w.slice(room - 1); }
            if (!cur) cur = w;
            else if (cur.length + 1 + w.length <= room) cur += ' ' + w;
            else { ls.push(cur); cur = w; }
          }
          if (cur) ls.push(cur);
        }
        while (ls.length && !ls[ls.length - 1]) ls.pop();
        const tail = ls[ls.length - 1];                  // (room for the closing mark: the last line's indent
        if (tail && tail.length + 1 > room && (ls.length === 1 || tail.length + 1 > box.w)) {   // given up, if that's
          const cut = tail.lastIndexOf(' ');             // enough)
          if (cut > 0) ls.splice(ls.length - 1, 1, tail.slice(0, cut), tail.slice(cut + 1));
          else ls.splice(ls.length - 1, 1, tail.slice(0, room - 2) + '-', tail.slice(room - 2));
        }
        if (ls.length > box.h) ls = ls.filter(l => l);
        const pages = [];
        for (let i = 0; i < ls.length; i += box.h) pages.push(ls.slice(i, i + box.h));
        return pages.map((pg, k) => pg.map((l, n) => {
          const first = k === 0 && n === 0, last = k === pages.length - 1 && n === pg.length - 1;
          return (first ? '"' : last && l.length + 2 > box.w ? '' : ' ') + l + (last ? '"' : '');
        }));
      };
      const doc = (pages, first) => full
        ? pages.flatMap((lines, n) => { const qs = quotedPages(lines, DOC); return qs.map((ls, k) => ({ ...DOC, lines: ls, sound: 'type',
            textSlot: 0, clear: !first || n > 0 || k > 0, pause: n < pages.length - 1 || k < qs.length - 1 ? 64 : 32 })); })
        : pages.map((lines, n) => ({ ...DOC, lines: said(lines, DOC.h), sound: 'type',
        textSlot: 0, clear: !first || n > 0, pause: n < pages.length - 1 ? 64 : 32 }));
      const listen = [['LISTEN', `    ${P.hud}!!`]];
      const rival = q => {                               // his line; too long for his box: two pages, split where
        if (full) {
          const qs = quotedPages(q, RIVAL);
          return qs.map((ls, k) => ({ ...RIVAL, lines: ls, sound: 'type_alt', textSlot: 0, pause: k < qs.length - 1 ? 64 : 0, ...(k ? { clear: true } : {}) }));
        }
        const solid = q.filter(l => l);                  // the NES leaves its gap
        if (solid.length <= RIVAL.h) return { ...RIVAL, lines: said(q, RIVAL.h), sound: 'type_alt', textSlot: 0, pause: 0 };
        const gaps = q.map((l, i) => l ? -1 : i).filter(i => i > 0);   // (the gap that leaves both pages fitting;
        const fits = i => q.slice(0, i).filter(l => l).length <= RIVAL.h && q.slice(i).filter(l => l).length <= RIVAL.h;
        const gap = gaps.find(fits) ?? Math.ceil(q.length / 2);           // none: halfway)
        const [a, b] = [q.slice(0, gap).filter(l => l), q.slice(gap).filter(l => l)];
        const la = said(a, RIVAL.h), lb = said(b, RIVAL.h);
        la[la.length - 1] = la[la.length - 1].replace(/"$/, '');        // (one quote: its marks at its ends)
        lb[0] = ' ' + lb[0].slice(1);
        return [{ ...RIVAL, lines: la, sound: 'type_alt', textSlot: 0, pause: 64 },
                { ...RIVAL, lines: lb, sound: 'type_alt', textSlot: 0, pause: 0, clear: true }];
      };
      const n = Math.max(pack.docLines.length, rv.quotes.length);
      const sayings = [...Array(n).keys()].map(k => [...doc([pack.docLines[k % pack.docLines.length]], true),
                                                     rival(rv.quotes[k % rv.quotes.length])].flat());
      // (a fight with its own talk in the corner, Mac's and Doc's turns in Doc's box: a page each, a longer pause)
      const talk = pages => full
        ? pages.flatMap((lines, n) => { const qs = quotedPages(lines, DOC); return qs.map((ls, k) => ({ ...DOC, lines: ls, sound: 'type',
            textSlot: 0, clear: n > 0 || k > 0, pause: n < pages.length - 1 || k < qs.length - 1 ? 96 : 32 })); })
        : pages.map((lines, n) => ({ ...DOC, lines: said(lines, DOC.h), sound: 'type', textSlot: 0,
                                                      clear: n > 0, pause: n < pages.length - 1 ? 96 : 32 }));
      const corner = k => rv.talk?.[k] ? rv.quotes.map(q => [...talk(rv.talk[k]), rival(q)].flat()) : null;
      scene.typed = { every: 4, pick: 'round', groups: [   // (no tip of his own: Doc's sayings after round 1 too)
        corner(0) || (rv.tip ? rv.quotes.map(q => [...doc([...listen, ...rv.tip], true), rival(q)].flat()) : sayings),
        corner(1) || sayings,
      ] };
      if (rv.nes?.sound) scene.nesDmc = 1;              // the crowd between rounds too
      scene.pressStart = { target: id.fight, flashes: 1, area: null, quiet: true,   // (no sound on Start)
                           prompt: full ? { label: 'PUSH\nSTART!', x: M.CW - FW, y: M.CH - 2, textSlot: 1, blink: true }   // (the NES's,
                                        : { label: 'PUSH START!', x: PT + 1, y: M.CH - 1, textSlot: 1, blink: true },   // on two lines)
                           ...(CARD !== null ? { card: { ...card([{ label: 'ROUND', dots: dots(2) },          // the next
                                                                  { label: 'FINAL ROUND', dots: dots(3) }]),   // round's
                                                         pick: 'round' } } : {}) };                           // card
    }
    challenger(S[id.challenger], layer(id.challenger), false);
    challenger(S[id.rematch], layer(id.rematch), true);  // after a loss: Punch-Out!!'s REMATCH

    // ---- The ring ----
    const sf = S[id.fight], ring = layer(id.fight);
    let crowd = 1;                                          // his crowd's color (Punch-Out!!'s differs by fight)
    if (rv.crowdColor) {
      const [c0, , c2, c3] = p.palettes[1].colors;
      crowd = addPal(`${rv.short} crowd`, [c0, rv.crowdColor, c2, c3]);
    }
    let mat = 2;                                            // his ring's mat (another circuit's: its own)
    if (String(matOf(rv)) !== String(p.palettes[2].colors[0])) {
      mat = addPal(`${rv.short} mat`, [matOf(rv), ...p.palettes[2].colors.slice(1)]);
    }
    cellPalettes(sf, 0, 0, M.CW, 3, 0);
    cellPalettes(sf, 0, 3, M.CW, 2, crowd);
    cellPalettes(sf, 0, 5, M.CW, 13, mat);
    let ropeRow = null, sideRope = null;                    // (Punch-Out!!'s: the crowd's last row, behind his head;
                                                            // the side ropes' ends below it)
    const nesRing = ringOf(rv)?.wall;                       // Punch-Out!!'s: the HUD in boxes on its wall, the crowd
    const hud = nesRing                                     // behind three ropes, red posts with blue pads
      ? { stars: { x: 1, y: 1 }, hearts: { x: 3, y: 1 }, points: { x: 7, y: 1 }, clock: { x: 15, y: 1 },
          round: { x: 12, y: 2 }, playerBar: { x: 0, y: 2 }, rivalBar: { x: 14, y: 2 } }
      : { stars: { x: 1, y: 0 }, hearts: { x: 3, y: 0 }, points: { x: 6, y: 0 }, clock: { x: 15, y: 0 },
          round: { x: 13, y: 0 }, playerBar: { x: 1, y: 1 }, rivalBar: { x: 13, y: 1 } };
    if (nesRing) {
      const r = ringOf(rv), [white, , , dark] = p.palettes[crowd].colors;
      const wall = addPal(`${rv.short} wall`, [r.wall, white, r.wall, r.brick]);
      const posts = addPal(`${rv.short} posts`, [white, matOf(rv), dark, r.post]);
      // The HUD as Punch-Out!!'s: boxes on the arena's wall (its lamps along the top). Left: stars, hearts, your
      // bar; middle: points, the round; right: the clock, his bar.
      const boxes = [[0, 5], [7, 12], [14, 19]];
      cellPalettes(sf, 0, 0, M.CW, 3, wall);
      for (const [x0, x1] of boxes) cellPalettes(sf, x0, 1, x1 - x0 + 1, 2, 0);
      for (let y = 0; y < 24; y++) for (let x = 0; x < M.W; x++)       // bricks, joints staggered
        ring.pixels[y * M.W + x] = y % 4 === 3 || x % 8 === (y % 8 >= 4 ? 4 : 0) ? 3 : 0;
      for (let x = 2; x < M.W; x += 8) {                    // the lamps
        fillRect(ring, x, 0, 4, 3, 1); ring.pixels[x] = 3; ring.pixels[x + 3] = 3;
      }
      for (const [x0, x1] of boxes) fillRect(ring, x0 * 8, 8, (x1 - x0 + 1) * 8, 16, 3);
      icon(ring, 0, 1, STAR); icon(ring, 2, 1, HEART);
      M.drawText(ring, 'ROUND', 56, 16, 0);
      // The crowd: heads in rows behind three ropes, as tall as Punch-Out!!'s (to the fighter's head: he stands in
      // front of them); the posts' cells their own (the floor's blue outside the ring). The bottom 8 lines are the
      // rope row (the band over his area's first row, his head in front of it: sprites).
      const CROWD = 24, crowdPx = new Uint8Array(M.W * CROWD).fill(3);
      const CROWD_REPEAT = 128;                             // (the crowd's art: the ring's width of it, 1:1)
      const put = (x, y, slot) => { crowdPx[(y - 24) * M.W + x] = slot; };
      const ropes = [29, 36, 43];
      for (let y = 24; y < 24 + CROWD; y++) {
        if (ropes.includes(y)) continue;
        const art = pack.crowdArt?.[y - 24];              // Punch-Out!!'s own spectators (1:1), else a pattern
        for (let x = 16; x < M.W - 16; x++) {
          if (art) { if (art[(x - 16) % CROWD_REPEAT] === '1') put(x, y, 1); continue; }   // (its first stretch, again:
          const r4 = (y - 24) % 5, shift = Math.floor((y - 24) / 5) % 2 ? 2 : 0, k = (x + shift) % 4;
          if ((r4 < 2 && k < 2) || (r4 === 2 && k < 3) || (r4 === 3 && k === 1)) put(x, y, 1);
        }
      }
      for (const y of ropes) for (let x = 12; x < M.W - 12; x++) put(x, y, 0);
      // The posts a tile in from the edges, as Punch-Out!!'s: red, a blue pad at each rope, the ring's sides off
      // them down to the screen's edge (the last of them, past the crowd's rows, sprites: SIDE_ROPE)
      const sideY = (y0, x) => y0 + Math.round(1.8 * (8 - x));   // a side rope's line, x 0-7 (its post at 8)
      for (const side of [0, 1]) {
        const at = (x, y, slot) => put(side ? M.W - 1 - x : x, y, slot);
        for (let y = 24; y < 24 + CROWD; y++) for (let x = 0; x < 16; x++) at(x, y, 2);   // outside the ring: dark
        for (let y = 24; y < 24 + CROWD; y++) { at(8, y, 3); at(9, y, 3); at(10, y, 2); }   // the post (its edge dark)
        for (const y of ropes) {
          for (let x = 11; x < 16; x++) at(x, y, 0);        // the rope to it
          for (let x = 7; x < 11; x++) for (let dy = -1; dy <= 1; dy++) at(x, y + dy, 1);   // its pad
          for (let x = 0; x < 8; x++) {                     // and the ring's side, down off it (unbroken)
            for (let yy = sideY(y, x + 1) + 1; yy <= sideY(y, x); yy++) if (yy < 24 + CROWD) at(x, yy, 0);
          }
        }
      }
      sideRope = [...Array(8 * 16)].map((_, i) => {        // (below the crowd's rows: the side ropes' ends, 8x16)
        const x = i % 8, y = 48 + (i >> 3);
        return ropes.some(y0 => y > sideY(y0, x + 1) && y <= sideY(y0, x)) ? 2 : 0;
      }).join('');
      cellPalettes(sf, 0, 3, 2, 2, posts); cellPalettes(sf, M.CW - 2, 3, 2, 2, posts);
      for (let i = 0; i < M.W * 16; i++) ring.pixels[24 * M.W + i] = crowdPx[i];   // two rows in the scene, the
      ropeRow = { pixels: [...crowdPx.slice(M.W * 16)].join(''),                    // third its own
                  cells: [...Array(M.CW).keys()].map(c => (c < 2 || c >= M.CW - 2 ? posts : crowd)) };
        } else {
      if (ringOf(rv)?.post) {                               // the corner posts in the ring's colors, pads the mat's
        const [c0, , c2] = p.palettes[crowd].colors;
        const posts = addPal(`${rv.short} posts`, [c0, matOf(rv), c2, ringOf(rv).post]);
        cellPalettes(sf, 0, 4, 1, 1, posts); cellPalettes(sf, M.CW - 1, 4, 1, 1, posts);
      }
      fillRect(ring, 0, 0, M.W, 24, 3);                     // HUD
      icon(ring, 0, 0, STAR); icon(ring, 2, 0, HEART);
      M.drawText(ring, 'R', 96, 0, 0);
      M.drawText(ring, P.hud, 8, 16, 1); M.drawText(ring, rv.hud, 104, 16, 1);
      fillRect(ring, 0, 24, M.W, 16, 3);                    // crowd in the dark, ropes across
      for (let x = 0; x < M.W; x += 4) {
        ring.pixels[(26 + (x % 8 ? 1 : 3)) * M.W + x] = 1; ring.pixels[(27 + (x % 8 ? 1 : 3)) * M.W + x + 1] = 1;
      }
      for (const y of [32, 36]) { fillRect(ring, 0, y, M.W, 1, 0); fillRect(ring, 0, y + 1, M.W, 1, 2); }
      for (const side of [0, 1]) {                          // the corner posts (a tile each), their pads on the
        const at = (x, y, slot) => { ring.pixels[y * M.W + (side ? M.W - 1 - x : x)] = slot; };   // ropes, and the
        for (let y = 32; y < 40; y++) for (let x = 0; x < 4; x++) at(x, y, 3);                   // side ropes off the edge
        for (const y of [32, 36]) for (let j = 0; j < 3; j++) {
          if (y + 1 + j < 40) at(2 - j, y + 1 + j, 0);
          if (y + 2 + j < 40) at(2 - j, y + 2 + j, 2);
        }
        for (let y = 26; y < 40; y++) { at(4, y, 0); at(5, y, 2); at(6, y, 2); }  // (up in the crowd: no flashes there)
        at(4, 26, 3); at(6, 26, 3);
        for (const y of [32, 36]) for (let x = 3; x < 8; x++) { at(x, y, 1); at(x, y + 1, 1); }
      }
    }
    fillRect(ring, 0, 40, M.W, 104, 0);                     // the mat, plain to the bottom as Punch-Out!!'s (the rival's
                                                            // rows scroll on their own as he moves)
    sf.fight = {
      rival: { x: 6, y: 5, palettes: rivalPals, poses: rv.poses, ...(rv.cgbPoses ? { cgbPoses: rv.cgbPoses } : {}) },
      player: { palette: 0, tiredPalette: 2, ...(P.downColors ? { downPalette: 3 } : {}), poses: P.poses, ...(P.cgbPoses ? { cgbPoses: P.cgbPoses } : {}) },
      referee: { palette: 1, poses: pack.referee?.poses || REF_POSES, ...(pack.referee?.words ? { words: pack.referee.words } : {}),
                 ...(pack.referee?.shirtColors ? { shirtPalette: P.downColors ? 4 : 3 } : {}) },
      hud, ...(ropeRow ? { ropeRow } : {}), ...(sideRope ? { sideRope } : {}),
      textSlot: 0, barSlot: 2, crowdRow: 3,
      opening: [['idle', 250], ['idle', 250], ['idle', 250], ['idle', 250]],      // does nothing for 40 seconds
      loop: [['idle', 90], ['jab', 0], ['idle', 60], ['guard', 90], ['jab', 0], ['idle', 40], ['hook', 0],
             ['idle', 70], ['guard', 60], ['jab', 0], ['idle', 30], ['jab', 0], ['idle', 50], ['hook', 0]],
      timed: [{ round: 1, time: '0:40', op: 'taunt', arg: 0 }, { round: 2, time: '0:30', op: 'taunt', arg: 0 },
              { round: 3, time: '0:30', op: 'taunt', arg: 0 }],
      win: id.win, lose: id.lose, corner: id.corner, ...(pack.loseGlove ? { winTko: id.winTko } : {}),
      ...(pack.effects ? { effects: { ...pack.effects } } : {}),
      ...(rv.nes ? { nes: { ...rv.nes } } : {}),
    };
    for (const [c, palette] of M.rivalPoseCells(sf.fight, 'idle')) sf.cellPal[c] = palette;

    // ---- After the fight ----
    if (pack.loseGlove) {                                  // Punch-Out!!'s: "GREAT FIGHTING", ranked up
      const ranked = rv.winRank || `RANKED UP TO #${(rv.rank.match(/\d+/) || ['1'])[0]}`;
      for (const [sc, how] of [[id.win, 'KO'], [id.winTko, 'TKO']]) {
        const champ = rv.winRank ? [ranked, 80, M.W - 8 - ranked.length * 8] : [ranked, 80];   // a title: the glove
        nesScreen(S[sc], layer(sc), [['"GREAT FIGHTING"', 40], [`YOU WON BY ${how}!`, 56], champ, ...NEXT], ranked,
                  rv.winRank ? 8 : undefined, circuitOf(rv));                                                  // beside the line
        S[sc].pressStart = { target: next, flashes: 3, area: null, quiet: true, prompt: { label: 'PUSH START!', x: 4, y: 17, textSlot: 1, blink: true } };
      }
      const rematch = "LET'S REMATCH!";                  // "DON'T CRY, MAC!", then the rematch
      nesScreen(S[id.lose], layer(id.lose), [[`"DON'T CRY,${P.hud}!"`, 40], ['YOU LOST!', 56], [rematch, 80], ...NEXT], rematch,
                undefined, circuitOf(rv));
      S[id.lose].pressStart = { target: id.rematch, flashes: 3, area: null, quiet: true, prompt: { label: 'PUSH START!', x: 4, y: 17, textSlot: 1, blink: true } };
    } else {
      const winL = layer(id.win), loseL = layer(id.lose);
      fillRect(winL, 0, 0, M.W, M.H, 3);
      M.drawText(winL, 'K.O.!', 41, 33, 2, 3); M.drawText(winL, 'K.O.!', 40, 32, 1, 3);
      S[id.win].texts = pack.win.map((label, n) => ({ label, x: centered(label) >> 3, y: 9 + n, textSlot: 0 }));
      S[id.win].pressStart = { target: next, flashes: 3, area: null, prompt: { label: 'PRESS START', x: 4, y: 15, textSlot: 1, blink: true } };
      fillRect(loseL, 0, 0, M.W, M.H, 3);
      const wins = `${rv.hud} WINS`;
      M.drawText(loseL, wins, centered(wins, 2) + 1, 41, 2, 2); M.drawText(loseL, wins, centered(wins, 2), 40, 0, 2);
      S[id.lose].texts = pack.lose.map((label, n) => ({ label, x: centered(label) >> 3, y: 9 + n, textSlot: 1 }));
      S[id.lose].pressStart = { target: 0, flashes: 3, area: null, prompt: { label: 'PRESS START', x: 4, y: 15, textSlot: 1, blink: true } };
    }

    // ---- The corner, between rounds: a word from each side ----
    const cornerL = layer(id.corner), sc = S[id.corner];
    fillRect(cornerL, 0, 0, M.W, M.H, 3);
    if (rv.quotes && pack.docLines) {                    // Punch-Out!!'s: the challenger screen, Doc's word typed
      nesCorner(sc, cornerL);                            // top left, then the rival's under his portrait
      return;
    }
    portrait(sc, cornerL, rv.hurtPortrait || rv.portrait, 1, 2);
    const say = PT + 2;                                    // his words, right of his portrait
    const words = rv.corner || pack.corner;
    sc.texts = [
      { label: 'BETWEEN ROUNDS', x: 3, y: 0, textSlot: 1 },
      { label: `${rv.hud}:`, x: say, y: 3, textSlot: 2 },
      ...words.rival.map((label, n) => ({ label, x: say, y: 4 + n, textSlot: 0 })),
      { label: 'COACH:', x: 1, y: 10, textSlot: 2 },
      ...words.coach.map((label, n) => ({ label, x: 0, y: 11 + n, textSlot: 0 })),
      { label: 'SELECT: CATCH BREATH', x: 0, y: 15, textSlot: 1 },
    ];
    if (rv.nes?.sound) sc.nesDmc = 1;                     // the crowd between rounds too
    sc.pressStart = { target: id.fight, flashes: 1, area: null, quiet: true,   // (Punch-Out!!'s corner: no sound on Start)
                      prompt: { label: 'START: FIGHT', x: 4, y: 17, textSlot: 1, blink: true } };
  });

  // ---- Pass key: Punch-Out!!'s ten digits (not checked yet) ----
  cellPalettes(S[5], 0, 0, M.CW, M.CH, ROLE.t);
  fillRect(passKey, 0, 0, M.W, M.H, 3);
  S[5].texts = [{ label: 'PASS KEY', x: 6, y: 4, textSlot: 1 },
                { label: 'UP/DOWN: NUMBER', x: 2, y: 12, textSlot: 0 }, { label: 'LEFT/RIGHT: MOVE', x: 2, y: 13, textSlot: 0 },
                { label: 'START: OK  B: BACK', x: 1, y: 15, textSlot: 0 }];
  S[5].passKey = { x: 4, y: 8, textSlot: 0, target: 1 };
  S[5].back = 0;

  // ---- Punch-Out!!'s Another World Circuit (its pass key): these fights in this order, each on to the next's
  // challenger, a loss down to the one before's ----
  const awOrder = (pack.anotherWorld || []).map(short => rivals.findIndex(rv => rv.short === short)).filter(k => k >= 0);
  awOrder.forEach((k, j) => {
    S[ids[k].fight].fight.anotherWorld = {
      next: j + 1 < awOrder.length ? (j + 2 === awOrder.length && awTbId !== null ? awTbId : ids[awOrder[j + 1]].challenger) : null,
      drop: j > 0 ? ids[awOrder[j - 1]].challenger : null, first: j === 0, final: j === awOrder.length - 1 };
  });

  // ---- The ending, after the last rival (Punch-Out!!'s, after Mike Tyson): his word to Mac under his portrait (his
  // win screens become it), each fighter's portrait and name in turn (the ten, no rematches), then Mac standing on
  // blue (the game's own picture), his record and THE END typed under him. Its song plays from the first; Start
  // at the end goes back to the title (the game's stays there). ----
  if (pack.ending) {
    const E = pack.ending, last = rivals[rivals.length - 1], lid = ids[rivals.length - 1];
    const blank = name => ({ name, pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH).fill(ROLE.t),
      menu: null, pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [] });
    const parade = rivals.filter(r => !/2$/.test(r.short) && r !== last);
    const at = p.scenes.length;                          // the parade's first, then the end
    parade.forEach((rv, k) => {
      const sc = blank(`Ending: ${rv.short}`), lay = { palettes: p.palettes, pixels: sc.pixels, cellPal: sc.cellPal };
      fillRect(lay, 0, 0, M.W, M.H, 3);
      portrait(sc, lay, rv.portrait, 6, 5);
      sc.texts = [{ label: rv.name, x: centered(rv.name) >> 3, y: 4, textSlot: 0 }];
      sc.pressStart = { target: at + k + 1, flashes: 1, area: null, quiet: true, auto: E.frames.portrait };
      sc.notes = 'Punch-Out!!\'s ending: each fighter in turn. It goes on by itself.';
      p.scenes.push(sc);
    });
    const end = blank('The end');
    const endPal = addPal('Ending', [E.navy, [31, 31, 31], [31, 31, 31], [31, 31, 31]]);
    end.cellPal.fill(endPal);
    const macPals = E.mac.palettes.map((c, k) => addPal(`Ending Mac ${k + 1}`, c));
    const mx = (M.W - E.mac.w) >> 1, my = 8;
    for (let i = 0; i < E.mac.w * E.mac.h; i++) end.pixels[(my + (i / E.mac.w | 0)) * M.W + mx + i % E.mac.w] = +E.mac.pixels[i];
    [...E.mac.cells].forEach((c, k) => { end.cellPal[((my >> 3) + (k / (E.mac.w >> 3) | 0)) * M.CW + (mx >> 3) + k % (E.mac.w >> 3)] = macPals[+c]; });
    const record = last.playerLines[last.playerLines.length - 1].replace(/^(\d+)-(\d+) (\d+)KO$/, (_, w, l, ko) => nesText(`${+w + 1}-${l} ${+ko + 1}KO`));
    end.texts = [{ label: record, x: centered(record) >> 3, y: 15, textSlot: 3, record: true }];   // (his, as it stands)
    end.typed = { every: 15, pick: 'random', groups: [[[{ x: centered('THE END') >> 3, y: 17, w: 7, h: 1, lines: ['THE END'],
                                                           textSlot: 3, sound: null, pause: 0 }]]] };
    end.pressStart = { target: 0, flashes: 1, area: null, quiet: true, never: true };
    end.notes = 'Punch-Out!!\'s last screen: Mac, his record, THE END. It stays (Start does nothing, as the game\'s).';
    p.scenes.push(end);
    for (const w of [lid.win, lid.winTko]) {             // his word to Mac, where the win screen was
      const sc = S[w], lay = layer(w);
      sc.cellPal.fill(ROLE.t); fillRect(lay, 0, 0, M.W, M.H, 3);
      portrait(sc, lay, last.portrait, 6, 1);
      sc.texts = E.tyson.map((label, n) => ({ label, x: centered(label) >> 3, y: 9 + n + (n > 0), textSlot: 0 }));
      if ((pack.anotherWorld || []).includes(last.short))   // the Another World Circuit's: the fight's time, as the NES
        sc.awTexts = [...sc.texts, { label: 'TIME 0:00.00,R1', x: 2, y: 16, textSlot: 0, fightTime: true }];   // gives it
      sc.pressStart = { target: at, flashes: 1, area: null, quiet: true, auto: E.frames.word };
      sc.notes = 'Punch-Out!!\'s ending begins: his word to Mac. It goes on by itself; the end music the fight '
        + 'started as he went down plays on (as the game\'s: none of its ending screens starts a song).';
    }
  }

  // ---- Punch-Out!!'s staff credits (its key, 106 113 0120 with Select held): on black, each typed a letter at a time
  // as the NES types them, a pause after each; two pages (the NES's one is wider than ours). It stays. ----
  if (pack.credits) {
    const sc = plain('Credits');
    sc.cellPal.fill(ROLE.t);
    fillRect({ palettes: p.palettes, pixels: sc.pixels, cellPal: sc.cellPal }, 0, 0, M.W, M.H, 3);
    const steps = [];
    let y = 1, page = 0;
    for (const [role, ...names] of pack.credits) {
      const lines = [role, ...names.map(n => `  ${n}`)];
      if (y + lines.length > M.CH - 1) {                 // (a page full: held, cleared, the rest on the next)
        steps[steps.length - 1].pause = 240;
        steps.push({ x: 0, y: 0, w: M.CW, h: M.CH, lines: [], textSlot: 0, sound: null, pause: 36, clear: true });
        y = 1; page++;
      }
      steps.push({ x: 0, y, w: M.CW, h: lines.length, lines, textSlot: 0, sound: null, pause: 36 });
      y += lines.length + page;                           // (the second page has room for a row between)
    }
    sc.typed = { every: 4, pick: 'random', groups: [[steps]] };
    sc.pressStart = { target: 0, flashes: 1, area: null, quiet: true, never: true };
    sc.credits = true;
    sc.nesMusic = 0x1A;
    sc.notes = 'Punch-Out!!\'s staff credits (106 113 0120, Select held on its last digit): typed in, then it stays.';
    p.scenes.push(sc);
  }

  // ---- Game over (Punch-Out!!'s: the third loss, or losing the last fight): Mac on his stool, head down, the game's
  // own picture; GIVE UP? and RETIRE? either side of him, GAME OVER, and Doc's word. Start goes back to the title. ----
  if (pack.gameOver) {
    const G = pack.gameOver;
    const go = { name: 'Game over', pixels: new Uint8Array(M.W * M.H), cellPal: new Uint8Array(M.CW * M.CH),
      menu: null, pressStart: null, pressed: null, options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [] };
    const goPal = addPal('Game over', [G.bg, [0, 0, 0], [31, 31, 31], [31, 31, 31]]);   // (the line black, the words white)
    go.cellPal.fill(goPal);
    const macPals = G.mac.palettes.map((c, k) => addPal(`Game over Mac ${k + 1}`, c));
    const mx = 64, my = 8;
    for (let x = 0; x < M.W; x++) go.pixels[(my + G.line) * M.W + x] = 1;
    for (let i = 0; i < G.mac.w * G.mac.h; i++) go.pixels[(my + (i / G.mac.w | 0)) * M.W + mx + i % G.mac.w] = +G.mac.pixels[i];
    [...G.mac.cells].forEach((c, k) => { go.cellPal[((my >> 3) + (k / (G.mac.w >> 3) | 0)) * M.CW + (mx >> 3) + k % (G.mac.w >> 3)] = macPals[+c]; });
    go.texts = [{ label: G.left, x: 0, y: 3, textSlot: 3 }, { label: G.right, x: M.CW - G.right.length, y: 3, textSlot: 3 },
                { label: G.over, x: centered(G.over) >> 3, y: 14, textSlot: 3 },
                ...G.doc.map((label, n) => ({ label, x: centered(label) >> 3, y: 16 + n, textSlot: 3 }))];
    go.pressStart = { target: 0, flashes: 1, area: null };
    go.notes = 'Punch-Out!!\'s game over: the third loss, or losing to the last fighter. Start goes back to the title.';
    const goId = p.scenes.push(go) - 1;
    for (const lid of ids) S[lid.fight].fight.gameOver = goId;
  }

  // ---- First screen: Punch-Out!!'s from power-on, MIKE IS WAITING FOR YOUR CHALLENGE!!, its song playing (on
  // into the title); it goes on by itself, as the game's does (Start does nothing there). ----
  if (pack.splash) {
    const sp = pack.splash, at = p.scenes.length, slot = [];
    for (const colors of sp.palettes) {                  // (the same colors twice: one palette)
      const k = p.palettes.findIndex(q => JSON.stringify(q.colors) === JSON.stringify(colors));
      slot.push(k >= 0 ? k : p.palettes.push(pal(`First screen ${slot.length + 1}`, colors)) - 1);
    }
    p.scenes.push({ name: 'First screen', pixels: Uint8Array.from(sp.pixels, ch => +ch),
      cellPal: Uint8Array.from(sp.cells, ch => slot[+ch]),
      menu: null, pressStart: { target: 0, flashes: 1, area: null, quiet: true, auto: sp.frames }, pressed: null,
      options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [], nesMusic: sp.music,
      notes: 'Punch-Out!!\'s first screen, from power-on: its song starts here and plays on into the title. It goes on by itself.' });
    p.start = at;
    if (sp.bells) {                                      // before it, over black: the bells (as the game rings them)
      const bells = { name: 'Bells', pixels: new Uint8Array(M.W * M.H).fill(3), cellPal: new Uint8Array(M.CW * M.CH).fill(ROLE.t),
        menu: null, pressStart: { target: at, flashes: 1, area: null, quiet: true, auto: sp.bells.frames,
                                  ring: { nesSfx: sp.bells.sfx, at: sp.bells.at } }, pressed: null,
        options: null, puzzle: null, fight: null, passKey: null, back: null, texts: [],
        notes: 'Power-on, as Punch-Out!!\'s: the bell rung over black, then its first screen. It goes on by itself.' };
      p.start = p.scenes.push(bells) - 1;
    }
  }
  return p;
}
