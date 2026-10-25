"""apply_rewarp.py RIVAL KEYS...: the full-size redraws (out/rewarp-RIVAL-KEY.json, rewarp.py) put in: each one's
touch-up (its rows, 96 tall, and how far it moved), and in the art file its picture and its place (the same head
on screen: the place takes the change in how far it moved). Nothing else in the art file changes."""
import json, re, sys
from pathlib import Path
import build as B, warp

def touch_path(rival, key):
    return B.TOUCHUPS / rival / f"{key.replace('|', 'm')}.txt"

def main(rival, keys):
    up = rival.upper()
    js = B.OUT_JS.read_text()
    a = js.index(f"export const {up}_PICTURES = {{ poses: {{")
    b = js.index(" };", js.index("}, places:", a)) + 3
    block = js[a:b]
    pm = re.search(r"\}, places: (\{.*?\})(, next: |, jewel: | \};)", block)
    places = json.loads(pm.group(1))
    _, pals, _ = B.import_rival(str(B.HERE / "out" / f"{rival}-from-nes.png"), [26, 28, 31])
    LEG = warp.LEGENDS[rival]
    for key in keys:
        new = json.loads((B.HERE / "out" / f"rewarp-{rival}-{key.replace('|', 'm')}.json").read_text())
        rows, mv = new["rows"], tuple(new["mv"])
        p = touch_path(rival, key)
        lines = p.read_text().splitlines()
        old_mv = next(tuple(map(int, l.split()[1:3])) for l in lines if l.startswith("moved "))
        head = [l for l in lines if l.startswith(("#", "auto", "final", "legend"))]
        head = [h.replace(", baked", ", baked; full size, 96 rows: his feet below his frame") if h.startswith("#") and "96 rows" not in h else h
                for h in head]
        out = [h for h in head if not h.startswith("legend")] + [f"moved {mv[0]} {mv[1]}"] + [h for h in head if h.startswith("legend")] + rows
        p.write_text("\n".join(out) + "\n")
        fr = [[(LEG[c] + (255,)) if c not in ".-" else None for c in r] for r in rows]
        imp = B.import_pictures({key: fr}, pals)[key]
        line_re = re.compile(r"  '" + re.escape(key) + r"': \{[^\n]*\n")
        m = line_re.search(block)
        assert m, key
        entry = {"pixels": imp["pixels"], "cells": imp["cells"]}
        if imp.get("whites"):
            entry["whites"] = imp["whites"]
        line = f"  '{key}':" + B.pic(entry)[1:] if hasattr(B, "pic") else None
        if line is None:
            body = f"{{ pixels: '{entry['pixels']}', cells: '{entry['cells']}'" + (f", whites: {json.dumps(entry['whites'])}" if entry.get("whites") else "") + " }"
            line = f"  '{key}': {body},"
        old_line = m.group(0)
        if old_line.rstrip().endswith("},") and not line.endswith(","):
            line += ","
        block = block[:m.start()] + line + "\n" + block[m.end():]
        dx, dy = old_mv[0] - mv[0], old_mv[1] - mv[1]
        x, y = places.get(key, [0, 0])
        x, y = x + dx, y + dy
        if (x, y) == (0, 0):
            places.pop(key, None)
        else:
            places[key] = [x, y]
        print(rival, key, "moved", old_mv, "->", mv, "place", places.get(key, [0, 0]), "tiles rows", len(rows))
    block = re.sub(r"\}, places: \{.*?\}(, next: |, jewel: | \};)", lambda mm: "}, places: " + json.dumps(places) + mm.group(1), block, count=1)
    B.OUT_JS.write_text(js[:a] + block + js[b:])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
