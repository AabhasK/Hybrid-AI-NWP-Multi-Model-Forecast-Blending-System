"""
Step 3 - The blending model layer.
=================================================================
SIH26081 - Hybrid AI-NWP Multi-Model Forecast Blending

Three trained artefacts:

  1. BLENDER (LightGBM regressor)      - predicts the corrected rainfall value
                                         directly from the four source forecasts
                                         plus context (lead, regime, terrain).
                                         A second regressor does 2m temperature.

  2. RELIABILITY WEIGHTS (constrained  - per (grid cell x lead time) and per
     non-negative least squares)         (regime x lead time), the sum-to-one
                                         non-negative weights that best combine
                                         the four sources. This is what the
                                         "model reliability map" deliverable
                                         plots, and what makes the blend
                                         interpretable rather than a black box.

  3. EXTREME FLAGGER (LightGBM         - P(rainfall >= 40mm) from the blended
     classifier)                         value, ensemble spread and regime.

EVALUATION PROTOCOL
-------------------
All reported numbers are OUT-OF-SAMPLE. The 92-day season is cut into 4
contiguous time blocks; each block is predicted by a model trained only on the
other three. Blocking by time (not random rows) is essential here - adjacent
days and neighbouring cells are strongly correlated, so a random split would
leak the answer across the fold boundary and inflate every metric.

Skill score is computed against Model D (persistence), the standard operational
reference:   SS = 1 - RMSE_model / RMSE_persistence

Run:  python model_training.py
"""

from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

SOURCES = ["a", "b", "c", "d"]
SOURCE_LABEL = {
    "a": "Model A - Physics NWP",
    "b": "Model B - AI/ML",
    "c": "Model C - Ensemble Mean",
    "d": "Model D - Persistence",
}
N_FOLDS = 4
EXTREME_MM = 40.0
SEED = 20260918

CAT_FEATURES = ["season", "regime"]


# ==========================================================================
# metrics
# ==========================================================================
def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def skill(y, p, ref):
    """Murphy skill score vs a reference forecast. 1.0 = perfect, 0 = no gain."""
    r_ref = rmse(y, ref)
    return float(1.0 - rmse(y, p) / r_ref) if r_ref > 0 else 0.0


# ==========================================================================
# features
# ==========================================================================
def diagnose_regime_from_forecasts(df):
    """
    Regime state as it would actually be known AT ISSUE TIME.

    The `regime` / `domain_rain_z` columns in the training table are diagnosed
    from ERA5 truth on the valid date. They are perfectly fine for stratifying a
    report, but feeding them to the model would be target leakage - they are a
    function of the very rainfall field we are predicting.

    Operationally you diagnose the active/break state from the forecast fields
    themselves. So we recompute the domain-mean anomaly from the mean of the
    three skilful sources (A, B, C) for that (date, lead) pair, which a
    forecaster genuinely has in hand, and threshold that instead.
    """
    src = ["model_a_rain", "model_b_rain", "model_c_rain"]
    dom = df.groupby(["date", "lead_time"])[src].transform("mean").mean(axis=1)
    z = (dom - dom.mean()) / dom.std()
    reg = pd.Series(
        np.where(z >= 0.50, "active", np.where(z <= -0.50, "break", "normal")),
        index=df.index,
    )

    # transition flag: did the diagnosed state change vs the previous calendar
    # day at the same lead? (shifted within each cell x lead series)
    key = df[["cell_id", "lead_time"]].copy()
    key["reg"] = reg.values
    key["date"] = df.date.values
    key = key.sort_values(["cell_id", "lead_time", "date"])
    prev = key.groupby(["cell_id", "lead_time"]).reg.shift(1)
    trans = (key.reg != prev.fillna(key.reg)).reindex(df.index)
    return z, reg, trans.astype(int)


