# What I need from you

The project runs end to end right now with **zero credentials**. Nothing below
blocks a demo — each item either makes it yours, or upgrades one specific part.

---

## 1. API keys — placeholders are already wired

`.env.example` is in the repo with every key documented. Copy it and fill in
whatever you have, whenever you have it:

```bash
cp .env.example .env
python config.py          # prints what is active and what each missing key buys
python build_dashboard.py # picks the token up automatically
```

`.env` is gitignored. The code reads it through `config.py`, which needs no
pip install. **Nothing breaks if a key is absent** — every one has a working
fallback, and `config.py` tells you what that fallback is.

| Key | What it unlocks | Priority | Without it |
|---|---|---|---|
| `MAPBOX_TOKEN` | Mapbox GL basemap + terrain DEM | **Do this one** | MapLibre + OpenFreeMap tiles, keyless, ~90% as good |
| `OPENMETEO_API_KEY` | Removes the archive rate limit, lets us train on a full year instead of six months | High — best value for the model | Free tier; the fetcher waits out the hourly quota and resumes |
| `IMD_API_KEY` | Verify against IMD gauge-based gridded rainfall instead of ERA5 | High — scientific | Verification stays on ERA5 (see caveat below) |
| `CDS_API_KEY` | ERA5 direct from Copernicus | Low | We already use the same ECMWF ERA5 product via a keyless mirror |

**Mapbox:** get a **public** token (starts `pk.`) at
<https://account.mapbox.com/access-tokens/>. Free tier is 50,000 map loads a
month. It gets embedded in `dashboard.html`, so restrict it by URL in the
Mapbox dashboard (add `localhost`) before sharing the file.

**Open-Meteo:** <https://open-meteo.com/en/pricing>. Non-commercial use is free
*without* a key — a key only raises the rate limit. This is the one that would
most improve the numbers, because the blend weights are currently estimated on
six months of data and more history is the main thing they're short of.

**IMD:** worth asking a mentor or your college. This is the only key that fixes
a real methodological weakness rather than a convenience one — see §4.

---

## 2. Branding — required before submission

The dashboard says "Blend Desk" with no team identity. Send me these and I'll
wire them in:

| Field | Currently |
|---|---|
| Team name | *(missing)* |
| Team leader + members | *(missing)* |
| Institute / college | *(missing)* |
| Exact PS title | "Hybrid AI–NWP multi-model forecast blending" |
| Category (Software / Hardware) | assumed Software |
| Theme name | *(missing)* |
| Team logo (PNG/SVG) | *(none)* |

Tell me if you want to keep the product name **Blend Desk** or use something
your team picked.

---

## 3. How this is different from what other teams will build

This is the section to internalise before you present. The problem statement
asks for *hybrid AI–NWP multi-model blending*. Most submissions will read that
as "train an ML model on weather data." Five things separate ours.

**1 — The "AI" is a real AI weather model, not our own regressor.**
Most teams will put their own LightGBM/LSTM in the "AI" slot. We include
**ECMWF AIFS**, an actual operational data-driven forecasting system, as one of
the *sources being blended*, alongside physics models IFS, GFS, ICON and GEM.
The ML decides *when to trust the AI model versus the physics models*. That is
the literal reading of "hybrid AI–NWP", and it is a much harder thing to
assemble than another regressor.

**2 — Real multi-model forecasts at real lead times.**
Five operational centres, leads T+1 to T+5, verified against ERA5 reanalysis.
`precipitation_previous_day3_ecmwf_ifs025` is what ECMWF actually predicted
three days ahead of that date. Nothing is simulated. Teams that cannot obtain
multi-model archives will perturb a single source and call the copies
"models" — and a judge who knows the field will ask.

**3 — The weights are the product, not a by-product.**
The PS asks for per-model weights that sum to one. We solve constrained
non-negative least squares per **(grid cell × lead time)** and per
**(weather regime × lead time)**. The "model reliability map" is a genuine
deliverable you can read off the screen: *which centre to trust, where, and how
far out*. A SHAP plot over a black box is not the same thing and does not
answer the question the PS asks.

