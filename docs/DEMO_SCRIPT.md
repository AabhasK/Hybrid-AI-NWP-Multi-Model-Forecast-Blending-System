# 2-minute demo script

Read the **bold** lines aloud. Everything else is what to do with the mouse.
Rehearse once: the whole thing is four clicks.

Numbers below are from the **21 September 2026** run, trained on the national
archive (286 cells, 116 days). Re-check them against the screen before
recording — `run_daily.py` changes the forecast figures daily.

---

## Before you start

- Run `python run_daily.py --publish` that morning. If *Run issued* shows
  **"· yesterday"** in amber, the run is stale — fix it before recording.
- Open `dashboard.html` fresh. Collapse **Forecast sources** so the page
  starts compact.
- Start on the **Forecast** tab, **Rainfall**, lead **T+3**.
- Full screen. Hide bookmarks. 1920×1080.

---

## 0:00 — 0:20 · What it is

*Screen: top of the page, nothing clicked yet.*

> **No single weather model is best everywhere. Which one is right changes with
> the place, how far ahead you're looking, and the weather itself — and a
> forecaster has to pick one before knowing which was right.**
>
> **Blend Desk measures which model to trust, and combines five of them into
> one national forecast.**

*Click **Details** on the Forecast sources bar.*

> **Five real operational models, from four national weather centres. ECMWF's
> physics model and their AI model, NOAA, the German service, and Environment
> Canada. Nothing here is simulated — these are archived operational runs,
> verified against ERA5 reanalysis.**

*Collapse it again.*

---

## 0:20 — 0:50 · The forecast

*Screen: Forecast tab, rainfall map.*

> **This is tomorrow-plus-three over all of India — 4,645 cells at 28 km.**

*Read the amber summary line under the rail, verbatim from the screen. On
21 September it said:*

> **"Forecast for 24 September, three days ahead. An active monsoon spell.
> The blend trusts ECMWF AIFS most, at 63% of the weight."**
>
> *(The cell counts change every run — read whatever is on screen.)*

*Drag the horizon rail slowly from T+1 to T+5. Watch the weight bars on the
right change shape.*

> **One run, walked out day by day. The mix shifts as the range extends —
> a model that's good tomorrow isn't always good on day five.**

*Hover one cell in the heavy-rain area over the north.*

> **Every cell shows what each of the five models said, and how much weight
> each one got. That's the difference between a number and a forecast you can
> argue with.**

---

## 0:50 — 1:20 · The point of the whole thing

**This is the most important 30 seconds. Do not rush it.**

*Still on Forecast. Click **Temperature**.*

> **Now watch the weights.**

*Point at the "Who is driving this forecast" chart — it flips from orange to
blue.*

> **For rainfall, ECMWF's AI model carries most of the weight and their physics
> model gets almost none. Switch to temperature and it inverts — the physics
> model takes the lead and the AI model drops behind it.** (Read the exact
> percentages off the chart; they move with the run.)
>
> **The best rainfall model is one of the worst temperature models. That's
> measured, not assumed. It's why you can't just pick a favourite and use it
> for everything — and it's exactly what this system is for.**

*Click **Model weights** tab → **Where models disagree**.*

> **Where the models agree, any of them will do. Where they diverge — here,
> and here — the choice of model is the entire forecast.**

---

## 1:20 — 1:45 · Does it actually work

*Click **Verification** tab.*

> **Everything is scored out of sample, on contiguous time blocks — never a
> random split, because neighbouring days leak into each other.**

*Point at the scorecard.*

> **Against ECMWF IFS, the model a forecaster reaches for by default, we cut
> error by 29%. We beat the strongest single model, ECMWF AIFS, by 2.2%. And
> we beat a plain equal-weight average of all five by 7.9% — the benchmark
> most published blending schemes fail to clear.**

*Click **Extremes** tab.*

> **Heavy rain, heat and high wind. The rain flag is a calibrated
> probability, not a yes/no — it scores 0.947 ROC-AUC.**

---

## 1:45 — 2:00 · Close

*Back to the Forecast tab.*

> **One scheduled command refreshes the whole thing every morning. It's a
> single HTML file — no server, no install. And every source is free and
> needs no API key.**
>
> **Five models disagree. We measure which to trust, and show our working.**

*Stop.*

---

## If you have 30 seconds more

*Type "Kerala" into the search box.* It zooms, outlines the state, and every
panel narrows to it.

> **Any state or district. The forecast, the weights and the warnings all
> follow.**

---

## Hard rules

**Say these:**
- "five model streams from four centres" — not "five centres"
- "archived operational runs" — not "historical data"
- "ahead of a plain average" — not "far ahead of"

**Never say:**
- any figure from the "+ ML correction" row — that model is not saved to
  disk, so the daily product cannot compute it
- "real-time" — it is a daily run on medium-range forecasts
- that IMD data is integrated — it is not
- any number that is not on screen at that moment

**If asked "why not just use AIFS?"**
> Because it's third of five on temperature, behind ECMWF's physics model.
> The blend beats AIFS alone by 50% there. And AIFS only became operational in 2025 — its lead is something
> this system *found*, not something we assumed. Next season it could be a
> different model, and the framework would tell us.

**If asked "is AIFS flattered by your verification?"**
> Yes, and we say so. AIFS is trained on ERA5 and we verify against ERA5.
> IMD's gauge-based gridded rainfall is the fix, it needs no API key, and it
> is the next thing we would do.
