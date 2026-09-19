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
  C  NOAA GFS        physics-based NWP
  D  DWD ICON        physics-based NWP
  E  EC GEM          physics-based NWP
  F  persistence     last verifying analysis available at issue time (ERA5);
                     the skill reference, not a blend member

Each centre enters the blend SEPARATELY. An earlier version averaged GFS, ICON
and GEM into one "ensemble mean" member, which threw away two independent
skilful forecasts and cost the blend real accuracy (RMSE 10.67 averaged vs
10.54 separate).

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

import config

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CACHE = DATA / "_real_raw"
CACHE.mkdir(exist_ok=True)

# --- same grid as the synthetic pipeline so results stay comparable ---------
LAT_MIN, LAT_MAX = 16.0, 21.0
LON_MIN, LON_MAX = 73.0, 78.0
STEP = 0.5

# Open-Meteo prices a request by locations x variables x days, so a full year
# across five models exhausts the hourly quota. 180 days still doubles the
# independent sample versus the original 88, which is what the blend weights
# were short of. Cached longer windows are reused rather than refetched.
PAST_DAYS = 180
LEADS = [1, 2, 3, 4, 5]
EXTREME_MM = 40.0
ACTIVE_Z, BREAK_Z = 0.50, -0.50

# Hosts and key come from config.py, which reads .env. With no key these are
# the free public endpoints; with OPENMETEO_API_KEY set they become the
# customer endpoints and the hourly rate limit stops being the bottleneck.
PREV_API = config.OPENMETEO_PREV_HOST + "/v1/forecast"
ERA5_API = config.OPENMETEO_ARCHIVE_HOST + "/v1/era5"
KEY_SUFFIX = config.openmeteo_suffix()

# model id -> the role it plays in the blend
# NOTE on the AI model id: `ecmwf_aifs025` serves live forecasts but returns
# all-null for every `_previous_dayN` variable - Open-Meteo keeps no previous-
# runs archive under that id. `ecmwf_aifs025_single` (the deterministic AIFS
# run) does carry the archive. `gfs_graphcast025` resolves but is likewise
# empty on this endpoint. Verified 2026-09-19.
MODELS = {
    "ecmwf_ifs025": "A",          # ECMWF IFS      - physics NWP, operational standard
    "ecmwf_aifs025_single": "B",  # ECMWF AIFS     - data-driven AI forecast system
    "gfs_seamless": "C",          # NOAA GFS       - physics NWP
    "icon_seamless": "D",         # DWD ICON       - physics NWP
    "gem_seamless": "E",          # EC GEM         - physics NWP
}
# F is persistence, computed from the verifying analysis below. It is the SKILL
# REFERENCE, not a blend member: including it in the weight solve measurably
# degraded out-of-sample blend RMSE (10.54 -> 10.77) because it adds no
# independent information and destabilises the fitted weights.
# At a 365-day window the server times out streaming more than ~6 locations
# per request ("Unexpected error while streaming data: timeout"); 4 returns in
# under 3 s. Measured, not guessed.
ROW_BATCH = 4


# ---------------------------------------------------------------------------
def build_grid():
    lats = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-9, STEP), 2)
    lons = np.round(np.arange(LON_MIN, LON_MAX + 1e-9, STEP), 2)
    return [(float(a), float(o)) for a in lats for o in lons]


def seconds_to_next_hour():
    now = time.gmtime()
    return (60 - now.tm_min) * 60 - now.tm_sec + 90   # +90s of slack


def fetch(url, tries=5, timeout=180):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                # The hourly quota resets on the hour, so waiting it out is the
                # correct move - failing the whole run would throw away every
                # request already paid for.
                wait = seconds_to_next_hour()
                print("  [hourly API quota reached; waiting %d min for reset]"
                      % (wait // 60), flush=True)
                time.sleep(wait)
                continue
            if a == tries - 1:
                raise
            time.sleep(4 * (a + 1))
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


def fetch_model_block(model, cells, var, leads, batch_id):
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
           "&timezone=UTC&models=%s%s"
           % (PREV_API, lat, lon, ",".join(names), PAST_DAYS, model, KEY_SUFFIX))
    key = CACHE / ("%s_%s_%dd_b%03d.json" % (model, var, PAST_DAYS, batch_id))
    if key.exists():
        return json.loads(key.read_text())
    # a previously cached LONGER window already contains this one
    for other in sorted(CACHE.glob("%s_%s_*d_b%03d.json" % (model, var, batch_id))):
        try:
            days = int(other.name.split("_")[-2].rstrip("d"))
        except ValueError:
            continue
        if days >= PAST_DAYS:
            return json.loads(other.read_text())
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
                pr = fetch_model_block(model, batch, "precipitation", LEADS, bi)
                tp = fetch_model_block(model, batch, "temperature_2m", LEADS, bi)
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
            if bi % 5 == 0: print(".", end="", flush=True)
            time.sleep(0.3)
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
                            "&daily=precipitation_sum,temperature_2m_mean&timezone=UTC%s"
                            % (ERA5_API, lat, lon, start, end, KEY_SUFFIX))
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


