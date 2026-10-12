// Joe vs Mac: a fighter pack for the boxing template (boxing.js, which describes a pack's shape) with
// Little Mac and Glass Joe from Punch-Out!! (NES). For local testing only: the art is Nintendo's, so this file
// and art/mac-vs-joe.js (written by tools/punchout_art/build.py) stay out of git.

import { boxingGame, BOXING_VERSION } from './boxing.js';
import { JOE_PALETTES, JOE_POSES, JOE_POSES_CGB, MAC_COLORS, MAC_DOWN_COLORS, MAC_TIRED_COLORS, MAC_POSES, TEXT_PALETTE, PORTRAIT_PALETTES, PORTRAITS, JOE_NES, KAISER_PALETTES, KAISER_POSES, KAISER_POSES_CGB, KAISER_NES, HONDA_PALETTES, HONDA_POSES, HONDA_POSES_CGB, HONDA_NES, TITLE_LOGO, TITLE_PUNCH, LOSE_GLOVE, REFEREE, CROWD_COLORS, RING_COLORS }
  from './art/mac-vs-joe.js';

export const MAC_VS_JOE_VERSION = BOXING_VERSION;

const JOE = {
  short: 'Joe', hud: 'JOE', name: 'GLASS JOE', rank: 'RANKED NO.2',
  lines: ['1-99 1KO', 'FROM PARIS,', 'FRANCE', 'AGE: 38', 'WEIGHT:110'],
  palettes: JOE_PALETTES,
  poses: JOE_POSES,
  cgbPoses: JOE_POSES_CGB,             // finer, in Game Boy Color's second tile bank
  crowdColor: CROWD_COLORS.joe,        // his fight's crowd, as the NES colors it
  portrait: PORTRAITS.joe,
  hurtPortrait: PORTRAITS.joe_hurt,
  nes: JOE_NES,                       // his NES game logic, run as the original
};

const KAISER = {
  short: 'Kaiser', hud: 'KAISER', name: 'VON KAISER', rank: 'RANKED NO.1',
  lines: ['23-13 10KO', 'FROM BERLIN,', 'GERMANY', 'AGE: 42', 'WEIGHT:144'],
  playerRank: 'RANKED NO.2',            // Mac, once Joe's beaten
  playerLines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '1-0 1KO'],
  palettes: KAISER_PALETTES,
  poses: KAISER_POSES,
  cgbPoses: KAISER_POSES_CGB,
  crowdColor: CROWD_COLORS.kaiser,
  portrait: PORTRAITS.kaiser,
  nes: { ...JOE_NES, ...KAISER_NES },  // (Mac and the sound engine are the game's, the same in every fight)
  corner: { rival: ['DISCIPLINE!', 'I WILL', 'TEACH YOU!'],
            coach: ['WATCH HIS JAB', 'AND HIS UPPERCUT.', 'DODGE, THEN HIT!'] },
};

const HONDA = {
  short: 'Honda', hud: 'HONDA', name: 'PISTON HONDA', rank: 'CHAMPION',
  lines: ['26-1 18KO', 'FROM TOKYO,', 'JAPAN', 'AGE: 32', 'WEIGHT:174'],
  playerRank: 'RANKED NO.1',            // Mac, once Von Kaiser's beaten
  playerLines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '2-0 2KO'],
  winRank: 'NEW CHAMPION!',             // the Minor Circuit's title fight
  palettes: HONDA_PALETTES,
  poses: HONDA_POSES,
  cgbPoses: HONDA_POSES_CGB,
  crowdColor: CROWD_COLORS.honda,
  portrait: PORTRAITS.honda,
  nes: { ...JOE_NES, ...HONDA_NES },
  corner: { rival: ['MY TITLE', 'STAYS IN', 'TOKYO!'],
            coach: ['WHEN HIS EYEBROWS', 'GO UP, GET READY:', 'DODGE THE RUSH!'] },
};

export const JOE_VS_MAC = {
  id: 'mac-vs-joe',
  name: 'Joe vs Mac',
  credit: '(C)2026 ELEVENDO',
  title: [{ text: 'MIKE TYSON\'S', x: 32, y: 8, scale: 1, slot: 1 }],    // over the logo, as Punch-Out!!'s
  titleLogo: { ...TITLE_LOGO, y: 24 },
  titlePunch: TITLE_PUNCH,
  circuit: 'MINOR CIRCUIT',
  ring: RING_COLORS.minor,              // the Minor Circuit's ring, as the NES colors it
  textPalette: TEXT_PALETTE,
  portraitPalettes: PORTRAIT_PALETTES,
  rival: JOE,
  rivals: [JOE, KAISER, HONDA],            // fought in turn: each win on to the next
  player: {
    name: 'LITTLE MAC', hud: 'MAC', rank: 'RANKED NO.3',
    lines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '0-0 0KO'],
    colors: MAC_COLORS,
    downColors: MAC_DOWN_COLORS,        // knocked down, as the NES shows him
    tiredColors: MAC_TIRED_COLORS,      // worn out, as the NES shows him (purple)
    poses: MAC_POSES,
    portrait: PORTRAITS.mac,
  },
  referee: REFEREE,                     // Mario, as the NES game draws him
  effects: { stars: false, sweat: false, spark: false },   // the NES poses draw their own spit and impacts
  win: ['JOE IS DOWN', 'FOR GOOD!'],
  lose: ['HE CAN\'T BELIEVE IT', 'EITHER.'],
  loseGlove: LOSE_GLOVE,                // the NES's "YOU LOST!" screen, its glove over LET'S REMATCH!
  corner: { rival: ['MY CHIN!', 'NOT AGAIN!'],
            coach: ['HE DOES NOTHING TILL', 'THEN HE BACKS OFF.', 'HIT HIM COMING IN!'] },
};

export const macVsJoe = () => boxingGame(JOE_VS_MAC);
