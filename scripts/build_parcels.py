"""Join the parcel fabric, 2023 zoning, named Guelph areas and wards to every address,
and write data/area.json for the "About this area" description.

Per address (same order as data/addresses.json):
  lot   - area of the surface parcel the address sits on, m² (0 = none found)
  units - number of addresses sharing that parcel (apartments, plazas, townhouse blocks)
  near  - median area of the single-address residential lots within 150 m, m² (0 = too few)
  zone  - index into "zones" ([code, description, type]) or -1
  area  - index into "areas" (named Guelph area) or -1
  ward  - index into "wards" ([number, name]) or -1
"""
import json, glob, math, collections, statistics
SRC = "/mnt/user-data/uploads/City of Guelph Data/"
OUT = "/home/claude/15-minute-guelph/data/"
LAT0 = 43.54
KX = 111320 * math.cos(math.radians(LAT0)); KY = 110574
CELL = 200.0   # m, grid cell for the spatial index

A = json.load(open(OUT + "addresses.json"))
AX = [(x / 1e5 + 80.25) * KX for x in A["lon"]]; AY = [(y / 1e5 - LAT0) * KY for y in A["lat"]]
NA = len(AX)

def proj(ring): return [((p[0] + 80.25) * KX, (p[1] - LAT0) * KY) for p in ring]
def polys_of(geom):
    if not geom: return []
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"] if geom["type"] == "MultiPolygon" else []
def pip(x, y, ring):
    ins = False; n = len(ring); j = n - 1
    for i in range(n):
        x1, y1 = ring[i]; x2, y2 = ring[j]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: ins = not ins
        j = i
    return ins
def ring_area(r): return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2

class Layer:
    """Polygons in local metres with a grid index; contains(x, y) returns the feature index or -1."""
    def __init__(self, feats):
        self.items = []; self.grid = collections.defaultdict(list)
        for fi, f in enumerate(feats):
            for poly in polys_of(f["geometry"]):
                rings = [proj(r) for r in poly]; xs = [p[0] for p in rings[0]]; ys = [p[1] for p in rings[0]]
                k = len(self.items); self.items.append((fi, rings, min(xs), max(xs), min(ys), max(ys)))
                for gx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
                    for gy in range(int(min(ys) // CELL), int(max(ys) // CELL) + 1): self.grid[(gx, gy)].append(k)
    def contains(self, x, y):
        for k in self.grid.get((int(x // CELL), int(y // CELL)), ()):
            fi, rings, x0, x1, y0, y1 = self.items[k]
            if x0 <= x <= x1 and y0 <= y <= y1 and pip(x, y, rings[0]) and not any(pip(x, y, h) for h in rings[1:]): return fi
        return -1

def load(fn): return json.load(open(SRC + fn))["features"]

# ---- parcels (surface + condo only; roads, walkways, rail and lanes are not lots)
parcels = [f for fn in sorted(glob.glob(SRC + "_parcels/*.json")) for f in json.load(open(fn))["features"]
           if f["properties"].get("PARCELTYPE") in ("SURFACE PARCEL", "CONDO PARCEL")]
P = Layer(parcels)
parea = [sum(ring_area(proj(p[0])) - sum(ring_area(proj(h)) for h in p[1:]) for p in polys_of(f["geometry"])) for f in parcels]
pidx = [P.contains(AX[i], AY[i]) for i in range(NA)]
units = collections.Counter(p for p in pidx if p >= 0)

# ---- zoning
Z = load("Zoning_2023.geojson"); ZL = Layer(Z); zones, zkey = [], {}
def zone_of(i):
    fi = ZL.contains(AX[i], AY[i])
    if fi < 0: return -1
    pr = Z[fi]["properties"]; key = (pr.get("ZONING_CODE") or "", (pr.get("ZONING_CODE_DESC") or "").strip(), pr.get("Type_") or "")
    if key not in zkey: zkey[key] = len(zones); zones.append(list(key))
    return zkey[key]
zidx = [zone_of(i) for i in range(NA)]

# ---- named areas and wards
AR = load("Guelph_Areas.geojson"); ARL = Layer(AR)
W = load("Wards.geojson"); WL = Layer(W)
aidx = [ARL.contains(AX[i], AY[i]) for i in range(NA)]
widx = [WL.contains(AX[i], AY[i]) for i in range(NA)]

# ---- typical lot size nearby: single-address lots in residential zones within 150 m
lots = {}   # parcel -> (x, y, area) for single-address residential lots
for i in range(NA):
    p = pidx[i]
    if p >= 0 and units[p] == 1 and zidx[i] >= 0 and zones[zidx[i]][2] == "Residential" and 60 <= parea[p] <= 20000:
        lots[p] = (AX[i], AY[i], parea[p])
lg = collections.defaultdict(list)
for x, y, a in lots.values(): lg[(int(x // 150), int(y // 150))].append((x, y, a))
near = []
for i in range(NA):
    gx, gy = int(AX[i] // 150), int(AY[i] // 150); v = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for x, y, a in lg.get((gx + dx, gy + dy), ()):
                if (x - AX[i]) ** 2 + (y - AY[i]) ** 2 <= 22500: v.append(a)
    near.append(round(statistics.median(v)) if len(v) >= 5 else 0)

out = {
    "zones": zones,
    "areas": [f["properties"]["AREA_NAME"] for f in AR],
    "wards": [[f["properties"]["WARD"], f["properties"].get("NAME") or ""] for f in W],
    "lot": [round(parea[p]) if p >= 0 else 0 for p in pidx],
    "units": [units[p] if p >= 0 else 0 for p in pidx],
    "near": near, "zone": zidx, "area": aidx, "ward": widx,
    "city_lot_median": round(statistics.median(a for _, _, a in lots.values())),
}
json.dump(out, open(OUT + "area.json", "w"), separators=(",", ":"))
hit = lambda arr: sum(1 for v in arr if v not in (0, -1)) / NA
print(f"addresses {NA}: parcel {hit(out['lot']):.1%}, zone {hit([z+1 for z in zidx]):.1%}, area {hit([a+1 for a in aidx]):.1%}, ward {hit([w+1 for w in widx]):.1%}; "
      f"city median residential lot {out['city_lot_median']} m²; zones {len(zones)}")
