# Engineering decision log

Team **Stash&Rebase** · SIH26081 · Hybrid AI–NWP Multi-Model Forecast Blending
Ministry of Earth Sciences / NCMRWF

Every entry records what we chose, what we rejected, and **the measurement that
decided it**. Numbers here were produced by the pipeline in this repository and
can be reproduced by re-running the step named.

---

## D1 — Real multi-model archives, not synthetic sources

**Decision.** Blend genuine archived output from operational centres, verified
against ERA5 reanalysis.

**Rejected.** Perturbing one forecast into four "models". Our first prototype
did exactly this, and it is what most teams without archive access will submit.

**Why it changed.** Open-Meteo's *Previous Runs* API exposes
`<variable>_previous_dayN` — the value a model predicted for a given hour using
the run issued N days earlier. Summing
`precipitation_previous_day3_ecmwf_ifs025` across a UTC day is literally "the
daily rainfall ECMWF IFS forecast for that day, three days ahead". Real
forecasts, real lead times, no key.

**Consequence we accepted.** Real models are far harder to beat than synthetic
ones. Our synthetic prototype showed a 14.6% RMSE gain over the best single
model; on real data that collapsed to ~1–2%. We kept the real data and changed
the claim rather than keeping the flattering number. See D7.

---

## D2 — The "AI" is a real AI weather model, not our own regressor

**Decision.** **ECMWF AIFS** enters the blend as a *source*, alongside physics
models. Our machine learning decides *when to trust it*.

**Rejected.** Putting our own LightGBM in the "AI" slot, which is how most
submissions will read "hybrid AI–NWP".

**Measurement.** On our Maharashtra verification set, AIFS scored RMSE 10.73
mm/day against ECMWF IFS's 15.73 — the AI model beats the physics model, which
is the interesting finding the problem statement is pointing at.

**Gotcha, documented for the panel.** `ecmwf_aifs025` serves live forecasts but
returns **all-null** for every `_previous_dayN` variable — Open-Meteo keeps no
previous-runs archive under that id. `ecmwf_aifs025_single` (the deterministic
AIFS run) does. `gfs_graphcast025` resolves but is likewise empty. We lost half
a day to this; it is recorded in `03_fetch_real_models.py`.

---

## D3 — Keep every centre separate; never pre-average them

**Decision.** Each centre is its own blend member.

**Rejected.** Collapsing GFS + ICON + GEM into a single "ensemble mean" member,
which we originally did for narrative tidiness.

**Measurement.** Averaged: blend RMSE **10.670**. Separate: **10.536**. Folding
three independent forecasts into one threw away real information.

---

## D4 — Persistence is the skill reference, not a blend member

**Measurement.** Including persistence in the weight solve *degraded*
out-of-sample blend RMSE from **10.536 to 10.771**. It carries no information
the models lack and destabilises the fitted weights.

It remains the denominator of the Murphy skill score, which is standard
operational practice.

---

## D5 — Contiguous time-block cross-validation, never a random split

**Decision.** The record is cut into 4 contiguous calendar blocks; each block is
predicted by a model trained only on the other three. Every row receives an
out-of-fold prediction, asserted in code.

**Why.** Adjacent days and neighbouring cells are strongly autocorrelated. A
random row split puts 21 July in training and 22 July in test, so the model has
effectively seen the answer. Expect competing submissions to report inflated
numbers for exactly this reason.

---

## D6 — No target leakage in the regime feature

**Decision.** The active/break/normal regime fed to the model is diagnosed from
the **forecast fields available at issue time**, never from observations.

**What we caught.** An earlier version used `regime` and `domain_rain_z`
computed from ERA5 truth *on the valid date* — a function of the very rainfall
being predicted. It was the top-ranked feature, which is what gave it away.

**Measurement.** After removing the leakage the scores got *better*
(heavy-rain ROC-AUC 0.985 → 0.991), which showed the leaked features were
carrying noise rather than signal.

Truth-derived regime labels survive only for stratifying the report.

---

## D7 — The equal-weight multi-model mean is the baseline that matters

**Decision.** Report against the plain average of all members, not only against
the best single model.

**Why.** A simple multi-model mean is a notoriously stubborn benchmark and many
published adaptive schemes fail to beat it. A submission that omits it has
avoided the only comparison that counts.

**Measurement (Maharashtra set, 5 real members).**

| Forecast | RMSE mm/day | MAE |
|---|---|---|
| ECMWF IFS | 15.734 | 5.698 |
| ECMWF AIFS | 10.733 | 4.600 |
| NOAA GFS | 13.905 | 6.250 |
| DWD ICON | 14.923 | 6.224 |
| EC GEM | 13.680 | 6.272 |
| Persistence (reference) | 17.664 | 7.944 |
| **Equal-weight mean (naive)** | **10.590** | 4.477 |
| **Learned blend (ours)** | **10.576** | **4.427** |

**The honest reading.** Against the equal-weight mean our margin is slim. Against
**ECMWF IFS — the model a forecaster would reach for by default — the blend cuts
error by about a third.** Both numbers go in the deck. The second is what makes
the first credible.

