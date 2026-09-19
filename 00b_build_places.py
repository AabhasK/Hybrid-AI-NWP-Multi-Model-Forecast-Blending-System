"""
Step 0b - The searchable gazetteer.

Builds the index behind the dashboard's search box: every Indian state and
district, with what each needs to be found and flown to.

WHAT IS STORED, AND WHY IT DIFFERS BY LEVEL
-------------------------------------------
States keep a simplified outline, because a state spans many analysis cells,
so selecting one can genuinely filter the grid and is worth drawing.

Districts keep only a centroid and a bounding box. At the 1 deg analysis grid
a district is usually SMALLER than a single cell, so "filter the cells inside
this district" would be a meaningless operation dressed up as a feature.
Searching a district therefore zooms the map and pins the cell containing it,
which is the honest thing the data can support - and it keeps ~750 district
polygons out of a file that has to stay openable by double-click.

Output: data/places.json
"""

import json
import urllib.request
from pathlib import Path

from importlib import import_module

_region = import_module("00_build_region") if False else None  # see below

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

STATE_SRC = "https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson"
DIST_SRC = "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson"

STATE_RAW = DATA / "_india_states.geojson"
DIST_RAW = DATA / "_india_districts.geojson"

STATE_TOL = 0.035          # degrees; states only need to read at national zoom
MIN_RING_AREA = 0.01

# The public boundary files are 2011-census vintage, so they carry names that
# have since changed and predate Telangana (2014) and Ladakh (2019). Display
# the current name, and keep the old one as a search alias so both work.
RENAME = {
    "Orissa": "Odisha", "Uttaranchal": "Uttarakhand", "Pondicherry": "Puducherry",
    "Bangalore": "Bengaluru", "Bangalore Rural": "Bengaluru Rural",
    "Mysore": "Mysuru", "Belgaum": "Belagavi", "Gulbarga": "Kalaburagi",
    "Bellary": "Ballari", "Tumkur": "Tumakuru", "Shimoga": "Shivamogga",
    "Bijapur": "Vijayapura", "Chikmagalur": "Chikkamagaluru",
    "Aurangabad": "Chhatrapati Sambhajinagar", "Osmanabad": "Dharashiv",
    "Allahabad": "Prayagraj", "Faizabad": "Ayodhya", "Gurgaon": "Gurugram",
    "Hoshangabad": "Narmadapuram", "Calcutta": "Kolkata", "Madras": "Chennai",
    "Bombay": "Mumbai", "Baroda": "Vadodara", "Poona": "Pune",
}

# States created after these files were published. No outline is available, so
# they carry a bounding box only - enough to search and fly to, and flagged so
# nothing pretends to a boundary it does not have.
LATER_STATES = [
    {"n": "Telangana", "k": "state", "approx": True,
     "b": [77.20, 15.80, 81.80, 19.95], "c": [79.40, 17.90]},
    {"n": "Ladakh", "k": "state", "approx": True,
     "b": [75.80, 32.20, 80.35, 36.05], "c": [77.60, 34.20]},
]

# geohacker's files use varying property spellings between releases
STATE_KEYS = ["NAME_1", "ST_NM", "STATE", "st_nm", "name"]
DIST_KEYS = ["NAME_2", "DISTRICT", "district", "dtname", "name"]


def perp(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def simplify(pts, tol):
    """Iterative Douglas-Peucker; recursion overflows on these rings."""
    if len(pts) < 3:
        return pts[:]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        worst, wi = -1.0, -1
        for i in range(lo + 1, hi):
            d = perp(pts[i], pts[lo], pts[hi])
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep[wi] = True
            stack.append((lo, wi))
            stack.append((wi, hi))
    return [p for p, k in zip(pts, keep) if k]


def ring_area(r):
    s = 0.0
    for i in range(len(r) - 1):
        s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
    return abs(s) / 2.0


def download(url, path, label):
    if not path.exists():
        print("downloading %s ..." % label)
        urllib.request.urlretrieve(url, path)
    return json.loads(path.read_text(encoding="utf-8"))


def prop(props, keys):
    for k in keys:
        if props.get(k):
            return str(props[k]).strip()
    return None


def polys_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    return []


def bbox_of(polys):
    xs, ys = [], []
    for rings in polys:
        for x, y in rings[0]:
            xs.append(x)
            ys.append(y)
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]


def centroid_of(polys):
    """Area-weighted centroid of the largest ring - good enough to fly to."""
    best, best_a = None, -1.0
    for rings in polys:
        a = ring_area(rings[0])
        if a > best_a:
            best, best_a = rings[0], a
    xs = [p[0] for p in best]
    ys = [p[1] for p in best]
    return [round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4)]


def main():
    places = []

    # ---- states: keep a simplified outline ------------------------------
    sg = download(STATE_SRC, STATE_RAW, "state boundaries (~23 MB, once)")
    kept = 0
    for feat in sg.get("features", []):
        name = prop(feat.get("properties", {}), STATE_KEYS)
        if not name:
            continue
        polys = polys_of(feat.get("geometry") or {})
        if not polys:
            continue
        out = []
        for rings in polys:
            if ring_area(rings[0]) < MIN_RING_AREA:
                continue
            r = simplify([(float(a), float(b)) for a, b in rings[0]], STATE_TOL)
            if len(r) >= 4:
                if r[0] != r[-1]:
                    r.append(r[0])
                out.append([[round(x, 3), round(y, 3)] for x, y in r])
        if not out:
            continue
        current = RENAME.get(name, name)
        rec = {"n": current, "k": "state", "b": bbox_of(polys),
               "c": centroid_of(polys), "r": out}
        if current != name:
            rec["a"] = [name]          # searchable under the old name too
        places.append(rec)
        kept += 1
    print("  states: %d" % kept)

    # ---- districts: centroid + bbox only --------------------------------
    dg = download(DIST_SRC, DIST_RAW, "district boundaries (~34 MB, once)")
    seen = set()
    dn = 0
    for feat in dg.get("features", []):
        props = feat.get("properties", {})
        name = prop(props, DIST_KEYS)
        state = prop(props, STATE_KEYS) or ""
        if not name:
            continue
        key = (name.lower(), state.lower())
        if key in seen:
            continue
        seen.add(key)
        polys = polys_of(feat.get("geometry") or {})
        if not polys:
            continue
        current = RENAME.get(name, name)
        rec = {"n": current, "k": "district", "s": RENAME.get(state, state),
               "b": bbox_of(polys), "c": centroid_of(polys)}
        if current != name:
            rec["a"] = [name]
        places.append(rec)
        dn += 1
    print("  districts: %d" % dn)

    places.extend(LATER_STATES)
    print("  post-2011 states added without outlines: %s"
          % ", ".join(x["n"] for x in LATER_STATES))

    out = DATA / "places.json"
    out.write_text(json.dumps(places, separators=(",", ":")))
    print("\n  wrote %s (%.0f KB, %d entries)"
          % (out, out.stat().st_size / 1024, len(places)))


if __name__ == "__main__":
    main()
