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

export const BOXING_VERSION = 29;

const pal = (name, colors) => ({ name, colors });
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
  const matOf = rv => ringOf(rv)?.mat || MAT;
  const ROLE = { s: 3, g: 4, h: 5, t: 6 };               // portrait cells: these letters, or a digit k for portraitPalettes[k]
  const role = r => ROLE[r] ?? 7 + (/[A-Z]/.test(r) ? r.charCodeAt(0) - 55 : +r);   // (0-9, then A-Z)
  const p = {
    name: pack.name,
    palettes: [
      pal('HUD', [[31, 31, 31], [31, 26, 6], [28, 6, 6], [3, 4, 10]]),
      pal('Crowd', [[31, 31, 31], [18, 16, 24], [26, 6, 8], [4, 4, 10]]),
      pal('Mat', [matOf(R), [20, 22, 28], [8, 12, 24], [3, 3, 6]]),
      ...['skin', 'gloves', 'hair'].map((part, k) => pal(`${R.short} ${part}`, [matOf(R), ...R.palettes[k].slice(1)])),
      pal('Text', pack.textPalette),
      ...(pack.portraitPalettes || []).map((colors, k) => pal(`Portrait ${k + 1}`, colors)),
      ...(pack.titleLogo ? [pal('Title logo', pack.titleLogo.colors)] : []),
    ],
    objPalettes: [pal('Player', [[0, 0, 0], ...P.colors]),
                  pal('Referee', [[0, 0, 0], ...(pack.referee?.colors || [[31, 24, 18], [26, 29, 31], [3, 3, 6]])]),
                  pal('Player tired', [[0, 0, 0], ...P.tiredColors]),
                  ...(P.downColors ? [pal('Player down', [[0, 0, 0], ...P.downColors])] : []),
                  ...(pack.referee?.shirtColors ? [pal('Referee shirt', [[0, 0, 0], ...pack.referee.shirtColors])] : [])],
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
  const S = p.scenes;

  // A 48x48 portrait into a scene at tile (cx, cy).
  function portrait(scene, layer, face, cx, cy) {
    for (let i = 0; i < PORTRAIT * PORTRAIT; i++) {
      layer.pixels[(cy * 8 + (i / PORTRAIT | 0)) * M.W + cx * 8 + i % PORTRAIT] = +face.pixels[i];
    }
    [...face.cells].forEach((r, k) => { scene.cellPal[(cy + (k / PT | 0)) * M.CW + cx + k % PT] = role(r); });
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
      cellPalettes(S[0], 0, t.y >> 3, M.CW, t.scale, LOGO);
      fillRect(title, 0, t.y & ~7, M.W, 8 * t.scale, 0);
    }
    if (t.shadow !== undefined) M.drawText(title, t.text, t.x + 1, t.y + 1, t.shadow, t.scale);
    M.drawText(title, t.text, t.x, t.y, t.slot, t.scale);
  }
  S[0].menu = { x: 6, y: logo ? 11 : 10, spacing: 2, textSlot: 0, cursorAnimation: 'bob', blinks: 3, selectMoves: true,
                items: [{ label: 'NEW', target: 1 }, { label: 'CONTINUE', target: 5 }] };
  const punch = logo && pack.titlePunch;
  if (punch) {                                           // the glove: behind the logo's mesh, then punching out
    const text = pack.textPalette;
    S[0].menu.confirm = {
      sprite: { ...punch.sprite }, faded: true,
      steps: punch.steps.map(st => ({ frames: st.frames, colors: st.colors, front: st.front, nesSfx: st.nesSfx || 0,
                                      bg: { [LOGO]: st.logo, [ROLE.t]: [text[0], text[1], text[2], st.backdrop] } })),
    };
  }
  S[0].texts = [{ label: pack.credit, x: centered(pack.credit) >> 3, y: 16, textSlot: 0 }];

  // ---- Endings and help ----
  // Punch-Out!!'s screens after the fight: blue, the W.V.B.A. header, a word for Mac, the big glove, the next
  // challenge. LOSS and its glove's palette, then each screen's lines (rows; the glove covers the one at row 10).
  let LOSS = null;
  function nesScreen(scene, layer, lines, gloveAt, gloveX) {   // (gloveX: the glove's own place, a line's third its x)
    if (LOSS === null) {
      LOSS = p.palettes.length;
      p.palettes.push(pal('Loss', [[1, 2, 18], [7, 22, 25], [29, 29, 29], [0, 0, 0]]),       // NES $02, $2C, $30
                      pal('Loss glove', [[1, 2, 18], [19, 4, 4], [29, 13, 12], [0, 0, 0]]));  // $16, $26
    }
    cellPalettes(scene, 0, 0, M.CW, M.CH, LOSS);
    fillRect(layer, 0, 0, M.W, M.H, 0);
    const line = (text, y, slot) => M.drawText(layer, text, centered(text) >> 3 << 3, y, slot);   // (on whole tiles, as the NES's)
    line('THE W.V.B.A.', 8, 1); line(pack.circuit, 16, 1);
    for (let x = 0; x < M.W; x += 8) fillRect(layer, x + 1, 27, 5, 1, 1);
    for (const [text, y, x] of lines) x === undefined ? line(text, y, 2) : M.drawText(layer, text, x, y, 2);
    const g = pack.loseGlove, gx = gloveX ?? (centered(gloveAt) >> 3 << 3) + 5 * 8, gy = 8 * 8;
    for (let i = 0; i < g.w * g.h; i++) {               // over the line at row 10, as the NES has it (on whole tiles:
      const v = +g.pixels[i], x = gx + i % g.w, y = gy + (i / g.w | 0);   // the letters beside it keep their color)
      if (v) { layer.pixels[y * M.W + x] = v; scene.cellPal[(y >> 3) * M.CW + (x >> 3)] = LOSS + 1; }
    }
  }
  const NEXT = [['ARE YOU READY', 104], ['FOR THE', 114], ['NEXT CHALLENGE ?', 124]];

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
  rivals.forEach((rv, k) => {
    const id = ids[k], next = k + 1 < rivals.length ? ids[k + 1].challenger : 0;
    const rivalPals = k === 0 ? { s: 3, g: 4, h: 5 } : (() => {   // his own three, past the first rival's
      const at = p.palettes.length;
      ['skin', 'gloves', 'hair'].forEach((part, j) => p.palettes.push(pal(`${rv.short} ${part}`, [matOf(rv), ...rv.palettes[j].slice(1)])));
      return { s: at, g: at + 1, h: at + 2 };
    })();
    for (const sc of [id.challenger, id.rematch, id.corner]) cellPalettes(S[sc], 0, 0, M.CW, M.CH, ROLE.t);
    for (const sc of [id.win, id.lose, id.winTko]) cellPalettes(S[sc], 0, 0, M.CW, M.CH, ROLE.t);

    // ---- Challenger: his rank, name and portrait top right with your record beside it; your name and portrait
    // bottom left with his record beside it ----
    function challenger(scene, lay, rematch) {
      fillRect(lay, 0, 0, M.W, M.H, 3);
      portrait(scene, lay, rv.portrait, M.CW - PT, 3);
      portrait(scene, lay, P.portrait, 0, 10);
      const right = (label, y, textSlot) => ({ label, x: M.CW - label.length, y, textSlot });
      const lines = rv.playerLines || P.lines;          // (your record as it stands by then)
      const record = rematch ? lines.map(l => l.replace(/^(\d+)-(\d+) /, (_, w, l2) => `${w}-${+l2 + 1} `)) : lines;
      scene.texts = [
        { label: pack.circuit, x: 0, y: 0, textSlot: 1 },
        ...(rematch ? [{ label: 'REMATCH', x: 0, y: 1, textSlot: 1 }] : []),
        right(rv.rank, 1, 2), right(rv.name, 2, 0),
        ...record.map((label, n) => ({ label, x: 0, y: 3 + n, textSlot: 0 })),
        { label: rv.playerRank || P.rank, x: 0, y: 8, textSlot: 2 }, { label: P.name, x: 0, y: 9, textSlot: 0 },
        { label: 'VS.', x: PT + 1, y: 10, textSlot: 1 },
        ...rv.lines.map((label, n) => right(label, 11 + n, 0)),
      ];
      scene.pressStart = { target: id.fight, flashes: 3, area: null, prompt: { label: 'PUSH START!', x: 9, y: 17, textSlot: 1, blink: true },
                           ...(rv.nes?.sound ? { nesDmc: 1, hold: 160 } : {}) };   // Start sets the crowd off and the
                                                                   // screen stays a while with it, as in Punch-Out!!
      scene.slideIn = true;
    }
    challenger(S[id.challenger], layer(id.challenger), false);
    challenger(S[id.rematch], layer(id.rematch), true);  // after a loss: Punch-Out!!'s REMATCH

    // ---- The ring ----
    const sf = S[id.fight], ring = layer(id.fight);
    let crowd = 1;                                          // his crowd's color (Punch-Out!!'s differs by fight)
    if (rv.crowdColor) {
      crowd = p.palettes.length;
      const [c0, , c2, c3] = p.palettes[1].colors;
      p.palettes.push(pal(`${rv.short} crowd`, [c0, rv.crowdColor, c2, c3]));
    }
    let mat = 2;                                            // his ring's mat (another circuit's: its own)
    if (String(matOf(rv)) !== String(p.palettes[2].colors[0])) {
      mat = p.palettes.length;
      p.palettes.push(pal(`${rv.short} mat`, [matOf(rv), ...p.palettes[2].colors.slice(1)]));
    }
    cellPalettes(sf, 0, 0, M.CW, 3, 0);
    cellPalettes(sf, 0, 3, M.CW, 2, crowd);
    cellPalettes(sf, 0, 5, M.CW, 13, mat);
    const nesRing = ringOf(rv)?.wall;                       // Punch-Out!!'s: the HUD in boxes on its wall, the crowd
    const hud = nesRing                                     // behind three ropes, red posts with blue pads
      ? { stars: { x: 1, y: 1 }, hearts: { x: 3, y: 1 }, points: { x: 7, y: 1 }, clock: { x: 15, y: 1 },
          round: { x: 12, y: 2 }, playerBar: { x: 0, y: 2 }, rivalBar: { x: 14, y: 2 } }
      : { stars: { x: 1, y: 0 }, hearts: { x: 3, y: 0 }, points: { x: 6, y: 0 }, clock: { x: 15, y: 0 },
          round: { x: 13, y: 0 }, playerBar: { x: 1, y: 1 }, rivalBar: { x: 13, y: 1 } };
    if (nesRing) {
      const r = ringOf(rv), [white, , red, dark] = p.palettes[crowd].colors;
      const wall = p.palettes.length, posts = wall + 1;
      p.palettes.push(pal(`${rv.short} wall`, [r.wall, white, r.wall, r.brick]),
                      pal(`${rv.short} posts`, [white, matOf(rv), dark, r.post]));
      // The HUD as Punch-Out!!'s: boxes on the arena's wall (its lamps along the top). Left: stars, hearts, your
      // bar; middle: points, the round; right: the clock, his bar.
      const boxes = [[0, 5], [7, 12], [14, 19]];
      cellPalettes(sf, 0, 0, M.CW, 3, wall);
      for (const [x0, x1] of boxes) cellPalettes(sf, x0, 1, x1 - x0 + 1, 2, 0);
      for (let y = 0; y < 24; y++) for (let x = 0; x < M.W; x++)       // bricks, joints staggered
        ring.pixels[y * M.W + x] = y % 4 === 3 || x % 8 === (y & 4 ? 4 : 0) ? 3 : 0;
      for (let x = 2; x < M.W; x += 8) {                    // the lamps
        fillRect(ring, x, 0, 4, 3, 1); ring.pixels[x] = 3; ring.pixels[x + 3] = 3;
      }
      for (const [x0, x1] of boxes) fillRect(ring, x0 * 8, 8, (x1 - x0 + 1) * 8, 16, 3);
      icon(ring, 0, 1, STAR); icon(ring, 2, 1, HEART);
      M.drawText(ring, 'ROUND', 56, 16, 0);
      // The crowd: heads in rows behind three ropes; the posts' cells their own (the floor's blue outside the ring).
      cellPalettes(sf, 0, 3, 1, 2, posts); cellPalettes(sf, M.CW - 1, 3, 1, 2, posts);
      fillRect(ring, 0, 24, M.W, 16, 3);
      const ropes = [29, 34, 39];
      for (let y = 24; y < 40; y++) {
        if (ropes.includes(y)) continue;
        const r4 = (y - 24) % 5, shift = Math.floor((y - 24) / 5) % 2 ? 2 : 0;
        for (let x = 8; x < M.W - 8; x++) {
          const k = (x + shift) % 4;
          if ((r4 < 2 && k < 2) || (r4 === 2 && k < 3) || (r4 === 3 && k === 1)) ring.pixels[y * M.W + x] = 1;
        }
      }
      for (const y of ropes) fillRect(ring, 8, y, M.W - 16, 1, 0);
      for (const side of [0, 1]) {
        const at = (x, y, slot) => { ring.pixels[y * M.W + (side ? M.W - 1 - x : x)] = slot; };
        for (let y = 24; y < 40; y++) for (let x = 0; x < 8; x++) at(x, y, 1);
        for (let y = 25; y < 40; y++) for (let x = 3; x < 7; x++) at(x, y, (y >> 1) & 1 ? 0 : 3);   // the post, striped
        for (const y of ropes) {
          for (let x = 2; x < 8; x++) at(x, y, 0);          // the rope to it, its pad blue under
          if (y > 24) for (let x = 2; x < 8; x++) at(x, y - 1, 1);
          at(1, y, 0); at(0, y, 0);                         // and on off the side
        }
        for (let y = 24; y < 40; y++) at(2, y, 2);           // (its edge)
      }
        } else {
      if (ringOf(rv)?.post) {                               // the corner posts in the ring's colors, pads the mat's
        const [c0, , c2] = p.palettes[crowd].colors;
        const posts = p.palettes.length;
        p.palettes.push(pal(`${rv.short} posts`, [c0, matOf(rv), c2, ringOf(rv).post]));
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
      player: { palette: 0, tiredPalette: 2, ...(P.downColors ? { downPalette: 3 } : {}), poses: P.poses },
      referee: { palette: 1, poses: pack.referee?.poses || REF_POSES,
                 ...(pack.referee?.shirtColors ? { shirtPalette: P.downColors ? 4 : 3 } : {}) },
      hud,
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
                  rv.winRank ? 8 : undefined);                                                  // beside the line
        S[sc].pressStart = { target: next, flashes: 3, area: null, quiet: true, prompt: { label: 'PUSH START!', x: 4, y: 17, textSlot: 1, blink: true } };
      }
      const rematch = "LET'S REMATCH!";                  // "DON'T CRY, MAC!", then the rematch
      nesScreen(S[id.lose], layer(id.lose), [[`"DON'T CRY,${P.hud}!"`, 40], ['YOU LOST!', 56], [rematch, 80], ...NEXT], rematch);
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
  return p;
}
