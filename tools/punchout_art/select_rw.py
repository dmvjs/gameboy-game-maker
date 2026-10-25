"""select_rw.py: from out/rw3/*.log, the redraws to take (head on today's grid and its face the same, no more black
filling than today's or the free fit) and those left as they are, with why. -> out/rw3/accept.json"""
import re, ast, glob, json
acc, rej = {}, {}
for f in sorted(glob.glob("out/rw3/*.log")):
    r = f.split("/")[-1][:-4]
    for l in open(f):
        m = re.match(r"(\w+) (\S+) (\{.*\})$", l.strip())
        if not m: continue
        k, d = m.group(2), ast.literal_eval(m.group(3))
        b80, bfree, bforced = d["black"]
        hd, dy, dx = d["head"]
        why = []
        if dy % 8 or dx % 8: why.append(f"head off the grid ({dy},{dx})")
        if bforced > max(b80, bfree) + 4: why.append(f"black filling {bforced} vs {max(b80, bfree)}")
        if d["tiles96"] > 60: why.append(f"tiles {d['tiles96']}")
        (rej if why else acc).setdefault(r, {})[k] = "; ".join(why) or f"h {d['h96']}, head diff {hd}"
json.dump({"accept": {r: sorted(v) for r, v in acc.items()}, "reject": rej}, open("out/rw3/accept.json", "w"), indent=1)
for r in sorted(set(acc) | set(rej)):
    print(r, "take", len(acc.get(r, {})), "leave", len(rej.get(r, {})), rej.get(r, {}))
