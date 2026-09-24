# What every part of the dashboard means

Written to be read straight through. Each section names a thing on screen,
says what it is, and says which part of **SIH26081** it exists to satisfy.

If something is on screen and is not in this file, it should not be on screen.

---

## The idea in one paragraph

Five weather models disagree about tomorrow. Each is better in some places,
at some ranges, in some weather. We measured how each one performed over
116 days across India, learned how much to trust each one **per region, per
day-ahead, per weather situation**, and combine them into a single forecast.
The screen shows the combined forecast *and* which model it leaned on.

---

## Top of the page — always visible

### Header strip

| Field | Meaning |
|---|---|
| **Region** | Area in view. Always *India* unless you search a state or district. |
| **Run issued** | The date and hour the forecast run started. `00Z` = midnight UTC, the standard issue time. If it reads **"· yesterday"** in amber, you are looking at an old run — re-run `run_daily.py`. |
| **Diagnosed spell** | The monsoon situation the system detected: **active** (widespread rain), **break** (a lull), or **normal**. Important: this is read from the *forecasts*, never from what actually happened — otherwise the system would be using the answer to make the prediction. |
| **Console time** | Local clock. Cosmetic. |

### Forecast sources (collapsed bar)

Click **Details** to expand. Collapsed it names all five model streams; expanded
it gives each one's full name, the institution behind it, and a link to that
institution's own documentation.

| Shown as | Full name | Who runs it | Type |
|---|---|---|---|
| ECMWF IFS | Integrated Forecasting System | European Centre for Medium-Range Weather Forecasts | physics |
| ECMWF AIFS | Artificial Intelligence Forecasting System | ECMWF | **machine learning** |
| NOAA GFS | Global Forecast System | NOAA, USA | physics |
| DWD ICON | Icosahedral Nonhydrostatic model | Deutscher Wetterdienst, Germany | physics |
| EC GEM | Global Environmental Multiscale model | Environment and Climate Change Canada | physics |

**AIFS is the AI half**, and it is the reason this counts as a *hybrid
AI–NWP* system: a real operational neural forecasting system, not something we
trained. Everything else in the list is physics. The panel says so in words —
*Artificial Intelligence Forecasting System* — rather than with a badge.
`IFS` and `AIFS` differ by a single letter, so every chart labels them
`(physics)` and `(AI)` to keep them apart.

Also listed when expanded:
- **Persistence** — "tomorrow will be like today". Never blended. It exists
  only as the zero mark for the skill score: beating it is the minimum bar.
- **ERA5** — the Copernicus/ECMWF reanalysis used as *truth*. Every score on
  the Verification tab is measured against this.

### Forecast horizon (the rail)

Six stops, **T** (today) through **T+5**, each with the date it is valid for.
Today has no archived skill of its own, so it uses the T+1 weights. **This is the
master control — every map, chart and number below follows it.** Drag it or
click a stop.

The coloured bar fills to the selected stop, and its colour is the model
currently carrying the most weight at that range. Watch it change colour as
you drag: that *is* the product.

> **If T shows a date before today, the run is stale.** The first stop should
> always be today. Check the amber note on *Run issued*.

### Search box

Type any state or district. The map zooms and outlines it, and everything
below narrows to that area. Clear it to return to India.

### The sentence below the rail

Plain English summary of the selected lead: the date, the diagnosed spell,
which model is being trusted most and by how much, and how many cells are
flagged for heavy rain, heat and high wind. **Read this aloud in the demo.**

---

## Tab 1 — Forecast
### *Satisfies: "a dynamically blended forecast"*

The blended forecast for all India, 4,645 cells at 0.25° (~28 km).

**The map.** Colour is the blended value. The smooth field is interpolated
between cell centres; the thin contour lines are isohyets, joining points of
equal rainfall the way an operational weather chart does. Terrain shading
underneath is why the Western Ghats show up as a rainfall stripe — that is
orographic rain, and it is real, not decoration.

**Rainfall / Temperature / Wind** — the three variables the statement names.
Colour bands for rainfall follow **IMD's operational classes** (*light*,
*moderate*, *rather heavy*, *heavy*, *very heavy*, *extremely heavy*), so a
forecaster reads them without a key.

**Cell readout** (right). Hover any cell. Shows the blended value, and beneath
it **what each of the five models said for that exact cell** and the weight
each was given. This is the answer to "why should I believe this number".

**Who is driving this forecast** (right). One bar per lead time, each split by
model, summing to 100%. Long bar = that model is trusted at that range.
Notice the bars change shape as the range extends — models that are good at
day 1 are not always good at day 5, and that is the thing being exploited.

**Legend** (bottom). The colour scale with its numeric bands.

---

## Tab 2 — Model weights
### *Satisfies: "model weight maps"*

**This is the deliverable a forecaster would pin to the wall.**

**Leading source** — every cell coloured by *which* model earns the most
weight there, at the selected lead. Read it as a map of *who to trust where*.
Colours match the source colours used everywhere else.

