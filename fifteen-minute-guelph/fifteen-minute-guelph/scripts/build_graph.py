"""Build a walkable network graph for Guelph from streets + trails, snap
addresses, amenities and bus stops to it, and write compact JSON for the app."""
import json, math, heapq, collections, csv, os, pickle
import numpy as np

U = "/mnt/user-data/uploads/City of Guelph Data/"
T = U + "_testdata/"
OUT = "/home/claude/guelph/app/data/"
WORK = "/home/claude/guelph/work/"
os.makedirs(OUT, exist_ok=True); os.makedirs(WORK, exist_ok=True)

LAT0, LON0 = 43.54, -80.25
KX = 111320 * math.cos(math.radians(LAT0)); KY = 110574
def proj(lon, lat): return ((lon - LON0) * KX, (lat - LAT0) * KY)
def unproj(x, y): return (x / KX + LON0, y / KY + LAT0)

def lines_of(geom):
    if geom is None: return []
    if geom["type"] == "LineString": return [geom["coordinates"]]
    if geom["type"] == "MultiLineString": return geom["coordinates"]
    return []

# ---------- 1. collect lines ----------
lines = []  # (kind, [(x,y),...])
streets = json.load(open(T + "streets.geojson"))
for f in streets["features"]:
    cls = f["properties"].get("ROADCLASS")
    if cls in ("Expressway", "Ramp"): continue
    for l in lines_of(f["geometry"]):
        lines.append((cls or "Local", [proj(*p[:2]) for p in l]))
trails = json.load(open(T + "trails.geojson"))
for f in trails["features"]:
    for l in lines_of(f["geometry"]):
        lines.append(("Trail", [proj(*p[:2]) for p in l]))
print("lines", len(lines))

# ---------- 2. vertex graph (1 m snapping) ----------
key_of = {}; vx = []; vy = []
def vid(x, y):
    k = (round(x), round(y))
    i = key_of.get(k)
    if i is None:
        i = len(vx); key_of[k] = i; vx.append(x); vy.append(y)
    return i

