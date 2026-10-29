"""Extra City layers for the report card and the area profile; writes data/extra.json.

Places (same row format as places.json: [name, address, lon*1e5, lat*1e5, node, conn, extra]):
  childcare - licensed child care centres (extra: ages served)
  healthcity - City list of family health teams, walk-in clinics, community health centres, hospitals
  program   - free community programs (name = program, address = location, extra = "day/time · audience")
  sport     - sports fields and park courts, one point per field/court (extra: type)

Per address (same order as data/addresses.json):
  sw    - sidewalk coverage within 150 m, % (sidewalk length / both sides of public streets)
  bike  - metres of in-service bike lanes, cycle tracks and multi-use paths within 400 m
  bnear - straight-line metres to the nearest of those (capped at 5000)
  bref  - index into "bikes" ([type, street]) for that nearest facility, or -1
  ix    - street intersections within 400 m
  pond  - stormwater ponds/greenways/wetlands within 400 m
"""
import json, math, collections, re
import numpy as np
from scipy.spatial import cKDTree
SRC = "/mnt/user-data/uploads/City of Guelph Data/"
OUT = "/home/claude/15-minute-guelph/data/"
LAT0, LON0 = 43.54, -80.25
KX = 111320 * math.cos(math.radians(LAT0)); KY = 110574
proj = lambda lon, lat: ((lon - LON0) * KX, (lat - LAT0) * KY)
E5 = lambda v: round(v * 1e5)
feats = lambda fn: json.load(open(SRC + fn))["features"]

# ---- walk graph nodes for snapping (graph.json nodes are lon/lat * 1e5 pairs)
g = json.load(open(OUT + "graph.json"))["nodes"]
NXY = np.array([proj(g[k] / 1e5, g[k + 1] / 1e5) for k in range(0, len(g), 2)])
NT = cKDTree(NXY)
def snap(lon, lat):
    d, n = NT.query(proj(lon, lat)); return int(n), round(float(d))

