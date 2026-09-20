# PPT handoff brief

**For the designer building the SIH idea-submission deck.**
Everything needed is in this file. Numbers are final unless marked *pending*.
Do not invent, round up, or soften any of them.

- **Problem Statement ID:** SIH26081
- **Title:** Hybrid AI–NWP Multi-Model Forecast Blending System
- **Organisation:** Ministry of Earth Sciences (MoES)
- **Department:** National Centre for Medium Range Weather Forecasting (NCMRWF)
- **Category:** Software · **Theme:** Disaster Management
- **Team name:** Stash&Rebase
- **Product name:** Blend Desk

> **Verify the template first.** SIH publishes its idea-submission format per
> year and headings change. The structure below is the long-standing one
> (6 slides, fixed headings, PDF upload). Download the current year's official
> template from the SIH portal and map this content onto it rather than
> recreating the layout. **Do not exceed the slide count** — submissions are
> rejected for it.

> **⚠ Numbers are in flux this week.** A national retrain is now possible
> (the archive finished downloading on 20 Sep 2026). If it runs, every figure
> in §"Results" changes. **Confirm with the team before finalising slide 5.**
> Everything else in this brief is stable.

---

## The one-sentence pitch

> Five global weather models disagree about tomorrow. Blend Desk learns which
> one to trust — for each place, each day ahead and each kind of weather — and
> blends them into a single national forecast, while showing you which model it
> trusted and why.

---

## Slide 1 — Title

Standard SIH title block. Nothing creative needed. Fields: PS ID, PS title,
theme, category, team name, team ID (team leader fills in the ID).

---

## Slide 2 — Idea / Proposed Solution

**The problem, in one line.**
No single weather model is best everywhere. Which model is right changes with
the region, the lead time and the weather situation itself — and a forecaster
must commit to one before knowing which was right.

**What we built.**
A blending framework that ingests real operational forecasts from five
independent model streams, learns sum-to-one weights conditioned on verified
historical skill, lead time, region and weather regime, and publishes one
blended national forecast every morning.

**The five sources — name them, they carry the credibility.**
Expand every acronym on the slide. "IFS" and "AIFS" mean nothing to a judge
who does not work in numerical weather prediction.

| | Source | Expansion | Institution | Type |
|---|---|---|---|---|
| A | ECMWF IFS | Integrated Forecasting System | European Centre for Medium-Range Weather Forecasts | Physics NWP |
| B | **ECMWF AIFS** | **Artificial Intelligence Forecasting System** | ECMWF | **AI / data-driven** |
| C | NOAA GFS | Global Forecast System | National Oceanic and Atmospheric Administration, USA | Physics NWP |
| D | DWD ICON | Icosahedral Nonhydrostatic model | Deutscher Wetterdienst, Germany | Physics NWP |
| E | EC GEM | Global Environmental Multiscale model | Environment and Climate Change Canada | Physics NWP |

**Five model streams, four institutions** — ECMWF supplies two. Say it that way;
"five centres" is wrong and a judge from MoES will notice.

Truth for verification is **ERA5** (Copernicus Climate Change Service / ECMWF).
Persistence — yesterday repeated — is carried as a skill reference and is
**never blended**.

**Innovation and uniqueness — the three points that separate this:**

1. **The "AI" is a real AI weather model, not our own regressor.** Most
   submissions will put their own ML model in the AI slot. We include ECMWF
   AIFS — an operational data-driven forecasting system — as one of the
   *sources being blended*, and our ML decides *when to trust it over the
   physics models*. That is the literal reading of "hybrid AI–NWP".
2. **The weights are the deliverable, not a by-product.** Constrained
   non-negative least squares gives interpretable sum-to-one weights per grid
   cell and lead time. A forecaster reads "trust ECMWF AIFS here, at this
   range" off the screen. A feature-importance plot over a black box does not
   answer that.
3. **We publish where the models disagree.** Agreement means any model will do;
   divergence is where the choice of model *is* the forecast. That map is live
   and answers the operational question a weight map cannot on a future date.

---

## Slide 3 — Technical Approach

**Technologies:** Python · LightGBM · SciPy (NNLS) · pandas / NumPy ·
Mapbox GL JS with MapLibre GL JS fallback · Chart.js · ERA5 reanalysis ·
Open-Meteo Previous Runs API

