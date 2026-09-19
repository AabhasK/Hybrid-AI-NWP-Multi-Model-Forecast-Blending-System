# Blend Desk — Hybrid AI–NWP Multi-Model Forecast Blending

**SIH26081** · Ministry of Earth Sciences / NCMRWF · Team **Stash&Rebase**

Five global weather models disagree about tomorrow. This learns which one to
trust — for each place, each day ahead and each kind of weather — and blends
them into a single forecast.

**Open `dashboard.html`.** One self-contained file, no server, no build step.

---

## What it does

| Problem-statement deliverable | Where it lives |
|---|---|
| Dynamically blended forecast | **Forecast** tab — rainfall, temperature and wind over all India at 0.25° |
| Model weight maps | **Model weights** tab — which centre leads each cell, plus where the centres disagree |
| Improved forecast skill | **Verification** tab — scored against every member, a plain equal-weight mean, and persistence |
| Extreme weather guidance | **Extremes** tab — heavy rainfall, heat stress and high wind |
| Operational workflow | `run_daily.py` — fetches today's runs and publishes, schedulable |

## What is being blended

Real archived output from five operational centres, at real lead times T+1…T+5.

| | Source | Type |
|---|---|---|
| A | **ECMWF IFS** | Physics NWP |
| B | **ECMWF AIFS** | **AI / data-driven** |
| C | **NOAA GFS** | Physics NWP |
| D | **DWD ICON** | Physics NWP |
| E | **EC GEM** | Physics NWP |
| F | Persistence | Skill reference, not a blend member |

Because AIFS is a genuine operational AI forecasting system and the rest are
physics models, *"hybrid AI–NWP"* is literal here rather than a proxy for it.
Truth is **ERA5 reanalysis**.

---

## Running it

```bash
cp .env.example .env        # optional; everything works without any key
python config.py            # shows what is configured and what each key buys

python 00_build_region.py   # India boundary + the two analysis grids
python 00b_build_places.py  # searchable gazetteer (34 states, 594 districts)
python 03_fetch_real_models.py   # archived multi-model forecasts + ERA5 truth
python model_training.py         # weights, blender, extreme flagger, metrics
python run_daily.py              # today's live blend over India
python export_dashboard_data.py
python build_dashboard.py        # -> dashboard.html
```

`run_daily.py --publish` does the last three in one step. Schedule it:

```
0 7 * * *  cd /path/to/NWP-SIH && python run_daily.py --publish
```

Requires `numpy pandas scipy scikit-learn lightgbm pyarrow joblib`.
On this machine: `C:/Users/khand/anaconda3/python.exe`.

---

## How it works

**Two halves, deliberately separated.**

*Offline* (`model_training.py`) estimates the weights. It needs months of
archived forecasts whose outcomes are known, so it is slow and historical.
Constrained non-negative least squares gives sum-to-one weights per
**(weather regime × lead time)** and per **(grid cell × lead time)** — the
interpretable object the problem statement asks for. A LightGBM correction then
learns the residual on top, shrunk by a factor λ fitted on held-out days so a
useless correction decays to zero and the system falls back exactly to the
linear blend.

*Online* (`run_daily.py`) applies them. It fetches today's runs, diagnoses the
weather regime **from the forecast fields themselves**, and combines the
members. It takes seconds and never waits on verification data that cannot
exist yet for a future date.

**Two grids, for the same reason.** The archive is priced per cell *per day*,
so weights are fitted on a coarse 1° grid (286 land cells). The daily run only
needs the next week, so it runs at 0.25° (4,645 cells, ~28 km) — fine enough
that a city search lands in a meaningful box. The weights transfer because they
are fitted per regime and lead, not per cell.

---

## Honesty

These are the things we would rather say ourselves than be caught on.

- **The equal-weight mean is hard to beat, and on the current verification set
  it is still ahead of the learned blend.** The dashboard's verdict sentence is
  computed from the table and says so.
- **We verify against ERA5, and ECMWF AIFS is trained on ERA5**, which flatters
  it. Gauge-based truth via `imdlib` (IMD's own 0.25° gridded rainfall, no API
  key) is validated and is the fix.
- **A live run has no climatology**, so heat stress switches from an anomaly to
  an absolute threshold and the panel says why.
- Scores come from **contiguous time-block cross-validation**, never a random
  split, and the regime feature is diagnosed from forecasts rather than from the
  observations being predicted.

Full detail in **`docs/DECISIONS.md`** (20 numbered decisions, each with the
measurement that settled it, including the bugs) and **`DATA_NOTE.md`**.

---

## Files

| | |
|---|---|
| `dashboard.html` | **The deliverable.** Self-contained |
| `dashboard_template.html` | Source for the above — edit this, not the built file |
| `00_build_region.py` | India boundary, mask, and the training + live grids |
| `00b_build_places.py` | Searchable gazetteer of states and districts |
| `03_fetch_real_models.py` | Archived multi-model forecasts at lead times |
| `model_training.py` | Weights, blender, extreme flagger, all metrics |
| `run_daily.py` | **The operational routine** |
| `config.py` / `.env.example` | Credentials, all optional, each with a fallback |
| `imd_client.py` | IMD API client, ready if institutional access appears |
| `docs/DECISIONS.md` | Engineering decision log |
| `docs/DATA_SOURCES.md` | Every source, live-probe status, rate limits |
| `TEAM.md` | What the team needs to supply |
| `02_synth_models.py`, `01_fetch_era5.py` | Superseded synthetic pipeline, kept as fallback |
