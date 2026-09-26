"""
Step 4 - Bundle trained outputs into the payload the dashboard embeds.

FRAMING NOTE
------------
The training table is indexed by VALID date + lead time. A forecaster does not
think that way - they think in forecast RUNS: "the 06 UTC run of 20 July said
this about T+1 ... T+5". So the export is re-indexed by ISSUE date, pulling
row (date = issue + L, lead_time = L) for each L. That is what makes the
dashboard's lead-time slider mean something: it holds one forecast run fixed
and walks out its horizon, exactly as an operational duty forecaster would.

A subset of issue dates is exported (not all 92) purely to keep the
self-contained HTML small. Dates are chosen to span active / break / normal
monsoon regimes so the demo can show the blend re-weighting as conditions
change.

Output: data/dashboard_data.json
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config
try:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
except ImportError:
    def brier_score_loss(truth, probability):
        return float(np.mean((np.asarray(probability) - np.asarray(truth)) ** 2))

    def roc_auc_score(truth, probability):
        truth = np.asarray(truth, dtype=bool)
        probability = np.asarray(probability)
        order = np.argsort(probability, kind="stable")
        values = probability[order]
        ranks = np.empty(len(order), dtype=float)
        starts = np.r_[0, np.flatnonzero(np.diff(values)) + 1]
        ends = np.r_[starts[1:], len(values)]
        for start, end in zip(starts, ends):
            ranks[order[start:end]] = (start + end + 1) / 2
        positive = truth.sum()
        negative = len(truth) - positive
        return float((ranks[truth].sum() - positive * (positive + 1) / 2) /
                     (positive * negative))

    def average_precision_score(truth, probability):
        truth = np.asarray(truth, dtype=bool)
        probability = np.asarray(probability)
        order = np.argsort(-probability, kind="stable")
        labels = truth[order]
        values = probability[order]
        ends = np.r_[np.flatnonzero(np.diff(values)), len(values) - 1]
        positives = np.cumsum(labels)
        return float(np.sum((positives[ends] / (ends + 1)) *
                            (np.diff(np.r_[0, positives[ends]]) / positives[-1])))


def read_parquet(path):
    try:
        return pd.read_parquet(path)
    except ImportError:
        import polars as pl
        return pd.DataFrame(pl.read_parquet(path).to_dict(as_series=False))

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# Five real forecasting centres enter the blend; persistence is the skill
# reference and carries no weight, so it is listed but flagged.
SOURCES = ["a", "b", "c", "d", "e", "f"]
BLEND = ["a", "b", "c", "d", "e"]
SOURCE_META = [
    {"key": "A", "name": "ECMWF IFS", "sub": "Physics NWP, ECMWF", "blend": True},
    {"key": "B", "name": "ECMWF AIFS", "sub": "AI model, ECMWF", "blend": True},
    {"key": "C", "name": "NOAA GFS", "sub": "Physics NWP, NOAA", "blend": True},
    {"key": "D", "name": "DWD ICON", "sub": "Physics NWP, DWD", "blend": True},
    {"key": "E", "name": "EC GEM", "sub": "Physics NWP, Env. Canada", "blend": True},
    {"key": "F", "name": "Persistence", "sub": "Skill reference, not blended", "blend": False},
]
N_ISSUE_DATES = 12
EXTREME_MM = 40.0
HEAT_C = 34.0
HIGH_WIND_KMH = 40.0
CELL_DEG = 0.5


def r1(x):
    return [round(float(v), 1) for v in x]


def r3(x):
    return [round(float(v), 3) for v in x]


def r4(x):
    return [round(float(v), 4) for v in x]


def pick_issue_dates(pred, n):
    """Issue dates spanning all three regimes, biased toward eventful spells."""
    days = pred.drop_duplicates("date")[["date", "regime"]].sort_values("date")
    last = days.date.max()
    valid = days[days.date <= last - pd.Timedelta(days=5)]

    # rank days by how much heavy rain falls in their T+1..T+5 window, so the
    # demo defaults to runs that actually have something to show
    daily_ext = pred[pred.lead_time == 1].groupby("date").is_extreme.sum()
    score = {}
    for d in valid.date:
        window = [d + pd.Timedelta(days=k) for k in range(1, 6)]
        score[d] = int(sum(daily_ext.get(w, 0) for w in window))

    chosen = []
    for reg, grp in valid.groupby("regime"):
        ranked = sorted(grp.date, key=lambda d: -score[d])
        chosen.extend(ranked[: max(2, n // 3)])
    # top up by eventfulness, keep chronological
    extra = sorted(valid.date, key=lambda d: -score[d])
    for d in extra:
        if len(chosen) >= n:
            break
        if d not in chosen:
            chosen.append(d)
    return sorted(set(chosen))[:n]


def build_live():
    """
    Today's live run over the national grid.

    run_daily.py fetches every centre's current forecast for all India and
    applies the learned weights. The saved live product carries the exact
    weights applied at every cell for rainfall, temperature and wind.
    """
    live = read_parquet(DATA / "live_blend.parquet")
    live["valid_date"] = pd.to_datetime(live["valid_date"])

    # the same file run_daily.py blends with, so the page cannot disagree
    # with the numbers it is displaying
    wsets = {}
    wf = DATA / "blend_weight_sets.json"
    if wf.exists():
        wsets = json.loads(wf.read_text(encoding="utf-8"))

    cells = (live[["cell_id", "lat", "lon", "elevation_m"]]
             .drop_duplicates("cell_id").sort_values(["lat", "lon"]).reset_index(drop=True))
    order = list(cells.cell_id)

    issued_at = (live.valid_date - pd.to_timedelta(live.lead_time, unit="D")).min()
    issued = issued_at.strftime("%Y-%m-%d")
    by_lead = {}
    for lead in range(0, 6):
        g = live[live.lead_time == lead].set_index("cell_id").reindex(order)
        if g.blend_rain.isna().all():
            continue
        regime = str(g.regime.mode().iat[0])
        slice_ = {
            "valid": g.valid_date.iloc[0].strftime("%Y-%m-%d"),
            "regime": regime,
            "rain": r1(g.blend_rain), "t2m": r1(g.blend_t2m), "wind": r1(g.blend_wind),
            # No climatology exists for a future date, so the old code stored a
            # byte-identical copy of t2m here. The dashboard reads a missing
            # ct2m as "no climatology" already, so the copy is pure weight.
            "conf": r1(g.confidence),
            "pext": r3(g.prob_heavy),
        }
        for m in BLEND:
            slice_["m" + m] = r1(g["model_%s_rain" % m])
            slice_["t" + m] = r1(g["model_%s_t2m" % m])
            slice_["u" + m] = r1(g["model_%s_wind" % m])
        # Keep run-wide vectors as a fallback for older live products.
        wv = {}
        for var in ("rain", "t2m", "wind"):
            byvar = wsets.get(str(max(1, lead)), {})
            table = byvar.get(var) or byvar.get("rain") or {}
            vec = table.get(regime) or table.get("_all")
            if vec and len(vec) == len(BLEND):
                wv[var] = {m: round(float(vec[i]), 3) for i, m in enumerate(BLEND)}
        if wv:
            slice_["wv"] = wv
        # These are the weights actually applied to each live forecast row,
        # including local transfer and any missing-member renormalisation.
        applied = {}
        for var in ("rain", "t2m", "wind"):
            columns = ["weight_%s_%s" % (var, m) for m in BLEND]
            if all(col in g.columns for col in columns):
                applied[var] = {m: r4(g["weight_%s_%s" % (var, m)]) for m in BLEND}
        if applied:
            slice_["wa"] = applied
        by_lead[str(lead)] = slice_

    return cells, order, {issued: by_lead}, issued


def regional_leaders(cells, live):
    """Compact trained-map leaders, separate from the applied live weights."""
    maps = {"rain": DATA / "weight_map.csv", "t2m": DATA / "weight_map_t2m.csv"}
    if not maps["rain"].exists():
        return {}
    training = pd.read_csv(maps["rain"]).drop_duplicates("cell_id")
    if live:
        live_xy = cells[["lat", "lon"]].to_numpy(dtype=float)
        train_xy = training[["lat", "lon"]].to_numpy(dtype=float)
        idx = np.argmin(((live_xy[:, None, :] - train_xy[None, :, :]) ** 2).sum(axis=2), axis=1)
        nearest = training.cell_id.to_numpy()[idx]
    else:
        nearest = cells.cell_id.to_numpy()

    result = {}
    for var, path in maps.items():
        if not path.exists():
            continue
        table = pd.read_csv(path)
        result[var] = {}
        for lead in range(6):
            selected = table[table.lead_time == max(1, lead)].set_index("cell_id")
            rows = selected.reindex(nearest)
            result[var][str(lead)] = {
                "dom": rows.dominant_model.fillna("A").tolist(),
                "domw": [round(float(w), 4) if pd.notna(w) else .2
                         for w in rows.dominant_weight],
            }
    return result


def main():
    wreg_df = pd.read_csv(DATA / "weights_by_regime.csv")
    # per-cell weight map from the TRAINED grid. Used for the dominant-share
    # statistic, which describes the verification domain regardless of which
    # grid the live forecast is on.
    wmap = pd.read_csv(DATA / "weight_map.csv")
    live_file = DATA / "live_blend.parquet"
    USE_LIVE = live_file.exists()

    pred = read_parquet(DATA / "predictions.parquet")
    pred["date"] = pd.to_datetime(pred["date"])

    if USE_LIVE:
        cells, order, runs, default_run = build_live()
        print("LIVE national run %s: %d cells x %d leads"
              % (default_run, len(order), len(runs[default_run])))
    else:
        cells = (pred[["cell_id", "lat", "lon", "elevation_m"]]
                 .drop_duplicates("cell_id").sort_values(["lat", "lon"]).reset_index(drop=True))
        order = list(cells.cell_id)
        wlook = {(r.cell_id, int(r.lead_time)): r for r in wmap.itertuples(index=False)}
        runs, default_run = {}, None

        for d0 in pick_issue_dates(pred, N_ISSUE_DATES):
            key = d0.strftime("%Y-%m-%d")
            by_lead = {}
            for lead in range(0, 6):
                valid_date = d0 + pd.Timedelta(days=lead)
                g = pred[(pred.date == valid_date) & (pred.lead_time == lead)]
                g = g.set_index("cell_id").reindex(order)
                if g.blend_rain.isna().any():
                    continue
                weights = {m: [] for m in BLEND}
                for c in order:
                    w = wlook.get((c, lead))
                    for m in BLEND:
                        weights[m].append(getattr(w, "w_%s" % m))
                slice_ = {
                    "valid": valid_date.strftime("%Y-%m-%d"),
                    "regime": str(g.regime.iloc[0]),
                    "rain": r1(g.blend_rain), "t2m": r1(g.blend_t2m),
                    "ct2m": r1(g.clim_t2m), "truth": r1(g.truth_rain),
                    "conf": r1(g.confidence), "pext": r3(g.prob_extreme),
                }
                for m in SOURCES:
                    slice_["m" + m] = r1(g["model_%s_rain" % m])
                    slice_["t" + m] = r1(g["model_%s_t2m" % m])
                for m in BLEND:
                    slice_["w" + m] = r3(weights[m])
                by_lead[str(lead)] = slice_
            if len(by_lead) == 5:
                runs[key] = by_lead
                default_run = default_run or key
        print("archived runs exported: %d" % len(runs))

    # ---- skill panel ------------------------------------------------------
    by_lead_m = pd.read_csv(DATA / "metrics_by_lead.csv")
    by_reg_m = pd.read_csv(DATA / "metrics_by_regime.csv")
    overall = pd.read_csv(DATA / "metrics_overall.csv")
    clf = pd.read_csv(DATA / "metrics_extreme_classifier.csv")
    wreg = pd.read_csv(DATA / "weights_by_regime.csv")
    imp = pd.read_csv(DATA / "feature_importance.csv", index_col=0)

    # ---- dominant-source share per lead (the reliability headline) --------
    keys = [m.upper() for m in BLEND]
    share = (wmap.groupby(["lead_time", "dominant_model"]).size().unstack(fill_value=0))
    for m in keys:
        if m not in share.columns:
            share[m] = 0
    share = share[keys]
    share_pct = (100 * share.div(share.sum(axis=1), axis=0)).round(1)

    # ---- empirical P(heavy | blended amount), for the live panel ----------
    # The trained LightGBM flagger cannot run in a browser, so the live view
    # needs a lookup it CAN evaluate. This is the observed frequency of a
    # >=40 mm breach within each band of blended rainfall, measured on the
    # out-of-sample predictions - an honest empirical curve, not a guess.
    edges = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 80, 100, 150, 10**6]
    curve = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = pred[(pred.blend_rain >= lo) & (pred.blend_rain < hi)]
        curve.append(round(float(sel.is_extreme.mean()), 4) if len(sel) >= 25 else None)
    # carry the last measured value forward across any thin bands
    last = 0.0
    for i, v in enumerate(curve):
        if v is None:
            curve[i] = last
        else:
            last = v

    verified_file = DATA / "regional_verification.json"
    verification_method = None
    if verified_file.exists():
        verified = json.loads(verified_file.read_text())
        verification_method = verified["method"]
        selected = overall.source == "Linear blend (weights)"
        for key in ("rmse", "mae", "skill"):
            overall.loc[selected, key] = verified["overall"][key]
        for lead, row in verified["by_lead"].items():
            selected = by_lead_m.lead_time == int(lead)
            for source_key, target_key in (("rmse", "blend"), ("mae", "mae_blend"),
                                           ("skill", "skill_blend"), ("gain_pct", "gain_pct")):
                by_lead_m.loc[selected, target_key] = row[source_key]
        for regime, row in verified["by_regime"].items():
            selected = by_reg_m.regime == regime
            for source_key, target_key in (("rmse", "blend"), ("skill", "skill_blend"),
                                           ("gain_pct", "gain_pct")):
                by_reg_m.loc[selected, target_key] = row[source_key]
        edges = verified["pext_curve"]["edges"] + [10**6]
        curve = verified["pext_curve"]["p"]

    # India outline, simplified by 00_build_region.py. The mask is a world
    # rectangle with the national rings punched out: filling it with the page
    # background clips the forecast raster to the country instead of leaving a
    # rectangle lying across the Arabian Sea and four neighbours.
    geo = {}
    mask_f = DATA / "india_mask.json"
    if mask_f.exists():
        geo["mask"] = json.loads(mask_f.read_text())

    # Trim coordinate precision. 4 dp is ~11 m at this latitude, which is far
    # finer than a 28 km grid or any zoom the map allows, and it removes the
    # single largest block of redundant bytes in the payload.
    def trim(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, list):
            return [trim(x) for x in o]
        if isinstance(o, dict):
            return {k: trim(v) for k, v in o.items()}
        return o
    geo = trim(geo)
    places_f = DATA / "places.json"
    if places_f.exists():
        geo["places"] = json.loads(places_f.read_text())

    # cell size must describe the grid the FORECAST is on, not the coarser
    # grid the weights were trained on
    for name in ("grid_cells_live.json", "grid_cells.json"):
        gf = DATA / name
        if gf.exists():
            g = json.loads(gf.read_text())
            geo["bbox"] = g["bbox"]
            geo["grid_deg"] = g["grid_deg"]
            break

    payload = {
        "geo": geo,
        "meta": {
            "team": config.TEAM_NAME,
            "institute": config.TEAM_INSTITUTE,
            "region": "India" if USE_LIVE else "Maharashtra, India",
            # the map frames itself on this; it must follow the actual grid
            "bbox": (geo.get("bbox") or [6.5, 68.0, 37.5, 97.5]) if USE_LIVE
                    else [16.0, 73.0, 21.0, 78.0],
            "cell_deg": (geo.get("grid_deg") or CELL_DEG) if USE_LIVE else CELL_DEG,
            "live": USE_LIVE,
            "issued": default_run,
            "high_wind_kmh": HIGH_WIND_KMH,
            "season": ("Live run " + str(default_run)) if USE_LIVE
                      else "SW Monsoon (Jun-Aug) 2023",
            "truth_source": "ERA5 reanalysis",
            "n_cells": len(order),
            "n_days": int(pred.date.nunique()),
            "n_rows": int(len(pred)),
            "extreme_mm": EXTREME_MM,
            "heat_c": HEAT_C,
            "sources": SOURCE_META,
            "generated": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y-%m-%d %H:%M"),
        },
        "cells": [
            {"id": r.cell_id, "lat": round(r.lat, 3), "lon": round(r.lon, 3),
             "elev": int(r.elevation_m)}
            for r in cells.itertuples(index=False)
        ],
        "issue_dates": list(runs.keys()),
        "runs": runs,
        "metrics": {
            "verification_method": verification_method,
            # `key` is carried explicitly so the dashboard can colour a row by
            # its source rather than parsing a letter out of a display string
            "overall": [
                {"source": r.source, "rmse": round(r.rmse, 3),
                 "mae": round(r.mae, 3), "skill": round(r.skill, 3),
                 # only the "A  ECMWF IFS" rows are models; a bare first
                 # letter would tag "Equal-weight mean" as member E
                 "key": (re.match(r"^([A-F])\s\s", r.source.strip()).group(1)
                         if re.match(r"^([A-F])\s\s", r.source.strip()) else None)}
                for r in overall.itertuples(index=False)
            ],
            "by_lead": by_lead_m.round(3).to_dict(orient="records"),
            "by_regime": by_reg_m.round(3).to_dict(orient="records"),
            "classifier": clf.round(3).to_dict(orient="records"),
            "classifier_headline": {
                "auc": round(float(roc_auc_score(pred.is_extreme, pred.prob_extreme)), 4),
                "pr_auc": round(float(average_precision_score(pred.is_extreme, pred.prob_extreme)), 4),
                "brier": round(float(brier_score_loss(pred.is_extreme, pred.prob_extreme)), 4),
                "base_rate": round(float(pred.is_extreme.mean()), 4),
                "positives": int(pred.is_extreme.sum()),
            },
            "feature_importance": [
                {"feature": k, "importance": round(float(v), 1)}
                for k, v in imp.importance.head(10).items()
            ],
            # lower edge of each band, and the observed breach frequency in it
            "pext_curve": {"edges": edges[:-1], "p": curve},
        },
        "weights": {
            "by_regime_lead": wreg.round(3).to_dict(orient="records"),
            "dominant_share": {
                str(int(lead)): {m: float(share_pct.loc[lead, m]) for m in keys}
                for lead in share_pct.index
            },
            "regional_lead": regional_leaders(cells, USE_LIVE),
        },
    }

    out = DATA / "dashboard_data.json"
    txt = json.dumps(payload, separators=(",", ":"))
    out.write_text(txt)
    print("\nwrote %s  (%.0f KB)" % (out, len(txt) / 1024))
    print("  runs: %d issue dates x 5 leads x %d cells" % (len(runs), len(order)))


if __name__ == "__main__":
    main()
