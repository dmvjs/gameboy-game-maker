"""Fight kit: a boxing match against one rival, seen from behind the player.

The rival is drawn with background tiles: every pose is a full 8x10-tile picture, all poses' tiles
stay in video memory, and changing pose rewrites that part of the map during VBlank. The player is
sprites. The numbers here are shared by the project checks, the code generator and the tests.
"""

REGION_W, REGION_H = 8, 10                      # rival area, in tiles
PIC_H = 12                                      # an NES fighter's picture, in rows: his area's, and two below it (the
                                                #  NES's tallest frames' feet: none cut off)
# With a rope row (Punch-Out!!'s ring: the fighters stand in front of the ropes and crowd), his rows above his
# band's top are sprites over them: his top HEAD_ROWS of tiles (HEAD_ROWS_TALL for the poses the NES walks him
# in and steps him back with: up over the crowd), kept in tiles sprites can reach.
HEAD_ROWS, HEAD_ROWS_TALL = 4, 7
HEAD_TALL = {"idle", "idle2", "idle3", "taunt", "tell1", "tell2", "tell3", "tell4", "tell5",   # (and knocked down:
             "kd_stagger", "kd_fall", "kd_down", "kd_kneel", "kd_rise", "kd2_stagger", "kd2_fall", "kd2_down", "kd2_kneel",
             "kd2_rise"}   # back up into the crowd)


def head_rows(pose):
    return HEAD_ROWS_TALL if pose in HEAD_TALL else HEAD_ROWS
RIVAL_POSES = ["idle", "idle2", "guard", "hit_l", "hit_r", "hit_body", "dazed",
               "jab_tell", "jab_mid", "jab", "hook_tell", "hook_mid", "hook", "slip", "idle3", "hit_back",
               "kd_stagger", "kd_fall", "kd_down", "kd_kneel", "kd_rise",   # (rise: up off the knee)
               "taunt", "arm_pop", "guard_low",
               "tell1", "tell2", "tell3", "tell4", "tell5",  # a fighter's own wind-up frames (Honda's gloves rolling)
               "extra1", "extra2", "extra3", "extra4",       # more of his own (a big fighter's spin punches)
               "kd2_stagger", "kd2_fall", "kd2_down", "kd2_kneel", "kd2_rise"]  # his other way down (the NES drops him
                                                                                # either way)
# Pose sets share one area of video memory: the attack set is there normally; the knockdown set replaces it
# while he's down, the special set while he taunts or pops an arm. Poses in no set are always there.
POSE_SETS = {"attack": ["jab_tell", "hook_tell", "tell1", "tell2", "tell3", "tell4", "tell5",   # (tells first: shared
                                                                                              # tiles keep theirs)
                        "idle2", "idle3", "guard", "guard_low", "hit_back", "jab_mid", "jab", "hook_mid", "hook", "slip",
                        "extra1", "extra2", "extra3", "extra4"],
             "knockdown": ["kd_stagger", "kd_fall", "kd_down", "kd_kneel", "kd_rise", "kd2_stagger", "kd2_fall", "kd2_down",
                           "kd2_kneel", "kd2_rise"],
             "special": ["taunt", "arm_pop"]}
KD_POSES = POSE_SETS["knockdown"]
# Older projects: newer poses borrow one they already have.
POSE_FALLBACK = {"idle2": "idle", "idle3": "idle", "hit_back": "hit_l", "slip": "idle", "jab_mid": "jab_tell", "hook_mid": "hook_tell", "kd_stagger": "hit_body", "kd_fall": "fall",
                 "kd_down": "down", "kd_kneel": "fall", "arm_pop": "hit_body", "guard_low": "guard",
                 "tell1": "jab_tell", "tell2": "jab_tell", "tell3": "jab_tell", "tell4": "jab_tell", "tell5": "jab_tell",
                 "kd2_stagger": "kd_stagger", "kd2_fall": "kd_fall", "kd2_down": "kd_down", "kd2_kneel": "kd_kneel",
                 "extra1": "jab", "extra2": "jab", "extra3": "jab", "extra4": "jab",
                 "kd_rise": "kd_kneel", "kd2_rise": "kd2_kneel"}