def build_features(df):
    """Source forecasts + spread/consensus statistics + spatio-temporal context."""
    X = pd.DataFrame(index=df.index)

    for m in SOURCES:
        X["rain_%s" % m] = df["model_%s_rain" % m]
        X["t2m_%s" % m] = df["model_%s_t2m" % m]

    rain_cols = [df["model_%s_rain" % m] for m in SOURCES]
    stack = np.vstack([c.values for c in rain_cols])

    # Ensemble spread is the single most informative uncertainty predictor:
    # when the four sources disagree, none of them should be trusted much.
    X["rain_mean"] = stack.mean(axis=0)
    X["rain_spread"] = stack.std(axis=0)
    X["rain_range"] = stack.max(axis=0) - stack.min(axis=0)
    X["rain_median"] = np.median(stack, axis=0)
    # anchor = plain mean of the three skilful sources; persistence excluded.
    # This is the baseline the model learns a CORRECTION to (see ANCHOR note).
    X["rain_anchor"] = stack[:3].mean(axis=0)

    tstack = np.vstack([df["model_%s_t2m" % m].values for m in SOURCES])
    X["t2m_mean"] = tstack.mean(axis=0)
    X["t2m_spread"] = tstack.std(axis=0)
    X["t2m_anchor"] = tstack[:3].mean(axis=0)

    X["lead_time"] = df["lead_time"]
    X["lat"] = df["lat"]
    X["lon"] = df["lon"]
    X["elevation_m"] = df["elevation_m"]
    X["clim_rain"] = df["clim_rain"]
    X["clim_t2m"] = df["clim_t2m"]

    # Forecast-diagnosed regime state - available at issue time, no leakage.
    # `doy` is deliberately NOT a feature: with contiguous time-block CV the
    # held-out days fall outside the training day range entirely, and gradient
    # boosted trees cannot extrapolate past a split they have never seen. The
    # climatology columns carry the seasonal signal in a way that does transfer.
    z, reg, trans = diagnose_regime_from_forecasts(df)
    X["fcst_domain_z"] = z
    X["fcst_regime_transition"] = trans
    X["season"] = df["season"].astype("category")
    X["regime"] = pd.Categorical(reg, categories=["active", "break", "normal"])
    return X


def time_blocks(dates, n_folds):
    """Contiguous calendar blocks - NOT random rows. See EVALUATION PROTOCOL."""
    uniq = pd.DatetimeIndex(sorted(pd.to_datetime(pd.unique(dates))))
    return [pd.DatetimeIndex(b) for b in np.array_split(uniq, n_folds)]


# ==========================================================================
# 1 + 3. LightGBM blenders and extreme flagger, via blocked CV
# ==========================================================================
REG_PARAMS = dict(
    objective="regression",
    n_estimators=600,
    learning_rate=0.045,
    num_leaves=48,
    min_child_samples=40,
    subsample=0.85,
    subsample_freq=1,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    random_state=SEED,
    n_jobs=-1,
    verbose=-1,
)

CLF_PARAMS = dict(
    objective="binary",
    n_estimators=450,
    learning_rate=0.05,
    num_leaves=32,
    min_child_samples=50,
    subsample=0.85,
    subsample_freq=1,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    random_state=SEED,
    n_jobs=-1,
    verbose=-1,
)


