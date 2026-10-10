"""Built-in sound effects, played on the Game Boy's own channels.

Each effect: (voice, priority, duty, sweep, steps). Voices: "pulse1" (with sweep), "pulse2", "noise".
A step is (frames, volume, fade, note) for pulses (note like "C6", or None for a rest) or
(frames, volume, fade, noise) for noise, where noise is the NR43 value (low = deep, high = hiss).
fade is the envelope pace: 0 = hold, 1 = fast decay ... 7 = slow decay.
A higher priority effect can cut in on a voice; an equal or lower one can't interrupt it.
"""

NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
LOW_NOTE = 36          # C2: note index 1 in the ROM's table
NOTE_COUNT = 72        # C2 ... B7

SFX = {
    # menus and screens
    "menu_move":     ("pulse2", 1, 2, 0, [(2, 9, 1, "E6"), (2, 5, 1, "B5")]),
    "menu_confirm":  ("pulse1", 3, 1, 0, [(2, 12, 0, "C6"), (2, 12, 0, "E6"), (2, 12, 0, "G6"), (6, 12, 2, "C7")]),
    "menu_back":     ("pulse1", 3, 2, 0, [(2, 10, 0, "G5"), (5, 10, 2, "C5")]),
    "option_change": ("pulse2", 1, 1, 0, [(2, 9, 1, "A5"), (2, 6, 1, "E6")]),
    "press_start":   ("pulse1", 4, 2, 0, [(2, 13, 0, "C5"), (2, 13, 0, "E5"), (2, 13, 0, "G5"), (2, 13, 0, "C6"),
                                          (2, 13, 0, "E6"), (2, 13, 0, "G6"), (10, 13, 3, "C7")]),
    # the puzzle
    "move":          ("pulse2", 1, 0, 0, [(1, 6, 1, "C6"), (1, 3, 1, "C6")]),
    "move_held":     ("pulse2", 1, 0, 0, [(1, 5, 1, "D6"), (1, 2, 1, "D6")]),
    "rotate":        ("pulse2", 2, 0, 0, [(1, 9, 0, "G5"), (2, 9, 1, "D6")]),
    "land":          ("noise", 2, 0, 0, [(4, 11, 1, 0x67)]),
    "clear":         ("pulse1", 5, 2, 0, [(2, 12, 0, "C6"), (2, 12, 0, "E6"), (2, 12, 0, "G6"), (8, 12, 2, "C7")]),
    "virus":         ("noise", 5, 0, 0, [(2, 13, 0, 0x14), (6, 10, 1, 0x24)]),
    "win":           ("pulse1", 6, 2, 0, [(6, 12, 0, "C5"), (6, 12, 0, "E5"), (6, 12, 0, "G5"), (6, 12, 0, "C6"),
                                          (6, 12, 0, "E6"), (24, 12, 4, "G6")]),
    "lose":          ("pulse1", 6, 2, 0, [(10, 11, 0, "G5"), (10, 11, 0, "D#5"), (10, 11, 0, "C5"), (30, 11, 5, "G4")]),
    # the fight
    "punch":         ("noise", 1, 0, 0, [(2, 6, 1, 0x26), (3, 4, 1, 0x35)]),                      # swing
    "hit":           ("noise", 4, 0, 0, [(1, 15, 0, 0x51), (6, 12, 1, 0x63)]),                     # glove on body
    "block":         ("noise", 3, 0, 0, [(1, 12, 0, 0x22), (3, 8, 1, 0x31)]),                      # glove on glove
    "dodge":         ("noise", 2, 0, 0, [(2, 4, 0, 0x14), (3, 6, 0, 0x24), (4, 4, 1, 0x34)]),      # whoosh
    "tell":          ("pulse2", 2, 2, 0, [(2, 9, 0, "A6"), (6, 7, 2, "E7")]),                      # a glint
    "rival_swing":   ("noise", 3, 0, 0, [(3, 9, 0, 0x34), (4, 7, 1, 0x45)]),
    "player_hit":    ("noise", 5, 0, 0, [(1, 15, 0, 0x60), (8, 13, 2, 0x71)]),
    "star_get":      ("pulse2", 5, 2, 0, [(2, 11, 0, "E6"), (2, 11, 0, "G#6"), (2, 11, 0, "B6"), (8, 11, 2, "E7")]),
    "star_wind":     ("pulse1", 4, 2, 0x17, [(16, 10, 0, "C5")]),                                 # rising sweep
    "star_punch":    ("noise", 6, 0, 0, [(1, 15, 0, 0x50), (3, 15, 0, 0x61), (12, 13, 3, 0x72)]),
    "knockdown":     ("noise", 6, 0, 0, [(2, 15, 0, 0x71), (20, 14, 4, 0x75)]),                    # thud on the canvas
    "count":         ("pulse2", 4, 2, 0, [(3, 11, 0, "C6"), (6, 7, 1, "C6")]),
    "bell":          ("pulse1", 6, 2, 0, [(3, 13, 0, "E7"), (24, 13, 5, "E7")]),
    "ko":            ("pulse1", 7, 2, 0, [(4, 13, 0, "E7"), (4, 13, 0, "E7"), (4, 13, 0, "E7"), (30, 13, 6, "E7")]),
    "taunt":         ("pulse2", 2, 1, 0, [(4, 8, 0, "C6"), (4, 8, 0, "D6"), (4, 8, 0, "C6"), (4, 8, 0, "D6")]),  # winding the key
    "pop":           ("pulse2", 6, 2, 0, [(2, 12, 0, "G6"), (3, 10, 1, "C7")]),                    # arm out of its socket
    "click":         ("noise", 6, 0, 0, [(1, 13, 0, 0x10), (2, 9, 1, 0x00)]),                      # snapped back in
}