JEWEL_TILE = ["........", "........", "...33...", "..3113..", "..3113..", "...33...", "........", "........"]
JEWEL_MID = 4                                   # (its middle in the tile)
PLAYER_POSES = ["idle", "jab", "jab_high", "dodge", "block", "hit", "star", "down", "win",
                "star2", "star3", "star4",           # (the star punch as the NES's: wound up, rising, the uppercut, after)
                "jab_tell", "high_tell", "knocked", "duck"]   # (and the rest of his frames: wind-ups, knocked back,
                                                              # ducking)
PLAYER_FALLBACK = {"star2": "star", "star3": "star", "star4": "star", "jab_tell": "jab", "high_tell": "jab_high",
                   "knocked": "hit", "duck": "block"}   # (older projects: the nearest they have)
PLAYER_CGB_SHARED = ["star", "star2", "star3", "star4", "jab_tell", "high_tell", "knocked", "duck"]
                                                          # Color draws these from the original's tiles, loaded as needed
                                                          # (its own bank's 128 hold the rest)
PLAYER_HOLD = {"star": 1, "star2": 1, "star3": 1, "star4": 1, "knocked": 2, "down": 2}
                                                          # a sequence's frame held while its next loads
PLAYER_W, PLAYER_H = 24, 48                     # player pose size in pixels (3x6 sprites, empty ones skipped)
PLAYER_X = 80 - PLAYER_W // 2 - 8               # a little left of center, so the rival shows past him
CELL_KINDS = {"s": "skin", "g": "gloves", "h": "hair"}
OBJ_FIRST_TILE = 2                              # sprite tiles 0 and 1 belong to the menu cursor and slider marker
OBJ_TILE_LIMIT = 128                            # sprite tiles at $8000-$87FF
COUNT_GLYPHS = "0123456789KO!FIGHT"
GETUP_GLYPHS = "GETUP!"                 # (Punch-Out!!'s, when Mac's down: after the count's, in each fight)
# Sprite effects drawn over the art; a game whose poses already draw them (spit in the hit frames) turns them off.
EFFECTS = {"stars": "stars circling his head while he's dazed", "sweat": "sweat flying off a clean hit to the face",
           "spark": "a burst where a punch lands"}
BUBBLE_ENDS = [["..222222", ".2222222", "22222222", "22222222", "22222222", "22222222", ".3222222", "..333333"],
               ["222222..", "2222222.", "22222222", "22222233", "22222223", "22222222", "2222223.", "333333.."]]
SPARK_TILE = ["3.......", ".3...3..", "..3.32..", "...322..", "..3222..", ".32222..", "...22222", "....2222"]
DROP_TILE = ["...3....", "..323...", ".32223..", ".32223..", "..333...", "........", "........", "........"]
NES_ANCHOR = (35, 77)       # where the NES's place ($B0, $B1: its home) sits in a pose's 64x80 frame (the art's)
TWINKLE_TILE = ["...2....", "...2....", ".2.2.2..", "..232...", "2223222.", "..232...", ".2.2.2..", "...2...."]   # a star just earned (by the HUD's)
STAR_TILE = ["...1....", "...1....", ".11311..", "1133311.", ".11311..", "...1....", "...1....", "........"]             # sprite text: the referee's count, "KO!", "FIGHT!"
REF_POSES = ["stand", "count", "wave"]
REF_W, REF_H = 24, 32
PLAYER_RARE = ["star", "down", "win", "star2", "star3", "star4", "jab_tell", "high_tell", "knocked", "duck"]           # the player's poses loaded as they're needed (one at a time)
REF_Y = 84                                      # the referee's top, in screen pixels: his feet below the rival's (in front)

