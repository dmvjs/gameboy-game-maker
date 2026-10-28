// Joe vs Mac: a fighter pack for the boxing template (boxing.js, which describes a pack's shape) with
// Little Mac and his opponents from Punch-Out!! (NES): the art and the game's own code in art/mac-vs-joe.js, which
// tools/punchout_art/build.py writes from a copy of the game.

import { boxingGame, BOXING_VERSION } from './boxing.js';
import { JOE_PALETTES, JOE_POSES, JOE_POSES_CGB, MAC_COLORS, MAC_DOWN_COLORS, MAC_TIRED_COLORS, MAC_POSES, MAC_POSES_CGB, TEXT_PALETTE, PORTRAIT_PALETTES, PORTRAIT_GREYS, PORTRAITS, PORTRAITS_FULL, NES_GAME, JOE_NES, KAISER_PALETTES, KAISER_POSES, KAISER_POSES_CGB, KAISER_NES, HONDA_PALETTES, HONDA_POSES, HONDA_POSES_CGB, HONDA_NES, DON_PALETTES, DON_POSES, DON_POSES_CGB, DON_NES, HIPPO_PALETTES, HIPPO_POSES, HIPPO_POSES_CGB, HIPPO_NES, TIGER_PALETTES, TIGER_POSES, TIGER_POSES_CGB, TIGER_NES, BULL_PALETTES, BULL_POSES, BULL_POSES_CGB, BULL_NES, SODA_PALETTES, SODA_POSES, SODA_POSES_CGB, SODA_NES, TIGER_JEWEL, SANDMAN_PALETTES, SANDMAN_POSES, SANDMAN_POSES_CGB, SANDMAN_NES, MACHO_PALETTES, MACHO_POSES, MACHO_POSES_CGB, MACHO_NES, TYSON_PALETTES, TYSON_POSES, TYSON_POSES_CGB, TYSON_NES, TITLE_LOGO, TITLE_PUNCH, TITLE_GLOVES, SPLASH, ENDING, GAME_OVER, LOSE_GLOVE, REFEREE, CROWD_COLORS, CROWD_ART, RING_COLORS, INTERMISSION, NES_SCREENS }
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
  nes: { ...NES_GAME, ...JOE_NES },   // his NES game logic, run as the original
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
  nes: { ...NES_GAME, ...KAISER_NES },  // (Mac and the sound engine are the game's, the same in every fight)
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
  nes: { ...NES_GAME, ...HONDA_NES, cueFrames: { CE: '0A' } },   // (his fists' roll: frame $CE is $0A in his cue's red)
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
  nes: { ...NES_GAME, ...DON_NES },
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
  nes: { ...NES_GAME, ...HIPPO_NES },
  talk: [[['HIS', 'DEFENSE IS', 'TOO TOUGH,', 'DOC!'], ["DON'T GIVE", 'UP, MAC!', 'HE HAS A', 'WEAKNESS..', '......'],   // Mac,
          ['WEAKNESS?', 'COME ON', 'DOC!', 'TEACH ME', 'MORE...']],                                                     // Doc, Mac
         [['HIS', 'DEFENSE IS', 'TOO TOUGH,', 'DOC!'], ["DON'T GIVE", 'UP, MAC!', 'MAKE HIM', 'CLOSE HIS', 'BIG MOUTH'],
          ['BIG MOUTH?', 'COME ON', 'DOC!', 'TEACH ME', 'MORE...']]],
  quotes: [['HA,HA,HA!', '', 'I AM THE', 'KING!', '', 'HA,HA,HA!'],
           ['I HAVE MY', 'WEAKNESS.', '', 'BUT I', "WON'T TELL", 'YOU!', '', 'HA,HA,HA!']],
};