**4 — Regime-aware, and diagnosed honestly.**
Weights change between active-spell, break-spell and normal monsoon. Critically,
the regime fed to the model is diagnosed from the **forecast fields available at
issue time**, never from the observations being predicted. An earlier version of
this code used truth-derived regime labels; that is target leakage, and we
rebuilt it. Expect most teams' numbers to be inflated by exactly this mistake.

**5 — The ML layer cannot make the forecast worse.**
The boosted correction is applied as `blend = weights·models + λ·correction`,
with λ fitted on held-out days. If the correction is noise, λ goes to zero and
the system falls back exactly to the linear weighted blend. We added this after
measuring that an unshrunk model made the blend substantially *worse* than the
weights alone. A system that degrades gracefully is an engineering argument you
can make out loud.

### The honest value proposition

Do not claim "our blend beats every model by a huge margin." Claim this:

> **You cannot know in advance which model will be best.** ECMWF AIFS wins
> overall on our domain, but the ensemble takes over at longer leads and in
> active spells, and the ranking changes by region and regime. A forecaster
> picking one model in advance picks wrong much of the time. The blend tracks
> the best available source automatically, and the reliability map shows you
> which one it is.

Against **ECMWF IFS** — the model a forecaster would reach for by default —
the blend cuts error substantially. Against the *best* model chosen with
hindsight, the margin is modest. Say both. The second number is what makes the
first one believable.

---

## 4. The one weakness to disclose before a judge finds it

We verify against **ERA5**, and **ECMWF AIFS is trained on ERA5**. Part of
AIFS's advantage over IFS in our results is it being rewarded for having
learned the exact analysis we score against. AIFS genuinely is better here, and
published results agree it beats IFS on many headline scores — but the
evaluation flatters it.

Say this yourself, in one sentence, and say the fix: verify against IMD
gauge-based gridded rainfall instead. That is what `IMD_API_KEY` is for. A team
that names its own methodological weakness and the remedy reads as rigorous.
A team that gets caught does not.

Full list of caveats is in `DATA_NOTE.md` — it is written to be handed to a
judge.

---

## 5. Numbers for the PPT

Run this and copy from its output — it prints every figure the deck needs:

```bash
python model_training.py
```

The metrics are being regenerated against the expanded real-data window. I'll
fill the final table here once that run lands rather than paste figures that
are about to change. The ones that will not change:

- **Sources**: ECMWF IFS, ECMWF AIFS, NOAA GFS, DWD ICON, EC GEM, plus
  persistence as the skill reference
- **Grid**: 121 cells at 0.5° over Maharashtra (16–21 °N, 73–78 °E)
- **Lead times**: T+1 to T+5
- **Truth**: ERA5 reanalysis
- **Validation**: 4-fold contiguous time-block cross-validation, every score
  out-of-sample

---

## 6. Demo rehearsal

**The strongest 20 seconds:** drag the horizon rail from T+1 to T+5 and let the
weight bars flip as the dominant source changes. Rehearse that.

Then:
1. Hover a grid cell — the inspector reads that cell live
2. Click to pin it — the popup shows every source's forecast and its weight
3. Hit **Terrain** — the Western Ghats rise under the rainfall field
4. Switch to **Temperature**, pick the **break-spell run** — heat alerts fill
   while rainfall alerts go quiet, because the regime changed

**Before you present:**
- [ ] Open it on the actual laptop you'll present from
- [ ] Confirm the venue has internet — map tiles, Chart.js and the webfont come
      from CDN. Every number and grid cell is embedded and renders offline, but
      the basemap goes blank without a connection. **Tell me if the venue is
      offline and I'll vendor the libraries into the file.**
- [ ] Click a cell so you've seen the popup before a judge asks you to

---

## 7. Things you do NOT need to provide

- Python packages — everything is in your Anaconda (`lightgbm` was the only gap)
- Weather data — fetched and cached in `data/`
- Any credential, to run or demo this
- A server — `dashboard.html` is one self-contained file

## 8. Open questions for you

1. **Region** — locked to Maharashtra. Say the word if the PS or your mentor
   wants Odisha or a wider India domain; it is a constant at the top of the
   fetch script.
2. **Category** — I've assumed Software.
3. **Architecture diagram** — want one generated from the pipeline for a slide?
