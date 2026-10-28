"""Basemap layers: buildings, watercourses and named street lines (for labels)."""
import json, math, os
U = "/mnt/user-data/uploads/City of Guelph Data/"
OUT = "/home/claude/guelph/app/data/"
LAT0 = 43.54
KX = 111320 * math.cos(math.radians(LAT0)); KY = 110574
E5 = lambda v: round(v * 1e5)

def thin(ring, tol_m):
    """drop vertices closer than tol to the last kept one; returns int lon/lat pairs, delta-encoded"""
    out = [ring[0]]
    for p in ring[1:]:
        q = out[-1]
        if math.hypot((p[0] - q[0]) * KX, (p[1] - q[1]) * KY) >= tol_m: out.append(p)
    pts = [(E5(p[0]), E5(p[1])) for p in out]
    flat = []; px = py = 0
    for x, y in pts: flat += [x - px, y - py]; px, py = x, y
    return flat, len(pts)

def polys(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]

# buildings: outer ring only, 1.2 m thinning, drop slivers < 12 m2
b = json.load(open(U + "Buildings.geojson"))["features"]
bl = []
for f in b:
    if not f["geometry"]: continue
    if (f["properties"].get("Shape__Area") or 99) < 12: continue
    for poly in polys(f["geometry"]):
        flat, n = thin(poly[0], 1.2)
        if n >= 3: bl.append(flat)
json.dump(bl, open(OUT + "buildings.json", "w"), separators=(",", ":"))

# water polygons with holes
w = json.load(open(U + "Watercourse_Polygons.geojson"))["features"]
wl = []
for f in w:
    for poly in polys(f["geometry"]):
        rings = [thin(r, 2)[0] for r in poly]
        wl.append([f["properties"].get("COMMON_NAME") or "", round(f["properties"].get("Shape__Area") or 0), rings])
json.dump(wl, open(OUT + "water.json", "w"), separators=(",", ":"))

# street names: short form ("Cork St W"), thinned geometry
SUF = {"STREET": "St", "ROAD": "Rd", "DRIVE": "Dr", "AVENUE": "Ave", "CRESCENT": "Cres", "COURT": "Crt", "PLACE": "Pl", "LANE": "Lane", "BOULEVARD": "Blvd", "PARKWAY": "Pkwy", "WAY": "Way", "CIRCLE": "Cir", "TRAIL": "Trail", "EXPRESSWAY": "Expy"}
def short(p):
    nm = (p.get("STREETNAME") or "").strip()
    if not nm: return ""
    words = nm.split()
    out = []
    for i, wd in enumerate(words):
        if wd in ("N", "S", "E", "W") and i == len(words) - 1: out.append(wd)
        elif wd in ("ST", "RD", "DR", "AVE", "CRES", "CRT", "PL", "BLVD", "PKWY", "CIR", "CT"):
            out.append({"ST": "St", "RD": "Rd", "DR": "Dr", "AVE": "Ave", "CRES": "Cres", "CRT": "Crt", "CT": "Crt", "PL": "Pl", "BLVD": "Blvd", "PKWY": "Pkwy", "CIR": "Cir"}[wd])
        else:
            t = wd.capitalize()
            if t.startswith("Mc") and len(t) > 2: t = "Mc" + t[2:].capitalize()
            out.append(t)
    return " ".join(out)
s = json.load(open(U + "StreetCentrelines.geojson"))["features"]
names = []; nidx = {}; sl = []
CLS = {"Arterial": 3, "Collector": 2, "Expressway": 3}
for f in s:
    p = f["properties"]; nm = short(p)
    if not nm or p.get("ROADCLASS") == "Ramp": continue
    if nm not in nidx: nidx[nm] = len(names); names.append(nm)
    flat, n = thin([c[:2] for c in f["geometry"]["coordinates"]], 3)
    if n >= 2: sl.append([nidx[nm], CLS.get(p.get("ROADCLASS"), 1), flat])
hwy = []
for f in s:
    if f["properties"].get("ROADCLASS") in ("Expressway", "Ramp"):
        flat, n = thin([c[:2] for c in f["geometry"]["coordinates"]], 3)
        if n >= 2: hwy.append([1 if f["properties"]["ROADCLASS"] == "Ramp" else 0, flat])
json.dump({"names": names, "segs": sl, "hwy": hwy}, open(OUT + "streetnames.json", "w"), separators=(",", ":"))
print("expressway/ramp segments", len(hwy))
for fn in ["buildings.json", "water.json", "streetnames.json"]:
    print(fn, os.path.getsize(OUT + fn) // 1024, "KB")
print("buildings", len(bl), "water", len(wl), [x[0] for x in wl][:12], "streets", len(sl), names[:8])