def run_blocked_cv(df, X, blocks):
    """
    Out-of-fold predictions for every row: rainfall, temperature, P(extreme).

    ANCHOR / RESIDUAL TARGET
    -----------------------
    The regressors are trained on  (truth - anchor)  rather than on truth
    itself, where the anchor is the mean of the three skilful sources. Two
    reasons, both of which bite hard with time-blocked validation:

      * Boosted trees cannot extrapolate. Predicting the LEVEL means a held-out
        June block (hotter than anything in the July-August training data) is
        clipped to the largest leaf value ever learned. Predicting a small,
        zero-centred CORRECTION removes the problem - the level arrives via the
        anchor, which already has it.
      * It is the standard Model Output Statistics formulation: learn the
        systematic error of the sources, not the weather itself.

    PER-LEAD MODELS
    ---------------
    A separate blender per lead time. The optimal combination at day 1 (trust
    the sharp physics model) is a different function from day 5 (trust the
    AI model and the ensemble mean), and one shared model averages the two
    into something worse than either.
    """
    oof_rain = np.full(len(df), np.nan)
    oof_t2m = np.full(len(df), np.nan)
    oof_prob = np.full(len(df), np.nan)

    leads = sorted(df.lead_time.unique())
    for lead in leads:
        lead_mask = (df.lead_time == lead).values
        for k, block in enumerate(blocks, start=1):
            in_block = df.date.isin(block).values
            te = lead_mask & in_block
            tr = lead_mask & ~in_block

            Xtr, Xte = X[tr], X[te]
            anchor_tr, anchor_te = X.rain_anchor[tr], X.rain_anchor[te]
            tanch_tr, tanch_te = X.t2m_anchor[tr], X.t2m_anchor[te]

            r = lgb.LGBMRegressor(**REG_PARAMS)
            r.fit(Xtr, df.truth_rain[tr] - anchor_tr, categorical_feature=CAT_FEATURES)
            oof_rain[te] = anchor_te + r.predict(Xte)

            t = lgb.LGBMRegressor(**REG_PARAMS)
            t.fit(Xtr, df.truth_t2m[tr] - tanch_tr, categorical_feature=CAT_FEATURES)
            oof_t2m[te] = tanch_te + t.predict(Xte)

            # The flagger consumes the blended value, so it must be fed one
            # produced the same way it will be in deployment.
            Xc_tr = Xtr.copy()
            Xc_tr["blend_rain"] = anchor_tr + r.predict(Xtr)
            Xc_te = Xte.copy()
            Xc_te["blend_rain"] = oof_rain[te]

            c = lgb.LGBMClassifier(**CLF_PARAMS)
            c.fit(Xc_tr, df.is_extreme[tr], categorical_feature=CAT_FEATURES)
            oof_prob[te] = c.predict_proba(Xc_te)[:, 1]
        print("  lead %dd: %d folds fitted (%d rows scored out-of-sample)"
              % (lead, len(blocks), lead_mask.sum()))

    assert not np.isnan(oof_rain).any(), "every row must receive an out-of-fold prediction"
    return np.clip(oof_rain, 0.0, None), oof_t2m, oof_prob


def fit_final_models(df, X):
    """Full-data per-lead models for export / deployment."""
    rain_models, t2m_models, clf_models = {}, {}, {}
    for lead in sorted(df.lead_time.unique()):
        m = (df.lead_time == lead).values
        Xl = X[m]
        r = lgb.LGBMRegressor(**REG_PARAMS)
        r.fit(Xl, df.truth_rain[m] - X.rain_anchor[m], categorical_feature=CAT_FEATURES)
        t = lgb.LGBMRegressor(**REG_PARAMS)
        t.fit(Xl, df.truth_t2m[m] - X.t2m_anchor[m], categorical_feature=CAT_FEATURES)
        Xc = Xl.copy()
        Xc["blend_rain"] = X.rain_anchor[m] + r.predict(Xl)
        c = lgb.LGBMClassifier(**CLF_PARAMS)
        c.fit(Xc, df.is_extreme[m], categorical_feature=CAT_FEATURES)
        rain_models[int(lead)], t2m_models[int(lead)], clf_models[int(lead)] = r, t, c
    return rain_models, t2m_models, clf_models


# ==========================================================================
# 2. Constrained weight solver
# ==========================================================================
def solve_weights(F, y, penalty=25.0):
    """
    Non-negative weights summing to 1 that minimise ||F w - y||.

    scipy's nnls handles w >= 0. The sum-to-one constraint is imposed by
    appending a heavily-weighted row of ones to the system, so the solver pays
    a large cost for any deviation from sum(w) = 1. Cheap, stable, and it never
    fails to return a usable answer - which matters for 605 independent solves.
    """
    if len(y) < 8:
        return np.full(F.shape[1], 1.0 / F.shape[1])
    A = np.vstack([F, penalty * np.ones((1, F.shape[1]))])
    b = np.concatenate([y, [penalty]])
    try:
        w, _ = nnls(A, b)
    except Exception:
        return np.full(F.shape[1], 1.0 / F.shape[1])
    s = w.sum()
    return w / s if s > 1e-9 else np.full(F.shape[1], 1.0 / F.shape[1])


