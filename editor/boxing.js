// The boxing game template: a fight against one rival, seen from behind the player, with a title menu, a
// challenger screen, endings, help and a corner between rounds. Everything that makes it one particular game
// (names, text, colors, poses, portraits) comes from a fighter pack, so new art makes a new game on the same
// engine. Joe vs Mac (mac-vs-joe.js) is a pack.
//
// A fighter pack:
//   id, name, credit       sample id, project name, the title's credit line
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
//   player                 { name, hud, rank, lines (up to 5, 12 wide; name and rank too), colors (sprite slots 1-3), tiredColors,
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

export const BOXING_VERSION = 20;

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
  'You win': `A press-start screen. Start goes back to the title.`,
  [`${rival} wins`]: `A press-start screen. Start goes back to the title.`,
  'Corner': `Between rounds the fight fades to this corner screen, then Start goes back to the ring and the fight carries on where it was.
• Select, once per match, gets the coach working faster: a random chunk of health comes back.`,
});

const centered = (text, scale = 1) => (M.W - text.length * 8 * scale) >> 1;

export function boxingGame(pack) {
  M.useFont('bold');
  const R = pack.rival, P = pack.player;
  const ROLE = { s: 3, g: 4, h: 5, t: 6 };               // portrait cells: these letters, or a digit k for portraitPalettes[k]
  const role = r => ROLE[r] ?? 7 + +r;
  const p = {
    name: pack.name,
    palettes: [
      pal('HUD', [[31, 31, 31], [31, 26, 6], [28, 6, 6], [3, 4, 10]]),
      pal('Crowd', [[31, 31, 31], [18, 16, 24], [26, 6, 8], [4, 4, 10]]),
      pal('Mat', [MAT, [20, 22, 28], [8, 12, 24], [3, 3, 6]]),
      ...['skin', 'gloves', 'hair'].map((part, k) => pal(`${R.short} ${part}`, [MAT, ...R.palettes[k].slice(1)])),
      pal('Text', pack.textPalette),
      ...(pack.portraitPalettes || []).map((colors, k) => pal(`Portrait ${k + 1}`, colors)),
      ...(pack.titleLogo ? [pal('Title logo', pack.titleLogo.colors)] : []),
    ],
    objPalettes: [pal('Player', [[0, 0, 0], ...P.colors]),
                  pal('Referee', [[0, 0, 0], [31, 24, 18], [26, 29, 31], [3, 3, 6]]),
                  pal('Player tired', [[0, 0, 0], ...P.tiredColors])],
    cursor: { palette: 0, pixels: Uint8Array.from(
      '00333000' + '03313300' + '33133330' + '33333330' + '33333330' + '03333300' + '00222000' + '00000000', ch => +ch) },
    scenes: ['Title', 'Challenger', 'Fight', 'You win', `${R.short} wins`, 'Pass key', 'Corner'].map(name => ({
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
  const [title, tape, ring, win, lose, passKey, corner] = p.scenes.map((_, i) => M.layerOf(p, i));
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
  for (const s of [0, 1, 3, 4, 5, 6]) cellPalettes(S[s], 0, 0, M.CW, M.CH, ROLE.t);

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

  // ---- Challenger: his rank, name and portrait top right with your record beside it; your name and portrait
  // bottom left with his record beside it ----
  fillRect(tape, 0, 0, M.W, M.H, 3);
  portrait(S[1], tape, R.portrait, M.CW - PT, 3);
  portrait(S[1], tape, P.portrait, 0, 10);
  const right = (label, y, textSlot) => ({ label, x: M.CW - label.length, y, textSlot });
  S[1].texts = [
    { label: pack.circuit, x: 0, y: 0, textSlot: 1 },
    right(R.rank, 1, 2), right(R.name, 2, 0),
    ...P.lines.map((label, n) => ({ label, x: 0, y: 3 + n, textSlot: 0 })),
    { label: P.rank, x: 0, y: 8, textSlot: 2 }, { label: P.name, x: 0, y: 9, textSlot: 0 },
    { label: 'VS.', x: PT + 1, y: 10, textSlot: 1 },
    ...R.lines.map((label, n) => right(label, 11 + n, 0)),
  ];
  S[1].pressStart = { target: 2, flashes: 3, area: null, prompt: { label: 'PUSH START!', x: 9, y: 17, textSlot: 1, blink: true } };
  S[1].slideIn = true;
  if (R.nes?.sound) S[1].nesDmc = 1;                     // the crowd starts as the challenger scrolls in, as in Punch-Out!!

  // ---- The ring ----
  cellPalettes(S[2], 0, 0, M.CW, 3, 0);
  cellPalettes(S[2], 0, 3, M.CW, 2, 1);
  cellPalettes(S[2], 0, 5, M.CW, 13, 2);
  fillRect(ring, 0, 0, M.W, 24, 3);                       // HUD
  icon(ring, 0, 0, STAR); icon(ring, 2, 0, HEART);
  M.drawText(ring, 'R', 96, 0, 0);
  M.drawText(ring, P.hud, 8, 16, 1); M.drawText(ring, R.hud, 104, 16, 1);
  fillRect(ring, 0, 24, M.W, 16, 3);                      // crowd in the dark, ropes across
  for (let x = 0; x < M.W; x += 4) {
    ring.pixels[(26 + (x % 8 ? 1 : 3)) * M.W + x] = 1; ring.pixels[(27 + (x % 8 ? 1 : 3)) * M.W + x + 1] = 1;
  }
  for (const y of [32, 36]) { fillRect(ring, 0, y, M.W, 1, 0); fillRect(ring, 0, y + 1, M.W, 1, 2); }
  fillRect(ring, 0, 40, M.W, 104, 0);                     // the mat
  fillRect(ring, 0, 40, M.W, 1, 1);
  // The mat stays plain from here down to the apron: the rival's rows scroll on their own as he moves.
  fillRect(ring, 0, 128, M.W, 16, 2);                     // apron
  fillRect(ring, 0, 128, M.W, 1, 3);
  S[2].fight = {
    rival: { x: 6, y: 5, palettes: { s: 3, g: 4, h: 5 }, poses: R.poses },
    player: { palette: 0, tiredPalette: 2, poses: P.poses },
    referee: { palette: 1, poses: REF_POSES },
    hud: { stars: { x: 1, y: 0 }, hearts: { x: 3, y: 0 }, points: { x: 6, y: 0 }, clock: { x: 15, y: 0 },
           round: { x: 13, y: 0 }, playerBar: { x: 1, y: 1 }, rivalBar: { x: 13, y: 1 } },
    textSlot: 0, barSlot: 2, crowdRow: 3,
    opening: [['idle', 250], ['idle', 250], ['idle', 250], ['idle', 250]],      // does nothing for 40 seconds
    loop: [['idle', 90], ['jab', 0], ['idle', 60], ['guard', 90], ['jab', 0], ['idle', 40], ['hook', 0],
           ['idle', 70], ['guard', 60], ['jab', 0], ['idle', 30], ['jab', 0], ['idle', 50], ['hook', 0]],
    timed: [{ round: 1, time: '0:40', op: 'taunt', arg: 0 }, { round: 2, time: '0:30', op: 'taunt', arg: 0 },
            { round: 3, time: '0:30', op: 'taunt', arg: 0 }],
    win: 3, lose: 4, corner: 6,
    ...(pack.effects ? { effects: { ...pack.effects } } : {}),
    ...(R.nes ? { nes: { ...R.nes } } : {}),
  };
  for (const [c, palette] of M.rivalPoseCells(S[2].fight, 'idle')) S[2].cellPal[c] = palette;

  // ---- Endings and help ----
  fillRect(win, 0, 0, M.W, M.H, 3);
  M.drawText(win, 'K.O.!', 41, 33, 2, 3); M.drawText(win, 'K.O.!', 40, 32, 1, 3);
  S[3].texts = pack.win.map((label, n) => ({ label, x: centered(label) >> 3, y: 9 + n, textSlot: 0 }));
  S[3].pressStart = { target: 0, flashes: 3, area: null, prompt: { label: 'PRESS START', x: 4, y: 15, textSlot: 1, blink: true } };
  fillRect(lose, 0, 0, M.W, M.H, 3);
  const wins = `${R.hud} WINS`;
  M.drawText(lose, wins, centered(wins, 2) + 1, 41, 2, 2); M.drawText(lose, wins, centered(wins, 2), 40, 0, 2);
  S[4].texts = pack.lose.map((label, n) => ({ label, x: centered(label) >> 3, y: 9 + n, textSlot: 1 }));
  S[4].pressStart = { target: 0, flashes: 3, area: null, prompt: { label: 'PRESS START', x: 4, y: 15, textSlot: 1, blink: true } };
  // ---- Pass key: Punch-Out!!'s ten digits (not checked yet) ----
  fillRect(passKey, 0, 0, M.W, M.H, 3);
  S[5].texts = [{ label: 'PASS KEY', x: 6, y: 4, textSlot: 1 },
                { label: 'UP/DOWN: NUMBER', x: 2, y: 12, textSlot: 0 }, { label: 'LEFT/RIGHT: MOVE', x: 2, y: 13, textSlot: 0 },
                { label: 'START: OK  B: BACK', x: 1, y: 15, textSlot: 0 }];
  S[5].passKey = { x: 4, y: 8, textSlot: 0, target: 1 };
  S[5].back = 0;

  // ---- The corner, between rounds: a word from each side ----
  fillRect(corner, 0, 0, M.W, M.H, 3);
  portrait(S[6], corner, R.hurtPortrait || R.portrait, 1, 2);
  const say = PT + 2;                                    // his words, right of his portrait
  S[6].texts = [
    { label: 'BETWEEN ROUNDS', x: 3, y: 0, textSlot: 1 },
    { label: `${R.hud}:`, x: say, y: 3, textSlot: 2 },
    ...pack.corner.rival.map((label, n) => ({ label, x: say, y: 4 + n, textSlot: 0 })),
    { label: 'COACH:', x: 1, y: 10, textSlot: 2 },
    ...pack.corner.coach.map((label, n) => ({ label, x: 0, y: 11 + n, textSlot: 0 })),
    { label: 'SELECT: CATCH BREATH', x: 0, y: 15, textSlot: 1 },
  ];
  S[6].pressStart = { target: 2, flashes: 1, area: null, prompt: { label: 'START: FIGHT', x: 4, y: 17, textSlot: 1, blink: true } };
  return p;
}