# Sound styles: the same events with a different character. Arcade is the default.
STYLES = {
    "arcade": {},
    "boxing": {                     # glove taps for menus, ring bells for choosing
        "menu_move":     ("noise", 1, 0, 0, [(1, 9, 0, 0x22), (2, 5, 1, 0x32)]),
        "menu_confirm":  ("pulse1", 3, 2, 0, [(2, 13, 0, "E7"), (14, 12, 3, "E7")]),
        "menu_back":     ("noise", 3, 0, 0, [(1, 11, 0, 0x41), (5, 9, 1, 0x53)]),
        "option_change": ("noise", 1, 0, 0, [(1, 10, 0, 0x21), (2, 6, 1, 0x31)]),
        "press_start":   ("pulse1", 4, 2, 0, [(2, 13, 0, "E7"), (8, 12, 2, "E7"), (2, 13, 0, "E7"), (8, 12, 2, "E7"),
                                              (2, 13, 0, "E7"), (20, 12, 4, "E7")]),
        "win":           ("pulse1", 6, 2, 0, [(6, 12, 0, "G5"), (6, 12, 0, "C6"), (6, 12, 0, "E6"), (12, 12, 0, "G6"),
                                              (6, 12, 0, "E6"), (30, 12, 5, "G6")]),
        "lose":          ("pulse1", 6, 2, 0, [(12, 11, 0, "E5"), (12, 11, 0, "D5"), (12, 11, 0, "C5"), (36, 11, 6, "C4")]),
    },
}
VOICES = {"pulse1": 0, "pulse2": 1, "noise": 2}


def note_index(name):
    """'C6' -> index into the ROM's note table (1 = C2)."""
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + NOTES[pitch]
    index = midi - LOW_NOTE + 1
    if not 1 <= index <= NOTE_COUNT:
        raise ValueError(f"note {name} is outside C2-B7")
    return index


def note_table():
    """Game Boy period values for C2 ... B7 (f = 131072 / (2048 - x))."""
    out = []
    for k in range(NOTE_COUNT):
        midi = LOW_NOTE + k
        freq = 440 * 2 ** ((midi - 69) / 12)
        out.append(max(0, min(2047, round(2048 - 131072 / freq))))
    return out


def symbol(name):
    return "SFX_" + name.upper()


# Which kit uses which effects; a ROM only carries the groups it needs.
GROUPS = {
    "menu": ["menu_move", "menu_confirm", "menu_back", "option_change", "press_start"],
    "puzzle": ["move", "move_held", "rotate", "land", "clear", "virus", "win", "lose"],
    "fight": ["punch", "hit", "block", "dodge", "tell", "rival_swing", "player_hit", "star_get", "star_wind",
              "star_punch", "knockdown", "count", "bell", "ko", "taunt", "pop", "click", "win", "lose"],
}


def effects(style="arcade", groups=("menu", "puzzle")):
    """The effects a ROM carries, in table order."""
    names = [n for n in SFX if any(n in GROUPS[g] for g in groups)]
    table = {**SFX, **STYLES[style]}
    return {n: table[n] for n in names}


def asm_data(style="arcade", groups=("menu", "puzzle")):
    """Constants and data for the effects in these groups, in the given style."""
    table = effects(style, groups)
    defs, data = [f"DEF SFX_NOTE_TOP EQU {NOTE_COUNT}"], ["SfxTable:"]
    for k, name in enumerate(table):
        defs.append(f"DEF {symbol(name)} EQU {k}")
        data.append(f"    dw Sfx_{name}")
    for name, (voice, priority, duty, sweep, steps) in table.items():
        data.append(f"Sfx_{name}:")
        data.append(f"    db {VOICES[voice]}, {priority}, {duty << 6}, {sweep}   ; voice, priority, duty, sweep")
        for frames, volume, fade, note in steps:
            value = note if voice == "noise" else (note_index(note) if note else 0)
            data.append(f"    db {frames}, ${volume << 4 | fade:02X}, ${value:02X}")
        data.append("    db 0")
    data.append("SfxNotes:                   ; period for note index 1 (C2) upward; index 0 unused")
    data.append("    dw 0, " + ", ".join(str(v) for v in note_table()))
    return "\n".join(defs), "\n".join(data)
