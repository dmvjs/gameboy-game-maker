// Joe vs Mac: a fighter pack for the boxing template (boxing.js, which describes a pack's shape) with
// Little Mac and Glass Joe from Punch-Out!! (NES). For local testing only: the art is Nintendo's, so this file
// and art/mac-vs-joe.js (written by tools/punchout_art/build.py) stay out of git.

import { boxingGame, BOXING_VERSION } from './boxing.js';
import { JOE_PALETTES, JOE_POSES, MAC_COLORS, MAC_POSES, TEXT_PALETTE, PORTRAIT_PALETTES, PORTRAITS, JOE_NES, TITLE_LOGO, TITLE_PUNCH }
  from './art/mac-vs-joe.js';

export const MAC_VS_JOE_VERSION = BOXING_VERSION;

export const JOE_VS_MAC = {
  id: 'mac-vs-joe',
  name: 'Joe vs Mac',
  credit: '(C) 2026 YOU',
  title: [{ text: 'GLASS JOE\'S', x: 36, y: 8, scale: 1, slot: 1 }],     // over the logo, as "MIKE TYSON'S" is
  titleLogo: { ...TITLE_LOGO, y: 24 },
  titlePunch: TITLE_PUNCH,
  circuit: 'MINOR CIRCUIT',
  textPalette: TEXT_PALETTE,
  portraitPalettes: PORTRAIT_PALETTES,
  rival: {
    short: 'Joe', hud: 'JOE', name: 'GLASS JOE', rank: 'RANKED NO.2',
    lines: ['1-99 1KO', 'FROM PARIS,', 'FRANCE', 'AGE: 38', 'WEIGHT:110'],
    palettes: JOE_PALETTES,
    poses: JOE_POSES,
    portrait: PORTRAITS.joe,
    hurtPortrait: PORTRAITS.joe_hurt,
    nes: JOE_NES,                       // his NES game logic, run as the original
  },
  player: {
    name: 'LITTLE MAC', hud: 'MAC', rank: 'RANKED NO.3',
    lines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '0-0 0KO'],
    colors: MAC_COLORS,
    tiredColors: MAC_COLORS.map(([r, g, b]) => [Math.min(31, r + 3), Math.round(g * 0.7), Math.round(b * 0.85)]),
    poses: MAC_POSES,
    portrait: PORTRAITS.mac,
  },
  effects: { stars: false, sweat: false, spark: false },   // the NES poses draw their own spit and impacts
  win: ['JOE IS DOWN', 'FOR GOOD!'],
  lose: ['HE CAN\'T BELIEVE IT', 'EITHER.'],
  corner: { rival: ['MY CHIN!', 'NOT AGAIN!'],
            coach: ['HE DOES NOTHING TILL', 'THEN HE BACKS OFF.', 'HIT HIM COMING IN!'] },
};

export const macVsJoe = () => boxingGame(JOE_VS_MAC);