const TIGER = {
  short: 'Tiger', hud: 'TIGER', name: 'GREAT TIGER', rank: 'RANKED NO.1',
  circuit: 'MAJOR CIRCUIT', ring: RING_COLORS.major,
  lines: ['24-5 3KO', 'FROM BOMBAY,', 'INDIA', 'AGE: 29', 'WEIGHT:132'],
  playerRank: 'RANKED NO.2',            // Mac, once Hippo's beaten
  playerLines: ['"MINOR"', 'TITLE-', 'HOLDER', '', '5-0 5KO'],
  palettes: TIGER_PALETTES,
  poses: TIGER_POSES,
  cgbPoses: TIGER_POSES_CGB,
  crowdColor: CROWD_COLORS.tiger,
  portrait: PORTRAITS.tiger,
  nes: { ...NES_GAME, ...TIGER_NES, jewel: TIGER_JEWEL },   // (his jewel's tell:
                                                                                                      // his black goes gray)
  talk: [[['HIS FATHER', 'WAS A', 'GREAT', 'MAGICIAN', 'IN INDIA.'], ["DON'T BE", 'CHARMED BY', 'HIS MAGIC', 'PUNCHES.']]],
  quotes: [['SO A', 'PUSSYCAT', 'WANTS TO', 'FIGHT A', 'TIGER!'], ['BEWARE', 'MY TIGER', 'PUNCH!'],
           ['A KITTEN', 'IS NO', 'MATCH FOR', 'A TIGER!'], ['I HAVE', 'PURRED', 'LONG', 'ENOUGH.', '', 'NOW HEAR', 'ME ROAR!']],
};

const BULL = {
  short: 'Bull', hud: 'BULL', name: 'BALD BULL', rank: 'CHAMPION',
  circuit: 'MAJOR CIRCUIT', ring: RING_COLORS.major, titleBout: true,
  lines: ['34-4 29KO', 'FROM', 'ISTANBUL,', 'TURKEY', 'AGE: 36', 'WEIGHT:298'],
  playerRank: 'RANKED NO.1',            // Mac, once Tiger's beaten
  playerLines: ['"MINOR"', 'TITLE-', 'HOLDER', '', '6-0 6KO'],
  winRank: 'NEW CHAMPION!',             // the Major Circuit's title fight
  training: true,                       // then the training run, the World Circuit's pass key
  trainingKey: '605 897 1454',
  palettes: BULL_PALETTES,
  poses: BULL_POSES,
  cgbPoses: BULL_POSES_CGB,
  crowdColor: CROWD_COLORS.bull,
  portrait: PORTRAITS.bull,
  nes: { ...NES_GAME, ...BULL_NES },
  talk: [[['MAC! WATCH', 'HIS BULL', 'CHARGE!', 'STAND UP', 'TO HIM!']]],
  quotes: [["DOC CAN'T", 'HELP YOU', 'NOW.', '', 'WILL YOU', 'BEG ME FOR', 'HELP?'],
           ['HEY!LITTLE', 'MAC!', '', 'MAYBE DOC', 'SHOULD', 'THROW YOU', 'A TOWEL!'],
           ['MY BARBER', "DIDN'T", 'KNOW WHEN', 'TO QUIT...', '', 'DO YOU?'],
           ['ZIP YOUR', 'LIP,DOC!', '', 'LITTLE MAC', 'IS MINE', 'NOW.']],
};

const HONDA2 = {                        // the World Circuit's first: Honda again, his NES rematch (same art, bank 5 at $20)
  ...HONDA, short: 'Honda2', name: 'PISTON HONDA', rank: 'RANKED NO.5', titleBout: false, winRank: null,
  training: false, trainingKey: null, tip: null,
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world,
  lines: ['26-2 18KO', 'FROM TOKYO,', 'JAPAN', 'AGE: 28', 'WEIGHT:174'],
  playerRank: 'RANKED NO.6',
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '7-0 7KO'],
  nes: { ...NES_GAME, ...HONDA_NES, cueFrames: { CE: '0A' }, offset: 0x20 },
  quotes: [['I STILL', 'REMEMBER', 'OUR FIRST', 'FIGHT.', '', "NOW I'M", 'GONNA PAY', 'YOU BACK.', 'BANZAI!!'],
           ['YOU SHOULD', 'WEAR A', 'HELMET', 'WHEN YOU', 'FIGHT ME!'],
           ["I'LL GIVE", 'YOU A TKO', 'FROM', 'TOKYO!']],
};

