"""Join 2021 Census DA profile to DA polygons, attach mean 15-minute score of the
addresses inside each DA, and write data/census.json for the Neighbourhoods view."""
import json, csv, collections, math, os
C = "/mnt/user-data/uploads/City of Guelph Data/Census 2021/"
OUT = "/home/claude/guelph/app/data/"
E5 = lambda v: round(v * 1e5)

vals = collections.defaultdict(dict)
for r in csv.DictReader(open(C + "Guelph_DA_census_extract.csv", encoding="utf-8")):
    v = r["C1_COUNT_TOTAL"].strip()
    vals[r["DAUID"]][r["CHARACTERISTIC_ID"]] = float(v) if v not in ("", "x", "..", "...", "F") else None

A = json.load(open(OUT + "addresses.json"))
alon = [x / 1e5 for x in A["lon"]]; alat = [y / 1e5 for y in A["lat"]]

def pip(x, y, ring):
    ins = False; n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: ins = not ins
    return ins

g = json.load(open(C + "Guelph_DA_2021.geojson"))["features"]
out = []
pct = lambda a, b: None if a is None or not b else round(100 * a / b, 1)
for f in g:
    da = f["properties"]["DAUID"]; v = vals.get(da, {})
    geom = f["geometry"]; polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    scores = []
    for poly in polys:
        ring = poly[0]; xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        for i in range(len(alon)):
            if x0 <= alon[i] <= x1 and y0 <= alat[i] <= y1 and pip(alon[i], alat[i], ring) and not any(pip(alon[i], alat[i], h) for h in poly[1:]):
                scores.append(A["score"][i])
    if len(scores) < 5: continue          # area mostly outside the city's address points
    g_ = lambda k: v.get(k)
    rings = []
    for poly in polys:
        flat = []
        for lon, lat in poly[0]: flat += [E5(lon), E5(lat)]
        rings.append(flat)
    out.append({
        "da": da, "rings": rings, "n": len(scores), "score": round(sum(scores) / len(scores), 1),
        "pop": g_("1"), "density": g_("6"), "age": g_("39"),
        "kids": pct(g_("9"), g_("8")), "seniors": pct(g_("24"), g_("8")),
        "pop_kids": g_("9"), "pop_seniors": g_("24"),
        "income": g_("243"), "lowinc": g_("345"),
        "renters": pct(g_("1416"), g_("1414")), "hh": g_("50"), "renter_hh": g_("1416"),
        "towers": pct(g_("47"), g_("41")),
        "car": pct(g_("2604"), g_("2603")), "transit": pct(g_("2607"), g_("2603")),
        "active": pct((g_("2608") or 0) + (g_("2609") or 0), g_("2603")) if g_("2603") else None,
        "commuters": g_("2603"), "transit_n": g_("2607"),
    })
json.dump(out, open(OUT + "census.json", "w"), separators=(",", ":"))
pop = sum(d["pop"] or 0 for d in out)
print("DAs kept", len(out), "of", len(g), "population", pop, os.path.getsize(OUT + "census.json") // 1024, "KB")
# quick equity readout
def wavg(wkey):
    num = den = 0
    for d in out:
        w = d[wkey] if not callable(wkey) else wkey(d)
        if w: num += w * d["score"]; den += w
    return round(num / den, 1)
print("all residents", wavg("pop"), "kids", wavg("pop_kids"), "seniors", wavg("pop_seniors"),
      "low-income", wavg(lambda d: (d["pop"] or 0) * (d["lowinc"] or 0) / 100), "renter hh", wavg("renter_hh"), "transit commuters", wavg("transit_n"))
inc = sorted([d for d in out if d["income"]], key=lambda d: d["income"]); q = len(inc) // 5
print("lowest-income fifth avg score", round(sum(d["score"] for d in inc[:q]) / q, 1), "highest fifth", round(sum(d["score"] for d in inc[-q:]) / q, 1))
