// Joe vs Mac: a fighter pack for the boxing template (boxing.js, which describes a pack's shape) with
// Little Mac and Glass Joe from Punch-Out!! (NES). For local testing only: the art is Nintendo's, so this file
// and art/mac-vs-joe.js (written by tools/punchout_art/build.py) stay out of git.

import { boxingGame, BOXING_VERSION } from './boxing.js';
import { JOE_PALETTES, JOE_POSES, JOE_POSES_CGB, MAC_COLORS, MAC_DOWN_COLORS, MAC_TIRED_COLORS, MAC_POSES, MAC_POSES_CGB, TEXT_PALETTE, PORTRAIT_PALETTES, PORTRAITS, JOE_NES, KAISER_PALETTES, KAISER_POSES, KAISER_POSES_CGB, KAISER_NES, HONDA_PALETTES, HONDA_POSES, HONDA_POSES_CGB, HONDA_NES, DON_PALETTES, DON_POSES, DON_POSES_CGB, DON_NES, HIPPO_PALETTES, HIPPO_POSES, HIPPO_POSES_CGB, HIPPO_NES, TITLE_LOGO, TITLE_PUNCH, LOSE_GLOVE, REFEREE, CROWD_COLORS, RING_COLORS, INTERMISSION }
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
  // Between rounds, as Punch-Out!!'s (its words): Doc's tip after round 1, then one of the rival's lines
  tip: [['DODGE', 'HIS PUNCH', 'THEN', 'COUNTER-', 'PUNCH!']],
  quotes: [['THIS IS', 'MY LAST', 'MATCH!', '', "I'M TOO", 'OLD FOR', 'FIGHTING!'],
           ['MAKE IT', 'QUICK...', '', 'I WANT', 'TO RETIRE!'],
           ['WATCH THE', 'JAW!!', '', "DON'T HIT", 'MY JAW!'],
           ['DO I HAVE', 'TIME TO', 'TAKE A NAP', 'BEFORE THE', 'FIGHT?']],
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
  tip: [['DODGE', 'HIS PUNCH', 'THEN', 'COUNTER-', 'PUNCH!']],
  quotes: [['I WAS A', 'BOXING', 'TEACHER...', '..AT THE', 'MILITARY', 'ACADEMY!'],
           ["I'LL TEACH", 'YOU A', 'LESSON.', '', 'YOU WILL', 'FALL DOWN!'],
           ['YOUR PUNCH', 'IS SOFT...', '', 'JUST LIKE', 'YOUR', 'HEART!'],
           ['SURRENDER!', '', 'OR I WILL', 'CONQUER', 'YOU!!']],
};

const HONDA = {
  short: 'Honda', hud: 'HONDA', name: 'PISTON HONDA', rank: 'CHAMPION',
  lines: ['26-1 18KO', 'FROM TOKYO,', 'JAPAN', 'AGE: 32', 'WEIGHT:174'],
  playerRank: 'RANKED NO.1',            // Mac, once Von Kaiser's beaten
  playerLines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '2-0 2KO'],
  winRank: 'NEW CHAMPION!',             // the Minor Circuit's title fight
  training: true,                       // then the training run, its pass key
  trainingKey: '049 713 5423',
  palettes: HONDA_PALETTES,
  poses: HONDA_POSES,
  cgbPoses: HONDA_POSES_CGB,
  crowdColor: CROWD_COLORS.honda,
  portrait: PORTRAITS.honda,
  nes: { ...JOE_NES, ...HONDA_NES },
  titleBout: true,                      // TITLE BOUT under the circuit
  tip: [['CATCH HIM', 'OFF-GUARD', 'TO STUN', 'HIM!'], ['THEN', 'UNLOAD', 'ON HIM!']],
  quotes: [['YOU SHOULD', 'WEAR A', 'HELMET', 'WHEN YOU', 'FIGHT ME!'],
           ['WHERE IS', 'THE NHK TV', 'CAMERA?', '', 'HELLO,', 'TOKYO!'],
           ["I'LL GIVE", 'YOU A TKO', 'FROM', 'TOKYO!'],
           ['SUSHI,', 'KAMIKAZE,', 'FUJIYAMA,', 'NIPPON-', 'ICHI...']],
};