const SODA = {
  short: 'Soda', hud: 'SODA', name: 'SODA POPINSKI', rank: 'RANKED NO.4',
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world,
  lines: ['33-2 24KO', 'FROM MOSCOW,', 'U.S.S.R.', 'AGE: 35', 'WEIGHT:237'],
  playerRank: 'RANKED NO.5',            // Mac, once Honda's beaten again
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '8-0 8KO'],
  palettes: SODA_PALETTES,
  poses: SODA_POSES,
  cgbPoses: SODA_POSES_CGB,
  crowdColor: CROWD_COLORS.soda,
  portrait: PORTRAITS.soda,
  nes: { ...NES_GAME, ...SODA_NES },
  quotes: [['WOULD YOU', 'LIKE SOME', 'PUNCH TO', 'DRINK?', 'HA,HA,HA!'], ["I'M GONNA", 'MAKE YOU', 'FEEL', 'PUNCH', 'DRUNK!'],
           ['AFTER YOU', "LOSE,WE'LL", 'DRINK TO', 'YOUR', 'HEALTH!', '', 'HA,HA,HA!'],
           ['I DRINK TO', 'PREPARE', 'FOR A', 'FIGHT.', '', 'TONIGHT I', 'AM VERY', 'PREPARED!']],
};

const BULL2 = {                         // the World Circuit's third: Bald Bull again, his NES rematch (same art, bank 3 at $20)
  ...BULL, short: 'Bull2', rank: 'RANKED NO.3', titleBout: false, winRank: null,
  training: false, trainingKey: null,
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world,
  lines: ['34-5 29KO', 'FROM', 'ISTANBUL,', 'TURKEY', 'AGE: 36', 'WEIGHT:298'],
  playerRank: 'RANKED NO.4',            // Mac, once Soda's beaten
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '9-0 9KO'],
  nes: { ...NES_GAME, ...BULL_NES, offset: 0x20 },
  quotes: [['THIS TIME', "I'M GONNA", 'CHARGE', 'RIGHT OVER', 'YOU!'],     // (his own, half the time in the game's)
           ['THIS TIME', "I'M GONNA", 'CHARGE', 'RIGHT OVER', 'YOU!'],
           BULL.quotes[0], BULL.quotes[2], BULL.quotes[3]],
};

const DON2 = {                          // the World Circuit's fourth: Don again, his NES rematch (same art, bank 0 at $20)
  ...DON, short: 'Don2', rank: 'RANKED NO.2',
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world,
  lines: ['22-4 9KO', 'FROM MADRID,', 'SPAIN', 'AGE: 23', 'WEIGHT:152'],
  playerRank: 'RANKED NO.3',            // Mac, once Bull's beaten again
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '10-0 10KO'],
  nes: { ...NES_GAME, ...DON_NES, offset: 0x20 },
  quotes: [...Array(3)].map(() => ['FLAMENCO', 'STRIKES', 'BACK!!', '', 'RETURN OF', 'DON!!']).concat(   // (his own, most of
           [DON.quotes[0], DON.quotes[1], DON.quotes[3]]),                                             // the time in the game's)
};

const SANDMAN = {
  short: 'Sandman', hud: 'SANDMAN', name: 'MR.SANDMAN', rank: 'RANKED NO.1',
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world,
  lines: ['27-2 21KO', 'FROM', 'PHILADEL-', 'PHIA,PA.', 'AGE: 31', 'WEIGHT:284'],
  playerRank: 'RANKED NO.2',            // Mac, once Don's beaten again
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '11-0 11KO'],
  palettes: SANDMAN_PALETTES,
  poses: SANDMAN_POSES,
  cgbPoses: SANDMAN_POSES_CGB,
  crowdColor: CROWD_COLORS.sandman,
  portrait: PORTRAITS.sandman,
  nes: { ...NES_GAME, ...SANDMAN_NES },
  talk: [[['JOIN THE', 'NINTENDO', 'FUN CLUB', 'TODAY!', 'MAC.']]],   // (Doc, in his corner)
  quotes: [['HEY!', 'MAC BABY...', '', 'SAY', 'GOODNIGHT!'], ['WELCOME', 'TO', 'DREAMLAND,', 'BABY!'],
           ['I THINK', "YOU'RE", 'GONNA', 'HAVE A', 'NIGHTMARE', 'TONIGHT!'], ['BEDTIME', 'FOR LITTLE', 'MAC!']],
};