**Where models disagree** — the same grid, coloured by how far apart the five
models are for each cell. Dark = they agree, bright = they diverge.

> This second view is the argument for the whole project. Where the models
> agree, any of them will do and blending changes nothing. Where they diverge,
> **the choice of model is the entire forecast** — and that is exactly where a
> learned weighting earns its keep.

**Weights by spell and lead** (right). A grid: weather spell down the side,
lead time across. Each cell shows the weight split for that combination. Pale
means the models score close together, so the weighting is near-even; strong
colour means one model clearly wins there. This grid is the literal answer to
the statement's demand for weights conditioned on *lead time* and *weather
regime*.

---

## Tab 3 — Verification
### *Satisfies: "improved forecast skill"*

**How each source scored.** Ranked table, rainfall RMSE in mm/day, **lower is
better**. Every number is out-of-sample.

Rows to understand:

| Row | What it is |
|---|---|
| The five model names | Each model on its own |
| **Persistence** | "Tomorrow = today". The floor. Beating it is the minimum. |
| **Equal-weight mean** | A plain average of all five, no learning at all. **This is the row that matters** — it is the benchmark most published blending schemes fail to beat. |
| **Blend (ours, live product)** | The learned weights — what `run_daily.py` actually computes, and the number we stand behind. |
| + ML correction (offline only) | Scores better, but the trained model is not saved, so the daily product cannot apply it. Shown for honesty, never quoted. |

Three columns: **RMSE** (penalises large misses hardest), **MAE** (average
miss size), **Skill vs persistence** (0 = no better than persistence, 1 =
perfect).

**The sentence under the table is computed from the table**, not written by
hand — it cannot contradict the numbers above it.

**Error against lead time.** Error growing as the forecast reaches further
ahead. The white line is the blend; the dashed line is persistence. The gap
between them is the value added, and it widens with range.

**How this is measured.** States that scores come from **contiguous
time-block cross-validation**, not a random split. This matters: neighbouring
days are strongly correlated, so a random split leaks the answer across the
boundary and inflates every score. Every row here was predicted by a model
that never saw its block.

---

## Tab 4 — Extremes
### *Satisfies: "extreme weather indicators"*

Three columns, the three hazards the statement names.

| Column | Trigger |
|---|---|
| **Heavy rainfall** | A machine-learning classifier's probability of ≥40 mm in a day, listed where it exceeds 25%. Scores **ROC-AUC 0.947**. A calibrated probability, not a yes/no flag. |
| **Heat stress** | 1.5 °C or more above that location's seasonal normal. On a live run there *is* no seasonal normal for a future date, so it falls back to an absolute threshold — and the panel says so rather than printing a meaningless "+0.0 vs normal". |
| **High wind** | Daily-maximum 10 m wind at or above 40 km/h, which is IMD warning territory. |

Each entry names the cell, where it is, and the severity.

---

## Footer

**This forecast** — the run, how many cells, the area, and that the weights
were learned offline from archived forecasts verified against ERA5.

**Forecast sources** — the five streams, the retrieval route, and the
statement that nothing is perturbed, simulated or reconstructed.

---

## The five questions a judge will ask

**"Is this real data?"**
Yes. Archived operational output from five centres at real lead times, via
Open-Meteo's Previous Runs API. `precipitation_previous_day3_ecmwf_ifs025` is
literally *what IFS predicted for that day, three days ahead*. Truth is ERA5.

**"Why does one model get 68%?"**
Nobody chose that. Constrained non-negative least squares solved for it from
measured performance against ERA5. The weights are an output, not a setting —
and they move between 52% and 87% depending on spell and range.

**"Isn't this just an ECMWF forecast, since they supply two of the five?"**
AIFS is a neural network, IFS is physics. They fail in different ways, which
is precisely why blending them helps. Be ready to add the honest caveat:
we verify against ERA5 and AIFS is *trained* on ERA5, which flatters it.
Substituting IMD gauge data is the fix, and is validated.

**"Does it beat a simple average?"**
Yes, on both — 8.424 against 9.142 RMSE, and 4.282 against 4.457 MAE. That is
7.9%, on 116 days of national verification.

**"What does the ML layer add?"**
0.26 RMSE. But the trained booster is not saved to disk, so `run_daily.py`
cannot apply it and the daily product does not use it. We quote the 8.424 the
product actually computes. Persisting it is the next improvement.

---

## 90-second demo order

1. Read the sentence under the rail aloud.
2. Open **Forecast sources** → five real institutions. "Nothing is simulated."
3. Drag the rail T+1 → T+5. Weight bars shift. **This is the product.**
4. Hover a cell → what all five said, and the weight each got.
5. Search "Kerala" → it zooms and narrows.
6. **Model weights → Where models disagree.** "Where they agree, any model
   will do. Where they diverge, the choice of model *is* the forecast."
7. **Verification** → 33% better than IFS, and ahead of a plain average. Then
   the caveat, in that order.
