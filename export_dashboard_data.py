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
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).parent
DATA = ROOT / "data"

SOURCES = ["a", "b", "c", "d"]
SOURCE_META = [
    {"key": "A", "name": "Physics NWP", "sub": "IFS/GFS-class dynamical model"},
    {"key": "B", "name": "AI / ML Model", "sub": "GraphCast/Pangu-class data-driven"},
    {"key": "C", "name": "Ensemble Mean", "sub": "Multi-member ensemble average"},
    {"key": "D", "name": "Persistence", "sub": "Naive baseline / lower bound"},
]
N_ISSUE_DATES = 12
EXTREME_MM = 40.0
HEAT_C = 34.0
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


def main():
    pred = pd.read_parquet(DATA / "predictions.parquet")
    pred["date"] = pd.to_datetime(pred["date"])

    cells = (pred[["cell_id", "lat", "lon", "elevation_m"]]
             .drop_duplicates("cell_id")
             .sort_values(["lat", "lon"])
             .reset_index(drop=True))
    order = list(cells.cell_id)
    pos = {c: i for i, c in enumerate(order)}

    wmap = pd.read_csv(DATA / "weight_map.csv")
    wlook = {(r.cell_id, int(r.lead_time)): r for r in wmap.itertuples(index=False)}

    issue_dates = pick_issue_dates(pred, N_ISSUE_DATES)
    print("issue dates exported (%d):" % len(issue_dates))

    runs = {}
    for d0 in issue_dates:
        key = d0.strftime("%Y-%m-%d")
        by_lead = {}
        for lead in range(1, 6):
            valid_date = d0 + pd.Timedelta(days=lead)
            g = pred[(pred.date == valid_date) & (pred.lead_time == lead)]
            g = g.set_index("cell_id").reindex(order)
            if g.blend_rain.isna().any():
                continue

            wa, wb, wc, wd = [], [], [], []
            for c in order:
                w = wlook.get((c, lead))
                wa.append(w.w_a); wb.append(w.w_b); wc.append(w.w_c); wd.append(w.w_d)

            by_lead[str(lead)] = {
                "valid": valid_date.strftime("%Y-%m-%d"),
                "regime": str(g.regime.iloc[0]),
                "rain": r1(g.blend_rain),
                "t2m": r1(g.blend_t2m),
                "ct2m": r1(g.clim_t2m),   # local normal, for the heat anomaly
                "truth": r1(g.truth_rain),
                "conf": r1(g.confidence),
                "pext": r3(g.prob_extreme),
                "ma": r1(g.model_a_rain), "mb": r1(g.model_b_rain),
                "mc": r1(g.model_c_rain), "md": r1(g.model_d_rain),
                "ta": r1(g.model_a_t2m), "tb": r1(g.model_b_t2m),
                "tc": r1(g.model_c_t2m), "td": r1(g.model_d_t2m),
                "wa": r3(wa), "wb": r3(wb), "wc": r3(wc), "wd": r3(wd),
            }
        if len(by_lead) == 5:
            runs[key] = by_lead
            print("  %s  regime=%-7s  T+1 valid %s"
                  % (key, by_lead["1"]["regime"], by_lead["1"]["valid"]))

    # ---- skill panel ------------------------------------------------------
    by_lead_m = pd.read_csv(DATA / "metrics_by_lead.csv")
    by_reg_m = pd.read_csv(DATA / "metrics_by_regime.csv")
    overall = pd.read_csv(DATA / "metrics_overall.csv")
    clf = pd.read_csv(DATA / "metrics_extreme_classifier.csv")
    wreg = pd.read_csv(DATA / "weights_by_regime.csv")
    imp = pd.read_csv(DATA / "feature_importance.csv", index_col=0)

    # ---- dominant-source share per lead (the reliability headline) --------
    share = (wmap.groupby(["lead_time", "dominant_model"]).size().unstack(fill_value=0))
    for m in ["A", "B", "C", "D"]:
        if m not in share.columns:
            share[m] = 0
    share = share[["A", "B", "C", "D"]]
    share_pct = (100 * share.div(share.sum(axis=1), axis=0)).round(1)

    payload = {
        "meta": {
            "region": "Maharashtra, India",
            "bbox": [16.0, 73.0, 21.0, 78.0],
            "cell_deg": CELL_DEG,
            "season": "SW Monsoon (Jun-Aug) 2023",
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
            "overall": [
                {"source": r.source, "rmse": round(r.rmse, 3),
                 "mae": round(r.mae, 3), "skill": round(r.skill, 3)}
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
        },
        "weights": {
            "by_regime_lead": wreg.round(3).to_dict(orient="records"),
            "dominant_share": {
                str(int(lead)): {m: float(share_pct.loc[lead, m]) for m in ["A", "B", "C", "D"]}
                for lead in share_pct.index
            },
            "cell_lead": {
                str(lead): {
                    "dom": [wlook[(c, lead)].dominant_model for c in order],
                    "domw": [round(float(wlook[(c, lead)].dominant_weight), 3) for c in order],
                }
                for lead in range(1, 6)
            },
        },
    }

    out = DATA / "dashboard_data.json"
    txt = json.dumps(payload, separators=(",", ":"))
    out.write_text(txt)
    print("\nwrote %s  (%.0f KB)" % (out, len(txt) / 1024))
    print("  runs: %d issue dates x 5 leads x %d cells" % (len(runs), len(order)))


if __name__ == "__main__":
    main()
