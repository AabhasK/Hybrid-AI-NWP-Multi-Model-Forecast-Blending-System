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

### Header

**Blend Desk** and a one-line description on the left. On the right, the four
tabs — **Forecast · Model weights · Model comparisons · Extremes** — and the
console clock in IST.

### 6-day outlook

Six cards, **Today** through **+5 days**, each with the date it is valid for.
**This is the master control** — click a card and every map, chart and number
below moves to that day. It replaced the older horizon slider.

Each card shows an icon, the mean temperature, a rain descriptor, and rainfall
and wind. These are **national averages across all 4,645 cells** — see
`docs/UI_AUDIT.md` item 5 for why that matters.

Today has no archived skill of its own, so it uses the T+1 weights.

> **If the first card shows a date before today, the run is stale.** The page
> no longer flags this itself — check it before any demo.

### My location, search, run selector

**My location** centres the map on the viewer. **Search** takes any state or
district: the map zooms and outlines it, and the panels narrow to it. The
**Run** menu picks which day's issue you are looking at.

### The sentence below the cards

Plain English summary of the selected day: the date, the diagnosed monsoon
spell (active, break or normal — read from the *forecasts*, never from what
actually happened), which model the blend trusts most and by how much, and how
many cells are flagged for heavy rain, heat and high wind. **It changes with
the variable** — on Temperature it names a different model. Read it aloud in
the demo.

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

**Click any cell** to open its breakdown: the place name, the grid point, when
it is valid, and a **donut showing how the five models were weighted there**,
with the blended value in the centre and any active alert beneath.

**Switch Rainfall → Temperature and click the same cell again** — the donut
changes from mostly orange (ECMWF AIFS) to mostly blue (ECMWF IFS). That flip is
the whole argument for blending, shown on one location.

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

## Tab 3 — Model comparisons
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

**Forecast sources** — the five model streams as logo chips, plus
*verified vs ERA5*. This is where the sources live now; there is no longer a
separate sources panel at the top of the page.

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

## Demo order

See **`docs/DEMO_SCRIPT.md`** — the single canonical script, kept in one place
so it cannot drift from this guide.