const MACHO = {
  short: 'Macho', hud: 'MACHO', name: 'SUPER MACHO MAN', rank: 'CHAMPION',
  circuit: 'WORLD CIRCUIT', ring: RING_COLORS.world, titleBout: true,
  lines: ['35-0 29KO', 'FROM', 'HOLLYWOOD,', 'CA.', 'AGE: 27', 'WEIGHT:242'],
  playerRank: 'RANKED NO.1',            // Mac, once Sandman's beaten
  playerLines: ['"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '12-0 12KO'],
  winRank: 'NEW CHAMPION!',             // the World Circuit's title fight
  training: false, trainingKey: null,
  news: true,                           // then the KO News page (his pass key in it), THE DREAM FIGHT!!, Mike Tyson
  palettes: MACHO_PALETTES,
  poses: MACHO_POSES,
  cgbPoses: MACHO_POSES_CGB,
  crowdColor: CROWD_COLORS.macho,
  portrait: PORTRAITS.macho,
  nes: { ...NES_GAME, ...MACHO_NES },
  talk: [[['LOOK FOR', 'TWO TYPES', 'OF SPIN', 'PUNCH!', 'WATCH HIM']]],   // (Doc, in his corner)
  quotes: [['MY SUPER', 'SPIN PUNCH', 'IS TOTALLY', 'TOUGH!'], ['MY SUPER', 'SPIN PUNCH', 'IS TOTALLY', 'TOUGH!'],   // (his
           ['MY BODY', 'IS JUST', 'SO TOTALLY', 'COOL!'],                                                          // most often)
           ['I WORK ON', 'MY TAN', 'HARDER', "THAN I'LL", 'HAVE TO', 'WORK ON', 'YOU!'],
           ["I DON'T", 'SMOKE...', '', 'BUT', 'TONIGHT', "I'M GONNA", 'SMOKE YOU!']],
};

const TYSON = {
  short: 'Tyson', hud: 'TYSON', name: 'MIKE TYSON', rank: 'KID DYNAMITE',
  circuit: 'THE DREAM FIGHT', ring: RING_COLORS.dream,   // (his own ring: the game's last)
  lines: ['31-0 27KO', 'FROM', 'CATSKILL,', 'N.Y.', 'AGE: 21', 'WEIGHT:220'],
  playerRank: 'CHAMPION',               // Mac, the World Circuit's champion
  playerLines: ['"WORLD"', '"MAJOR"', '"MINOR"', 'TITLE-', 'HOLDER', '13-0 13KO'],
  winRank: 'THE CHAMPION!',
  palettes: TYSON_PALETTES,
  poses: TYSON_POSES,
  cgbPoses: TYSON_POSES_CGB,
  crowdColor: CROWD_COLORS.tyson,
  portrait: PORTRAITS.tyson,
  nes: { ...NES_GAME, ...TYSON_NES },
  quotes: [['YOU THINK', 'THE SPEED', 'OF YOUR', 'FINGERS', 'CAN MATCH', 'THE', 'STRENGTH', 'OF MY', 'FISTS?'],
           ['IF I KNOCK', 'YOU DOWN,', "DON'T", 'GET UP!'],
           ['THEY SAY', "I CAN'T", 'LOSE.', '', 'I SAY YOU', "CAN'T WIN!"],
           ['HEY!', '', 'IS THIS', 'KID A', 'JOKE?', '', "WHERE'S", 'THE REAL', 'CHALLENGER'],
           ['YOUR', 'EXPERIENCE', "DOESN'T", 'MATCH MINE.', '', 'GO HOME', 'AND', 'PRACTICE!']],
};

export const JOE_VS_MAC = {
  id: 'mac-vs-joe',
  name: "Mike Tyson's Punch-Out!! rev 0.4",
  credit: '(C)2026 DMVJS',
  roundCard: true,                      // Punch-Out!!'s ROUND card before each round
  docLines: [['KEEP YOUR', 'GUARD UP!'], ['PUT HIM', 'AWAY!!'], ['STICK AND', 'MOVE,', 'STICK AND', 'MOVE!'],   // Doc
             ['WATCH', 'HIS LEFT!'], ['ONE TWO,', 'ONE TWO', 'PUNCH', 'MAC!'],                              // after
             ["DANCIN'", 'LIKE A FLY,', 'BITE', 'LIKE A', 'MOSQUITO!']],                                     // round 2
  title: [{ text: 'MIKE TYSON\'S', x: 32, y: 8, scale: 1, slot: 1 }],    // over the logo, as Punch-Out!!'s
  titleLogo: { ...TITLE_LOGO, y: 24 },
  titlePunch: TITLE_PUNCH,
  splash: SPLASH,
  titleGloves: TITLE_GLOVES,
  ending: ENDING,
  gameOver: GAME_OVER,
  anotherWorld: ['Hippo', 'Tiger', 'Honda2', 'Soda', 'Bull2', 'Don2', 'Sandman', 'Macho', 'Tyson'],   // (its pass key's)
  crowdArt: CROWD_ART,
  circuit: 'MINOR CIRCUIT',
  intermission: INTERMISSION,           // the training run between circuits
  screens: NES_SCREENS,                 // TITLE BOUT!!, the KO News page, THE DREAM FIGHT!! (the game's)
  credits: [['PRODUCER', 'M. ARAKAWA'], ['SUPERVISOR', 'NOA'], ['DIRECTOR', 'G. TAKEDA'],   // its staff, as its key shows
            ['GAME DESIGNER', 'K. YONEYAMA', 'M. HIROTA'], ['CHARACTER DESIGNER', 'M. WADA'],   // them (106 113 0120)
            ['MUSIC COMPOSER', 'Y. KANEOKA', 'A. NAKATUKA', 'K. YAMAMOTO'],
            ['ELECTRICAL ENGINEER', 'S. FUNAKOSHI', 'M. TAYA'], ['PROGRAMMER', 'M. HATAKEYAMA'], ['SECRETARY', 'Y. KURIYAMA']],
  ring: RING_COLORS.minor,              // the Minor Circuit's ring, as the NES colors it
  textPalette: TEXT_PALETTE,
  portraitPalettes: PORTRAIT_PALETTES,
  portraitGreys: PORTRAIT_GREYS,         // (the original's greys for the full-size close-ups)
  rival: JOE,
  rivals: [JOE, KAISER, HONDA, DON, HIPPO, TIGER, BULL, HONDA2, SODA, BULL2, DON2, SANDMAN, MACHO, TYSON],            // fought in turn: each win on to the next
  player: {
    name: 'LITTLE MAC', hud: 'MAC', rank: 'RANKED NO.3',
    lines: ['FROM BRONX', 'N.Y.', 'AGE: 17', 'WEIGHT:107', '0-0 0KO'],
    colors: MAC_COLORS,
    downColors: MAC_DOWN_COLORS,        // knocked down, as the NES shows him
    tiredColors: MAC_TIRED_COLORS,      // worn out, as the NES shows him (purple)
    poses: MAC_POSES,
    cgbPoses: MAC_POSES_CGB,            // unshared, in Game Boy Color's second bank
    portrait: PORTRAITS.mac,
    portraitFull: PORTRAITS_FULL?.docmac,   // Doc and Mac as the NES shows them (the corner's four states)
  },
  referee: REFEREE,                     // Mario, as the NES game draws him
  effects: { stars: false, sweat: false, spark: false },   // the NES poses draw their own spit and impacts
  win: ['JOE IS DOWN', 'FOR GOOD!'],
  lose: ['HE CAN\'T BELIEVE IT', 'EITHER.'],
  loseGlove: LOSE_GLOVE,                // the NES's "YOU LOST!" screen, its glove over LET'S REMATCH!
  corner: { rival: ['MY CHIN!', 'NOT AGAIN!'],
            coach: ['HE DOES NOTHING TILL', 'THEN HE BACKS OFF.', 'HIT HIM COMING IN!'] },
};

for (const r of JOE_VS_MAC.rivals) {     // each rival's close-up at the NES's own size too
  const name = Object.keys(PORTRAITS).find(k => PORTRAITS[k] === r.portrait);
  if (PORTRAITS_FULL?.[name]) r.portraitFull = PORTRAITS_FULL[name];
}

export const macVsJoe = () => boxingGame(JOE_VS_MAC);
