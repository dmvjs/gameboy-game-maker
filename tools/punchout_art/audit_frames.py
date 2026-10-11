"""Which rip frame is each NES frame? Joe's silhouette in the NES render (what differs from the empty ring)
against every frame of the rip sheet, both scaled to one height: the best overlap (IoU), and its colors."""
import pickle, pathlib
import build, png

HERE = pathlib.Path(__file__).parent
FLIPPED = set(range(0x26, 0x3A))            # his knockdown frames: always drawn with $A2 set

def mask_of(img, empty=None):
    h, w = len(img), len(img[0])
    pts = [(x, y) for y in range(h) for x in range(w)
           if (empty is None and img[y][x]) or (empty is not None and tuple(img[y][x][:3]) != tuple(empty[y][x][:3]))]
    if not pts: return None
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    return [[(img[y][x] if (empty is None and img[y][x]) or (empty is not None and tuple(img[y][x][:3]) != tuple(empty[y][x][:3])) else None)
             for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)], (x0, y0)

def norm(m, H=48):
    s = H / len(m)
    return build.scale(m, s, outline_weight=1.0)

def iou(a, b):
    h = min(len(a), len(b)); w = max(len(a[0]), len(b[0]))
    best = 0
    for dx in range(-6, 7):
        inter = union = 0
        for y in range(h):
            for x in range(w):
                pa = 0 <= x < len(a[0]) and a[y][x] is not None
                xb = x + dx
                pb = 0 <= xb < len(b[0]) and b[y][xb] is not None
                inter += pa and pb; union += pa or pb
        best = max(best, inter / max(1, union))
    return best

data = pickle.load(open(HERE / "out" / "nes-frames.pkl", "rb"))
empty, frames = data["empty"], data["frames"]
px = build.load("glass-joe.png"); boxes = build.components(px, 120)
rips = {}
for i, box in enumerate(boxes):
    if box[3] < 40: continue                # (the small bits on the sheet)
    m = build.cut(px, box)
    rips[i] = norm(m)
mirror = lambda m: [list(reversed(r)) for r in m]
current = {int(k, 16): v for k, v in build.NES_FRAMES.items()}
pose_of = {v: k for k, v in build.JOE.items()}
results = {}
for f in sorted({k for k, _ in frames}):
    flip = 1 if f in FLIPPED else 0
    mm = mask_of(frames[(f, flip)], empty)
    if not mm: continue
    m = norm(mm[0])
    scores = sorted(((max(iou(m, r), iou(m, mirror(r))), i) for i, r in rips.items()), reverse=True)[:3]
    cur = current.get(f); cur_i = build.JOE.get(cur)
    results[f] = scores
    print(f"{f:02X} now {cur!s:11} (rip {cur_i!s:>3})  best: " + ", ".join(f"rip {i} ({pose_of.get(i, '-')}) {s:.2f}" for s, i in scores))
pickle.dump(results, open(HERE / "out" / "audit.pkl", "wb"))
