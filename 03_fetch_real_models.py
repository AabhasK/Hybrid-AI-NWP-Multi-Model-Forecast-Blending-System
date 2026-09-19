"""
Step 2-REAL - Genuine multi-model operational forecasts at real lead times.

This replaces the synthetic generator (02_synth_models.py) with actual archived
output from operational forecasting centres, retrieved from the Open-Meteo
Previous Runs API. No API key, no account.

WHERE THE LEAD TIME COMES FROM
------------------------------
The API exposes `<variable>_previous_dayN`, which is the value that model
predicted for a given hour using the run issued N days earlier. Summing
`precipitation_previous_day3_ecmwf_ifs025` across a UTC day therefore yields
"the daily rainfall total ECMWF IFS forecast for this day, three days ahead".
That is a real operational forecast at a real lead time - not a perturbation of
the verifying analysis.

THE FOUR SOURCES
----------------
  A  ECMWF IFS       physics-based NWP, the operational gold standard
  B  ECMWF AIFS      ECMWF's data-driven AI forecasting system
  C  multi-centre    mean of NOAA GFS, DWD ICON and Environment Canada GEM -
                     a real poor-man's ensemble mean, a standard operational
                     product in its own right
  D  persistence     last verifying analysis available at issue time (ERA5)

Truth remains ERA5 reanalysis, fetched for the same window and grid.

Output: data/forecasts_real.parquet, in exactly the schema model_training.py
already consumes, so nothing downstream changes.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CACHE = DATA / "_real_raw"
CACHE.mkdir(exist_ok=True)

# --- same grid as the synthetic pipeline so results stay comparable ---------
LAT_MIN, LAT_MAX = 16.0, 21.0
LON_MIN, LON_MAX = 73.0, 78.0
STEP = 0.5

PAST_DAYS = 92          # how far the Previous Runs archive is queried
LEADS = [1, 2, 3, 4, 5]
EXTREME_MM = 40.0
ACTIVE_Z, BREAK_Z = 0.50, -0.50

PREV_API = "https://previous-runs-api.open-meteo.com/v1/forecast"
ERA5_API = "https://archive-api.open-meteo.com/v1/era5"

# model id -> the role it plays in the blend
MODELS = {
    "ecmwf_ifs025": "A",
    "ecmwf_aifs025": "B",
    "gfs_seamless": "C",
    "icon_seamless": "C",
    "gem_seamless": "C",
}
ROW_BATCH = 11          # one latitude row per request; ~3 s each


# ---------------------------------------------------------------------------
def build_grid():
    lats = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-9, STEP), 2)
    lons = np.round(np.arange(LON_MIN, LON_MAX + 1e-9, STEP), 2)
    return [(float(a), float(o)) for a in lats for o in lons]


def fetch(url, tries=4, timeout=180):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            if a == tries - 1:
                raise
            wait = 4 * (a + 1)
            print("      retry %d (%s) in %ds" % (a + 1, type(exc).__name__, wait))
            time.sleep(wait)


def hourly_to_daily(times, values, how):
    """Collapse an hourly series to UTC calendar days."""
    s = pd.Series(values, index=pd.to_datetime(times), dtype="float64")
    g = s.groupby(s.index.normalize())
    return (g.sum(min_count=18) if how == "sum" else g.mean()).rename(None)


def fetch_model_block(model, cells, var, leads):
    """
    One request: all cells in `cells`, one model, one variable, every lead.

    Precipitation and temperature are deliberately fetched in SEPARATE requests.
    Asking for both at once pushes server-side generation past 50 s and the
    connection is dropped; split, the same data returns in about 3 s.
    """
    names = [("%s_previous_day%d" % (var, L)) for L in leads]
    lat = ",".join("%.2f" % c[0] for c in cells)
    lon = ",".join("%.2f" % c[1] for c in cells)
    url = ("%s?latitude=%s&longitude=%s&hourly=%s&past_days=%d&forecast_days=1"
           "&timezone=UTC&models=%s" % (PREV_API, lat, lon, ",".join(names), PAST_DAYS, model))
    key = CACHE / ("%s_%s_%.2f.json" % (model, var, cells[0][0]))
    if key.exists():
        return json.loads(key.read_text())
    payload = fetch(url)
    if not isinstance(payload, list):
        payload = [payload]
    key.write_text(json.dumps(payload))
    return payload


def collect_forecasts(cells):
    """-> tidy frame: cell_id, date, lead_time, model_id, rain, t2m"""
    rows = []
    batches = [cells[i:i + ROW_BATCH] for i in range(0, len(cells), ROW_BATCH)]

    for model in MODELS:
        print("  %-16s" % model, end="", flush=True)
        ok = True
        for bi, batch in enumerate(batches):
            try:
                pr = fetch_model_block(model, batch, "precipitation", LEADS)
                tp = fetch_model_block(model, batch, "temperature_2m", LEADS)
            except Exception as exc:
                print("  FAILED (%s) - dropping this model" % type(exc).__name__)
                ok = False
                break

            for loc_i, (locp, loct) in enumerate(zip(pr, tp)):
                lat, lon = batch[loc_i]
                cid = "C%03d" % cells.index((lat, lon))
                hp, ht = locp["hourly"], loct["hourly"]
                for L in LEADS:
                    pk = "precipitation_previous_day%d" % L
                    tk = "temperature_2m_previous_day%d" % L
                    # the model selector is echoed back in the key only when
                    # several models are requested at once; handle both shapes
                    pk = pk if pk in hp else "%s_%s" % (pk, model)
                    tk = tk if tk in ht else "%s_%s" % (tk, model)
                    rain = hourly_to_daily(hp["time"], hp[pk], "sum")
                    temp = hourly_to_daily(ht["time"], ht[tk], "mean")
                    rows.append(pd.DataFrame({
                        "cell_id": cid, "lat": lat, "lon": lon,
                        "date": rain.index, "lead_time": L, "model_id": model,
                        "rain": rain.values, "t2m": temp.reindex(rain.index).values,
                    }))
            print(".", end="", flush=True)
            time.sleep(0.4)
        if ok:
            print(" ok")
    return pd.concat(rows, ignore_index=True)


def fetch_truth(cells, start, end):
    print("  ERA5 truth %s .. %s" % (start, end), end="", flush=True)
    out = []
    batches = [cells[i:i + 25] for i in range(0, len(cells), 25)]
    for batch in batches:
        lat = ",".join("%.2f" % c[0] for c in batch)
        lon = ",".join("%.2f" % c[1] for c in batch)
        key = CACHE / ("era5_%.2f_%.2f_%s.json" % (batch[0][0], batch[0][1], start))
        if key.exists():
            payload = json.loads(key.read_text())
        else:
            payload = fetch("%s?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
                            "&daily=precipitation_sum,temperature_2m_mean&timezone=UTC"
                            % (ERA5_API, lat, lon, start, end))
            if not isinstance(payload, list):
                payload = [payload]
            key.write_text(json.dumps(payload))
        for loc_i, loc in enumerate(payload):
            lat_i, lon_i = batch[loc_i]
            d = loc["daily"]
            out.append(pd.DataFrame({
                "cell_id": "C%03d" % cells.index((lat_i, lon_i)),
                "lat": lat_i, "lon": lon_i,
                "elevation_m": float(loc.get("elevation") or 0.0),
                "date": pd.to_datetime(d["time"]),
                "truth_rain": pd.to_numeric(d["precipitation_sum"], errors="coerce"),
                "truth_t2m": pd.to_numeric(d["temperature_2m_mean"], errors="coerce"),
            }))
        print(".", end="", flush=True)
        time.sleep(0.4)
    print(" ok")
    return pd.concat(out, ignore_index=True)


PHASE = {5: "pre_monsoon", 6: "early_monsoon", 7: "peak_monsoon",
         8: "late_monsoon", 9: "withdrawal", 10: "post_monsoon"}


def main():
    cells = build_grid()
    print("grid: %d cells  |  archive window: last %d days" % (len(cells), PAST_DAYS))

    print("\nfetching archived operational forecasts...")
    fc = collect_forecasts(cells)
    got = sorted(fc.model_id.unique())
    print("  retrieved: %s" % ", ".join(got))

    # ERA5 lags real time by a few days; verify only where truth exists
    end = (pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=5)).tz_localize(None)
    start = fc.date.min()
    print("\nfetching verifying analysis...")
    truth = fetch_truth(cells, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    truth = truth.dropna(subset=["truth_rain", "truth_t2m"])
    truth["truth_rain"] = truth.truth_rain.clip(lower=0)

    # ---- fold the raw models into the four blend sources -------------------
    fc["role"] = fc.model_id.map(MODELS)
    fc = fc[fc.role.notna()]
    src = (fc.groupby(["cell_id", "date", "lead_time", "role"])[["rain", "t2m"]]
             .mean().reset_index())          # role C averages GFS + ICON + GEM
    wide = src.pivot_table(index=["cell_id", "date", "lead_time"],
                           columns="role", values=["rain", "t2m"])
    wide.columns = ["model_%s_%s" % (r.lower(), v.replace("rain", "rain").replace("t2m", "t2m"))
                    for v, r in wide.columns]
    wide = wide.reset_index()

    df = truth.merge(wide, on=["cell_id", "date"], how="inner")
    df = df.dropna(subset=["model_a_rain", "model_b_rain", "model_c_rain"])
    df["rain_mm"] = df.truth_rain

    # ---- climatology, regime, persistence ---------------------------------
    piv = df.drop_duplicates(["cell_id", "date"]).pivot(
        index="date", columns="cell_id", values=["truth_rain", "truth_t2m"])
    rain_c = piv["truth_rain"].sort_index()
    temp_c = piv["truth_t2m"].sort_index()

    dom = rain_c.mean(axis=1)
    z = (dom - dom.mean()) / dom.std()
    regime = pd.Series(np.where(z >= ACTIVE_Z, "active",
                       np.where(z <= BREAK_Z, "break", "normal")), index=dom.index)

    shape = (dom.rolling(15, center=True, min_periods=1).mean() / dom.mean())
    clim_rain = rain_c.mean(axis=0).to_frame().T.reindex(rain_c.index, method="ffill")
    clim_rain = rain_c.mean(axis=0) * shape.values[:, None]
    clim_rain = pd.DataFrame(clim_rain, index=rain_c.index, columns=rain_c.columns)

    dom_t = temp_c.mean(axis=1)
    shift = dom_t.rolling(15, center=True, min_periods=1).mean() - dom_t.mean()
    clim_t2m = pd.DataFrame(temp_c.mean(axis=0).values[None, :] + shift.values[:, None],
                            index=temp_c.index, columns=temp_c.columns)

    df["regime"] = df.date.map(regime)
    df["domain_rain_z"] = df.date.map(z)
    prev = regime.shift(1).bfill()
    trans = pd.Series(regime.values != prev.values, index=regime.index)
    df["regime_transition"] = df.date.map(trans)
    df["season"] = df.date.dt.month.map(lambda m: PHASE.get(m, "other"))
    df["clim_rain"] = [clim_rain.at[d, c] for d, c in zip(df.date, df.cell_id)]
    df["clim_t2m"] = [clim_t2m.at[d, c] for d, c in zip(df.date, df.cell_id)]

    # D = persistence: the analysis available `lead` days before the valid date
    tr_lookup = {(c, d): v for c, d, v in zip(df.cell_id, df.date, df.truth_rain)}
    tt_lookup = {(c, d): v for c, d, v in zip(df.cell_id, df.date, df.truth_t2m)}
    dr, dt = [], []
    for c, d, L in zip(df.cell_id, df.date, df.lead_time):
        src_d = d - pd.Timedelta(days=int(L))
        dr.append(tr_lookup.get((c, src_d), np.nan))
        dt.append(tt_lookup.get((c, src_d), np.nan))
    df["model_d_rain"] = dr
    df["model_d_t2m"] = dt
    df["model_d_rain"] = df.model_d_rain.fillna(df.clim_rain)
    df["model_d_t2m"] = df.model_d_t2m.fillna(df.clim_t2m)

    for c in ["model_a_rain", "model_b_rain", "model_c_rain", "model_d_rain"]:
        df[c] = df[c].clip(lower=0)
    df["is_extreme"] = (df.truth_rain >= EXTREME_MM).astype(int)
    df["doy"] = df.date.dt.dayofyear
    df = df.sort_values(["date", "lead_time", "cell_id"]).reset_index(drop=True)

    out = DATA / "forecasts_real.parquet"
    df.to_parquet(out, index=False)

    # ---- report ------------------------------------------------------------
    def rmse(a, b):
        return float(np.sqrt(np.mean((a - b) ** 2)))

    print("\n--- REAL multi-model error signature (all leads) --------------")
    print("%-26s%10s%9s%8s" % ("source", "bias(mm)", "RMSE", "corr"))
    names = {"a": "A  ECMWF IFS", "b": "B  ECMWF AIFS",
             "c": "C  GFS+ICON+GEM mean", "d": "D  Persistence"}
    for m in "abcd":
        f = df["model_%s_rain" % m]
        print("%-26s%10.2f%9.2f%8.3f" % (names[m], (f - df.truth_rain).mean(),
              rmse(f, df.truth_rain), np.corrcoef(f, df.truth_rain)[0, 1]))

    print("\n--- RMSE by lead time ----------------------------------------")
    print("%-6s%9s%9s%9s%9s" % ("lead", "A", "B", "C", "D"))
    for L, g in df.groupby("lead_time"):
        print("%-6d%9.2f%9.2f%9.2f%9.2f" % (L, *[rmse(g["model_%s_rain" % m], g.truth_rain) for m in "abcd"]))

    print("\n--- best source per (lead x regime) --------------------------")
    print("%-6s%14s%14s%14s" % ("lead", "active", "break", "normal"))
    for L, gl in df.groupby("lead_time"):
        out_c = []
        for reg in ("active", "break", "normal"):
            g = gl[gl.regime == reg]
            if not len(g):
                out_c.append("-"); continue
            sc = {m.upper(): rmse(g["model_%s_rain" % m], g.truth_rain) for m in "abcd"}
            b = min(sc, key=sc.get)
            out_c.append("%s (%.2f)" % (b, sc[b]))
        print("%-6d%14s%14s%14s" % (L, *out_c))

    print("\nregime days: %s" % regime.value_counts().to_dict())
    print("rows %d | cells %d | days %d | %s .. %s"
          % (len(df), df.cell_id.nunique(), df.date.nunique(),
             df.date.min().date(), df.date.max().date()))
    print("extreme cell-days (>=%dmm): %d" % (EXTREME_MM, df.is_extreme.sum()))
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
