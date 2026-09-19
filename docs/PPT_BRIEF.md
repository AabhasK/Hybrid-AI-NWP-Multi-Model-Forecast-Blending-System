# PPT handoff brief

**For the designer building the SIH idea-submission deck.**
Everything you need is in this file. Numbers are final unless marked *pending*;
do not invent, round up, or soften any of them.

- **Problem Statement ID:** SIH26081
- **Title:** Hybrid AI–NWP Multi-Model Forecast Blending System
- **Organisation:** Ministry of Earth Sciences (MoES)
- **Department:** National Centre for Medium Range Weather Forecasting (NCMRWF)
- **Category:** Software · **Theme:** Disaster Management
- **Team name:** Stash&Rebase
- **Product name:** Blend Desk

> **Verify the template first.** SIH's idea-submission format is published per
> year and the section headings occasionally change. The structure below is the
> long-standing one (6 slides, fixed headings, PDF upload). Download the current
> year's official template from the SIH portal and map this content onto it
> rather than recreating the layout from scratch. **Do not exceed the slide
> count** — submissions are rejected for it.

---

## The one-sentence pitch

> Five global weather models disagree about tomorrow. Blend Desk learns which
> one to trust — for each place, each day ahead and each kind of weather — and
> blends them into a single national forecast, while showing you which model it
> trusted and why.

---

## Slide 1 — Title

Standard SIH title block. Nothing creative needed. Fields: PS ID, PS title,
theme, category, team name, team ID (team leader fills the ID in).

---

## Slide 2 — Idea / Proposed Solution

**The problem, in one line.**
No single weather model is best everywhere. Which model is right changes with
the region, the lead time, and the weather situation itself — and a forecaster
has to commit to one before knowing which was right.

**What we built.**
A blending framework that ingests real operational forecasts from five
independent centres, learns sum-to-one weights conditioned on verified
historical skill, lead time, region and weather regime, and publishes one
blended national forecast every morning.

**The five sources — name them, they carry the credibility:**

| | Source | Type |
|---|---|---|
| A | ECMWF IFS | Physics NWP |
| B | **ECMWF AIFS** | **AI / data-driven** |
| C | NOAA GFS | Physics NWP |
| D | DWD ICON | Physics NWP |
| E | Environment Canada GEM | Physics NWP |

**Innovation and uniqueness — the three points that separate this:**

1. **The "AI" is a real AI weather model, not our own regressor.** Most
   submissions will put their own ML model in the AI slot. We include ECMWF
   AIFS — an operational data-driven forecasting system — as one of the
   *sources being blended*, and our ML decides *when to trust it over the
   physics models*. That is the literal reading of "hybrid AI–NWP".
2. **The weights are the deliverable, not a by-product.** Constrained
   non-negative least squares gives interpretable sum-to-one weights per grid
   cell and lead time. A forecaster can read "trust ECMWF AIFS here, at this
   range" off the screen. A feature-importance plot over a black box does not
   answer that.
3. **The system cannot underperform its own weights.** The ML correction is
   applied as `blend = weights·models + λ·correction`, with λ fitted on
   held-out days. A useless correction decays to λ=0 and the blend falls back
   exactly to the linear weighting.

---

## Slide 3 — Technical Approach

**Technologies:** Python · LightGBM · SciPy (NNLS) · pandas / NumPy ·
MapLibre & Mapbox GL JS · Chart.js · ERA5 reanalysis · Open-Meteo archive APIs

**Process flow — draw this as the slide's centrepiece:**

```
  FIVE CENTRES                  OFFLINE  (slow, historical)
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
  centres            fields themselves                     4,645 cells
                                                            0.25° · T+1…T+5
                                                                │
                              ┌─────────────────┬───────────────┤
                         weight maps      skill scores     extreme flags
```

**The architectural point worth a sentence:** weight *estimation* needs months
of verified history and is slow; weight *application* needs only today's
forecasts and takes seconds. Separating them is what makes this operational
rather than a retrospective study — the morning run never waits on verification
data that cannot exist yet for a future date.

**Methodology, four bullets:**
- Weights by constrained NNLS against ERA5 verification history
- Weather regime (active / break / normal monsoon) diagnosed from the **forecast
  fields available at issue time** — never from the observations being predicted
- Verified by **contiguous time-block cross-validation**, never a random split,
  because adjacent days and neighbouring cells are strongly correlated
- Extreme-rainfall probability from a LightGBM classifier on the blended field

---

## Slide 4 — Feasibility and Viability

**Feasibility — already built and running:**
- All five sources are free and need no API key
- Live national forecast for all India refreshes in 186 requests, minutes
- Dashboard is a single self-contained HTML file — no server, no install
- One scheduled command is the entire operational workflow

**Challenges and how we handled them — this is the credibility slide:**

| Challenge | What we did |
|---|---|
| The equal-weight multi-model mean is a notoriously hard baseline | Included it from day one and report it honestly, including where it still beats us |
| Weights fitted per region, season, lead and regime overfit a short history | Blocked time-series CV; λ-shrinkage so a noisy correction decays to zero; persistence dropped from the blend on measured evidence |
| Target leakage via the regime feature | Caught and rebuilt: regime is diagnosed from forecasts, not from truth |
| Free-tier API rate limits | Fetcher waits out the hourly quota and resumes; coarse grid for training, fine grid for the daily run |