def weights_by(df, keys):
    rows = []
    for key, g in df.groupby(keys, observed=True):
        F = np.column_stack([g["model_%s_rain" % m].values for m in SOURCES])
        w = solve_weights(F, g.truth_rain.values)
        rec = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        for m, wi in zip(SOURCES, w):
            rec["w_%s" % m] = round(float(wi), 4)
        rec["dominant_model"] = SOURCES[int(np.argmax(w))].upper()
        rec["dominant_weight"] = round(float(w.max()), 4)
        rec["n_samples"] = int(len(g))
        rows.append(rec)
    return pd.DataFrame(rows)


# ==========================================================================
# reporting
# ==========================================================================
def score_table(g, blend_col="blend_rain"):
    ref = g["model_d_rain"]
    out = {}
    for m in SOURCES:
        p = g["model_%s_rain" % m]
        out[SOURCE_LABEL[m]] = dict(rmse=rmse(g.truth_rain, p), mae=mae(g.truth_rain, p),
                                    skill=skill(g.truth_rain, p, ref))
    p = g[blend_col]
    out["BLENDED (ours)"] = dict(rmse=rmse(g.truth_rain, p), mae=mae(g.truth_rain, p),
                                 skill=skill(g.truth_rain, p, ref))
    return out


def print_scores(title, table):
    print("\n%s" % title)
    print("%-28s%10s%10s%10s" % ("forecast source", "RMSE", "MAE", "skill"))
    print("-" * 58)
    for name, s in table.items():
        mark = "  <<<" if name.startswith("BLENDED") else ""
        print("%-28s%10.3f%10.3f%10.3f%s" % (name, s["rmse"], s["mae"], s["skill"], mark))