const DON = {
  short: 'Don', hud: 'DON', name: 'DON FLAMENCO', rank: 'RANKED NO.3',
  circuit: 'MAJOR CIRCUIT', ring: RING_COLORS.major,   // the Major Circuit: its own ring (green)
  lines: ['22-3 9KO', 'FROM MADRID,', 'SPAIN', 'AGE: 23', 'WEIGHT:152'],
  playerRank: 'RANKED NO.4',            // Mac, the Minor Circuit's champion
  playerLines: ['"MINOR"', 'TITLE-', 'HOLDER', '', '3-0 3KO'],
  palettes: DON_PALETTES,
  poses: DON_POSES,
  cgbPoses: DON_POSES_CGB,
  crowdColor: CROWD_COLORS.don,
  portrait: PORTRAITS.don,
  nes: { ...JOE_NES, ...DON_NES },
  quotes: [["I'M A", 'BEAUTIFUL', 'FIGHTER.', '', 'I HAVE', 'SUCH A', 'STYLE!'],
           ['PEOPLE', 'LIKE MY', 'HAIR.', '', "DON'T MESS", 'MY HAIR!'],
           ['CARMEN,', 'MY LOVE...', '', 'I DANCE', 'SO SWEET', 'FOR YOU!'],
           ['HEY!MR.', 'REFEREE', 'MARIO...', '', 'I LIKE', 'YOUR HAIR!']],
};

const HIPPO = {
  short: 'Hippo', hud: 'HIPPO', name: 'KING HIPPO', rank: 'RANKED NO.2',
  circuit: 'MAJOR CIRCUIT', ring: RING_COLORS.major,
  lines: ['18-9 18KO', 'FROM HIPPO', 'ISLAND,', 'SOUTH PACIFIC', 'AGE: ??', 'WEIGHT:???'],
  playerRank: 'RANKED NO.3',            // Mac, once Don's beaten
  playerLines: ['"MINOR"', 'TITLE-', 'HOLDER', '', '4-0 4KO'],
  palettes: HIPPO_PALETTES,
  poses: HIPPO_POSES,
  cgbPoses: HIPPO_POSES_CGB,
  crowdColor: CROWD_COLORS.hippo,
  portrait: PORTRAITS.hippo,
  nes: { ...JOE_NES, ...HIPPO_NES },
  talk: [[['HIS', 'DEFENSE IS', 'TOO TOUGH,', 'DOC!'], ["DON'T GIVE", 'UP, MAC!', 'HE HAS A', 'WEAKNESS..', '......'],   // Mac,
          ['WEAKNESS?', 'COME ON', 'DOC!', 'TEACH ME', 'MORE...']],                                                     // Doc, Mac
         [['HIS', 'DEFENSE IS', 'TOO TOUGH,', 'DOC!'], ["DON'T GIVE", 'UP, MAC!', 'MAKE HIM', 'CLOSE HIS', 'BIG MOUTH'],
          ['BIG MOUTH?', 'COME ON', 'DOC!', 'TEACH ME', 'MORE...']]],
  quotes: [['HA,HA,HA!', '', 'I AM THE', 'KING!', '', 'HA,HA,HA!'],
           ['I HAVE MY', 'WEAKNESS.', '', 'BUT I', "WON'T TELL", 'YOU!', '', 'HA,HA,HA!']],
};

export const JOE_VS_MAC = {
  id: 'mac-vs-joe',
  name: 'Joe vs Mac',
  credit: '(C)2026 DMVJS',
  roundCard: true,                      // Punch-Out!!'s ROUND card before each round
  docLines: [['KEEP YOUR', 'GUARD UP!'], ['PUT HIM', 'AWAY!!'], ['STICK AND', 'MOVE,', 'STICK AND', 'MOVE!'],   // Doc
             ['WATCH', 'HIS LEFT!'], ['ONE TWO,', 'ONE TWO', 'PUNCH', 'MAC!'],                              // after
             ["DANCIN'", 'LIKE A FLY,', 'BITE', 'LIKE A', 'MOSQUITO!']],                                     // round 2
  title: [{ text: 'MIKE TYSON\'S', x: 32, y: 8, scale: 1, slot: 1 }],    // over the logo, as Punch-Out!!'s
  titleLogo: { ...TITLE_LOGO, y: 24 },
  titlePunch: TITLE_PUNCH,
  circuit: 'MINOR CIRCUIT',
  intermission: INTERMISSION,           // the training run between circuits
  ring: RING_COLORS.minor,              // the Minor Circuit's ring, as the NES colors it
  textPalette: TEXT_PALETTE,
  portraitPalettes: PORTRAIT_PALETTES,
  rival: JOE,
  rivals: [JOE, KAISER, HONDA, DON, HIPPO],            // fought in turn: each win on to the next
  player: {
    name: 'LITTLE MAC', hud: 'MAC', rank: 'RANKED NO.3',
    lines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '0-0 0KO'],
    colors: MAC_COLORS,
    downColors: MAC_DOWN_COLORS,        // knocked down, as the NES shows him
    tiredColors: MAC_TIRED_COLORS,      // worn out, as the NES shows him (purple)
    poses: MAC_POSES,
    cgbPoses: MAC_POSES_CGB,            // unshared, in Game Boy Color's second bank
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