def title(s):
    if not s or s == "None": return ""
    keep = lambda w: re.fullmatch(r"(?:[A-Z]\.)+|[NSEW]|II|III|IV|CS|PS|SS|CHS|CVI|YMCA|YWCA|\d+\w*", w)
    s = " ".join(w if keep(w) else re.sub(r"(^|[-/(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w.lower()) for w in str(s).split())
    for a, b in [(" Of ", " of "), (" And ", " and "), (" The ", " the "), ("Mcc", "McC"), (" Jr. ", " Jr. "), (" Sr. ", " Sr. ")]: s = s.replace(a, b)
    return s
def clean(s): return "" if s in (None, "None", " ") else str(s).strip()
def centroid(geom):
    ring = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]; return sum(xs) / len(xs), sum(ys) / len(ys)

out = {}
def place_rows(items, maxconn=250):
    rows = []
    for name, addr, lon, lat, extra in items:
        n, d = snap(lon, lat)
        if d <= maxconn: rows.append([name, addr, E5(lon), E5(lat), n, d, extra])   # drops places outside Guelph
    return rows

out["childcare"] = place_rows([(clean(f["properties"]["Name_of_th"]), title(clean(f["properties"]["Address"])), *f["geometry"]["coordinates"][:2],
                                clean(f["properties"].get("Age"))) for f in feats("Child_Care.geojson") if f["geometry"]])
KEEP = ("Family Health Team", "Walk in Clinic", "Community Health Centre", "Hospital")
out["healthcity"] = place_rows([(clean(f["properties"]["Name_of_th"]), title(clean(f["properties"]["Address"])), *f["geometry"]["coordinates"][:2],
                                 clean(f["properties"]["Types_of_C"])) for f in feats("Health_Services.geojson")
                                if f["geometry"] and any(k.lower() in clean(f["properties"]["Types_of_C"]).lower() for k in KEEP)])
out["program"] = place_rows([(clean(f["properties"]["Program_Na"]), clean(f["properties"]["Location_N"]), *f["geometry"]["coordinates"][:2],
                              " · ".join(x for x in (clean(f["properties"]["Day___Time"]), clean(f["properties"]["category"])) if x))
                             for f in feats("Program_Locations.geojson") if f["geometry"]])
sport = []
for fn, nk in (("Sports_Fields.geojson", "FieldName"), ("Park_Courts.geojson", "CourtName")):
    for f in feats(fn):
        p = f["properties"]
        if not f["geometry"] or clean(p.get("Status")) not in ("", "IN-USE"): continue
        lon, lat = centroid(f["geometry"]); typ = title(clean(p.get("Type")))
        if nk == "CourtName" and typ and "court" not in typ.lower(): typ += " court"
        sport.append((title(clean(p.get(nk))), "", lon, lat, typ))
out["sport"] = place_rows(sport)

# ---- per-address context
A = json.load(open(OUT + "addresses.json"))
AXY = np.array([proj(x / 1e5, y / 1e5) for x, y in zip(A["lon"], A["lat"])]); NA = len(AXY)

def pieces(lines, step=10.0):
    """Cut lines into ~10 m pieces: (midpoint xy array, length array, source index array)."""
    mids, lens, src = [], [], []
    for li, coords in enumerate(lines):
        pts = [proj(*c[:2]) for c in coords]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            L = math.hypot(x2 - x1, y2 - y1); k = max(1, int(L // step))
            for j in range(k):
                t = (j + .5) / k; mids.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)); lens.append(L / k); src.append(li)
    return np.array(mids), np.array(lens), np.array(src)
def lines_of(f):
    g = f["geometry"]
    if not g: return []
    return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
def length_within(lines, r):
    M, L, _ = pieces(lines); T = cKDTree(M)
    return np.array([L[ix].sum() if ix else 0.0 for ix in T.query_ball_point(AXY, r)])

side = [c for f in feats("Sidewalks.geojson") if clean(f["properties"].get("STATUS")) == "BUILT" for c in lines_of(f)]
street = [c for f in feats("StreetCentrelines.geojson")
          if clean(f["properties"].get("STATUS")) == "Active" and clean(f["properties"].get("ROADCLASS")) in ("Local", "Collector", "Arterial")
          and clean(f["properties"].get("OWNEDBY")) in ("City of Guelph", "") for c in lines_of(f)]
sw_len, st_len = length_within(side, 150), length_within(street, 150)
out["sw"] = [int(min(100, round(100 * s / (2 * t)))) if t > 50 else -1 for s, t in zip(sw_len, st_len)]

BIKE_OK = ("Bike Lane", "Cycle Track", "MUP", "Bike Lane - Green")
bk = [f for f in feats("Bike_Facilities.geojson") if clean(f["properties"].get("STATUS")) == "In Service" and clean(f["properties"].get("FACILITYTYPE")) in BIKE_OK]
blines, bsrc = [], []
for i, f in enumerate(bk):
    for c in lines_of(f): blines.append(c); bsrc.append(i)
M, L, S = pieces(blines); T = cKDTree(M)
out["bike"] = [int(round(L[ix].sum())) if ix else 0 for ix in T.query_ball_point(AXY, 400)]
d, k = T.query(AXY, distance_upper_bound=5000)
bikes, bkey = [], {}
def bref(j):
    if not np.isfinite(d[j]): return -1
    f = bk[bsrc[S[k[j]]]]["properties"]; key = ({"MUP": "multi-use path", "Cycle Track": "cycle track"}.get(f["FACILITYTYPE"], "bike lane"), title(clean(f.get("STREETNAME"))))
    if key not in bkey: bkey[key] = len(bikes); bikes.append(list(key))
    return bkey[key]
out["bref"] = [bref(j) for j in range(NA)]; out["bikes"] = bikes
out["bnear"] = [int(min(5000, round(float(x)))) if np.isfinite(x) else 5000 for x in d]

ixp = np.array([proj(*f["geometry"]["coordinates"][:2]) for f in feats("Street_Intersections.geojson") if f["geometry"] and clean(f["properties"].get("STATUS")) in ("In Service", "")])
out["ix"] = [len(x) for x in cKDTree(ixp).query_ball_point(AXY, 400)]
pp = np.array([proj(*centroid(f["geometry"])) for f in feats("Stormwater_Management_Pond.geojson") if f["geometry"]])
out["pond"] = [len(x) for x in cKDTree(pp).query_ball_point(AXY, 400)]

json.dump(out, open(OUT + "extra.json", "w"), separators=(",", ":"))
med = lambda a: sorted(a)[len(a) // 2]
print({k: len(out[k]) for k in ("childcare", "healthcity", "program", "sport")},
      "| median sw", med([v for v in out["sw"] if v >= 0]), "bike", med(out["bike"]), "ix", med(out["ix"]), "pond", med(out["pond"]))