**How the forecasts are obtained — this detail wins credibility.**
The Open-Meteo archive exposes `<variable>_previous_dayN`: the value a model
predicted for a given day using the run issued N days earlier. Summing
`precipitation_previous_day3_ecmwf_ifs025` over a UTC day gives *the daily
rainfall total ECMWF IFS forecast for that day, three days ahead*. That is an
actual operational forecast at an actual lead time — not a perturbation of an
analysis, not a reconstruction.

**Process flow — draw this as the slide's centrepiece:**

```
  FIVE MODEL STREAMS            OFFLINE  (slow, historical)
  ECMWF IFS ┐
  ECMWF AIFS│   archived           ┌──────────────────────┐
  NOAA GFS  ├─► forecasts at ────► │ NNLS sum-to-one      │
  DWD ICON  │   T+1…T+5            │ weights per          │
  EC GEM    ┘        │             │ (cell × lead)        │
                     │             │ (regime × lead)      │
            ERA5 ────┘             └──────────┬───────────┘
          (verification)            LightGBM correction, λ-shrunk
                                               │
                                        weights stored
                                               │
  ──────────────────────────────────────────────────────────
                     ONLINE  (fast, daily)     ▼
  today's runs ───► diagnose regime ───► apply weights ───► BLENDED
  from all five      from the forecast      (seconds)        FORECAST
  streams            fields themselves                     4,645 cells
                                                            0.25° · T+1…T+5
                                                                │
                              ┌─────────────────┬───────────────┤
                         weight maps      skill scores     extreme flags
```

**The architectural point worth a sentence.** Weight *estimation* needs months
of verified history and is slow; weight *application* needs only today's
forecasts and takes seconds. Separating them is what makes this operational
rather than a retrospective study — the morning run never waits on verification
data that cannot exist yet for a future date.

**Two grids, and why.** The archive is priced per cell per day, so weights are
fitted on a coarse **1° training grid (286 land cells)** and applied on a
**0.25° live grid (4,645 cells, ~28 km)**, clipped to the national boundary.
The weights transfer because they are fitted per regime and lead, not per cell.

**Methodology, four bullets:**
- Weights by constrained NNLS against ERA5 verification history
- Weather regime (active / break / normal monsoon) diagnosed from the
  **forecast fields available at issue time** — never from the observations
  being predicted
- Verified by **contiguous time-block cross-validation**, never a random split,
  because adjacent days and neighbouring cells are strongly correlated
- Extreme-rainfall probability from a LightGBM classifier on the blended field

**Training data actually used (state it, it is concrete):**

| | |
|---|---|
| Rows | 155,584 |
| Cells | 286 (1° national grid) |
| Days | 116 — 23 May to 15 Sep 2026 |
| Domain | 8.5–36.5 °N, 68.5–96.5 °E (all India) |
| Regime split | normal 54 days · break 34 · active 28 |
| Extreme cell-days (≥40 mm) | 3,350 |

---

## Slide 4 — Feasibility and Viability

**Feasibility — already built and running:**
- **All five sources are free and need no API key of any kind.** Verified: the
  system runs on Open-Meteo's public keyless endpoints
- Live national forecast for all India refreshes in **186 requests**, minutes
- Dashboard is a **single self-contained HTML file** — no server, no install
- One scheduled command is the entire operational workflow

**Challenges and how we handled them — this is the credibility slide:**

| Challenge | What we did |
|---|---|
| The equal-weight multi-model mean is a notoriously hard baseline | Included it from day one and report it honestly in both directions |
| Weights fitted per region, season, lead and regime overfit a short history | Blocked time-series CV; λ-shrinkage on the ML correction; persistence dropped from the blend on measured evidence |
| Target leakage via the regime feature | Caught and rebuilt: regime is diagnosed from forecasts, not from truth |
| Free-tier API rate limits | Fetcher waits out the hourly quota and resumes; coarse grid for training, fine grid for the daily run |

---

## Slide 5 — Impact and Benefits

### Results — out-of-sample, contiguous time-block cross-validation

Rainfall, mm/day. Lower RMSE and MAE are better; higher skill is better.