PHASE = {12: "winter", 1: "winter", 2: "winter",
         3: "pre_monsoon", 4: "pre_monsoon", 5: "pre_monsoon",
         6: "monsoon_onset", 7: "monsoon_peak", 8: "monsoon_peak",
         9: "monsoon_withdrawal", 10: "post_monsoon", 11: "post_monsoon"}


def main():
    cells = build_grid()
    print("grid: %d cells  |  archive window: last %d days" % (len(cells), PAST_DAYS))
    print("open-meteo: %s" % ("keyed endpoint (raised limits)"
          if config.is_set("OPENMETEO_API_KEY") else "free endpoint (hourly quota applies)"))

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
    # A model can answer 200 OK with every value null (some ids serve live
    # forecasts but keep no previous-runs archive). Catch that here rather
    # than letting it surface as a missing column three steps downstream.
    empty = [m for m, g in fc.groupby("model_id") if g.rain.isna().all()]
    if empty:
        raise SystemExit(
            "these models returned no archived data: %s\n"
            "they resolve but carry no previous-runs history - pick another id"
            % ", ".join(empty))

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
    df = df.dropna(subset=["model_%s_rain" % m for m in "abcde"])
    df["rain_mm"] = df.truth_rain

    # ---- climatology, regime, persistence ---------------------------------
    piv = df.drop_duplicates(["cell_id", "date"]).pivot(
        index="date", columns="cell_id", values=["truth_rain", "truth_t2m"])
    rain_c = piv["truth_rain"].sort_index()
    temp_c = piv["truth_t2m"].sort_index()

    # Anomaly against the SEASONAL CYCLE, not the annual mean. Over a full
    # year an absolute threshold would label every dry-season day a "break";
    # active and break spells are departures from what is normal for the time
    # of year, which is what a forecaster means by the terms.
    dom = rain_c.mean(axis=1)
    seasonal = dom.rolling(31, center=True, min_periods=7).mean()
    anom = dom - seasonal
    z = anom / anom.std()
    regime = pd.Series(np.where(z >= ACTIVE_Z, "active",
                       np.where(z <= BREAK_Z, "break", "normal")), index=dom.index)

    # climatology = each cell's seasonal level x a smooth domain-wide cycle
    shape = (dom.rolling(15, center=True, min_periods=1).mean() / dom.mean())
    clim_rain = pd.DataFrame(rain_c.mean(axis=0).values[None, :] * shape.values[:, None],
                             index=rain_c.index, columns=rain_c.columns)

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

    # F = persistence: the analysis available `lead` days before the valid date
    tr_lookup = {(c, d): v for c, d, v in zip(df.cell_id, df.date, df.truth_rain)}
    tt_lookup = {(c, d): v for c, d, v in zip(df.cell_id, df.date, df.truth_t2m)}
    dr, dt = [], []
    for c, d, L in zip(df.cell_id, df.date, df.lead_time):
        src_d = d - pd.Timedelta(days=int(L))
        dr.append(tr_lookup.get((c, src_d), np.nan))
        dt.append(tt_lookup.get((c, src_d), np.nan))
    df["model_f_rain"] = dr
    df["model_f_t2m"] = dt
    df["model_f_rain"] = df.model_f_rain.fillna(df.clim_rain)
    df["model_f_t2m"] = df.model_f_t2m.fillna(df.clim_t2m)

    for c in ["model_%s_rain" % m for m in "abcdef"]:
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
    names = {"a": "A  ECMWF IFS", "b": "B  ECMWF AIFS", "c": "C  NOAA GFS",
             "d": "D  DWD ICON", "e": "E  EC GEM", "f": "F  Persistence"}
    for m in "abcdef":
        f = df["model_%s_rain" % m]
        print("%-26s%10.2f%9.2f%8.3f" % (names[m], (f - df.truth_rain).mean(),
              rmse(f, df.truth_rain), np.corrcoef(f, df.truth_rain)[0, 1]))

    print("\n--- RMSE by lead time ----------------------------------------")
    print("%-6s%8s%8s%8s%8s%8s%8s" % ("lead", "A", "B", "C", "D", "E", "F"))
    for L, g in df.groupby("lead_time"):
        print("%-6d%8.2f%8.2f%8.2f%8.2f%8.2f%8.2f"
              % (L, *[rmse(g["model_%s_rain" % m], g.truth_rain) for m in "abcdef"]))

    print("\n--- best source per (lead x regime) --------------------------")
    print("%-6s%14s%14s%14s" % ("lead", "active", "break", "normal"))
    for L, gl in df.groupby("lead_time"):
        out_c = []
        for reg in ("active", "break", "normal"):
            g = gl[gl.regime == reg]
            if not len(g):
                out_c.append("-"); continue
            sc = {m.upper(): rmse(g["model_%s_rain" % m], g.truth_rain) for m in "abcde"}
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
