# Data Note

**Everything in this system is real data. There are no synthetic forecasts.**

Both halves of the problem are now genuine. The verification target is **ERA5
reanalysis** — daily rainfall and 2 m temperature for 121 grid cells at 0.5°
across a 5° × 5° box over Maharashtra (16–21 °N, 73–78 °E). The forecasts being
blended are **archived operational output from five forecasting centres**,
retrieved at real lead times from the Open-Meteo Previous Runs API:

| | Source | Type | Centre |
|---|---|---|---|
| A | ECMWF IFS | Physics NWP | ECMWF |
| B | ECMWF AIFS | **AI / data-driven** | ECMWF |
| C | NOAA GFS | Physics NWP | NOAA |
| D | DWD ICON | Physics NWP | Deutscher Wetterdienst |
| E | EC GEM | Physics NWP | Environment Canada |
| F | Persistence | Baseline | derived from ERA5 |

Because ECMWF AIFS is a genuine operational AI forecasting system and IFS/GFS/
ICON/GEM are genuine physics-based NWP, the phrase "Hybrid AI–NWP blending" is
literal here rather than a proxy for it.

## Where the lead times come from

The API exposes `<variable>_previous_dayN`: the value a model predicted for a
given hour using the run issued N days earlier. Summing
`precipitation_previous_day3_ecmwf_ifs025` across a UTC day gives *the daily
rainfall total ECMWF IFS forecast for that day, three days ahead*. That is an
actual operational forecast at an actual lead time. Nothing is perturbed,
simulated or reconstructed.

---

## Caveats you should raise before a judge does

**1. Verifying against ERA5 flatters AIFS.** ECMWF's AIFS is *trained on ERA5*.
Scoring it against ERA5 partly rewards it for having learned that specific
analysis. AIFS genuinely does beat IFS on this domain — and published results
agree it beats IFS on many headline scores — but some of the margin here is the
evaluation choice, not forecast quality. Verifying against rain-gauge or IMD
gridded observations would be the fair test and is the obvious next step.

**2. AI models drizzle.** AIFS forecasts measurable rain on ~88% of cell-days
against truth's ~79%. Data-driven models are known to over-produce light rain
and to be spatially smoother than physics models. Smoothness flatters an
RMSE-based comparison specifically, because RMSE rewards hedging.

**3. Rainfall RMSE is dominated by a handful of events.** Daily monsoon
rainfall is heavy-tailed; a few convective cells where every model fails
dominate the squared error. This is why the blend's advantage is clearer on MAE
than on RMSE, and why we report both.

**4. The learned weighting's margin over a naive average is small.** An
equal-weight mean of the five members is a strong baseline. See the README for
the current measured figures; where the learned blend's advantage over it is
slim, we say so rather than quoting only the comparison against the weakest
model.

**5. Climatology is computed across the analysis window.** `clim_rain` and
`clim_t2m` use the whole period rather than training folds alone. Operationally
you would use a 30-year normal, which is genuinely prior information, so we
treat climatology as known a priori. The effect is small but not exactly zero.

**6. One region, one archive window.** 121 cells over one 5° box. Cross-regional
and multi-year generalisation is untested.

## What is genuinely defensible

The evaluation discipline, which carries over to any data.

- **Contiguous time-block cross-validation**, not a random split. Adjacent days
  and neighbouring cells are strongly autocorrelated; a random row split leaks
  the answer across the fold boundary and inflates every metric. Every row gets
  an out-of-fold prediction, asserted in code.
- **No target leakage.** The regime and domain-anomaly features are diagnosed
  from the *forecast* fields available at issue time, never from the
  observations being predicted. An earlier version used truth-derived regime
  labels as model inputs; that was target leakage and was rebuilt. Truth-derived
  labels survive only for stratifying the report.
- **The non-linear correction cannot make things worse.** The LightGBM layer is
  applied as `anchor + λ·correction`, with λ fitted by least squares on a
  held-out slice taken from the end of the training window. A correction that is
  noise gets λ→0 and the system falls back exactly to the linear weighted blend.
  This was added after measuring that an unshrunk booster made the blend
  substantially worse than the weights alone.
- **Persistence is excluded from the blend**, on evidence: including it degraded
  out-of-sample blend RMSE, because it adds no information the models lack while
  destabilising the fitted weights. It remains the skill-score reference.

## The synthetic generator

`02_synth_models.py` is retained but is **no longer used**. It builds four
synthetic sources by perturbing ERA5 with distinct error signatures, and was the
original pipeline before real multi-model archives proved reachable. It stays in
the repository as a fallback and because it documents the error characteristics
we expected to find. `model_training.py` prefers `data/forecasts_real.parquet`
whenever it exists and prints which source it used.