The value proposition is not "our blend is much more accurate". It is *you
cannot know in advance which model will win, and the blend tracks the winner
automatically while showing you which one it is.*

---

## D8 — The ML layer is shrunk so it cannot make things worse

**Decision.** `blend = NNLS-weighted members + λ · boosted correction`, with λ
fitted by least squares on a held-out slice taken from the **end** of the
training window.

**What we measured first.** An unshrunk LightGBM correction made the blend
**substantially worse** than the weights alone: RMSE 13.774 against the linear
blend's 10.576. Real monsoon rainfall is heavy-tailed and each lead/fold has
only ~8,000 rows, so a 600-tree model memorised noise.

**After shrinkage.** λ lands at 0.3–0.8 for rainfall and ~1.0 for temperature —
the temperature correction is genuinely useful, the rainfall one only partly.
If a correction is pure noise λ goes to 0 and the system degrades *exactly* to
the linear weighted blend. It is structurally incapable of underperforming its
own weights.

---

## D9 — Anchor the residual on the weighted blend, not the plain mean

**Decision.** The booster learns a correction on top of the NNLS blend.

**What broke.** Anchoring on the plain mean of the members was fine with
synthetic sources of similar quality. With real ones, IFS (15.73) is far worse
than AIFS (10.73), so their mean is worse than AIFS alone and the booster spent
all its capacity climbing back to a source it already had.

Least squares assigns the weak member a small weight automatically, so the
linear blend starts ahead of every member.

---

## D10 — Two grids, because the two halves have opposite cost shapes

**Decision.** Weights are fitted on a **1° training grid** (286 land cells);
the daily product runs on a **0.25° live grid** (4,645 cells, ~28 km).

**Why.** The forecast archive is priced per cell *per day*, so 120 days of
history is what is expensive — a fine grid there is unaffordable. The daily run
only needs the next 7 days, so cells are nearly free.

The weights transfer because they are fitted per **(regime, lead time)**, not
per cell. A weight learned at 1° applies at any resolution.

**What forced it.** At 1° a grid cell is 111 km across, so searching for a city
returned a box that swallowed most of a state and could not be told apart from
its neighbours.

---

## D11 — Land-masked national domain, clipped to the Indian boundary

**Decision.** Grid cells are generated only where the cell centre falls inside
India, and the map raster is clipped to the national boundary.

**Rejected.** A 5°×5° rectangle over Maharashtra, which spilled into the Arabian
Sea and four neighbouring countries and read as a graphic pasted onto a map.

**How the clip works.** The boundary is inverted into a world rectangle with
India's rings punched out as holes; filling that polygon with the page
background clips the raster without touching the image itself. Boundary source
is DataMeet's `india-composite`, which follows the depiction used by the
Government of India — the correct depiction for a submission to an Indian
ministry.

---

## D12 — Interpolate the field, but forbid invented extremes

**Decision.** The 0.25° field is resampled with a Catmull-Rom bicubic kernel and
classified into IMD rainfall bands.

**Bug we caught by testing, not by looking.** A Catmull-Rom kernel is not
monotone: across a sharp gradient it overshot 123.5 mm → **128.5 mm**, crossing
the IMD "Very heavy" boundary at 124.5 and painting a class *no model had
forecast*. On the dry side it went negative.

**Fix.** Each sample is clamped to the min/max of its enclosing 2×2 cells. This
forbids new extrema while leaving the surface smooth, and because a cell centre
lies inside its own 2×2 box, exactness at the data points is preserved —
verified at `max abs err 0.000000`.

---

## D13 — Everything degrades gracefully; no credential is required

**Decision.** Every API key is optional, with a working fallback, and
`python config.py` states what each missing key would buy.

| Key | Fallback when absent |
|---|---|
| `MAPBOX_TOKEN` | MapLibre GL + OpenFreeMap vector tiles, keyless |
| `OPENMETEO_API_KEY` | free tier; the fetcher waits out the hourly quota and resumes |
| `CDS_API_KEY` | ERA5 from the Open-Meteo mirror — same ECMWF product |
| `IMD_API_KEY` | see D14 |

The map also survives its basemap failing: all data layers install on
`style.load` with a 7-second watchdog that swaps to raster tiles, because an
earlier version hung every layer off the vector style and would have shown a
black panel on a slow venue connection.

---

## D14 — IMD API ruled out; three alternatives adopted

**Situation.** All five IMD endpoints are live but return
`{"error":"API key missing"}`, and IMD does not issue personal API keys — only
institutional ones.

**What we needed IMD for, and what replaced it:**

1. **An extra forecast member.** Replaced, and improved on, by adding four more
   global centres that carry a lead-time archive over India with no key:
   **JMA**, **UK Met Office**, **Météo-France ARPEGE**, **CMA GRAPES**. All four
   verified returning 504/504 non-null values. This takes the blend from five
   members to nine — a larger and more diverse ensemble than IMD alone would
   have given.

