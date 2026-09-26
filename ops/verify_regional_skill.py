"""Verify the operational rainfall weight mix on contiguous held-out dates.

Run after model_training.py. The dashboard uses this scorecard and calibration
curve so its comparisons describe the same regional blend as run_daily.py.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = "abcde"
REGIONAL_SHARE = 0.20
FOLDS = 4


def simplex(v):
    ordered = np.sort(v)[::-1]
    delta = np.cumsum(ordered) - 1
    valid = np.flatnonzero(ordered - delta / np.arange(1, len(v) + 1) > 0)
    last = int(valid[-1]) if len(valid) else len(v) - 1
    return np.maximum(v - delta[last] / (last + 1), 0)


def fit_weights(models, truth, indices):
    if len(indices) < 8:
        return np.full(len(SOURCES), 1 / len(SOURCES))
    member = models[indices]
    target = truth[indices]
    centre = member.mean(axis=1)
    member = member - centre[:, None]
    target = target - centre
    hessian = member.T @ member / len(indices)
    target_cross = member.T @ target / len(indices)
    step = 1 / max(np.linalg.eigvalsh(hessian)[-1], 1e-6)
    weights = np.full(len(SOURCES), 1 / len(SOURCES))
    for _ in range(100):
        weights = simplex(weights - step * (hessian @ weights - target_cross))
    return weights


def scores(truth, forecast, reference):
    error = forecast - truth
    rmse = float(np.mean(error ** 2) ** .5)
    ref_rmse = float(np.mean((reference - truth) ** 2) ** .5)
    return {"rmse": round(rmse, 4), "mae": round(float(np.mean(np.abs(error))), 4),
            "skill": round(1 - rmse / ref_rmse, 4)}


def cross_validated(dates, cells, leads, regimes, truth, members, share, clip_zero):
    days = np.sort(np.unique(dates))
    predicted = np.full(len(truth), np.nan)
    for fold in range(FOLDS):
        first = len(days) * fold // FOLDS
        last = len(days) * (fold + 1) // FOLDS
        held = (dates >= days[first]) & (dates <= days[last - 1])
        train = ~held
        global_weights = {}
        local_weights = {}
        for lead in range(1, 6):
            for regime in np.unique(regimes):
                ix = np.flatnonzero(train & (leads == lead) & (regimes == regime))
                global_weights[(lead, regime)] = fit_weights(members, truth, ix)
            for cell in np.unique(cells):
                ix = np.flatnonzero(train & (leads == lead) & (cells == cell))
                local_weights[(lead, cell)] = fit_weights(members, truth, ix)
        ix = np.flatnonzero(held)
        global_for_rows = np.stack([global_weights[(leads[i], regimes[i])] for i in ix])
        local_for_rows = np.stack([local_weights[(leads[i], cells[i])] for i in ix])
        applied = (1 - share) * global_for_rows + share * local_for_rows
        forecast = (members[ix] * applied).sum(axis=1)
        predicted[ix] = np.maximum(0, forecast) if clip_zero else forecast
    if not np.isfinite(predicted).all():
        raise RuntimeError("verification left some archive rows without a forecast")
    return predicted


def read_archive(fields):
    try:
        return pd.read_parquet(DATA / "predictions.parquet", columns=fields)
    except ImportError:
        import polars as pl
        return pd.DataFrame(pl.read_parquet(DATA / "predictions.parquet",
                                            columns=fields).to_dict(as_series=False))


def main():
    fields = ["date", "cell_id", "lead_time", "regime", "truth_rain"] + [
        "model_%s_rain" % source for source in SOURCES] + ["model_f_rain"]
    frame = read_archive(fields)
    frame = frame.dropna(subset=fields[4:]).reset_index(drop=True)
    dates = frame.date.to_numpy()
    cells = frame.cell_id.to_numpy()
    leads = frame.lead_time.to_numpy()
    regimes = frame.regime.to_numpy()
    truth = frame.truth_rain.to_numpy(dtype=float)
    members = np.column_stack([frame["model_%s_rain" % key].to_numpy(dtype=float)
                               for key in SOURCES])
    reference = frame.model_f_rain.to_numpy(dtype=float)
    predicted = cross_validated(dates, cells, leads, regimes, truth, members,
                                REGIONAL_SHARE, clip_zero=True)

    overall = scores(truth, predicted, reference)
    by_lead = {}
    for lead in range(1, 6):
        mask = leads == lead
        row = scores(truth[mask], predicted[mask], reference[mask])
        member_rmse = [float(np.mean((members[mask, j] - truth[mask]) ** 2) ** .5)
                       for j in range(len(SOURCES))]
        row["gain_pct"] = round(100 * (1 - row["rmse"] / min(member_rmse)), 2)
        by_lead[str(lead)] = row

    by_regime = {}
    for regime in np.unique(regimes):
        mask = regimes == regime
        row = scores(truth[mask], predicted[mask], reference[mask])
        member_rmse = [float(np.mean((members[mask, j] - truth[mask]) ** 2) ** .5)
                       for j in range(len(SOURCES))]
        row["gain_pct"] = round(100 * (1 - row["rmse"] / min(member_rmse)), 2)
        by_regime[str(regime)] = row

    edges = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 80, 100, 150]
    bin_index = np.clip(np.searchsorted(edges, predicted, side="right") - 1,
                        0, len(edges) - 1)
    rates = []
    for index in range(len(edges)):
        mask = bin_index == index
        rates.append(round(float(np.mean(truth[mask] >= 40)), 4) if mask.any()
                     else (rates[-1] if rates else 0.0))

    temp_fields = ["date", "cell_id", "lead_time", "regime", "truth_t2m"] + [
        "model_%s_t2m" % source for source in SOURCES]
    temp_frame = read_archive(temp_fields).dropna(subset=temp_fields[4:]).reset_index(drop=True)
    temp_truth = temp_frame.truth_t2m.to_numpy(dtype=float)
    temp_members = np.column_stack([
        temp_frame["model_%s_t2m" % key].to_numpy(dtype=float) for key in SOURCES])
    temp_predicted = cross_validated(
        temp_frame.date.to_numpy(), temp_frame.cell_id.to_numpy(),
        temp_frame.lead_time.to_numpy(), temp_frame.regime.to_numpy(),
        temp_truth, temp_members, .80, clip_zero=False)
    temp_rmse = float(np.mean((temp_predicted - temp_truth) ** 2) ** .5)

    output = {"method": "four contiguous date blocks; regional share 20% rain, 80% temperature",
              "rows": len(frame), "overall": overall, "by_lead": by_lead,
              "by_regime": by_regime, "pext_curve": {"edges": edges, "p": rates},
              "temperature": {"rows": len(temp_frame), "regional_share": .8,
                              "rmse_c": round(temp_rmse, 4)}}
    path = DATA / "regional_verification.json"
    path.write_text(json.dumps(output, indent=2))
    print("wrote %s: RMSE %.3f over %d held-out rows" %
          (path, overall["rmse"], len(frame)))


if __name__ == "__main__":
    main()
