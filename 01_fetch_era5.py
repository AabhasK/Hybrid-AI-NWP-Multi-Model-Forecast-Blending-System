"""
Step 1 - Ground truth acquisition.

Pulls ERA5 reanalysis (daily precipitation + 2m temperature) for a 5 deg x 5 deg
box over Maharashtra, India, across the 2023 southwest monsoon (Jun-Aug).

Source: Open-Meteo ERA5 archive API (https://archive-api.open-meteo.com).
This serves the same ECMWF ERA5 reanalysis product as the Copernicus CDS, but
pre-interpolated to arbitrary lat/lon and delivered as JSON with no API key and
no request queue. Swapping in `cdsapi` later changes only this file.

Output: data/era5_truth.parquet
"""

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CACHE = DATA / "_era5_raw.json"

# --- Region: Maharashtra. Konkan coast -> Western Ghats -> Marathwada rain shadow.
LAT_MIN, LAT_MAX = 16.0, 21.0
LON_MIN, LON_MAX = 73.0, 78.0
STEP = 0.5

START_DATE = "2023-06-01"
END_DATE = "2023-08-31"

API = "https://archive-api.open-meteo.com/v1/era5"
DAILY_VARS = "precipitation_sum,temperature_2m_mean,temperature_2m_max"
BATCH = 25  # locations per HTTP request


def build_grid():
    lats = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-9, STEP), 2)
    lons = np.round(np.arange(LON_MIN, LON_MAX + 1e-9, STEP), 2)
    cells = []
    for la in lats:
        for lo in lons:
            cells.append((float(la), float(lo)))
    return cells


def fetch_batch(pairs):
    lat_s = ",".join(f"{p[0]:.2f}" for p in pairs)
    lon_s = ",".join(f"{p[1]:.2f}" for p in pairs)
    url = (
        f"{API}?latitude={lat_s}&longitude={lon_s}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        f"&daily={DAILY_VARS}&timezone=UTC"
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                payload = json.load(r)
            return payload if isinstance(payload, list) else [payload]
        except Exception as exc:  # transient rate-limit / network hiccup
            wait = 3 * (attempt + 1)
            print(f"    retry {attempt + 1} after {type(exc).__name__}: {exc} (sleep {wait}s)")
            time.sleep(wait)
    raise RuntimeError("ERA5 fetch failed after 4 attempts")


def fetch_all(cells):
    if CACHE.exists():
        print(f"Using cached raw ERA5 response: {CACHE}")
        return json.loads(CACHE.read_text())

    out = []
    for i in range(0, len(cells), BATCH):
        chunk = cells[i : i + BATCH]
        print(f"  fetching cells {i + 1}-{i + len(chunk)} of {len(cells)} ...")
        out.extend(fetch_batch(chunk))
        time.sleep(1.0)  # be polite to a free public API
    CACHE.write_text(json.dumps(out))
    return out


def to_frame(raw, cells):
    rows = []
    for idx, (loc, (req_lat, req_lon)) in enumerate(zip(raw, cells)):
        d = loc["daily"]
        n = len(d["time"])
        rows.append(
            pd.DataFrame(
                {
                    "cell_id": f"C{idx:03d}",
                    "lat": req_lat,
                    "lon": req_lon,
                    "elevation_m": float(loc.get("elevation") or 0.0),
                    "date": pd.to_datetime(d["time"]),
                    "rain_mm": d["precipitation_sum"],
                    "t2m_mean": d["temperature_2m_mean"],
                    "t2m_max": d["temperature_2m_max"],
                }
            )
        )
    df = pd.concat(rows, ignore_index=True)
    for c in ("rain_mm", "t2m_mean", "t2m_max"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # ERA5 has no gaps over land here, but guard anyway.
    df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
    df[["rain_mm", "t2m_mean", "t2m_max"]] = (
        df.groupby("cell_id")[["rain_mm", "t2m_mean", "t2m_max"]]
        .transform(lambda s: s.ffill().bfill())
    )
    df["rain_mm"] = df["rain_mm"].clip(lower=0.0)
    return df


def main():
    cells = build_grid()
    print(f"Region: {LAT_MIN}-{LAT_MAX}N, {LON_MIN}-{LON_MAX}E  ->  {len(cells)} grid cells @ {STEP} deg")
    print(f"Window: {START_DATE} .. {END_DATE} (SW monsoon 2023)")
    raw = fetch_all(cells)
    df = to_frame(raw, cells)

    out = DATA / "era5_truth.parquet"
    df.to_parquet(out, index=False)

    print("\n--- ERA5 ground truth summary -------------------------------")
    print(f"rows            : {len(df):,}  ({df.cell_id.nunique()} cells x {df.date.nunique()} days)")
    print(f"date range      : {df.date.min().date()} .. {df.date.max().date()}")
    print(f"elevation range : {df.elevation_m.min():.0f} - {df.elevation_m.max():.0f} m")
    print(f"mean daily rain : {df.rain_mm.mean():.2f} mm   (max {df.rain_mm.max():.1f} mm)")
    print(f"mean T2m        : {df.t2m_mean.mean():.2f} C   (max {df.t2m_max.max():.1f} C)")
    wet = df.groupby("cell_id").rain_mm.sum()
    wettest, driest = wet.idxmax(), wet.idxmin()
    gw = df[df.cell_id == wettest].iloc[0]
    gd = df[df.cell_id == driest].iloc[0]
    print(
        f"wettest cell    : {wettest} ({gw.lat:.1f}N,{gw.lon:.1f}E, {gw.elevation_m:.0f}m) "
        f"= {wet.max():.0f} mm season total"
    )
    print(
        f"driest  cell    : {driest} ({gd.lat:.1f}N,{gd.lon:.1f}E, {gd.elevation_m:.0f}m) "
        f"= {wet.min():.0f} mm season total"
    )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