2. **Gauge-based verification truth.** Replaced by **`imdlib`**, which downloads
   **IMD's own 0.25° gridded rainfall** from IMD Pune's public data portal with
   **no API key**. Verified: 2025 downloads cleanly at 129×135 cells covering
   6.5–38.5 °N, 66.5–100 °E. This is the same underlying gauge product the API
   would have served. **CHIRPS** (UCSB, 0.05°, gauge+satellite) is confirmed
   reachable as a second independent option.

3. **Official warnings as a benchmark.** No open equivalent. Dropped, and
   recorded as future work.

**Caveat retained.** `imdlib` currently fails on the partial 2026 file
(`mismatch in size of data-length`), so gauge verification runs on complete
years. This does not affect the live forecast.

---

## D15 — What "current" means, and where it cannot

The **forecast** is current: `run_daily.py` fetches today's runs from every
centre and blends them for T+1…T+5. The dashboard opens on today's run.

The **verification** is necessarily historical, and this is not a limitation we
can engineer away: measuring whether a forecast was right requires the weather
to have happened. Skill scores are computed on archived forecasts whose outcomes
are known; those scores then govern how today's forecast is weighted.

That split — slow offline weight estimation, fast online weight application — is
what makes the system operational rather than retrospective, and it is the
honest answer if a judge asks why the verification tab shows past dates.

---

## D16 — The map is the product, so it gets the page

**Decision.** The map occupies the full stage width and whatever screen height
is left under the header. The weight chart, cell readout and watch list float
over it as glass cards in a collapsible right-hand rail.

**Rejected.** The map as one column of a CSS grid beside equal-weight panels,
which is what the first three versions did. It made the central artefact look
like a thumbnail next to a bar chart.

**Detail that mattered.** `fitBounds` only guarantees the country fits inside
the container, and the container includes the 344 px the dock covers, so India
was being centred *underneath* the panels and rendered small. The fit is now
padded by the dock width, and zoom is nudged halfway toward filling the free
width, so the country is the subject without being cropped.

---

## D17 — The reliability map needed something per-cell to say

**Problem.** A live run uses one weight vector per (regime, lead time), shared
by every cell, so the "model reliability map" rendered as a single flat colour
over the whole country. Honest, and useless to look at.

**Decision.** A second view on the same map: **where the centres disagree**,
measured as the standard deviation of the five members' rainfall in each cell.
That is genuinely per-cell, available live, and it argues the product's case
better than the weight map does — where the models agree any of them will do;
where they diverge, the choice of model *is* the forecast.

Per-cell dominant source returns as soon as the national archive finishes
training. The disagreement view stays regardless; it answers a different and
equally operational question.

---

## D18 — The verdict sentence is derived, not asserted

**What we caught.** The verification tab's summary sentence read "ahead of
every individual source **and of a plain equal-weight average**" as fixed copy,
while the ranked table directly above it showed the equal-weight mean at 10.59
against the blend's 10.67. The page contradicted itself.

**Decision.** The sentence is computed from the same numbers the table renders,
and it states a loss when there is one:

> "A plain equal-weight average of all five scores **10.59**, so on this set the
> learned weighting has not yet beaten simple averaging. We report that rather
> than omit the comparison."

This is the single most attackable number in the submission, and the page now
says it out loud.

---

## D19 — No climatology means no anomaly

**What we caught.** The heat-stress list showed `+0.0° vs normal` for every
cell. A live run has no 30-year normal for a date that has not happened, so the
exporter had set climatology equal to the blended value and every anomaly was
identically zero.

**Decision.** The dashboard detects whether a slice carries a real climatology.
Where it does, heat stress is an anomaly against the local seasonal normal.
Where it cannot, the criterion switches to an absolute threshold and the panel
says why. Sanity check: the absolute view correctly ranks western Rajasthan
(26.9 °N, 69.6 °E — the Thar) as the hottest cells for 23 September.

---

## D20 — Typography and palette chosen against the defaults

**Decision.** **Archivo** and **Archivo Narrow** on a warm ink-and-charcoal
base (`#100f0d` page, `#171613` panels).

**Rejected.** IBM Plex Sans on cool blue-slate, which the first version used.
Both are the reflex choice for a technical dashboard, and together they read as
generated rather than designed.

The base is deliberately desaturated and warm so that the only saturated things
on screen are the weather layers — teal rainfall, amber heat, violet wind and
the five series hues. The series palette was re-run through the CVD validator
against the new surface rather than assumed to still pass: worst adjacent pair
ΔE 9.4 under deuteranopia, all five clearing 3:1 contrast.

---

## Open items

- National archive fetch for retraining weights on the 1° India grid is
  rate-limited on the free Open-Meteo tier and resumes across hourly windows.
  Current weights come from the Maharashtra verification set.
- Adding JMA / UKMO / Météo-France / CMA as members (D14) requires re-running
  the archive fetch and retraining.
- Gauge-based verification via `imdlib` is validated but not yet wired into
  `model_training.py` as an alternative truth source.
