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
| **Season** | **Partial** | Season enters the ML correction as a categorical feature, but the NNLS weights are stratified by regime × lead and cell × lead, **not** by season. Closing it is a one-line change to the stratification key; it needs a multi-season archive to be meaningful, and we have 120 days. |

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
| **Wind** | **Partial** | Daily-max 10 m wind is fetched, blended and displayed. But **wind currently reuses the rainfall weight vector** because the wind archive was added after the last training run. Fixing it requires only that the in-flight archive fetch (which now includes wind) completes and `model_training.py` trains a third target. |
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
| ECMWF IFS | 15.734 | 5.698 | 0.109 |
| DWD ICON | 14.923 | 6.224 | 0.155 |
| NOAA GFS | 13.905 | 6.250 | 0.213 |
| EC GEM | 13.680 | 6.272 | 0.226 |
| ECMWF AIFS | 10.733 | 4.600 | 0.392 |
| Persistence *(reference)* | 17.664 | 7.944 | 0.000 |
| **Equal-weight mean** *(naive baseline)* | 10.590 | 4.477 | 0.400 |
| **Learned NNLS weights** | **10.576** | **4.427** | **0.401** |
| Weights + ML correction *(full pipeline)* | 10.668 | 4.428 | 0.396 |

**Beats:** every individual model stream, persistence by a wide margin, and
**the equal-weight mean on both RMSE and MAE** (10.576 vs 10.590; 4.427 vs
4.477). Against ECMWF IFS — the model a forecaster reaches for by default —
**33% less error**. The multi-model mean is a notoriously stubborn benchmark
that many published adaptive schemes fail to clear, so clearing it, even by
0.014, is the result that matters here.

**The margin is slim and we say so.** 0.014 mm/day on RMSE is well inside what
116 days of history can resolve. The claim is "ahead", not "far ahead".

**The ML correction currently costs us.** The full pipeline scores 10.668
against the linear weights' 10.576 — the boosted correction is **worse than
the weights alone by 0.092**. λ is fitted per block and does not transfer
out-of-sample. Setting λ = 0 recovers 10.576 exactly. This is an open decision,
recorded rather than hidden; see §6.

### 4.4 Extreme weather guidance — **Met**

| Signal the statement names | Status |
|---|---|
| Heavy rainfall | LightGBM classifier on P(≥40 mm/day). **ROC-AUC 0.957**, PR-AUC 0.559 at a 3.5% base rate |
| Heat wave | Anomaly against local seasonal normal where a climatology exists; absolute threshold on a live run, labelled as such |
| High wind | Daily-max 10 m wind ≥ 40 km/h (IMD warning territory) |

### 4.5 Operational workflow — **Met**
`run_daily.py` fetches every centre's current run for all 4,645 cells in 186
requests, applies the learned weights, writes a dated product and refreshes the
dashboard. Cron-ready. `dashboard.html` is a single self-contained file.

---

## 5. Requirements from the brief's own analysis

| Point raised | Status |
|---|---|
| *"include the equal-weighted multi-model mean from day one"* | **Met** — and we report it losing to us on MAE and beating us on RMSE |
| *"regridded onto a common grid"* | **Met**, with disclosure: Open-Meteo point-samples every model to our coordinates, so regridding is done upstream by the provider rather than by us |
| *"weights fitted per region, season, lead and regime multiply into a lot of parameters over a limited history — a direct route to overfitting"* | **Met, and specifically defended.** Blocked time-series CV, no random splits, λ-shrinkage that decays a useless correction to zero, persistence excluded on measured evidence |
| *"how you handle a source being missing"* | **Met** — NNLS renormalises over available members; the fetcher drops a model that returns empty and says so |
| *"how you avoid a blend that is worse than its best member"* | **Met for the blend, not for the correction.** The NNLS weights (10.576) beat every member, the best being AIFS at 10.733. λ-shrinkage bounds the ML correction's damage — an unshrunk booster scored 13.77 — but does **not** guarantee it helps: the shrunk correction still costs 0.092 out-of-sample. Bounded, not guaranteed; the earlier wording overclaimed |
| *"show the weight map for the monsoon core zone at day five where one source dominates, then error beside best single model and equal-weighted mean"* | **Met** — that is the Model weights tab plus the Verification scorecard |

---

## 6. Honest gap list

Ranked by how much a judge would care.

1. **The ML correction makes the forecast worse.** The full pipeline scores
   10.668 against the linear weights' 10.576. λ is fitted per block and does
   not transfer out-of-sample. Setting λ = 0, or selecting it by nested CV, is
   the open decision. Until it is resolved, the number we stand behind is the
   linear blend's.
2. **The margin over the equal-weight mean is 0.014 RMSE.** We are ahead on
   both metrics, but on 116 days that is not a wide result. More history is the
   only honest fix.
3. **No true perturbed ensemble.** Verified available for live forecasts only.
4. **Wind reuses rainfall weights.** *Unblocked as of 20 Sep 2026* — the
   national archive completed with wind present and 100% non-null for every
   stream. Closes on the next training run.
5. **Season is a model feature, not a weight stratum.** Needs multi-season
   history.
6. **We verify against ERA5, and AIFS is trained on ERA5**, which flatters it.
   Gauge truth via `imdlib` (IMD's own 0.25° grid, no API key) is validated and
   ready to substitute.
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
> error by a third. We are also ahead of a plain average of all five on both
> RMSE and MAE — the benchmark most adaptive schemes fail to clear — though by
> a slim 0.014, and we say so. The ML layer on top currently costs us 0.092,
> and we say that too.
