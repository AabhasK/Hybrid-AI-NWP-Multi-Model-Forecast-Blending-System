"""
The operational routine.

This is the fifth deliverable the problem statement asks for: an automated
script a duty forecaster could run every morning. It does not train anything.
It fetches TODAY's live forecast from every centre, applies the blend weights
that were learned offline, and writes a dated product.

  python run_daily.py              # blend today's runs
  python run_daily.py --publish    # also refresh the dashboard payload

Schedule it with Task Scheduler or cron:
  0 7 * * *  cd /path/to/NWP-SIH && python run_daily.py --publish

WHY THE WEIGHTS ARE APPLIED, NOT REFITTED
-----------------------------------------
Weight estimation needs months of verification history and is the slow,
offline half of the system (model_training.py). The daily routine is the fast
half: it reads data/blend_weight_sets.json, diagnoses today's weather regime
from the forecast fields themselves, and combines the live members. That split
is what makes the thing operational - the morning run takes seconds and never
depends on verification data that does not exist yet for today.
"""

import argparse
import json
import subprocess
import sys
import time
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
LEADS = [1, 2, 3, 4, 5]
VARS = {"rain": "precipitation_sum", "t2m": "temperature_2m_mean",
        "wind": "wind_speed_10m_max"}
BATCH = 25
ACTIVE_Z, BREAK_Z = 0.50, -0.50
EXTREME_MM, HIGH_WIND_KMH = 40.0, 40.0


def load_grid():
    gf = DATA / "grid_cells.json"
    if not gf.exists():
        raise SystemExit("run 00_build_region.py first - no grid_cells.json")
    g = json.loads(gf.read_text())
    return g["cells"], g["grid_deg"]


def load_weights():
    wf = DATA / "blend_weight_sets.json"
    if not wf.exists():
        raise SystemExit("run model_training.py first - no blend_weight_sets.json")
    return json.loads(wf.read_text())


def fetch_live(cells):
    """All five centres, three variables, six days - one request per batch."""
    host = config.OPENMETEO_HOST
    suffix = config.openmeteo_suffix()
    models = ",".join(MODELS)
    rows = []
    batches = [cells[i:i + BATCH] for i in range(0, len(cells), BATCH)]
    print("fetching live runs: %d cells in %d requests" % (len(cells), len(batches)))

    for bi, batch in enumerate(batches):
        lat = ",".join("%.2f" % c["lat"] for c in batch)
        lon = ",".join("%.2f" % c["lon"] for c in batch)
        url = ("%s/v1/forecast?latitude=%s&longitude=%s&daily=%s"
               "&forecast_days=7&timezone=UTC&models=%s%s"
               % (host, lat, lon, ",".join(VARS.values()), models, suffix))
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    payload = json.load(r)
                break
            except Exception as exc:
                if attempt == 3:
                    raise
                print("   retry %d (%s)" % (attempt + 1, type(exc).__name__))
                time.sleep(4 * (attempt + 1))
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
        time.sleep(0.3)
    print()
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


def blend(df, weights):
    """Apply the learned sum-to-one weights, per variable, lead and regime."""
    for var in ("rain", "t2m", "wind"):
        out = np.full(len(df), np.nan)
        F = np.column_stack([df["model_%s_%s" % (m, var)].values for m in BLEND])
        for lead in LEADS:
            sel = (df.lead_time == lead).values
            if not sel.any():
                continue
            wset = weights.get(str(lead), {}).get(var if var in weights.get(str(lead), {}) else "rain", {})
            for reg in df.regime[sel].unique():
                m = sel & (df.regime == reg).values
                w = np.array(wset.get(reg) or wset.get("_all") or
                             [1.0 / len(BLEND)] * len(BLEND), dtype=float)
                if w.shape[0] != len(BLEND):
                    w = np.full(len(BLEND), 1.0 / len(BLEND))
                out[m] = F[m] @ (w / w.sum())
        df["blend_%s" % var] = out
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
    cf = DATA / "dashboard_data.json"
    edges, ps = None, None
    if cf.exists():
        try:
            c = json.loads(cf.read_text())["metrics"]["pext_curve"]
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
    issued = date.today()

    df = fetch_live(cells)
    if df.empty:
        raise SystemExit("no live data returned - check connectivity")

    df["valid_date"] = pd.to_datetime(df.valid_date).dt.date
    df["lead_time"] = df.valid_date.map(lambda d: (d - issued).days)
    df = df[df.lead_time.isin(LEADS)].reset_index(drop=True)

    df["regime"], df["domain_z"] = diagnose_regime(df)
    df = blend(df, weights)
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
            subprocess.run([sys.executable, str(ROOT / step)], check=False)


if __name__ == "__main__":
    main()