adj = collections.defaultdict(dict)  # v -> {w: (len, kind)}
line_of_v = collections.defaultdict(set)
endpoints = []
KIND_RANK = {"Trail": 0, "Local": 1, "Private": 1, "University": 1, "Collector": 2, "Arterial": 3}
def densify(pts, step=50):
    out = [pts[0]]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        d = math.hypot(x2 - x1, y2 - y1); n = int(d // step)
        for i in range(1, n + 1):
            t = i / (n + 1); out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
        out.append((x2, y2))
    return out
for li, (kind, pts) in enumerate(lines):
    ids = [vid(x, y) for x, y in densify(pts)]
    ids = [v for i, v in enumerate(ids) if i == 0 or v != ids[i - 1]]
    if len(ids) < 2: continue
    for a, b in zip(ids, ids[1:]):
        d = math.hypot(vx[a] - vx[b], vy[a] - vy[b])
        adj[a][b] = (d, kind); adj[b][a] = (d, kind)
    for v in ids: line_of_v[v].add(li)
    endpoints += [ids[0], ids[-1]]
vx = np.array(vx); vy = np.array(vy)
print("vertices", len(vx))

# ---------- 3. connect dangling ends to nearby other lines (<= 25 m) ----------
CELL = 30
grid = collections.defaultdict(list)
for i in range(len(vx)): grid[(int(vx[i] // CELL), int(vy[i] // CELL))].append(i)
def near(x, y, r):
    cx, cy = int(x // CELL), int(y // CELL); n = int(r // CELL) + 1
    for gx in range(cx - n, cx + n + 1):
        for gy in range(cy - n, cy + n + 1):
            for j in grid.get((gx, gy), ()):
                d = math.hypot(vx[j] - x, vy[j] - y)
                if d <= r: yield j, d
added = 0
for v in set(endpoints):
    if len(adj[v]) != 1: continue
    best = None
    for j, d in near(vx[v], vy[v], 25):
        if j == v or j in adj[v]: continue
        if line_of_v[j] & line_of_v[v]: continue
        if best is None or d < best[1]: best = (j, d)
    if best:
        j, d = best
        adj[v][j] = (max(d, 1), "Link"); adj[j][v] = (max(d, 1), "Link"); added += 1
print("dangle links", added)

# ---------- 3b. node at-grade crossings that share no vertex ----------
vx = list(vx); vy = list(vy)
segs = [(a, b) for a in adj for b in adj[a] if a < b]
sgrid = collections.defaultdict(list)
for i, (a, b) in enumerate(segs):
    for gx in range(int(min(vx[a], vx[b]) // 50), int(max(vx[a], vx[b]) // 50) + 1):
        for gy in range(int(min(vy[a], vy[b]) // 50), int(max(vy[a], vy[b]) // 50) + 1):
            sgrid[(gx, gy)].append(i)
def orient(a, b, c): return (vx[b] - vx[a]) * (vy[c] - vy[a]) - (vy[b] - vy[a]) * (vx[c] - vx[a])
splits = collections.defaultdict(list)  # seg index -> [(t, vertex)]
seen_pairs = set()
for ids in sgrid.values():
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            i, j = ids[x], ids[y]
            if (i, j) in seen_pairs: continue
            seen_pairs.add((i, j))
            (a, b), (c, d) = segs[i], segs[j]
            if len({a, b, c, d}) < 4: continue
            d1, d2, d3, d4 = orient(c, d, a), orient(c, d, b), orient(a, b, c), orient(a, b, d)
            if d1 * d2 < 0 and d3 * d4 < 0:
                t = d1 / (d1 - d2)
                px, py = vx[a] + t * (vx[b] - vx[a]), vy[a] + t * (vy[b] - vy[a])
                nv = len(vx); vx.append(px); vy.append(py)
                splits[i].append((t, nv))
                u = d3 / (d3 - d4); splits[j].append((u, nv))
for i, lst in splits.items():
    a, b = segs[i]; d, kind = adj[a][b]
    del adj[a][b]; del adj[b][a]
    chain = [a] + [v for _, v in sorted(lst)] + [b]
    for p, q in zip(chain, chain[1:]):
        L = max(math.hypot(vx[p] - vx[q], vy[p] - vy[q]), 0.1)
        adj[p][q] = (L, kind); adj[q][p] = (L, kind)
vx = np.array(vx); vy = np.array(vy)
print("crossings noded", sum(len(l) for l in splits.values()) // 2)

# ---------- 4. keep the largest connected component ----------
seen = np.full(len(vx), -1); comp = 0; sizes = []
for s in range(len(vx)):
    if seen[s] >= 0 or s not in adj: continue
    st = [s]; seen[s] = comp; n = 0
    while st:
        u = st.pop(); n += 1
        for w in adj[u]:
            if seen[w] < 0: seen[w] = comp; st.append(w)
    sizes.append(n); comp += 1
big = int(np.argmax(sizes))
print("components", comp, "largest", sizes[big], "of", sum(sizes))
keep = set(np.where(seen == big)[0].tolist())

# ---------- 5. collapse chains into edges, splitting every <=70 m ----------
MAXSEG = 70
is_key = {v for v in keep if len(adj[v]) != 2}
visited = set(); edges = []  # (a, b, length, kind, [vertex ids])
def walk_chain(a, b):
    path = [a, b]; length = adj[a][b][0]; kinds = collections.Counter({adj[a][b][1]: adj[a][b][0]})
    prev, cur = a, b
    while cur not in is_key and length < MAXSEG:
        nxt = [w for w in adj[cur] if w != prev][0]
        d, k = adj[cur][nxt]
        length += d; kinds[k] += d; path.append(nxt); prev, cur = cur, nxt
    if cur not in is_key: is_key.add(cur)
    return path, length, kinds.most_common(1)[0][0]
# first pass: pure cycles without key nodes get one
for v in keep:
    if v in is_key: continue
# iterate until all edges consumed
pending = list(is_key)
done_pairs = set()
while pending:
    a = pending.pop()
    for b in list(adj[a]):
        if b not in keep or (a, b) in done_pairs: continue
        path, length, kind = walk_chain(a, b)
        for p, q in zip(path, path[1:]): done_pairs.add((p, q)); done_pairs.add((q, p))
        edges.append((path[0], path[-1], length, kind, path))
        if path[-1] not in pending: pending.append(path[-1])
# isolated cycles with no key vertex
left = [v for v in keep if any((v, w) not in done_pairs for w in adj[v])]
for v in left:
    if v in is_key: continue
    is_key.add(v); pending.append(v)
    while pending:
        a = pending.pop()
        for b in list(adj[a]):
            if (a, b) in done_pairs: continue
            path, length, kind = walk_chain(a, b)
            for p, q in zip(path, path[1:]): done_pairs.add((p, q)); done_pairs.add((q, p))
            edges.append((path[0], path[-1], length, kind, path))
            if path[-1] not in pending: pending.append(path[-1])

keys = sorted({e[0] for e in edges} | {e[1] for e in edges})
kidx = {v: i for i, v in enumerate(keys)}
print("nodes", len(keys), "edges", len(edges))

N = len(keys)
nx_ = vx[keys]; ny_ = vy[keys]
G = [[] for _ in range(N)]
for ei, (a, b, L, k, p) in enumerate(edges):
    G[kidx[a]].append((kidx[b], L)); G[kidx[b]].append((kidx[a], L))

# node spatial index
ngrid = collections.defaultdict(list)
for i in range(N): ngrid[(int(nx_[i] // CELL), int(ny_[i] // CELL))].append(i)
def nearest_node(x, y, rmax=600):
    best = (None, 1e18); r = CELL
    while r <= rmax:
        cx, cy = int(x // CELL), int(y // CELL); n = r // CELL
        for gx in range(cx - n, cx + n + 1):
            for gy in range(cy - n, cy + n + 1):
                for j in ngrid.get((gx, gy), ()):
                    d = math.hypot(nx_[j] - x, ny_[j] - y)
                    if d < best[1]: best = (j, d)
        if best[0] is not None and best[1] <= r: return best
        r *= 2
    return best

pickle.dump(dict(N=N, nx=nx_, ny=ny_, G=G, edges=[(kidx[a], kidx[b], L, k, [(float(vx[v]), float(vy[v])) for v in p]) for a, b, L, k, p in edges]),
            open(WORK + "graph.pkl", "wb"))

# ---------- write graph for the client ----------
def ll(x, y):
    lon, lat = unproj(x, y); return [round(lon * 1e5), round(lat * 1e5)]
KCODE = {"Trail": 0, "Local": 1, "Private": 1, "University": 1, "Link": 1, "Collector": 2, "Arterial": 3}
gnodes = []
for i in range(N): gnodes += ll(nx_[i], ny_[i])
gedges = []; ggeom = []
for a, b, L, k, p in edges:
    gedges += [kidx[a], kidx[b], round(L), KCODE.get(k, 1)]
    # simplify interior: drop vertices closer than 4 m to previous kept
    pts = [p[0]]
    for v in p[1:-1]:
        if math.hypot(vx[v] - vx[pts[-1]], vy[v] - vy[pts[-1]]) >= 6: pts.append(v)
    pts.append(p[-1])
    flat = []
    for v in pts[1:-1]: flat += ll(vx[v], vy[v])
    ggeom.append(flat)
json.dump({"nodes": gnodes, "edges": gedges, "geom": ggeom}, open(OUT + "graph.json", "w"), separators=(",", ":"))
print("graph.json", os.path.getsize(OUT + "graph.json") // 1024, "KB")