# ==========================================================================
def main():
    print("=" * 66)
    print(" SIH26081 - Hybrid AI-NWP Multi-Model Forecast Blending")
    print(" Region: Maharashtra (16-21N, 73-78E) | SW monsoon Jun-Aug 2023")
    print("=" * 66)

    df = pd.read_parquet(DATA / "forecasts.parquet")
    print("\ntraining table: %d rows, %d cells, %d days, leads %s"
          % (len(df), df.cell_id.nunique(), df.date.nunique(), sorted(df.lead_time.unique())))
    print("regime mix: %s" % df.drop_duplicates("date").regime.value_counts().to_dict())

    X = build_features(df)
    blocks = time_blocks(df.date, N_FOLDS)
    print("\n--- blocked time-series CV (%d contiguous folds) ---" % N_FOLDS)
    oof_rain, oof_t2m, oof_prob = run_blocked_cv(df, X, blocks)

    df["blend_rain"] = oof_rain
    df["blend_t2m"] = oof_t2m
    df["prob_extreme"] = oof_prob

    # Forecast confidence shown in the dashboard popup. Derived from relative
    # ensemble spread: when the four sources agree the blend is trustworthy,
    # when they diverge it is not. Normalised by (mean + 2mm) so that tiny
    # absolute disagreements on a dry day do not read as low confidence.
    rel_spread = X["rain_spread"] / (X["rain_mean"].abs() + 2.0)
    df["confidence"] = (100.0 * np.exp(-1.6 * rel_spread)).clip(35, 99).round(1)

    # ---------------- headline metrics --------------------------------
    print_scores("=== OVERALL (all leads, all regimes, out-of-sample) ===", score_table(df))

    best_single = min(rmse(df.truth_rain, df["model_%s_rain" % m]) for m in SOURCES[:3])
    blend_rmse = rmse(df.truth_rain, df.blend_rain)
    print("\n  >> blend RMSE %.3f mm vs best single model %.3f mm  =  %.1f%% reduction"
          % (blend_rmse, best_single, 100 * (1 - blend_rmse / best_single)))
    print("  >> skill score vs persistence baseline: %.3f"
          % skill(df.truth_rain, df.blend_rain, df.model_d_rain))

    # ---------------- by lead time ------------------------------------
    print("\n=== RMSE by LEAD TIME (mm) ===")
    print("%-6s%9s%9s%9s%9s%11s%9s" % ("lead", "A", "B", "C", "D", "BLEND", "gain%"))
    print("-" * 62)
    rows_lead = []
    for lead, g in df.groupby("lead_time"):
        vals = [rmse(g.truth_rain, g["model_%s_rain" % m]) for m in SOURCES]
        b = rmse(g.truth_rain, g.blend_rain)
        gain = 100 * (1 - b / min(vals[:3]))
        print("%-6d%9.3f%9.3f%9.3f%9.3f%11.3f%9.1f" % (lead, *vals, b, gain))
        rows_lead.append(dict(lead_time=lead,
                              **{"model_%s" % m: round(v, 4) for m, v in zip(SOURCES, vals)},
                              blend=round(b, 4),
                              mae_blend=round(mae(g.truth_rain, g.blend_rain), 4),
                              skill_blend=round(skill(g.truth_rain, g.blend_rain, g.model_d_rain), 4),
                              gain_pct=round(gain, 2)))
    by_lead = pd.DataFrame(rows_lead)

    # ---------------- by regime ---------------------------------------
    print("\n=== RMSE by WEATHER REGIME (mm) ===")
    print("%-10s%9s%9s%9s%9s%11s%9s" % ("regime", "A", "B", "C", "D", "BLEND", "gain%"))
    print("-" * 66)
    rows_reg = []
    for reg, g in df.groupby("regime"):
        vals = [rmse(g.truth_rain, g["model_%s_rain" % m]) for m in SOURCES]
        b = rmse(g.truth_rain, g.blend_rain)
        gain = 100 * (1 - b / min(vals[:3]))
        print("%-10s%9.3f%9.3f%9.3f%9.3f%11.3f%9.1f" % (reg, *vals, b, gain))
        rows_reg.append(dict(regime=reg,
                             **{"model_%s" % m: round(v, 4) for m, v in zip(SOURCES, vals)},
                             blend=round(b, 4),
                             skill_blend=round(skill(g.truth_rain, g.blend_rain, g.model_d_rain), 4),
                             gain_pct=round(gain, 2), n=len(g)))
    by_regime = pd.DataFrame(rows_reg)

    # ---------------- temperature -------------------------------------
    print("\n=== 2m TEMPERATURE RMSE (degC) ===")
    tvals = {SOURCE_LABEL[m]: rmse(df.truth_t2m, df["model_%s_t2m" % m]) for m in SOURCES}
    tvals["BLENDED (ours)"] = rmse(df.truth_t2m, df.blend_t2m)
    for k, v in tvals.items():
        print("  %-28s%8.3f" % (k, v))

    # ---------------- extreme flagger ---------------------------------
    print("\n=== EXTREME RAINFALL FLAGGER (>= %.0f mm/day) ===" % EXTREME_MM)
    auc = roc_auc_score(df.is_extreme, df.prob_extreme)
    ap = average_precision_score(df.is_extreme, df.prob_extreme)
    brier = brier_score_loss(df.is_extreme, df.prob_extreme)
    base = df.is_extreme.mean()
    print("  positives          : %d / %d  (%.2f%% base rate)" % (df.is_extreme.sum(), len(df), 100 * base))
    print("  ROC-AUC            : %.4f" % auc)
    print("  PR-AUC (avg prec.) : %.4f   (%.1fx over base rate)" % (ap, ap / base))
    print("  Brier score        : %.4f" % brier)
    print("  %-12s%10s%10s%10s" % ("threshold", "precision", "recall", "F1"))
    clf_rows = []
    for thr in (0.20, 0.30, 0.40, 0.50, 0.60):
        pred = (df.prob_extreme >= thr).astype(int)
        tp = int(((pred == 1) & (df.is_extreme == 1)).sum())
        fp = int(((pred == 1) & (df.is_extreme == 0)).sum())
        fn = int(((pred == 0) & (df.is_extreme == 1)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        print("  %-12.2f%10.3f%10.3f%10.3f" % (thr, prec, rec, f1))
        clf_rows.append(dict(threshold=thr, precision=round(prec, 4),
                             recall=round(rec, 4), f1=round(f1, 4), tp=tp, fp=fp, fn=fn))

    # ---------------- weight maps -------------------------------------
    print("\n--- solving constrained blend weights ---")
    wmap = weights_by(df, ["cell_id", "lead_time"])
    wmap = wmap.merge(df[["cell_id", "lat", "lon", "elevation_m"]].drop_duplicates("cell_id"),
                      on="cell_id", how="left")
    wreg = weights_by(df, ["regime", "lead_time"])
    wlead = weights_by(df, ["lead_time"])

    print("  cell x lead weight map : %d rows" % len(wmap))
    print("\n=== MODEL RELIABILITY MAP - dominant source share by lead time ===")
    share = (wmap.groupby(["lead_time", "dominant_model"]).size()
             .unstack(fill_value=0))
    share_pct = (100 * share.div(share.sum(axis=1), axis=0)).round(1)
    print(share_pct.to_string())

    print("\n=== MEAN BLEND WEIGHTS by regime x lead ===")
    print(wreg[["regime", "lead_time", "w_a", "w_b", "w_c", "w_d", "dominant_model"]].to_string(index=False))

    # ---------------- feature importance ------------------------------
    print("\n--- retraining full-data per-lead models for export ---")
    final_rain, final_t2m, final_clf = fit_final_models(df, X)

    imp = (pd.DataFrame({l: m.feature_importances_ for l, m in final_rain.items()},
                        index=X.columns).mean(axis=1)
           .sort_values(ascending=False))
    print("\n=== TOP 12 BLENDER FEATURES (gain-split importance) ===")
    for k, v in imp.head(12).items():
        print("  %-24s%9.1f" % (k, v))

    # ---------------- persist ------------------------------------------
    joblib.dump(final_rain, MODELS_DIR / "blender_rain.joblib")
    joblib.dump(final_t2m, MODELS_DIR / "blender_t2m.joblib")
    joblib.dump(final_clf, MODELS_DIR / "extreme_classifier.joblib")

    keep = ["cell_id", "lat", "lon", "elevation_m", "date", "lead_time", "season",
            "regime", "regime_transition", "truth_rain", "truth_t2m",
            "clim_rain", "clim_t2m",
            "model_a_rain", "model_b_rain", "model_c_rain", "model_d_rain",
            "model_a_t2m", "model_b_t2m", "model_c_t2m", "model_d_t2m",
            "blend_rain", "blend_t2m", "prob_extreme", "confidence", "is_extreme"]
    df[keep].to_parquet(DATA / "predictions.parquet", index=False)

    overall = pd.DataFrame(score_table(df)).T.reset_index().rename(columns={"index": "source"})
    overall.to_csv(DATA / "metrics_overall.csv", index=False)
    by_lead.to_csv(DATA / "metrics_by_lead.csv", index=False)
    by_regime.to_csv(DATA / "metrics_by_regime.csv", index=False)
    pd.DataFrame(clf_rows).to_csv(DATA / "metrics_extreme_classifier.csv", index=False)
    wmap.to_csv(DATA / "weight_map.csv", index=False)
    wreg.to_csv(DATA / "weights_by_regime.csv", index=False)
    wlead.to_csv(DATA / "weights_by_lead.csv", index=False)
    imp.to_csv(DATA / "feature_importance.csv", header=["importance"])

    print("\n" + "=" * 66)
    print(" artefacts written to data/ and models/")
    for f in sorted(DATA.glob("*.csv")):
        print("   data/%s" % f.name)
    print("   data/predictions.parquet")
    for f in sorted(MODELS_DIR.glob("*.joblib")):
        print("   models/%s" % f.name)
    print("=" * 66)


if __name__ == "__main__":
    main()