| Forecast | RMSE | MAE | Skill vs persistence |
|---|---|---|---|
| Persistence *(reference)* | 17.664 | 7.944 | 0.000 |
| ECMWF IFS | 15.734 | 5.698 | 0.109 |
| DWD ICON | 14.923 | 6.224 | 0.155 |
| NOAA GFS | 13.905 | 6.250 | 0.213 |
| EC GEM | 13.680 | 6.272 | 0.226 |
| ECMWF AIFS | 10.733 | 4.600 | 0.392 |
| Equal-weight mean *(naive baseline)* | 10.590 | 4.477 | 0.400 |
| **Learned NNLS weights** | **10.576** | **4.427** | **0.401** |
| Weights + ML correction *(full pipeline)* | 10.668 | 4.428 | 0.396 |

**The headline claims that are true and defensible:**

| Claim | Number |
|---|---|
| vs **ECMWF IFS**, the default operational choice | **33% less error** (15.734 → 10.576) |
| vs the **equal-weight mean** | **ahead on both** RMSE and MAE |
| vs every individual model stream | ahead |
| vs persistence | **skill score 0.401** |
| Heavy-rainfall flagging | **ROC-AUC 0.957**, PR-AUC 0.559, Brier 0.023 |
| at a base rate of | 3.5% (1,865 positive cell-days) |
| Coverage | **4,645 cells · 0.25° (~28 km) · all India · T+1…T+5** |

**Lead the slide with the learned NNLS weights (10.576), not the full
pipeline.** The weights are the problem statement's actual deliverable, and
they beat the equal-weight mean on both metrics — which is the benchmark most
published adaptive schemes fail to clear.

**Be straight about the last row.** The LightGBM correction on top currently
*costs* 0.092 RMSE (10.668 vs 10.576). The team is deciding whether to set
λ = 0 and ship the linear weights. **Do not put a claim on the slide that the
ML layer cannot underperform the weights — that is not what the numbers show.**
If asked, the honest answer is: λ is fitted per block and does not transfer
out-of-sample, so it is being reconsidered. Volunteering this is a strength.

**Impact:**
- *Disaster management:* earlier, better-targeted heavy-rainfall and high-wind
  signals at district scale, with a calibrated probability rather than a
  yes/no flag
- *Operational:* a duty forecaster sees *which* model to trust, not just a
  number — the reliability map is the artefact they would keep
- *Economic:* free data sources only; no licensing cost to deploy nationally
- *Extensible:* adding IMD's own forecast as a sixth member is a config change

---

## Slide 6 — Research and References

