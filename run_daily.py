"""
The operational routine.

This is the fifth deliverable the problem statement asks for: an automated
script a duty forecaster could run every morning. It does not train anything.
It fetches TODAY's live forecast from every centre, applies the blend weights
that were learned offline, and writes a dated product.

  python run_daily.py              # blend today's runs
  python run_daily.py --publish    # also refresh the dashboard payload

For a shared deployment, run it with the server-side Docker Compose setup
described in README.md. The server refreshes every three hours by default.

WHY THE WEIGHTS ARE APPLIED, NOT REFITTED
-----------------------------------------
Weight estimation needs months of verification history and is the slow,
offline half of the system (model_training.py). The daily routine is the fast
half: it reads the regime and regional weight tables, diagnoses today's weather
regime from the forecast fields themselves, and combines the live members. That split
is what makes the thing operational - the morning run takes seconds and never
depends on verification data that does not exist yet for today.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import config

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "daily"
OUT.mkdir(parents=True, exist_ok=True)

# Same model ids the blender was trained on. AIFS must be the *_single id:
# `ecmwf_aifs025` returns nulls on both the live and archive endpoints.
MODELS = {
    "ecmwf_ifs025": "a",
    "ecmwf_aifs025_single": "b",
    "gfs_seamless": "c",
    "icon_seamless": "d",
    "gem_seamless": "e",
}
BLEND = ["a", "b", "c", "d", "e"]
# Include the issue date itself (T), followed by five daily leads.
LEADS = [0, 1, 2, 3, 4, 5]
VARS = {"rain": "precipitation_sum", "t2m": "temperature_2m_mean",
        "wind": "wind_speed_10m_max"}
# Open-Meteo bills per HTTP request, with a fractional surcharge past ten
# weather variables rather than per location, so packing more cells into each
# request cuts the call count for the same data. 60 keeps the URL near 1.5 kB,
# far inside any practical limit.
BATCH = 60
ACTIVE_Z, BREAK_Z = 0.50, -0.50
EXTREME_MM, HIGH_WIND_KMH = 40.0, 40.0
REGIONAL_SHARE = {"rain": 0.20, "t2m": 0.80, "wind": 0.0}


def load_grid():
    """
    The FINE grid. Weights are fitted on the coarse training grid because the
    archive is priced per cell per day, but the daily run only asks for the
    next week, so cells are nearly free here - and a 28 km cell is what makes
    a city search legible instead of swallowing a whole state in one box.
    """
    for name in ("grid_cells_live.json", "grid_cells.json"):
        gf = DATA / name
        if gf.exists():
            g = json.loads(gf.read_text())
            return g["cells"], g["grid_deg"]
    raise SystemExit("run 00_build_region.py first - no grid file")


def load_weights():
    wf = DATA / "blend_weight_sets.json"
    if not wf.exists():
        raise SystemExit("run model_training.py first - no blend_weight_sets.json")
    return json.loads(wf.read_text())


def load_regional_weights(cells):
    """Transfer verified 1° cell weights to the nearest live grid cell."""
    maps = {"rain": DATA / "weight_map.csv", "t2m": DATA / "weight_map_t2m.csv"}
    for path in maps.values():
        if not path.exists():
            raise SystemExit("missing %s - rerun model_training.py" % path)

    rain = pd.read_csv(maps["rain"])
    training = rain.drop_duplicates("cell_id")[["cell_id", "lat", "lon"]]
    live_xy = np.array([[c["lat"], c["lon"]] for c in cells], dtype=float)
    train_xy = training[["lat", "lon"]].to_numpy(dtype=float)
    idx = np.argmin(((live_xy[:, None, :] - train_xy[None, :, :]) ** 2).sum(axis=2), axis=1)
    nearest = dict(zip([c["id"] for c in cells], training.cell_id.to_numpy()[idx]))

    tables = {}
    for var, path in maps.items():
        table = pd.read_csv(path)
        tables[var] = {(r.cell_id, int(r.lead_time)):
                       np.array([float(getattr(r, "w_%s" % m)) for m in BLEND])
                       for r in table.itertuples(index=False)}
    return nearest, tables


def fetch_live(cells):
    """All five centres, three variables, six days - one request per batch."""
    host = config.OPENMETEO_HOST
    suffix = config.openmeteo_suffix()
    models = ",".join(MODELS)
    rows = []
    batches = [cells[i:i + BATCH] for i in range(0, len(cells), BATCH)]
    print("fetching live runs: %d cells in %d requests" % (len(cells), len(batches)))

    # Responses are cached per run date so an interrupted run resumes instead
    # of restarting. On a free-tier quota a full national sweep can straddle
    # several hourly windows, and losing that to a closed terminal is costly.
    #
    # The key hashes the COORDINATES, never the batch index: a key built from
    # position would silently serve one batch's data for another the moment
    # the grid or batch size changed.
    cache_dir = DATA / "_live_raw" / date.today().isoformat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    hits = 0

    for bi, batch in enumerate(batches):
        lat = ",".join("%.2f" % c["lat"] for c in batch)
        lon = ",".join("%.2f" % c["lon"] for c in batch)
        # Fetch today (T) through T+5 so the dashboard timeline always starts
        # on the current date. T uses the nearest trained weights, T+1.
        url = ("%s/v1/forecast?latitude=%s&longitude=%s&daily=%s"
               "&start_date=%s&end_date=%s&timezone=UTC&models=%s%s"
               % (host, lat, lon, ",".join(VARS.values()),
                  (date.today() + timedelta(days=min(LEADS))).isoformat(),
                  (date.today() + timedelta(days=max(LEADS))).isoformat(),
                  models, suffix))

        ckey = hashlib.md5(("%s|%s|%s|%s" % (lat, lon, models,
                            ",".join(VARS.values()))).encode()).hexdigest()
        cfile = cache_dir / (ckey + ".json")
        payload = None
        if cfile.exists():
            try:
                payload = json.loads(cfile.read_text(encoding="utf-8"))
                hits += 1
            except Exception:
                payload = None          # corrupt entry; refetch below
        from_cache = payload is not None

        for attempt in range(6):
            if payload is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    payload = json.load(r)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # The free tier limits per minute (600), per hour (5,000)
                    # and per day. Sleeping to the top of the hour on the FIRST
                    # 429 treats a one-minute burst limit as an hourly outage
                    # and throws away up to 59 minutes of usable quota. Back
                    # off briefly first and only wait out the hour once short
                    # retries have clearly failed.
                    if attempt < 2:
                        nap = 75 * (attempt + 1)
                        print("  [rate limited; retrying in %ds]" % nap, flush=True)
                        time.sleep(nap)
                        continue
                    now = time.gmtime()
                    wait = (60 - now.tm_min) * 60 - now.tm_sec + 90
                    print("  [hourly quota reached; waiting %d min for reset]"
                          % (wait // 60), flush=True)
                    time.sleep(wait)
                    continue
                if attempt == 5:
                    raise
                time.sleep(4 * (attempt + 1))
            except Exception as exc:
                if attempt == 5:
                    raise
                print("   retry %d (%s)" % (attempt + 1, type(exc).__name__))
                time.sleep(4 * (attempt + 1))
        if not cfile.exists():
            try:
                cfile.write_text(json.dumps(payload), encoding="utf-8")
            except Exception:
                pass                    # a cache write must never fail the run

        if not isinstance(payload, list):
            payload = [payload]

        for loc, cell in zip(payload, batch):
            d = loc["daily"]
            for k, t in enumerate(d["time"]):
                rec = {"cell_id": cell["id"], "lat": cell["lat"], "lon": cell["lon"],
                       "elevation_m": float(loc.get("elevation") or 0.0),
                       "valid_date": t}
                ok = True
                for mid, role in MODELS.items():
                    for vname, api in VARS.items():
                        col = "%s_%s" % (api, mid)
                        v = d.get(col, [None] * len(d["time"]))[k]
                        if v is None:
                            ok = False
                        rec["model_%s_%s" % (role, vname)] = v
                if ok:
                    rows.append(rec)
        print("   batch %d/%d" % (bi + 1, len(batches)), end="\r", flush=True)
        if not from_cache:
            time.sleep(0.3)             # be polite only when we actually called
    print()
    if hits:
        print("   resumed %d/%d batches from cache" % (hits, len(batches)))
    return pd.DataFrame(rows)


def diagnose_regime(df):
    """
    Active / break / normal from the forecast fields themselves.

    Exactly the definition used in training: no observation for a future date
    exists, so the regime has to come from what the models are predicting.
    """
    src = ["model_%s_rain" % m for m in BLEND]
    dom = df.groupby("valid_date")[src].mean().mean(axis=1)
    z = (dom - dom.mean()) / (dom.std() or 1.0)
    lab = pd.Series(np.where(z >= ACTIVE_Z, "active",
                    np.where(z <= BREAK_Z, "break", "normal")), index=dom.index)
    return df.valid_date.map(lab), df.valid_date.map(z)


def blend(df, weights, regional):
    """Apply verified local and spell weights; retain the actual row weights."""
    nearest, tables = regional
    for var in ("rain", "t2m", "wind"):
        out = np.full(len(df), np.nan)
        applied = np.zeros((len(df), len(BLEND)), dtype=float)
        F = np.column_stack([df["model_%s_%s" % (m, var)].values for m in BLEND])
        for lead in LEADS:
            sel = (df.lead_time == lead).values
            if not sel.any():
                continue
            # Lead zero has no trained skill estimate; use the nearest trained
            # horizon (T+1) weights for today's forecast.
            wlead = str(max(1, lead))
            wset = weights.get(wlead, {}).get(var if var in weights.get(wlead, {}) else "rain", {})
            for reg in df.regime[sel].unique():
                m = sel & (df.regime == reg).values
                w = np.array(wset.get(reg) or wset.get("_all") or
                             [1.0 / len(BLEND)] * len(BLEND), dtype=float)
                if w.shape[0] != len(BLEND):
                    w = np.full(len(BLEND), 1.0 / len(BLEND))
                w = w / w.sum()
                share = REGIONAL_SHARE[var]
                if share:
                    local = np.stack([
                        tables[var].get((nearest.get(c), max(1, lead)), w)
                        for c in df.loc[m, "cell_id"]
                    ])
                    local /= np.maximum(local.sum(axis=1, keepdims=True), 1e-12)
                    row_weights = (1 - share) * w + share * local
                else:
                    row_weights = np.broadcast_to(w, (m.sum(), len(BLEND)))
                # A single missing member used to poison the whole cell: a
                # plain dot product returns NaN if any term is NaN, so one
                # centre dropping a variable blanked the blend there. Mask the
                # absent members and renormalise over what did arrive, which
                # is what the documentation always claimed happened.
                Fm = F[m]
                ok = ~np.isnan(Fm)
                den = (ok * row_weights).sum(axis=1)
                actual = np.divide(np.where(ok, row_weights, 0.0), den[:, None],
                                   out=np.zeros_like(row_weights), where=den[:, None] > 0)
                applied[m] = actual
                num = np.nansum(np.where(ok, Fm, 0.0) * row_weights, axis=1)
                out[m] = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
        df["blend_%s" % var] = out
        for j, source in enumerate(BLEND):
            df["weight_%s_%s" % (var, source)] = applied[:, j]
    df["blend_rain"] = df.blend_rain.clip(lower=0)
    df["blend_wind"] = df.blend_wind.clip(lower=0)

    spread = np.std(np.column_stack(
        [df["model_%s_rain" % m].values for m in BLEND]), axis=1)
    mean = np.mean(np.column_stack(
        [df["model_%s_rain" % m].values for m in BLEND]), axis=1)
    df["confidence"] = (100 * np.exp(-1.6 * spread / (np.abs(mean) + 2.0))).clip(35, 99).round(1)
    return df


def prob_heavy(values):
    """Empirical P(>=40 mm) by blended amount, measured out-of-sample."""
    cf = DATA / "regional_verification.json"
    if not cf.exists():
        cf = DATA / "dashboard_data.json"
    edges, ps = None, None
    if cf.exists():
        try:
            payload = json.loads(cf.read_text())
            c = payload.get("pext_curve") or payload["metrics"]["pext_curve"]
            edges, ps = c["edges"], c["p"]
        except Exception:
            pass
    if not edges:
        return np.clip((values - 20.0) / 40.0, 0, 1)
    idx = np.searchsorted(np.array(edges), values, side="right") - 1
    idx = np.clip(idx, 0, len(ps) - 1)
    return np.array(ps, dtype=float)[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true",
                    help="refresh the dashboard payload after blending")
    args = ap.parse_args()

    cells, _ = load_grid()
    weights = load_weights()
    regional = load_regional_weights(cells)
    issued = date.today()

    df = fetch_live(cells)
    if df.empty:
        raise SystemExit("no live data returned - check connectivity")

    df["valid_date"] = pd.to_datetime(df.valid_date).dt.date
    df["lead_time"] = df.valid_date.map(lambda d: (d - issued).days)
    df = df[df.lead_time.isin(LEADS)].reset_index(drop=True)

    df["regime"], df["domain_z"] = diagnose_regime(df)
    df = blend(df, weights, regional)
    df["prob_heavy"] = prob_heavy(df.blend_rain.values).round(3)
    df["high_wind"] = (df.blend_wind >= HIGH_WIND_KMH).astype(int)

    stamp = issued.isoformat()
    path = OUT / ("blend_%s.parquet" % stamp)
    df.to_parquet(path, index=False)
    # stable path the exporter picks up without needing to know today's date
    df.to_parquet(DATA / "live_blend.parquet", index=False)

    print("\n=== blended product, run issued %s ===" % stamp)
    print("%-8s%-10s%10s%10s%10s%9s" %
          ("lead", "regime", "rain mm", "T2m C", "wind kmh", "alerts"))
    for lead, g in df.groupby("lead_time"):
        print("%-8s%-10s%10.2f%10.2f%10.1f%9d"
              % ("T+%d" % lead, g.regime.mode().iat[0], g.blend_rain.mean(),
                 g.blend_t2m.mean(), g.blend_wind.mean(),
                 int((g.prob_heavy >= 0.25).sum() + g.high_wind.sum())))

    heavy = df[df.prob_heavy >= 0.25].nlargest(5, "blend_rain")
    if len(heavy):
        print("\ntop heavy-rain cells:")
        for r in heavy.itertuples(index=False):
            print("   T+%d  %-5s %5.1f mm  %.1fN %.1fE  P=%.0f%%"
                  % (r.lead_time, r.cell_id, r.blend_rain, r.lat, r.lon, 100 * r.prob_heavy))

    print("\nwrote %s  (%d rows)" % (path, len(df)))

    if args.publish:
        print("\nrefreshing dashboard payload ...")
        for step in ("export_dashboard_data.py", "build_dashboard.py"):
            subprocess.run([sys.executable, str(ROOT / step)], check=True)


if __name__ == "__main__":
    main()
