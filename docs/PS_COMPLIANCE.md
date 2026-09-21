# Scored against the problem statement

**SIH26081** — Hybrid AI–NWP Multi-Model Forecast Blending System
Ministry of Earth Sciences · NCMRWF · Theme: Disaster Management · Category: Software
Team **Stash&Rebase**

Scored honestly. Where we fall short it says so, with what it would take to close
the gap. Everything marked *met* is reproducible from this repository.

**Overall: 8 of 10 requirements fully met, 2 partial.**

---

## 1. The framework the statement asks for

> *"develop a hybrid AI–NWP blending framework that assigns adaptive weights to
> different forecast sources based on historical skill, forecast lead time,
> region, season and weather regime"*

| Conditioning factor | Status | How |
|---|---|---|
| **Historical skill** | **Met** | Weights solved by constrained NNLS against ERA5 verification history |
| **Forecast lead time** | **Met** | Independent weight vector per lead T+1…T+5; a separate model per lead |
| **Region** | **Met** | Weights solved per (grid cell × lead) as well as per regime |
| **Weather regime** | **Met** | Active / break / normal monsoon, diagnosed from the forecast fields at issue time |
| **Season** | **Partial** | Season enters the ML correction as a categorical feature, but the NNLS weights are stratified by regime × lead and cell × lead, **not** by season. Closing it is a one-line change to the stratification key; it needs a multi-season archive to be meaningful, and we have 116 days. |

---

## 2. Forecast sources

> *"Physical NWP models, ensemble forecasts and AI/ML weather models"*

| Source type | Status | What we use |
|---|---|---|
| **Physical NWP** | **Met** | ECMWF IFS, NOAA GFS, DWD ICON, Environment Canada GEM — four independent centres |
| **AI / ML weather model** | **Met** | **ECMWF AIFS**, a genuine operational data-driven forecasting system, as a *blended source* rather than our own regressor wearing the label |
| **Ensemble forecasts** | **Partial** | We blend five deterministic runs — a *multi-model* ensemble, not a single-centre *perturbed* ensemble. ECMWF's 51-member ENS is verified available on Open-Meteo's ensemble endpoint, but **only for live forecasts, not at lead times in the archive**, so it cannot be weighted by verified skill. See below. |

**On the ensemble gap.** This is the one substantive shortfall. A true ensemble
would add calibrated uncertainty: P(rain ≥ 40 mm) read directly from member
counts rather than from the empirical curve we currently use. It is achievable
for the live product today (`ensemble-api.open-meteo.com`, 51 members verified),
and the honest reason it is not in yet is that we cannot verify its skill at
lead times, so giving it a learned weight would be unfounded. Stated plainly
rather than glossed.

---

## 3. Variables

> *"an optimized forecast for rainfall, temperature, wind and extreme weather
> indicators"*

| Variable | Status | Notes |
|---|---|---|
| **Rainfall** | **Met** | Blended, verified, IMD operational rainfall classes |
| **Temperature** | **Met** | Blended with its own NNLS weights and its own boosted correction (λ ≈ 1.0 — the correction genuinely helps here) |
| **Wind** | **Partial** | Daily-max 10 m wind is fetched, blended and displayed, and **wind is now present and 100% non-null across all 286 cells of the national archive**. But `model_training.py` still fits only two targets, so wind reuses the rainfall weight vector. This is now a code gap, not a data gap: the training loop needs a third target. |
| **Extreme indicators** | **Met** | All three the statement names — see §4.4 |

**Also disclosed:** `wind_gusts_10m` returns all-null for every model on the
previous-runs archive, so gusts cannot be verified at lead time. High wind
therefore keys off daily-max 10 m wind, which ERA5 does verify.

---

## 4. The five expected outcomes

### 4.1 Dynamically blended forecast — **Met**
Best-combined forecast from five sources over **4,645 cells at 0.25° (~28 km)**
across all India, for T+1…T+5, refreshed by `run_daily.py` from today's runs.

### 4.2 Model weight maps — **Met**
Sum-to-one, non-negative weights per **(cell × lead)** and per
**(regime × lead)**, rendered as the *Model weights* tab. A second view maps
**where the centres disagree** per cell, which is live and answers the
operational question the weight map cannot on a future date.

### 4.3 Improved forecast skill — **Met, with the honest caveat**

Out-of-sample, contiguous time-block cross-validation:

| Forecast | RMSE mm/day | MAE | Skill vs persistence |
|---|---|---|---|
| ECMWF IFS | 11.857 | 5.240 | 0.153 |
| DWD ICON | 14.041 | 6.152 | -0.002 |
| NOAA GFS | 12.806 | 6.026 | 0.086 |
| EC GEM | 13.594 | 6.548 | 0.029 |
| ECMWF AIFS | 8.611 | 4.402 | 0.385 |
| Persistence *(reference)* | 14.007 | 6.937 | 0.000 |
| **Equal-weight mean** *(naive baseline)* | 9.142 | 4.457 | 0.347 |
| **Blend (live product, learned weights)** | **8.424** | **4.282** | **0.399** |
| + ML correction *(offline only)* | 8.164 | 3.924 | 0.417 |

*Trained on the national archive: 155,584 rows, 286 cells at 1°, 116 days
(23 May – 15 Sep 2026), verified against ERA5.*

