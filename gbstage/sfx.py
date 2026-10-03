"""Built-in sound effects, played on the Game Boy's own channels.

Each effect: (voice, priority, duty, sweep, steps). Voices: "pulse1" (with sweep), "pulse2", "noise".
A step is (frames, volume, fade, note) for pulses (note like "C6", or None for a rest) or
(frames, volume, fade, noise) for noise, where noise is the NR43 value (low = deep, high = hiss).
fade is the envelope pace: 0 = hold, 1 = fast decay ... 7 = slow decay.
A higher priority effect can cut in on a voice; an equal or lower one can't interrupt it.
"""

NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
LOW_NOTE = 36          # C2: note index 1 in the ROM's table
NOTE_COUNT = 63        # C2 ... D7

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
}
VOICES = {"pulse1": 0, "pulse2": 1, "noise": 2}


def note_index(name):
    """'C6' -> index into the ROM's note table (1 = C2)."""
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + NOTES[pitch]
    index = midi - LOW_NOTE + 1
    if not 1 <= index <= NOTE_COUNT:
        raise ValueError(f"note {name} is outside C2-D7")
    return index


def note_table():
    """Game Boy period values for C2 ... D7 (f = 131072 / (2048 - x))."""
    out = []
    for k in range(NOTE_COUNT):
        midi = LOW_NOTE + k
        freq = 440 * 2 ** ((midi - 69) / 12)
        out.append(max(0, min(2047, round(2048 - 131072 / freq))))
    return out


def symbol(name):
    return "SFX_" + name.upper()


def asm_data():
    """Constants and data for every effect."""
    defs, data = [], ["SfxTable:"]
    for k, (name, (voice, priority, duty, sweep, steps)) in enumerate(SFX.items()):
        defs.append(f"DEF {symbol(name)} EQU {k}")
        data.append(f"    dw Sfx_{name}")
    for name, (voice, priority, duty, sweep, steps) in SFX.items():
        data.append(f"Sfx_{name}:")
        data.append(f"    db {VOICES[voice]}, {priority}, {duty << 6}, {sweep}   ; voice, priority, duty, sweep")
        for frames, volume, fade, note in steps:
            value = note if voice == "noise" else (note_index(note) if note else 0)
            data.append(f"    db {frames}, ${volume << 4 | fade:02X}, ${value:02X}")
        data.append("    db 0")
    data.append("SfxNotes:                   ; period for note index 1 (C2) upward; index 0 unused")
    data.append("    dw 0, " + ", ".join(str(v) for v in note_table()))
    return "\n".join(defs), "\n".join(data)
