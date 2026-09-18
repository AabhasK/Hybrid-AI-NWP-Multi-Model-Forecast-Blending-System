# Hybrid AI–NWP Multi-Model Forecast Blending — SIH26081

A learned blending layer that combines several weather-model forecasts into one corrected
forecast, and — more usefully — tells you *which model to trust, where, and how far out*.

Region: **Maharashtra, India** (16–21 °N, 73–78 °E), 121 cells at 0.5°.
Period: **SW monsoon, 1 Jun – 31 Aug 2023**. Lead times: **1–5 days**.

**Open `dashboard.html`.** One file, no server, no build step.

---

## Headline result

| | RMSE (mm/day) | Skill vs persistence |
|---|---|---|
| Model A — physics NWP proxy | 5.26 | 0.518 |
| Model B — AI/ML proxy | 4.96 | 0.545 |
| Model C — ensemble-mean proxy | 5.13 | 0.530 |
| Model D — persistence baseline | 10.90 | 0.000 |
| **Blended (this system)** | **4.24** | **0.611** |

**14.6% below the best individual source**, rising to **16.5% at T+5** and **26.7% during
break spells**. All figures out-of-sample. Heavy-rain flagger: ROC-AUC 0.983.

The blend's advantage grows with lead time, which is the expected signature — at day one a
single model is already near-optimal and the blender correctly declines to interfere.

## Pipeline

```
01_fetch_era5.py       ERA5 truth, 121 cells x 92 days      -> data/era5_truth.parquet
02_synth_models.py     4 forecast streams x 5 leads         -> data/forecasts.parquet
model_training.py      blenders + weights + flagger         -> data/*.csv, models/*.joblib
export_dashboard_data.py  re-index by forecast run          -> data/dashboard_data.json
build_dashboard.py     inline the payload                   -> dashboard.html
```

Run the whole thing:

```bash
python 01_fetch_era5.py        # cached; safe to re-run
python 02_synth_models.py
python model_training.py       # prints every metric in this README
python export_dashboard_data.py
python build_dashboard.py
```

Requires `numpy pandas scipy scikit-learn lightgbm pyarrow joblib`. On this machine use
the Anaconda interpreter: `C:/Users/khand/anaconda3/python.exe`.

Iterating on the dashboard only means editing `dashboard_template.html` and re-running
`build_dashboard.py` — no need to retrain.

## How the model layer works

**Blender.** One LightGBM regressor *per lead time*, trained on the residual
`truth − anchor` where the anchor is the mean of the three skilful sources. Two reasons
the residual form matters: boosted trees cannot extrapolate past a split they have seen,
so predicting the *level* breaks on a held-out block that is hotter or wetter than
anything in training; and learning the systematic error of the sources rather than the
weather itself is the standard Model Output Statistics formulation. Per-lead models are
necessary because the optimal combination at day 1 is a different function from day 5 —
one shared model averages them into something worse than either.

**Weights.** Separately, a constrained non-negative least squares solve per
`(cell × lead)` and per `(regime × lead)` produces true sum-to-one weights. `scipy.nnls`
gives non-negativity; the sum-to-one constraint is imposed by appending a
heavily-weighted row of ones to the system. This is what the reliability map plots — the
regressor delivers the accuracy, the NNLS solve delivers the interpretation, and the two
deliverables stop competing.

**Extreme flagger.** A LightGBM classifier on P(rainfall ≥ 40 mm/day), consuming the
blended value plus ensemble spread and regime. It is fed a blended value produced the
same way it will be at deployment — in-sample on the training fold, out-of-fold at
prediction time — so its input distribution does not shift between training and use.

## Evaluation discipline

Scores come from **contiguous time-block cross-validation** (4 blocks over 92 days), not a
random split. Adjacent days and neighbouring cells are strongly autocorrelated, so a
random row split leaks the answer across the fold boundary and inflates every metric.
Every row receives an out-of-fold prediction, asserted in code.

The regime and domain-anomaly features are diagnosed from the **forecast** fields
available at issue time, never from the observations being predicted. An earlier version
used truth-derived regime labels as inputs; that is target leakage and was rebuilt.
Truth-derived regime labels survive only for stratifying the report.

## What the reliability map shows

Share of the 121 cells where each source earns the largest blend weight:

| lead | A (physics) | B (AI/ML) | C (ensemble) |
|---|---|---|---|
| T+1 | **97.5%** | 0.8% | 1.7% |
| T+2 | 66.9% | 9.1% | 24.0% |
| T+3 | 42.1% | **48.8%** | 9.1% |
| T+4 | 23.1% | **68.6%** | 8.3% |
| T+5 | 5.8% | **85.1%** | 9.1% |

A clean handover from the physics model to the AI model as the horizon extends — which is
the entire argument for blending rather than picking one model.

## Files

| | |
|---|---|
| `dashboard.html` | **The deliverable.** Self-contained, 698 KB |
| `dashboard_template.html` | Source for the above; edit this, not the built file |
| `model_training.py` | Training pipeline, prints every metric |
| `DATA_NOTE.md` | Disclosure: which data is real, which is synthetic, and why |
| `TEAM.md` | **What's needed from you** — branding, demo prep, PPT numbers |
| `data/` | ERA5 truth, training table, predictions, metrics, weight maps |
| `models/` | Trained LightGBM artefacts (per lead time) |

## Data provenance

Ground truth is genuine ERA5 reanalysis. The four contributing forecast streams are
synthetic, with deliberately distinct error signatures. The blending method is
source-agnostic — substituting real model output is a change to one loading step.
**Read `DATA_NOTE.md`** before presenting; it's written to be shown to a judge.
