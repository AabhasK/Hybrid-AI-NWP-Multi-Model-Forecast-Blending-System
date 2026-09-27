# Blend Desk — Hybrid AI–NWP Multi-Model Forecast Blending

**SIH26081** · Ministry of Earth Sciences / NCMRWF · Team **Stash&Rebase**

Five global weather models disagree about tomorrow. This learns which one to
trust — for each place, each day ahead and each kind of weather — and blends
them into a single forecast.

**Deploy once on a server.** Users open the shared dashboard URL in a browser; no
local installation is needed for them.

---

## What it does

| Problem-statement deliverable | Where it lives |
|---|---|
| Dynamically blended forecast | **Forecast** tab — rainfall, temperature and wind over all India at 0.25° |
| Model weight maps | **Model weights** tab — which centre leads each cell, plus where the centres disagree |
| Improved forecast skill | **Verification** tab — scored against every member, a plain equal-weight mean, and persistence |
| Extreme weather guidance | **Extremes** tab — heavy rainfall, heat stress and high wind |
| Operational workflow | `ops/server_refresh.py` + Docker Compose — fetch, blend, publish, and serve on a recurring schedule |

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

To preview the checked-in dashboard without fetching data or retraining, open
`dashboard.html` in a browser.

```bash
cp .env.example .env        # optional; everything works without any key
python config.py            # shows what is configured and what each key buys

python 00_build_region.py   # India boundary + the two analysis grids
python 00b_build_places.py  # searchable gazetteer (34 states, 594 districts)
python 03_fetch_real_models.py   # archived multi-model forecasts + ERA5 truth
python model_training.py         # weights, held-out skill, calibration, metrics
python run_daily.py              # today's live blend over India
python export_dashboard_data.py
python build_dashboard.py        # -> dashboard.html
```

`run_daily.py --publish` does the last three in one step and includes today's
forecast (T) through T+5. The T blend uses the nearest trained weights, T+1.

### Deploy as a shared server dashboard

The Docker Compose deployment runs the complete operational cycle on the
server: fetch live model runs, apply the trained blend, rebuild the dashboard,
and atomically publish the new page for every user. It runs immediately at
startup, then every three hours by default. The last successful dashboard
stays available if a later refresh fails. Each API response is cached for two
hours to let an interrupted fetch resume; that cache expires before the next
scheduled run so the dashboard receives fresh forecasts.

```bash
docker compose up -d --build
```

Open `http://<server-address>:8080`. Set `PORT` in a server-side `.env` file to
change the published port, or `REFRESH_INTERVAL_SECONDS` to change the refresh
interval (for example, `3600` for hourly). Set `LIVE_CACHE_TTL_SECONDS` below
the refresh interval (for example, `2400` for hourly) so each scheduled run
retrieves new data while retries can reuse recent batches. Keep exactly one
refresher service instance so two jobs do not run at once. For a public
deployment, put the web service behind the server's HTTPS reverse proxy and
allow its port through the server firewall.

Optional `OPENMETEO_API_KEY` and `MAPBOX_TOKEN` values in the server `.env`
are passed into the refresher container. No API key is required for the
default forecast source.

The server needs outbound access to the forecast data source used by
`run_daily.py`. To update the application or trained files, redeploy the image
with `docker compose up -d --build`; the generated dashboard volume is retained.
Users only need the shared URL. The older macOS LaunchAgent setup is no longer
used.

The server image installs its runtime dependencies from
`requirements-runtime.txt`. It uses the trained artifacts and grid already in
the project; retraining is an offline maintenance step, not something the
routine repeats every refresh. `docker compose logs -f refresher` shows fetch,
blend, and publish progress; `docker compose logs -f web` shows the web server.

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
members. Rainfall uses 80% regime weights and 20% regional weights;
temperature uses 20% regime weights and 80% regional weights. Those shares
were selected from four contiguous held-out date blocks. Wind keeps the
regime/lead mix until locally verified wind weights are trained.

**Two grids, for the same reason.** The archive is priced per cell *per day*,
so regional weights are fitted on a coarse 1° grid (286 land cells). The daily
run only needs the next week, so it runs at 0.25° (4,645 cells, ~28 km) — fine
enough that a city search lands in a meaningful box. Each live cell inherits
regional weights from its nearest training cell. The dashboard map and cards
read the weights saved with the blended forecast, including any adjustment for
a missing model value.

---

## Honesty

These are the things we would rather say ourselves than be caught on.

- **The equal-weight mean is a stubborn benchmark.** The operational blend clears it by
  8.9% on the national verification set (8.326 vs 9.142 RMSE), but it beat an
  earlier regional build, and the dashboard's verdict sentence is computed from
  the table rather than asserted, so it cannot drift from the numbers.
- **The best-scoring pipeline is not the one that ships.** A boosted correction
  reaches 8.164, but it is not persisted to disk, so the daily run applies the
  learned weights alone. The scorecard labels both rows and marks the
  weights-only row as the product.
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
| `ops/verify_regional_skill.py` | Held-out skill for the operational regional mix |
| `run_daily.py` | **The operational routine** |
| `config.py` / `.env.example` | Credentials, all optional, each with a fallback |
| `imd_client.py` | IMD API client, ready if institutional access appears |
| `docs/DECISIONS.md` | Engineering decision log |
| `docs/DATA_SOURCES.md` | Every source, live-probe status, rate limits |
| `docs/DEMO_SCRIPT.md` | Two-minute demo, timed and scripted |
| `docs/DASHBOARD_GUIDE.md` | What every element on screen means |
| `docs/PPT_BRIEF.md` | Slide-by-slide content, numbers and design system for the deck |
| `docs/DESIGN_PROMPT.md` | Copy-paste prompt for the slide-building agent |
| `docs/UI_AUDIT.md` | Current UI issues, ranked |
| `02_synth_models.py`, `01_fetch_era5.py` | Superseded synthetic pipeline, kept as fallback |
