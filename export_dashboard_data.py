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
from pathlib import Path

import numpy as np
import pandas as pd

import config
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

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


def build_live(wreg_df):
    """
    Today's live run over the national grid.

    run_daily.py fetches every centre's current forecast for all India and
    applies the learned weights. Per-CELL weights are not available for the
    national grid until the national archive finishes training, so each cell
    carries the (regime, lead) weights that were actually used to blend it -
    which is honest: those are the weights this forecast was made with.
    """
    live = pd.read_parquet(DATA / "live_blend.parquet")
    live["valid_date"] = pd.to_datetime(live["valid_date"])

    cells = (live[["cell_id", "lat", "lon", "elevation_m"]]
             .drop_duplicates("cell_id").sort_values(["lat", "lon"]).reset_index(drop=True))
    order = list(cells.cell_id)

    wlook = {}
    for r in wreg_df.itertuples(index=False):
        wlook[(str(r.regime), int(r.lead_time))] = r

    issued = (live.valid_date.min() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    by_lead = {}
    for lead in range(1, 6):
        g = live[live.lead_time == lead].set_index("cell_id").reindex(order)
        if g.blend_rain.isna().all():
            continue
        regime = str(g.regime.mode().iat[0])
        w = wlook.get((regime, lead)) or wlook.get(("normal", lead))

        slice_ = {
            "valid": g.valid_date.iloc[0].strftime("%Y-%m-%d"),
            "regime": regime,
            "rain": r1(g.blend_rain), "t2m": r1(g.blend_t2m), "wind": r1(g.blend_wind),
            "ct2m": r1(g.blend_t2m),          # no climatology on a live run
            "conf": r1(g.confidence),
            "pext": r3(g.prob_heavy),
        }
        for m in BLEND:
            slice_["m" + m] = r1(g["model_%s_rain" % m])
            slice_["t" + m] = r1(g["model_%s_t2m" % m])
        # A live run uses one weight vector per (regime, lead), so it is the
        # same for every cell. Storing 4,645 identical copies per source would
        # be most of the payload for no information.
        slice_["w"] = {m: round(float(getattr(w, "w_%s" % m)) if w else 1.0 / len(BLEND), 3)
                       for m in BLEND}
        by_lead[str(lead)] = slice_

    return cells, order, {issued: by_lead}, issued


def main():
    wreg_df = pd.read_csv(DATA / "weights_by_regime.csv")
    # per-cell weight map from the TRAINED grid. Used for the dominant-share
    # statistic, which describes the verification domain regardless of which
    # grid the live forecast is on.
    wmap = pd.read_csv(DATA / "weight_map.csv")
    live_file = DATA / "live_blend.parquet"
    USE_LIVE = live_file.exists()

    pred = pd.read_parquet(DATA / "predictions.parquet")
    pred["date"] = pd.to_datetime(pred["date"])

    if USE_LIVE:
        cells, order, runs, default_run = build_live(wreg_df)
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
            for lead in range(1, 6):
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

    # India outline, simplified by 00_build_region.py. The mask is a world
    # rectangle with the national rings punched out: filling it with the page
    # background clips the forecast raster to the country instead of leaving a
    # rectangle lying across the Arabian Sea and four neighbours.
    geo = {}
    mask_f = DATA / "india_mask.json"
    if mask_f.exists():
        geo["mask"] = json.loads(mask_f.read_text())
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

    # per-cell dominant source. On the live national grid the trained per-cell
    # weights do not exist yet (that needs the national archive), so each cell
    # reports the regime weights the forecast was actually blended with.
    cell_lead = {}
    for lead in range(1, 6):
        if USE_LIVE:
            sl = runs[default_run].get(str(lead))
            if not sl:
                continue
            # a live run carries one weight vector per lead, shared by every
            # cell, so the dominant source is the same everywhere at that lead
            w = [float(sl["w"][m]) for m in BLEND]
            dom = BLEND[int(np.argmax(w))].upper()
            doms = [dom] * len(order)
            domw = [round(float(max(w)), 3)] * len(order)
        else:
            doms = [wlook[(c, lead)].dominant_model for c in order]
            domw = [round(float(wlook[(c, lead)].dominant_weight), 3) for c in order]
        cell_lead[str(lead)] = {"dom": doms, "domw": domw}

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
            "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        },
        "cells": [
            {"id": r.cell_id, "lat": round(r.lat, 3), "lon": round(r.lon, 3),
             "elev": int(r.elevation_m)}
            for r in cells.itertuples(index=False)
        ],
        "issue_dates": list(runs.keys()),
        "runs": runs,
        "metrics": {
            # `key` is carried explicitly so the dashboard can colour a row by
            # its source rather than parsing a letter out of a display string
            "overall": [
                {"source": r.source, "rmse": round(r.rmse, 3),
                 "mae": round(r.mae, 3), "skill": round(r.skill, 3),
                 "key": (r.source.strip()[0] if r.source.strip()[0] in "ABCDEF" else None)}
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
            "cell_lead": cell_lead,
        },
    }

    out = DATA / "dashboard_data.json"
    txt = json.dumps(payload, separators=(",", ":"))
    out.write_text(txt)
    print("\nwrote %s  (%.0f KB)" % (out, len(txt) / 1024))
    print("  runs: %d issue dates x 5 leads x %d cells" % (len(runs), len(order)))


if __name__ == "__main__":
    main()