- ECMWF AIFS — ECMWF's operational data-driven forecasting system
- ERA5 reanalysis (Copernicus Climate Change Service)
- Open-Meteo Previous Runs API — archived forecasts at real lead times
- IMD operational rainfall classification (used for the map's colour bands)
- Murphy skill score; multi-model ensemble / Bayesian model averaging literature
- Repository: decision log (`docs/DECISIONS.md`), data provenance
  (`docs/DATA_SOURCES.md`), PS scoring (`docs/PS_COMPLIANCE.md`)

---

## Visual assets

In `docs/assets/`, captured at device resolution from the live product.
**Recapture before submission** — the UI has changed since these were taken
(larger type, a new sources panel).

| File | Shows | Best used on |
|---|---|---|
| `01-forecast.png` | Blended rainfall over all India, floating panels, live summary line | Slide 2 — the hero |
| `02-disagreement.png` | **Where the five streams disagree**, per cell | Slide 2 or 3 — most persuasive single image |
| `03-verification.png` | Ranked scorecard + error-vs-lead-time chart | Slide 5 |
| `04-extremes.png` | Heavy rain / heat / high wind columns | Slide 5 |
| `05-terrain-3d.png` | 3D terrain with the field draped over it | Slide 2 — visually striking |

**If you use only one image, use `02-disagreement.png`** with the caption
*"Where the models disagree, the choice of model is the whole forecast."* It
makes the argument for the product in one picture.

---

## Design direction

Match the product so the deck and the demo read as one thing.

- **Type:** Archivo (body), Archivo Narrow (headings, data labels).
  Both are on Google Fonts. The product was trialled with other families and
  deliberately returned to Archivo — do not substitute.
- **Background:** warm ink `#100f0d`; panels `#171613`
- **Ink:** `#f2efe8` primary, `#aaa59a` secondary, `#7d776c` tertiary
- **Accent:** `#f0b429` (amber) — sparingly, for the one number per slide that
  matters, and for the **AI** badge on ECMWF AIFS
- **Source colours — keep these exact, they match the app:**
  ECMWF IFS `#3987e5` · ECMWF AIFS `#d95926` · NOAA GFS `#199e70` ·
  DWD ICON `#9085e9` · EC GEM `#c98500` · Persistence `#64788c`
- Let the map screenshots carry the colour; keep slide furniture quiet
- Tabular figures for all numbers
- **Type sizes were increased across the product** because the original set was
  too small to read in a demo. Keep deck body text ≥ 18pt for the same reason.

**Institutional logos.** The team is supplying ECMWF, NOAA, DWD, ECCC and
Copernicus marks (see `assets/logos/README.md`). Use them on slide 2 beside the
source table — a row of real institutional logos is the fastest trust signal in
the deck. Also needed for the title slide: MoES / NCMRWF, SIH 2026, and the
team's college mark.

---

## Demo script — 90 seconds

1. **Open on the Forecast tab.** Read the summary line aloud: *"Forecast for 23
   September, three days ahead over India. The blend trusts ECMWF AIFS most, at
   64% of the weight. Of 4,645 cells, 363 are flagged for heavy rain."*
2. **Open the Forecast sources panel.** One click shows all five streams with
   full names and institutions. *"Nothing here is simulated."*
3. **Drag the horizon rail T+1 → T+5.** The weight bars shift as the horizon
   extends. *This is the product in one gesture.* Rehearse it.
4. **Click a cell.** Show what each stream said and the weight each was given.
5. **Search a state** — type "Kerala". It zooms, outlines the state, and the
   watch list narrows to it.
6. **Model weights tab → "Where models disagree".** *"Where they agree, any
   model will do. Where they diverge — here, and here — the choice of model is
   the whole forecast. That is what we are solving."*
7. **Verification tab.** Say the 33%-vs-IFS number, then that the learned
   weights also beat a plain average of all five.

---

## Anticipated questions

| Question | Answer |
|---|---|
| *"Is this real model data?"* | Yes — archived operational output from five model streams at real lead times, verified against ERA5. Nothing is simulated. |
| *"What are IFS and AIFS?"* | Integrated Forecasting System and Artificial Intelligence Forecasting System, both from ECMWF. One is physics, one is data-driven. |
| *"Does it beat a simple average?"* | Yes, on both RMSE and MAE — 10.576 vs 10.590, and 4.427 vs 4.477. Slim, and we say so. |
| *"Why does AIFS win?"* | It genuinely verifies better here, and published results agree it beats IFS on many scores. But we verify against ERA5 and **AIFS is trained on ERA5**, which flatters it. Gauge-based truth via IMD's public gridded data is validated and is the fix. |
| *"What does the ML layer add?"* | On the current 116-day set, nothing — it costs 0.092 RMSE, so we are reconsidering λ. The linear weights are the result we stand behind. |
| *"Is IMD data in it?"* | Not yet — IMD issues no personal API keys. The client is written and works the moment institutional access appears. |
| *"How do you avoid overfitting?"* | Blocked time-series CV, no random splits, and a short history we state openly: 116 days, 286 cells. |
| *"What did it cost to run?"* | Nothing. No API keys, free endpoints, single HTML file. |

---

## Do not claim

- ❌ "Beats all models by a large margin" — the margin over the equal-weight
  mean is 0.014 RMSE. Slim. Say "ahead", not "far ahead"
- ❌ That the ML correction cannot underperform the linear weights — **it
  currently does**, by 0.092 RMSE
- ❌ "Five centres" — it is five model streams from **four** institutions
- ❌ "Real-time" without qualification — it is a **daily** operational run on
  medium-range forecasts, T+1…T+5
- ❌ That IMD data is integrated — it is not
- ❌ That a true perturbed ensemble is included — we blend five deterministic
  runs; ECMWF's 51-member ensemble is verified available but not yet weighted
- ❌ Any number not in this file

*Pending and may improve before submission: the national retrain (archive
completed 20 Sep 2026) will refresh every figure in slide 5 and give wind its
own weights instead of reusing the rainfall vector. Check
`docs/PS_COMPLIANCE.md` for the current state before finalising.*
