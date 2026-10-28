"""Snap places, addresses, trees and transit to the walk graph; compute the
15-minute score for every address; write compact JSON for the app."""
import json, math, heapq, collections, csv, os, pickle, datetime
import numpy as np

U = "/mnt/user-data/uploads/City of Guelph Data/"
T = U + "_testdata/"
GT = "/tmp/claude-0/gtfs/"
OUT = "/home/claude/guelph/app/data/"
WORK = "/home/claude/guelph/work/"

LAT0, LON0 = 43.54, -80.25
KX = 111320 * math.cos(math.radians(LAT0)); KY = 110574
def proj(lon, lat): return ((lon - LON0) * KX, (lat - LAT0) * KY)
E5 = lambda v: round(v * 1e5)
WALK = 80.0  # metres per minute (4.8 km/h)

g = pickle.load(open(WORK + "graph.pkl", "rb"))
N, NX, NY, G = g["N"], g["nx"], g["ny"], g["G"]
trail_nodes = sorted({e[0] for e in g["edges"] if e[3] == "Trail"} | {e[1] for e in g["edges"] if e[3] == "Trail"})

CELL = 40
ngrid = collections.defaultdict(list)
for i in range(N): ngrid[(int(NX[i] // CELL), int(NY[i] // CELL))].append(i)
def nearest_node(x, y):
    best = (None, 1e18); r = 1
    while True:
        cx, cy = int(x // CELL), int(y // CELL)
        for gx in range(cx - r, cx + r + 1):
            for gy in range(cy - r, cy + r + 1):
                for j in ngrid.get((gx, gy), ()):
                    d = math.hypot(NX[j] - x, NY[j] - y)
                    if d < best[1]: best = (j, d)
        if best[0] is not None and best[1] <= r * CELL: return best[0], best[1]
        r *= 2
        if r > 64: return best

def dijkstra(seeds, limit=1e18):
    dist = np.full(N, np.inf); pq = []
    for n, d in seeds:
        if d < dist[n]: dist[n] = d; heapq.heappush(pq, (d, n))
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u] or d > limit: continue
        for v, L in G[u]:
            nd = d + L
            if nd < dist[v]: dist[v] = nd; heapq.heappush(pq, (nd, v))
    return dist

def feats(name): return json.load(open(T + name))["features"]

# ---------------- places ----------------
def pt(f): return f["geometry"]["coordinates"][:2]
places = {}
def add_points(cat, items):
    out = []
    for name, addr, lon, lat, extra in items:
        n, d = nearest_node(*proj(lon, lat))
        out.append([name, addr, E5(lon), E5(lat), int(n), round(d), extra])
    places[cat] = out

tc = lambda s: " ".join(w.capitalize() if not w.isupper() or len(w) > 3 else w for w in (s or "").lower().split()) if s else ""
def title(s):
    if not s: return ""
    s = s.title()
    for a, b in [(" Cs", " CS"), (" Ps", " PS"), (" Ss", " SS"), (" Chs", " CHS"), (" Cvi", " CVI"), ("Ii", "II"), ("Mcc", "McC"), ("Mce", "McE"), ("Of ", "of "), ("And ", "and ")]:
        s = s.replace(a, b)
    return s

sch = []
for f in feats("schools.geojson"):
    p = f["properties"]
    if p["TYPE"] in ("ELEMENTARY", "MONTESSORI", "WALDORF", "SECONDARY", "POST SECONDARY"):
        sch.append((title(p["NAME"]), title(p["ADDRESS"]), *pt(f), [p["TYPE"].title(), p["BOARD"]]))
add_points("school", sch)
fac = []
for f in feats("facilities.geojson"):
    p = f["properties"]
    if p["CATEGORY"] in ("LIBRARY", "COMMUNITY CENTRE", "SENIORS CENTRE", "ARENA", "MUSEUM", "ARTS"):
        fac.append((title(p["NAME"]), title(p["ADDRESS"]), *pt(f), p["CATEGORY"].title()))
add_points("facility", fac)
add_points("restroom", [(title(f["properties"]["ParkName"]), "", *pt(f), "Permanent" if "PERMANENT" in f["properties"]["RestroomType"] else "Portable") for f in feats("restrooms.geojson")])
add_points("garden", [(title(f["properties"]["Name"]), title(f["properties"]["Address"]), *pt(f), title(f["properties"]["GardenType"])) for f in feats("gardens.geojson")])
aed_src = U + "live_samples/aeds.geojson"
if os.path.exists(aed_src):
    add_points("aed", [((f["properties"].get("Name") or "AED").strip(), title(f["properties"].get("Address2") or ""), *f["geometry"]["coordinates"][:2], (f["properties"].get("Placement") or "").strip()) for f in json.load(open(aed_src))["features"] if f.get("geometry") and -80.34 < f["geometry"]["coordinates"][0] < -80.14 and 43.46 < f["geometry"]["coordinates"][1] < 43.61])

# OpenStreetMap shops & services
osm = json.load(open(U + "OSM_Places.geojson"))["features"]
OSMCAT = {
    "grocery":   ({"shop=supermarket", "shop=grocery", "shop=greengrocer"}, "Grocery store"),
    "pharmacy":  ({"amenity=pharmacy", "shop=chemist"}, "Pharmacy"),
    "health":    ({"amenity=doctors", "amenity=clinic", "amenity=hospital", "healthcare=doctor", "healthcare=clinic", "healthcare=centre", "healthcare=hospital"}, "Doctor or clinic"),
    "food":      ({"amenity=cafe", "amenity=restaurant", "amenity=pub", "shop=bakery"}, "Café or restaurant"),
    "playground":({"leisure=playground"}, "Playground"),
}
for cat, (kinds, label) in OSMCAT.items():
    items = []
    for f in osm:
        q = f["properties"]
        if q["kind"] in kinds:
            nm = q["name"] or q["brand"] or label
            items.append((nm, q["address"], *f["geometry"]["coordinates"][:2], q["kind"].split("=")[1].replace("_", " ").title()))
    add_points(cat, items); print(cat, len(items))

# parks: polygons + access nodes
def pip(x, y, ring):
    ins = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: ins = not ins
    return ins
def segd(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)
parks = []
for f in feats("parks.geojson"):
    p = f["properties"]; geom = f["geometry"]
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    rings_ll = []; access = set(); area = 0
    for poly in polys:
        ring = [proj(*c[:2]) for c in poly[0]]
        a = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))); area += a
        xs = [q[0] for q in ring]; ys = [q[1] for q in ring]
        for gx in range(int((min(xs) - 30) // CELL), int((max(xs) + 30) // CELL) + 1):
            for gy in range(int((min(ys) - 30) // CELL), int((max(ys) + 30) // CELL) + 1):
                for j in ngrid.get((gx, gy), ()):
                    x, y = NX[j], NY[j]
                    if pip(x, y, ring) or min(segd(x, y, *a_, *b_) for a_, b_ in zip(ring, ring[1:])) <= 30:
                        access.add(j)
        # simplified ring for drawing (drop points < 4 m apart)
        r2 = [poly[0][0]]
        for c in poly[0][1:]:
            if math.hypot(*(np.subtract(proj(*c[:2]), proj(*r2[-1][:2])))) >= 4: r2.append(c)
        flat = []
        for c in r2: flat += [E5(c[0]), E5(c[1])]
        rings_ll.append(flat)
    if not access:
        best = min(((nearest_node(*proj(*c[:2])), c) for poly in polys for c in poly[0][::5]), key=lambda t: t[0][1])
        access = {best[0][0]}
    parks.append([p.get("Name") or title(p.get("ParkName")), p.get("Address") or "", round(area), sorted(int(a) for a in access), rings_ll])
print("parks", len(parks), "with access", sum(1 for p in parks if p[3]))

# ---------------- trees ----------------
trees_raw = feats.__globals__["json"].load(open(U + "Trees.geojson"))["features"]
sp_names = []; sp_idx = {}
tlon = []; tlat = []; tsp = []; tdbh = []; txy = []
for f in trees_raw:
    p = f["properties"]; lon, lat = f["geometry"]["coordinates"][:2]
    s = (p.get("SPECIES_COMMON") or "UNKNOWN").strip()
    if s not in sp_idx: sp_idx[s] = len(sp_names); sp_names.append(s)
    tlon.append(E5(lon)); tlat.append(E5(lat)); tsp.append(sp_idx[s]); tdbh.append(int(p.get("DBH") or 0)); txy.append(proj(lon, lat))
txy = np.array(txy)
tgrid = collections.defaultdict(list)
for i, (x, y) in enumerate(txy): tgrid[(int(x // 100), int(y // 100))].append(i)
def trees_within(x, y, r=100):
    out = []
    cx, cy = int(x // 100), int(y // 100)
    for gx in range(cx - 1, cx + 2):
        for gy in range(cy - 1, cy + 2):
            for j in tgrid.get((gx, gy), ()):
                if (txy[j, 0] - x) ** 2 + (txy[j, 1] - y) ** 2 <= r * r: out.append(j)
    return out
json.dump({"species": [title(s) for s in sp_names], "lon": tlon, "lat": tlat, "sp": tsp, "dbh": tdbh},
          open(OUT + "trees.json", "w"), separators=(",", ":"))
print("trees", len(tlon))

# ---------------- transit ----------------
def tsec(s):
    h, m, x = s.strip().split(":"); return int(h) * 3600 + int(m) * 60 + int(x)
cal = {r["service_id"]: r for r in csv.DictReader(open(GT + "calendar.txt"))}
cdates = collections.defaultdict(list)
for r in csv.DictReader(open(GT + "calendar_dates.txt")): cdates[r["date"]].append((r["service_id"], r["exception_type"]))
DAYS = {"weekday": "20261028", "saturday": "20261031", "sunday": "20261101"}
def active(date):
    dt = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][dt.weekday()]
    s = {sid for sid, r in cal.items() if r[wd] == "1" and r["start_date"] <= date <= r["end_date"]}
    for sid, ex in cdates.get(date, []):
        if ex == "1": s.add(sid)
        else: s.discard(sid)
    return s

routes = list(csv.DictReader(open(GT + "routes.txt")))
def rkey(r):
    n = r["route_short_name"]; num = int("".join(c for c in n if c.isdigit()) or 999)
    return (num, n)
routes.sort(key=rkey)
ridx = {r["route_id"]: i for i, r in enumerate(routes)}
stops = list(csv.DictReader(open(GT + "stops.txt")))
sidx = {s["stop_id"]: i for i, s in enumerate(stops)}
stop_out = []; stop_xy = []
for s in stops:
    lon, lat = float(s["stop_lon"]), float(s["stop_lat"]); x, y = proj(lon, lat)
    n, d = nearest_node(x, y); stop_xy.append((x, y))
    stop_out.append([s["stop_code"], s["stop_name"].strip(), E5(lon), E5(lat), int(n), round(d), s["stop_id"]])
trips = {t["trip_id"]: t for t in csv.DictReader(open(GT + "trips.txt"))}
st_by_trip = collections.defaultdict(list)
for r in csv.DictReader(open(GT + "stop_times.txt")):
    st_by_trip[r["trip_id"]].append((int(r["stop_sequence"]), sidx[r["stop_id"]], tsec(r["arrival_time"]), tsec(r["departure_time"])))

transit = {"days": {}, "routes": [[r["route_short_name"], r["route_long_name"], "#" + (r["route_color"] or "555555"), r["route_id"], "#" + (r.get("route_text_color") or "FFFFFF")] for r in routes],
           "stops": stop_out, "dates": DAYS}
midday_trips_at_stop = collections.defaultdict(set)
for day, date in DAYS.items():
    act = active(date)
    tlist = [tid for tid, t in trips.items() if t["service_id"] in act and tid in st_by_trip]
    tinfo = []; conns = []
    for ti, tid in enumerate(tlist):
        t = trips[tid]; seq = sorted(st_by_trip[tid])
        tinfo += [ridx[t["route_id"]]]
        for (s1, a, ar1, dp1), (s2, b, ar2, dp2) in zip(seq, seq[1:]):
            conns.append((dp1, ar2, a, b, ti))
        if day == "weekday":
            for _, s, ar, dp in seq[:-1]:
                if 10 * 3600 <= dp < 15 * 3600: midday_trips_at_stop[s].add(ti)
    conns.sort()
    heads = [trips[tid]["trip_headsign"].strip() for tid in tlist]
    hnames = sorted(set(heads)); hidx = {h: i for i, h in enumerate(hnames)}
    flat = []
    for dp, ar, a, b, ti in conns: flat += [dp, ar, a, b, ti]
    transit["days"][day] = {"trips": tinfo, "ids": tlist, "shape": [trips[tid]["shape_id"] for tid in tlist], "head": [hidx[h] for h in heads], "headsigns": hnames, "conns": flat}
    print(day, date, "services", sorted(act), "trips", len(tlist), "connections", len(conns))

# footpaths between stops (<= 250 m straight line, network-ish factor 1.25)
foot = []
SX = np.array(stop_xy)
for i in range(len(SX)):
    d = np.hypot(SX[:, 0] - SX[i, 0], SX[:, 1] - SX[i, 1])
    for j in np.where((d <= 250) & (d > 0))[0]:
        foot += [i, int(j), round(d[j] * 1.25 / WALK * 60)]
transit["foot"] = foot

# route shapes (most used shape per route+direction)
shape_use = collections.Counter((t["route_id"], t["direction_id"], t["shape_id"]) for t in trips.values())
best_shape = {}
for (rid, dr, sh), n in shape_use.items():
    if (rid, dr) not in best_shape or n > shape_use[(rid, dr, best_shape[(rid, dr)])]: best_shape[(rid, dr)] = sh
shp = collections.defaultdict(list)
for r in csv.DictReader(open(GT + "shapes.txt")): shp[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
rshapes = []
for (rid, dr), sh in best_shape.items():
    pts = [p[1:] for p in sorted(shp[sh])]
    keep = [pts[0]]
    for p in pts[1:]:
        if math.hypot(*np.subtract(proj(*p), proj(*keep[-1]))) >= 12: keep.append(p)
    flat = []
    for lon, lat in keep: flat += [E5(lon), E5(lat)]
    rshapes.append([ridx[rid], flat])
transit["shapes"] = rshapes
# every trip path, for gliding live buses along their route (thinned to ~8 m)
used = sorted({sid for d in transit["days"].values() for sid in d["shape"]})
sidx_ = {sid: i for i, sid in enumerate(used)}
tsh = []
for sid in used:
    pts = [p[1:] for p in sorted(shp[sid])]
    keep = [pts[0]]
    for p in pts[1:-1]:
        if math.hypot(*np.subtract(proj(*p), proj(*keep[-1]))) >= 8: keep.append(p)
    keep.append(pts[-1])
    flat = []
    for lon, lat in keep: flat += [E5(lon), E5(lat)]
    tsh.append(flat)
for d in transit["days"].values(): d["shape"] = [sidx_[x] for x in d["shape"]]
transit["tshapes"] = tsh
print("trip shapes", len(tsh), "points", sum(len(f) // 2 for f in tsh))
json.dump(transit, open(OUT + "transit.json", "w"), separators=(",", ":"))
print("transit.json", os.path.getsize(OUT + "transit.json") // 1024, "KB")

# ---------------- category distance fields ----------------
def field_points(cat, filt=lambda r: True):
    return dijkstra([(r[4], r[5]) for r in places[cat] if filt(r)])
fields = {
    "park": dijkstra([(a, 0.0) for p in parks for a in p[3]]),
    "school": field_points("school", lambda r: r[6][0] in ("Elementary", "Montessori", "Waldorf")),
    "community": field_points("facility", lambda r: r[6] in ("Library", "Community Centre", "Seniors Centre")),
    "trail": dijkstra([(n, 0.0) for n in trail_nodes]),
    "garden": field_points("garden"),
    "restroom": field_points("restroom"),
    **{c: field_points(c) for c in OSMCAT},
}
# stop -> nodes within 400 m
stop_reach = []
for si, s in enumerate(stop_out):
    if s[5] > 400: stop_reach.append(None); continue
    stop_reach.append(dijkstra([(s[4], s[5])], limit=400))

# ---------------- addresses + scores ----------------
def lin(t, full, zero): return 1.0 if t <= full else 0.0 if t >= zero else (zero - t) / (zero - full)
W = {"grocery": (15, 10, 25), "park": (12, 5, 15), "school": (10, 10, 20), "pharmacy": (8, 10, 25), "health": (8, 15, 30), "community": (8, 15, 30),
     "food": (5, 5, 15), "trail": (5, 5, 15), "playground": (4, 5, 15), "garden": (1, 10, 20), "restroom": (1, 10, 20)}  # + bus 20 + trees 3 = 100
addrs = json.load(open(U + "Addresses.geojson"))["features"]
A = {"text": [], "lon": [], "lat": [], "node": [], "conn": [], "score": []}
# trips within 400 m of each node -> computed lazily per address via stop_reach
stop_dist_arr = np.array([sr if sr is not None else np.full(N, np.inf) for sr in stop_reach])  # (stops, N)
scores = []; parts_dbg = []
for f in addrs:
    p = f["properties"]; lon, lat = f["geometry"]["coordinates"][:2]
    x, y = proj(lon, lat); n, c = nearest_node(x, y)
    sc = 0; parts = {}
    for k, (w, full, zero) in W.items():
        t = (fields[k][n] + c) / WALK; v = w * lin(t, full, zero); parts[k] = round(t, 1); sc += v
    near_stops = np.where(stop_dist_arr[:, n] + c <= 400)[0]
    tr = set()
    for s in near_stops: tr |= midday_trips_at_stop[s]
    tph = len(tr) / 5.0; sc += 20 * min(1, tph / 8); parts["tph"] = tph
    nt = len(trees_within(x, y)); sc += 3 * min(1, nt / 30); parts["trees"] = nt
    A["text"].append(p["ADDRESS"]); A["lon"].append(E5(lon)); A["lat"].append(E5(lat)); A["node"].append(int(n)); A["conn"].append(round(c)); A["score"].append(round(sc))
    parts_dbg.append(parts)
json.dump(A, open(OUT + "addresses.json", "w"), separators=(",", ":"))
json.dump({"parks": parks, **places}, open(OUT + "places.json", "w"), separators=(",", ":"))
pickle.dump(parts_dbg, open(WORK + "parts.pkl", "wb"))
s = np.array(A["score"])
print("addresses", len(s), "score pctiles", np.percentile(s, [5, 25, 50, 75, 95]))
for k in ["park", "school", "community", "trail"]:
    print(k, np.percentile([q[k] for q in parts_dbg], [10, 50, 90]))
print("tph", np.percentile([q["tph"] for q in parts_dbg], [10, 50, 90]), "trees", np.percentile([q["trees"] for q in parts_dbg], [10, 50, 90]))
for fn in os.listdir(OUT): print(fn, os.path.getsize(OUT + fn) // 1024, "KB")