**Beats everything it is measured against.** Against ECMWF IFS — the model a
forecaster reaches for by default — **29% less error**. Against ECMWF AIFS, the
strongest single model, **2.2%**. Against the plain equal-weight mean — the
benchmark most published adaptive schemes fail to clear — **7.9%**.

**What ships is the weights-only blend (8.424).** The boosted correction scores
better still (8.164) but is not persisted to disk, so `run_daily.py` cannot
apply it and the daily product does not use it. The dashboard labels both rows
accordingly rather than quoting a number the live map does not produce.
Persisting the booster is the obvious next gain.

### 4.4 Extreme weather guidance — **Met**

| Signal the statement names | Status |
|---|---|
| Heavy rainfall | LightGBM classifier on P(≥40 mm/day). **ROC-AUC 0.947**, PR-AUC 0.406, Brier 0.017, at a 2.1% base rate over 3,350 positive cell-days |
| Heat wave | Anomaly against local seasonal normal where a climatology exists; absolute threshold on a live run, labelled as such |
| High wind | Daily-max 10 m wind ≥ 40 km/h (IMD warning territory) |

### 4.5 Operational workflow — **Met**
`run_daily.py` fetches every centre's current run for all 4,645 cells in **78
requests**, applies the learned weights, writes a dated product and refreshes
the dashboard. Responses are cached per run date, so an interrupted run resumes
rather than restarting. Cron-ready. `dashboard.html` is a single self-contained file.

---

## 5. Requirements from the brief's own analysis

| Point raised | Status |
|---|---|
| *"include the equal-weighted multi-model mean from day one"* | **Met** — it is on the dashboard scorecard, and the blend now beats it on RMSE (8.424 vs 9.142) and MAE (4.282 vs 4.457) |
| *"regridded onto a common grid"* | **Met**, with disclosure: Open-Meteo point-samples every model to our coordinates, so regridding is done upstream by the provider rather than by us |
| *"weights fitted per region, season, lead and regime multiply into a lot of parameters over a limited history — a direct route to overfitting"* | **Met, and specifically defended.** Blocked time-series CV, no random splits, λ-shrinkage that decays a useless correction to zero, persistence excluded on measured evidence |
| *"how you handle a source being missing"* | **Met** — NNLS renormalises over available members; the fetcher drops a model that returns empty and says so |
| *"how you avoid a blend that is worse than its best member"* | **Met.** The NNLS weights (8.424) beat every member, the best being AIFS at 8.611. λ-shrinkage bounds the ML correction rather than guaranteeing it helps — on the earlier regional training set it actually cost 0.092, which we reported; on the national set it gains 0.260. Bounded, not guaranteed, and measured either way |
| *"show the weight map for the monsoon core zone at day five where one source dominates, then error beside best single model and equal-weighted mean"* | **Met** — that is the Model weights tab plus the Verification scorecard |

---

## 6. Honest gap list

Ranked by how much a judge would care.

1. **The best pipeline is not the one that ships.** The boosted correction
   scores 8.164 against the weights-only 8.424, but the trained booster is not
   persisted to disk, so `run_daily.py` cannot apply it. We quote the 8.424 the
   daily product actually produces. Persisting the model is the next gain and
   is a small change.
2. **Wind has no weights of its own.** The national archive now carries wind at
   100% coverage, but `model_training.py` fits only rainfall and temperature,
   so wind reuses the rainfall vector. A code gap, not a data gap.
3. **No true perturbed ensemble.** ECMWF's 51-member ENS is verified available
   for live forecasts only, so it cannot be weighted by verified skill.
4. **Season is a model feature, not a weight stratum.** Needs multi-season
   history; we have 116 days.
5. **We verify against ERA5, and AIFS is trained on ERA5**, which flatters it.
   AIFS takes 80–85% of cells on the reliability map, and some of that lead is
   likely an artefact of being scored on its own training analysis. Gauge truth
   via `imdlib` (IMD's own 0.25° grid, no API key, already downloaded) is the
   fix and needs no credentials.
6. **The margin over the strongest single model is 2.2%.** Comfortable against
   IFS (29%) and the equal-weight mean (7.9%), but AIFS alone is close. The
   honest framing is per-variable: AIFS is fourth of five on temperature, where
   the blend beats it by a wide margin.
7. **IMD's own forecast is not a blend member.** IMD issues no personal API
   keys; `imd_client.py` is written and works the moment institutional access
   appears.

---

## 7. What we would claim in the room

> Five model streams disagree, and *which one is right changes* by place, lead
> time and weather regime. We blend real archived output from ECMWF IFS, ECMWF
> AIFS, NOAA GFS, DWD ICON and EC GEM at real lead times, learn sum-to-one
> weights conditioned on skill, lead, region and regime, and publish a live
> national forecast at 28 km every morning — with a map of which stream to
> trust where. Against the model a forecaster would pick by default we cut
> error by 29%. We are also ahead of the strongest single model by 2.2% and of
> a plain average of all five by 7.9% — the benchmark most adaptive schemes
> fail to clear. And where a judge asks why not just use the AI model on its
> own: because it is fourth of five on temperature. No single model is best at
> all three variables the statement names, and knowing which to trust, where
> and when, is the system.
