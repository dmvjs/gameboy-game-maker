"""The Puzzle grid kit: a falling-capsule puzzle (match 4 of a color to clear, clear every virus to win).

This module holds the cell encoding, the default cell art, and a reference implementation of the rules.
The ROM's assembly follows the same rules; the golden tests run real games in the profiler and check,
every time a capsule locks, that the ROM resolves the board exactly as `resolve` does here.

Cell byte: shape << 2 | color. 0 means empty. Colors 0-2 are palette slots 1-3; slot 4 is the background.
"""

EMPTY, VIRUS, SINGLE, LEFT, RIGHT, TOP, BOTTOM, POP = range(8)
SHAPES = ["virus", "single", "left", "right", "top", "bottom", "pop"]   # shapes 1-7
COLORS = 3
BG_SLOT = 3
MIN_W, MAX_W, MIN_H, MAX_H = 4, 10, 4, 18

# 8x8 masks: '#' = the piece's color, '.' = background.
DEFAULT_SHAPES = {
    "virus": ["..####..", ".######.", "##.##.##", "##.##.##", "########", ".##..##.", "#.####.#", ".#....#."],
    "single": ["........", "..####..", ".######.", ".######.", ".######.", ".######.", "..####..", "........"],
    "left": ["........", "..######", ".#######", ".#######", ".#######", ".#######", "..######", "........"],
    "right": ["........", "######..", "#######.", "#######.", "#######.", "#######.", "######..", "........"],
    "top": ["........", "..####..", ".######.", ".######.", ".######.", ".######.", ".######.", ".######."],
    "bottom": [".######.", ".######.", ".######.", ".######.", ".######.", ".######.", "..####..", "........"],
    "pop": ["........", ".#....#.", "..#..#..", "...##...", "...##...", "..#..#..", ".#....#.", "........"],
}


def mask_from_rows(rows):
    return "".join("1" if c == "#" else "0" for row in rows for c in row)


DEFAULT_MASKS = {name: mask_from_rows(rows) for name, rows in DEFAULT_SHAPES.items()}


def cell(shape, color):
    return shape << 2 | color if shape else 0


def shape_of(c):
    return c >> 2


def color_of(c):
    return c & 3


def tile_slots(mask, color):
    """64 slots for a shape mask drawn in a color (empty background elsewhere)."""
    return tuple(color if bit == "1" else BG_SLOT for bit in mask)


def empty_tile():
    return tuple([BG_SLOT] * 64)


def virus_top(h):
    """Viruses only go in the lower rows, leaving room to play at the top."""
    return max(3, h - 10)


def max_viruses(w, h):
    """At most 60, and never more than 3/4 of the virus rows."""
    return min(60, w * (h - virus_top(h)) * 3 // 4)


def virus_count(level, w, h):
    """Dr. Mario's rule: 4 viruses per level step, capped so the board stays playable."""
    return min(4 * (level + 1), max_viruses(w, h))


SPEED_FRAMES = [30, 20, 12]       # frames per row for LOW / MED / HI
MIN_FRAMES = 4                    # fastest it gets
SPEEDUP_EVERY = 10                # capsules between speed-ups
POINTS = [1, 2, 3]                # hundreds per virus by speed, doubling within one clear


# ---- reference rules --------------------------------------------------------------

def find_matches(grid, w, h):
    """Cells in a horizontal or vertical run of 4+ of one color."""
    marked = set()
    for r in range(h):
        run = []
        for c in range(w + 1):
            v = grid[r * w + c] if c < w else 0
            if run and v and color_of(v) == color_of(grid[run[0]]):
                run.append(r * w + c)
            else:
                if len(run) >= 4:
                    marked.update(run)
                run = [r * w + c] if v else []
    for c in range(w):
        run = []
        for r in range(h + 1):
            v = grid[r * w + c] if r < h else 0
            if run and v and color_of(v) == color_of(grid[run[0]]):
                run.append(r * w + c)
            else:
                if len(run) >= 4:
                    marked.update(run)
                run = [r * w + c] if v else []
    return marked


def clear(grid, w, marked):
    """Turn matched cells into pops and unpair their partners. Returns viruses cleared."""
    viruses = 0
    for i in sorted(marked):
        s = shape_of(grid[i])
        if s == VIRUS:
            viruses += 1
        partner = {LEFT: i + 1, RIGHT: i - 1, TOP: i + w, BOTTOM: i - w}.get(s)
        if partner is not None and partner not in marked:
            grid[partner] = cell(SINGLE, color_of(grid[partner]))
        grid[i] = cell(POP, color_of(grid[i]))
    return viruses


def settle_step(grid, w, h):
    """Drop every unsupported loose piece by one row (bottom-up). Returns True if anything moved."""
    moved = False
    for r in range(h - 2, -1, -1):
        for c in range(w):
            i = r * w + c
            v = grid[i]
            s = shape_of(v)
            below = i + w
            if s in (SINGLE, BOTTOM) and grid[below] == 0:
                grid[below] = v
                grid[i] = 0
                if s == BOTTOM:
                    grid[i] = grid[i - w]       # the top half comes down into this cell
                    grid[i - w] = 0
                moved = True
            elif s == LEFT and grid[below] == 0 and grid[below + 1] == 0:
                grid[below], grid[below + 1] = v, grid[i + 1]
                grid[i] = grid[i + 1] = 0
                moved = True
    return moved


def add_bcd(score, hundreds):
    """score: int (decimal). Adds hundreds * 100, capped at 999999."""
    return min(score + hundreds * 100, 999999)


def resolve(grid, w, h, speed, score):
    """Everything that happens after a capsule locks: matches, pops, falling, chains.
    Returns (grid, score, viruses cleared)."""
    grid = list(grid)
    total = 0
    base = POINTS[speed]          # doubles with every virus this capsule clears, chains included
    while True:
        marked = find_matches(grid, w, h)
        if not marked:
            return grid, score, total
        n = clear(grid, w, marked)
        total += n
        for _ in range(n):
            score = add_bcd(score, base)
            base = min(base * 2, 99)
        for i in marked:
            grid[i] = 0
        while settle_step(grid, w, h):
            pass
