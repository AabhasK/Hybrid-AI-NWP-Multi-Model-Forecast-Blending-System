# What I need from you

Everything in this repo runs end to end right now with no input from you — you can open
`dashboard.html` today and demo it. The list below is what would make it *yours* and
close the gaps a judge might poke at.

Ordered by how much it matters. Items 1–3 take about twenty minutes and I'd do them
before anything else.

---

## 1. Branding — REQUIRED before submission

The dashboard currently says **"Blend Desk"** and **"SIH26081"** with no team identity.
Send me these and I'll wire them in (or edit `dashboard_template.html` and re-run
`python build_dashboard.py`):

| Field | Where it lands | Currently |
|---|---|---|
| Team name | Header, beside the title | *(missing)* |
| Team leader + members | Footer credit line | *(missing)* |
| Institute / college | Header subtitle | *(missing)* |
| Exact PS title | Header subtitle | "Hybrid AI–NWP multi-model forecast blending" |
| PS number confirmation | Header | SIH26081 |
| Category (Software / Hardware) | Footer | *(missing)* |
| Theme name | Footer | *(missing)* |

Also useful: a **team or college logo** as PNG/SVG. There's a generated circular mark in
the header (`.sigil`) that I'd swap for it.

> **Tell me if you'd rather I keep the product name "Blend Desk"** or rename it to
> something your team picked. It appears in the title, the browser tab and the footer.

## 2. Confirm the demo run — 2 minutes

During the live demo, the dashboard opens on a **specific forecast run**. Right now it
opens on `2023-07-16`, an active-spell run with heavy rainfall alerts firing. Two runs
are worth rehearsing:

- **`2023-07-16` (active spell)** — the rainfall story. Alerts fire, Model B dominates at
  long lead. This is the better opener.
- **`2023-06-19` (break spell)** — the heat story. Switch the map to *Temperature* and the
  heat-stress panel fills up while rainfall alerts go quiet.

**The single strongest 20 seconds of the demo** is dragging the horizon rail from T+1 to
T+5 and letting the judges watch the weight bars flip from blue (physics NWP) to orange
(AI model). Rehearse that. If you'd like a different default run, tell me the date.

## 3. Numbers for the PPT — copy these exactly

These are the load-bearing figures. All are out-of-sample.

| Metric | Value |
|---|---|
| Blended rainfall RMSE | **4.24 mm/day** |
| Best individual model RMSE | 4.96 mm/day (AI/ML proxy) |
| **Error reduction vs best single model** | **14.6%** |
| Skill score vs persistence baseline | **0.611** |
| Blended 2 m temperature RMSE | 0.83 °C (best single: 0.85 °C) |
| Heavy-rain flagger ROC-AUC | **0.983** |
| Heavy-rain flagger PR-AUC | 0.786 (26× the 2.97% base rate) |
| Precision / recall at p ≥ 0.40 | 81% / 73% |
| Largest regime gain | **26.7%** RMSE cut during break spells |
| Largest lead-time gain | **16.5%** at T+5 |
| Training set | 55,660 rows · 121 cells · 92 days · 5 lead times |

The one-line claim: *"A learned blend cuts rainfall forecast error 14.6% below the best
individual model, and the improvement grows with lead time — 16.5% at day five."*

**If a judge asks why the blend only gains 1.8% at T+1:** because at day one the physics
model is genuinely near-optimal and the blender correctly declines to interfere. That is
the system behaving properly, not underperforming. Say it that way — it's a strong answer.

---

## 4. Optional — real ERA5 via Copernicus instead of the mirror

Not needed. `01_fetch_era5.py` pulls genuine ERA5 from the Open-Meteo archive with no
API key, and the data is already cached in `data/`. If you want the Copernicus CDS route
for the writeup:

1. Register at <https://cds.climate.copernicus.eu>
2. Put your key in `%USERPROFILE%\.cdsapirc`
3. Send me the key location and I'll add a `cdsapi` path to `01_fetch_era5.py`

Be aware CDS requests queue for anywhere from 20 minutes to several hours. **Don't do
this in the last 48 hours before the deadline.**

## 5. Optional — real multi-model forecast data

This is the one thing that would materially strengthen the project, and the one thing
I couldn't get. If you or a mentor has access to any of these, tell me and I'll write the
loader:

- IMD or NCMRWF gridded forecast archives (NCUM / NEPS output)
- ECMWF IFS open data (<https://data.ecmwf.int/forecasts>) — genuinely public, 0.25°,
  though only ~4 days of rolling archive unless you start collecting now
- GFS archive via NOAA NOMADS
- Any AI-model output: GraphCast, Pangu-Weather, FourCastNet, Aurora

**If you can start a daily cron collecting ECMWF open data today**, by demo day you'd have
a couple of weeks of real multi-model output and could replace at least one synthetic
stream with the real thing. That single change upgrades the whole claim. Say the word and
I'll write the collector.

## 6. Check before you present

- [ ] Open `dashboard.html` on **the actual laptop** you'll present from
- [ ] Confirm the venue has **internet** — map tiles, Chart.js, Leaflet and the webfont
      load from CDN. Everything that carries meaning is embedded and renders offline, but
      the basemap goes blank without a connection. **Tell me if the venue is offline and
      I'll vendor the libraries into the file.**
- [ ] Try it at the presentation resolution — tested at 1512×950; it reflows to phone width
- [ ] Click a grid cell so you've seen the popup before a judge asks you to

---

## Things you do NOT need to provide

- Python packages — everything installed into your Anaconda (`lightgbm` was the only gap)
- ERA5 data — fetched and cached in `data/`
- Any API key, account or credential
- A server — `dashboard.html` is one self-contained file, no build step

## Questions I couldn't answer without you

1. Do you want the dashboard to carry a **disclosure line about synthetic sources on the
   face of the UI**, or keep it in `DATA_NOTE.md` only? Right now the footer says the
   sources are synthetic. Some judges reward the candour; some teams prefer it not be the
   first thing read. **My recommendation: leave it.** If a judge finds it themselves you
   look careless; volunteering it makes you look rigorous.
2. Is this **Software** category? I've assumed so.
3. Do you need a **separate architecture diagram** slide? I can generate one from the
   pipeline if useful.