# HUD items: (key, cells, what)
HUD_DIGITS = [("stars", 1, "stars"), ("hearts", 2, "hearts"), ("points", 6, "points"), ("clock", 3, "clock"),
              ("round", 1, "round")]
BAR_CELLS = 6                                   # health bars are 6 tiles (48 pixels) wide
HEALTH = 96                                     # full health; the bar shows a pixel per 2 points

# Script for the rival: (op, argument), frames are 1/60 s. The opening plays once, then the loop repeats.
# idle: stand guarding (gloves low cover the body, high cover the face); guard: switch guard, then stand;
# jab / hook: wind up, then swing; taunt: back off and taunt for the argument's frames, then shuffle in and hook.
OPS = {"idle": 0, "guard": 1, "jab": 2, "hook": 3, "taunt": 4}
DEFAULT_OPENING = [("idle", 250), ("idle", 250), ("idle", 250), ("idle", 250)]   # does nothing for the first 40 seconds
DEFAULT_LOOP = [("idle", 90), ("jab", 0), ("idle", 60), ("guard", 90), ("jab", 0), ("idle", 40), ("hook", 0),
                  ("idle", 70), ("taunt", 80), ("guard", 60), ("jab", 0), ("idle", 30), ("jab", 0), ("idle", 50),
                  ("hook", 0)]

# Timing and damage (frames / health points). The ROM's numbers come from here.
TUNING = {
    "JAB_TELL": 34, "HOOK_TELL": 46, "STRIKE": 14, "OPEN": 50, "RIVAL_HIT": 14,
    "CHARGE": 16, "RECOVER": 20, "HITSTOP": 5, "POP": 56, "SLIP": 12, "COUNTER_TELL": 22, "CHARGE_TELL": 18, "PUNCHES_PER_STAR": 20, "FALL": 30, "COUNT": 40, "GETUP": 40,
    "PUNCH": 14, "PUNCH_ACTIVE": 10, "DODGE": 26, "EVADE_FROM": 24, "EVADE_TO": 6, "PLAYER_HIT": 28,
    "STAR": 32, "STAR_ACTIVE": 18, "TIRED": 120, "BREAK": 120, "INTRO": 80, "ASIDE": 22, "END": 150,
    "DMG_BODY": 4, "DMG_HEAD": 4, "DMG_STAR": 18, "DMG_STAR_HOOK": 17, "DMG_STAR_JAB": 15, "DMG_STAR_STUNNED": 23,
    "DMG_JAB": 11, "DMG_HOOK": 11, "DMG_HOOK_BLOCKED": 3,
    "HEARTS": 20, "HEARTS_R3": 15, "HEARTS_HIT": 3, "HEARTS_RESTED": 15, "HEARTS_RESTED_HIT": 9, "HEARTS_R3_LESS": 5,
    "MASH_BASE": 8, "MASH_STEP": 6, "YAP": 22, "CHARGE_KO": 4,
    "OPEN_AFTER_HOOK": 6, "OPEN_AFTER_JAB": 4, "OPEN_AFTER_BLOCK": 4, "FIRST_STAR": 20, "NEXT_STAR": 8, "STAR_DODGE": 8,
    "DECISION_POINTS_BCD": 0x50,
    "FRAMES_PER_SECOND": 20, "ROUND_MINUTES": 3, "ROUNDS": 3, "DODGE_X": 14,
}
# Moves at set times on the clock: (round, "M:SS", op, argument). They wait until he's idle or guarding.
DEFAULT_TIMED = [(1, "0:40", "taunt", 0), (2, "0:30", "taunt", 0), (3, "0:30", "taunt", 0)]
# Getting up after knockdown n (1-5): (count, health) normally, or (1, 96) when the condition holds; 0 = stays down.
# Conditions: 1 = the player at full health and under a minute gone; 2 = the player at full health; 3+ = a star punch did it.
GETUP_PLAN = [(3, 80), (4, 48), (5, 40), (6, 8), (7, 8)]
PLAYER_GETUP_HEALTH = [72, 48]
