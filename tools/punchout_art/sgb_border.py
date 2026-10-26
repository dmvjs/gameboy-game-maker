"""The Super Game Boy border (frame), made from Punch-Out!! (NES) itself: the title's blue grid and PUNCH-OUT!! letters
along the top ("MIKE TYSON'S" over the short letters), the crowd round the rest. -> gbstage/sgb_border.hex (as text): 8 KB of SNES tiles (CHR_TRN's two halves), the 32x28 map (PCT_TRN), palette 4.

  python sgb_border.py [preview.png]"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent.parent / "gbstage" / "sgb_border.hex"

BLACK, GRID, ORANGE, RED, TEXT, CROWD = (0, 0, 0), (48, 50, 236), (212, 136, 32), (152, 34, 32), (76, 154, 236), \
    (236, 106, 100)
COLORS = [BLACK, BLACK, GRID, ORANGE, RED, TEXT]   # (0: see-through, the window's)


def frames():
    """The NES title (its letters settled) and a fight's first seconds (the crowd and the ropes clear of him)."""
    import nes_reference as R
    nes = R._nes()
    for t in range(691):
        f = nes.step()
    title = np.array(f)[:, :, :3].astype(int)
    nes = R._start(0)
    for _ in range(4):
        nes.controller = R.START
        nes.step()
    nes.controller = 0
    for t in range(501):
        f = nes.step()
    return title, np.array(f)[:, :, :3].astype(int)


def squeeze_text(title):
    """MIKE TYSON'S, its glyphs one column apart and the space narrowed (to fit between the P and the O)."""
    rows = title[25:32, 80:176]
    on = (rows == TEXT).all(2)
    cols, out, gap = [], [], 0
    for x in range(on.shape[1]):
        if on[:, x].any():
            if out and gap:
                out += [None] * (1 if gap < 6 else 4)
            out.append(x)
            gap = 0
        else:
            gap += 1
    return np.array([[on[y, x] if x is not None else False for x in out] for y in range(7)])


def compose(title, fight):
    img = np.zeros((224, 256, 3), int)
    img[0:40] = title[62:102]                           # the grid and the letters (3 rows down)
    tail = (img[:, 229:] == ORANGE).all(2) | (img[:, 229:] == RED).all(2)
    img[:, 229:][tail] = BLACK                          # (not the registered mark)
    grid = (title[45:48, 0:256] == GRID).all(2)
    for y in range(40):
        for x in range(229, 256):                       # (its grid filled in)
            img[y, x] = GRID if grid[(y + 62 - 45) % 3, x] else BLACK
    t = squeeze_text(title)
    h, w = t.shape
    x0 = 54 + (91 - w) // 2
    edge = np.zeros((h + 2, w + 2), bool)               # (outlined in black, over the grid)
    for dy in range(3):
        for dx in range(3):
            edge[dy:dy + h, dx:dx + w] |= t
    img[8:10 + h, x0 - 1:x0 + w + 1][edge] = BLACK
    img[9:9 + h, x0:x0 + w][t] = TEXT
    # Round the rest of the frame (both sides, under the screen): the crowd's rows from behind the ropes, the ropes
    # left out (stands), darker than at the ring; six-tile pieces, each row's shifted (few tiles, no seams).
    pieces = [fight[48 + 8 * k:53 + 8 * k, 20 + 40 * k:68 + 40 * k] for k in range(4)]
    for r in range(23):
        p = pieces[r % 4]
        row = np.zeros((8, 256, 3), int)
        for x in range(0, 256, 8):
            k = (x // 8 + 5 * r) % 6
            row[1:6, x:x + 8] = p[:, 8 * k:8 * k + 8]
        row[(row == CROWD).all(2)] = RED
        y = 40 + 8 * r
        if y < 184:
            img[y:y + 8, 0:48], img[y:y + 8, 208:256] = row[:, 0:48], row[:, 208:256]
        else:
            img[y:y + 8] = row
    return img


def tiles(img):
    """8x8 tiles, alike ones (flipped too) shared; the window's tile see-through. -> (tile list, map entries)."""
    idx = np.zeros(img.shape[:2], int)
    for i, c in enumerate(COLORS[1:], 1):
        idx[(img == c).all(2)] = i
    assert ((idx > 0) | (img == BLACK).all(2)).all(), "a colour the border has no room for"
    idx[(img == BLACK).all(2)] = 1
    found, chars, entries = {}, [], []
    blank = np.zeros((8, 8), int)
    chars.append(blank)
    found[blank.tobytes()] = (0, 0)
    for ty in range(28):
        for tx in range(32):
            if 6 <= tx < 26 and 5 <= ty < 23:
                entries.append(0x1000)                  # (palette 4, tile 0: the Game Boy's screen shows through)
                continue
            t = idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            hit = None
            for flip, v in ((0, t), (0x40, t[:, ::-1]), (0x80, t[::-1]), (0xC0, t[::-1, ::-1])):
                if v.tobytes() in found:
                    hit = found[v.tobytes()][0], flip
                    break
            if hit is None:
                found[t.tobytes()] = (len(chars), 0)
                hit = len(chars), 0
                chars.append(t)
            entries.append(0x1000 | hit[0] | hit[1] << 8)
    assert len(chars) <= 256, len(chars)
    return chars, entries


def snes(chars):
    out = bytearray()
    for t in chars + [np.zeros((8, 8), int)] * (256 - len(chars)):
        b = bytearray(32)
        for y in range(8):
            for x in range(8):
                v, m = t[y, x], 0x80 >> x
                if v & 1: b[2 * y] |= m
                if v & 2: b[2 * y + 1] |= m
                if v & 4: b[16 + 2 * y] |= m
                if v & 8: b[16 + 2 * y + 1] |= m
        out += b
    return out


def bgr(c):
    return (c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10


def main():
    title, fight = frames()
    img = compose(title, fight)
    chars, entries = tiles(img)
    data = snes(chars) + b"".join(e.to_bytes(2, "little") for e in entries) \
        + b"".join(bgr(c).to_bytes(2, "little") for c in COLORS + [BLACK] * (16 - len(COLORS)))
    OUT.write_text("".join(data[i:i + 32].hex() + "\n" for i in range(0, len(data), 32)))
    print(f"{OUT}: {len(chars)} tiles, {len(data)} bytes")
    if len(sys.argv) > 1:
        from PIL import Image
        Image.fromarray(img.astype(np.uint8)).resize((512, 448), Image.NEAREST).save(sys.argv[1])


if __name__ == "__main__":
    main()
