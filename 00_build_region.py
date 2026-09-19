"""
Step 0 - Define the forecast domain: India.

Downloads the Indian national boundary, simplifies it to something small
enough to embed in a single HTML file, and derives the analysis grid from it
so that every grid cell sits on Indian territory rather than on a rectangle
that spills into the Arabian Sea and four neighbouring countries.

Produces three things:

  data/india_boundary.json   simplified rings, for clipping the map
  data/india_mask.json       the inverse: a world polygon with India punched
                             out, which is what actually clips the raster
  data/grid_cells.json       the analysis grid - land cells only

Boundary source is DataMeet's india-composite, which follows the boundaries
as depicted by the Government of India. That is the correct depiction for a
submission to an Indian ministry.

No shapely or geopandas: both simplification and the point-in-polygon test
are implemented here so the project keeps running on a bare Anaconda install.
"""

import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
RAW = DATA / "_india_raw.geojson"

SOURCE = ("https://raw.githubusercontent.com/datameet/maps/master/"
          "Country/india-composite.geojson")

# TWO grids, because the two halves of the system have opposite cost shapes.
#
#   TRAIN_DEG  weights are fitted from months of archived forecasts, and the
#              archive is priced per cell PER DAY, so history is what is
#              expensive. A coarse grid keeps 120 days affordable.
#   LIVE_DEG   the daily run only needs the next 7 days, so cells are nearly
#              free. A fine grid is what makes a city search legible - at one
#              degree a cell is 111 km across and every city in a state lands
#              in the same box.
#
# The weights transfer between them because they are fitted per (regime, lead
# time), not per cell, so a weight learned on a coarse grid applies at any
# resolution.
TRAIN_DEG = 1.0
LIVE_DEG = 0.25
GRID_DEG = TRAIN_DEG
SIMPLIFY_TOL = 0.02        # degrees; ~2 km, plenty at national zoom
MIN_RING_AREA = 0.02       # drop specks smaller than this (sq deg)


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------
def perp_distance(p, a, b):
    """Perpendicular distance from p to the segment a-b."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(pts, tol):
    """Iterative Douglas-Peucker - recursion blows the stack on these rings."""
    if len(pts) < 3:
        return pts[:]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        worst, worst_i = -1.0, -1
        for i in range(lo + 1, hi):
            d = perp_distance(pts[i], pts[lo], pts[hi])
            if d > worst:
                worst, worst_i = d, i
        if worst > tol:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [p for p, k in zip(pts, keep) if k]


def ring_area(ring):
    """Absolute shoelace area in square degrees."""
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(s) / 2.0


def point_in_ring(x, y, ring):
    """Ray casting."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def point_in_polygons(x, y, polys):
    """polys: list of [outer, hole, hole, ...]"""
    for rings in polys:
        if point_in_ring(x, y, rings[0]):
            if not any(point_in_ring(x, y, h) for h in rings[1:]):
                return True
    return False


# ---------------------------------------------------------------------------
def load_boundary():
    if not RAW.exists():
        print("downloading India boundary (~10 MB, once) ...")
        urllib.request.urlretrieve(SOURCE, RAW)
    gj = json.loads(RAW.read_text(encoding="utf-8"))

    polys = []
    for feat in gj.get("features", [gj]):
        geom = feat.get("geometry", feat)
        if geom["type"] == "Polygon":
            polys.append(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            polys.extend(geom["coordinates"])
    return polys


def simplify(polys, tol):
    out = []
    kept_pts = raw_pts = 0
    for rings in polys:
        new_rings = []
        for ri, ring in enumerate(rings):
            ring = [(float(a), float(b)) for a, b in ring]
            raw_pts += len(ring)
            if ri == 0 and ring_area(ring) < MIN_RING_AREA:
                new_rings = []
                break
            s = douglas_peucker(ring, tol)
            if len(s) >= 4:
                if s[0] != s[-1]:
                    s.append(s[0])
                new_rings.append(s)
                kept_pts += len(s)
        if new_rings:
            out.append(new_rings)
    print("  rings: %d polygons, %d -> %d points (%.1f%% kept)"
          % (len(out), raw_pts, kept_pts, 100.0 * kept_pts / max(raw_pts, 1)))
    return out


def bounds_of(polys):
    xs = [p[0] for rings in polys for p in rings[0]]
    ys = [p[1] for rings in polys for p in rings[0]]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    polys = simplify(load_boundary(), SIMPLIFY_TOL)
    w, s, e, n = bounds_of(polys)
    print("  bounds: %.2f-%.2f E, %.2f-%.2f N" % (w, e, s, n))

    # ---- boundary, for the outline stroke --------------------------------
    boundary = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "MultiPolygon",
                     "coordinates": [[[list(p) for p in r] for r in rings]
                                     for rings in polys]}}]}
    (DATA / "india_boundary.json").write_text(json.dumps(boundary, separators=(",", ":")))

    # ---- inverse mask: a world rectangle with India punched out ----------
    # Filling this with the page background is what clips the forecast raster
    # to the national boundary - the raster itself stays a simple image.
    holes = [r for rings in polys for r in rings[:1]]
    world = [[-180.0, -85.0], [180.0, -85.0], [180.0, 85.0], [-180.0, 85.0], [-180.0, -85.0]]
    mask = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon",
                     "coordinates": [world] + [[list(p) for p in h] for h in holes]}}]}
    (DATA / "india_mask.json").write_text(json.dumps(mask, separators=(",", ":")))

    # ---- the analysis grids: land cells only -----------------------------
    def build(deg, fname):
        cells = []
        lat = math.floor(s / deg) * deg
        while lat <= n:
            lon = math.floor(w / deg) * deg
            while lon <= e:
                cx, cy = round(lon + deg / 2, 4), round(lat + deg / 2, 4)
                if point_in_polygons(cx, cy, polys):
                    cells.append({"lat": cy, "lon": cx})
                lon += deg
            lat += deg
        for i, c in enumerate(cells):
            c["id"] = "C%04d" % i
        (DATA / fname).write_text(json.dumps(
            {"grid_deg": deg, "bbox": [round(s, 2), round(w, 2), round(n, 2), round(e, 2)],
             "cells": cells}, separators=(",", ":")))
        return cells

    cells = build(TRAIN_DEG, "grid_cells.json")
    live_cells = build(LIVE_DEG, "grid_cells_live.json")

    kb = lambda p: (DATA / p).stat().st_size / 1024
    print("\n  grid: %d land cells at %.2f deg" % (len(cells), GRID_DEG))
    print("  wrote india_boundary.json (%.0f KB), india_mask.json (%.0f KB), "
          "grid_cells.json (%.0f KB)"
          % (kb("india_boundary.json"), kb("india_mask.json"), kb("grid_cells.json")))
    print("\n  forecast-archive cost of this grid:")
    print("    %d cells x 3 variables x 5 models = %d series per lead time"
          % (len(cells), len(cells) * 15))


if __name__ == "__main__":
    main()