**Risks we state rather than hide:** listed on slide 5 and in `DATA_NOTE.md`.

---

## Slide 5 — Impact and Benefits

**Headline results — out-of-sample, blocked cross-validation:**

| Claim | Number |
|---|---|
| vs **ECMWF IFS** (the default operational choice) | **32% less error** |
| vs every individual centre | blend is ahead |
| vs persistence baseline | **skill score 0.396** |
| Heavy-rainfall flagging | **ROC-AUC 0.957** at a 3.5% base rate |
| Best MAE of anything tested | **4.43 mm/day** |
| Coverage | **4,645 cells · 0.25° (~28 km) · all India · T+1…T+5** |

**Say this, and do not overstate it:** against a plain equal-weight average of
all five the blend is level (10.67 vs 10.59 RMSE; we win on MAE). The
multi-model mean is a stubborn benchmark many published schemes fail to beat.
**Volunteering this is a strength.** A judge who finds it themselves will
discount everything else on the slide.

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

In `docs/assets/`, captured at device resolution from the live product:

| File | Shows | Best used on |
|---|---|---|
| `01-forecast.png` | Blended rainfall over all India, floating panels, live summary line | Slide 2 — the hero |
| `02-disagreement.png` | **Where the five centres disagree**, per cell | Slide 2 or 3 — this is the most persuasive single image |
| `03-verification.png` | Ranked scorecard + error-vs-lead-time chart | Slide 5 |
| `04-extremes.png` | Heavy rain / heat / high wind columns | Slide 5 |
| `05-terrain-3d.png` | 3D terrain with the field draped over it | Slide 2 — visually striking |

**If you use only one image, use `02-disagreement.png`** with the caption
*"Where the models disagree, the choice of model is the whole forecast."* It
makes the argument for the product in one picture.

---

## Design direction

Match the product so the deck and the demo read as one thing.

- **Type:** Archivo (body), Archivo Narrow (headings, data labels)
- **Background:** warm ink `#100f0d`; panels `#171613`
- **Ink:** `#f2efe8` primary, `#aaa59a` secondary
- **Accent:** `#f0b429` (amber) — used sparingly, for the one number per slide
  that matters
- **Source colours — keep these exact, they match the app and are
  colourblind-validated:**
  ECMWF IFS `#3987e5` · ECMWF AIFS `#d95926` · NOAA GFS `#199e70` ·
  DWD ICON `#9085e9` · EC GEM `#c98500`
- Let the map screenshots carry the colour; keep slide furniture quiet
- Tabular figures for all numbers

---

## Demo script — 90 seconds

1. **Open on the Forecast tab.** Read the summary line aloud: *"Forecast for 23
   September, three days ahead over India. The blend trusts ECMWF AIFS most, at
   64% of the weight. 363 cells flagged for heavy rain."*
2. **Drag the horizon rail T+1 → T+5.** The weight bars shift as the horizon
   extends. *This is the product in one gesture.* Rehearse it.
3. **Hover a cell.** Show what each of the five centres said, and the weight
   each was given.
4. **Search a state** — type "Kerala". It zooms, outlines the state, and the
   watch list narrows to it.
5. **Model weights tab → "Where models disagree".** *"Where they agree, any
   model will do. Where they diverge — here, and here — the choice of model is
   the whole forecast. That is what we are solving."*
6. **Verification tab.** Point at the scorecard. Say the 32%-vs-IFS number
   **and** the equal-weight-mean caveat, in that order.

---

## Anticipated questions

| Question | Answer |
|---|---|
| *"Is this real model data?"* | Yes — archived operational output from five centres at real lead times, verified against ERA5. Nothing is simulated. |
| *"Does it beat a simple average?"* | On MAE yes, on RMSE not yet — 10.67 vs 10.59. We report it. More verification history is the fix; weights are currently fitted on 88 days. |
| *"Why does AIFS win?"* | It genuinely verifies better here, and published results agree it beats IFS on many scores. But we verify against ERA5 and **AIFS is trained on ERA5**, which flatters it. Gauge-based truth via IMD's public gridded data is validated and is the fix. |
| *"Why only 1.8% gain at day 1?"* | At day one a single model is already near-optimal and the blender correctly declines to interfere. That is the system behaving properly. |
| *"Is IMD data in it?"* | Not yet — IMD issues no personal API keys. The client is written and works the moment institutional access appears. We use IMD's public gridded rainfall for verification instead, which needs no key. |
| *"How do you avoid overfitting?"* | Blocked time-series CV, no random splits, and λ-shrinkage that makes it structurally impossible for the ML layer to underperform the linear weights. |

---

## Do not claim

- ❌ "Beats all models by a large margin" — the margin over the equal-weight
  mean is slim and currently negative on RMSE
- ❌ "Real-time" without qualification — it is a **daily** operational run on
  medium-range forecasts, T+1…T+5
- ❌ That IMD data is integrated — it is not
- ❌ That a true perturbed ensemble is included — we blend five deterministic
  runs; ECMWF's 51-member ensemble is verified available but not yet weighted
- ❌ Any number not in this file

*Pending items that may improve before submission: wind currently reuses the
rainfall weight vector, and the national-grid retrain is still running. Check
`docs/PS_COMPLIANCE.md` for the current state before finalising slide 5.*
