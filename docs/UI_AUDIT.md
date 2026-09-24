# UI audit — 24 Sep 2026

Audit of the redesigned dashboard (commits `bb7414a`…`6950ee3`) at 1920×1080,
against the problem statement and the demo. **Suggestions only — nothing here
has been changed.** Ranked by how much it would cost in front of judges.

Screenshots referenced are in `docs/assets/`.

---

## Must fix before the demo

### 1. Alerts are located by coordinates, not places
**Extremes tab.** Every alert reads like *"C0846 at 17.9°N 81.9°E"*. For a
**Disaster Management** problem statement this is the weakest point on the page:
a district officer cannot act on a lat/long.

**The fix is cheap — the data is already loaded.** The page's gazetteer (`PLACES`)
has all **594 districts with centroids**. The top alert would read
**"Malkangiri, Odisha"**. The click popups already do this ("Rainfall at
Malkangiri"), so the extremes list is just inconsistent with them.

Caveat: nearest-centroid is not point-in-polygon, so near a district border it
can pick the neighbour. Label it *"near Malkangiri"* or use the state outline
already drawn for search.

### 2. The popup donut has no labels
**Forecast tab, click any cell** (`03a-cell-rainfall.png`). The donut shows four
coloured arcs and nothing says which model is which. A judge cannot read it
without being told orange = ECMWF AIFS.

The previous readout also listed **what each model forecast** for that cell, not
just its weight. That is gone, and it was the answer to *"why should I believe
this number?"*. Suggest a compact legend beside the donut with each model's
value and weight.

### 3. The section heading makes a false promise
The Forecast tab says *"hover any cell to see what each centre said and how much
weight it was given"*. It opens on **click**, not hover, and it no longer shows
what each centre said. Either restore the per-model values (see 2) or change
the sentence.

### 4. The temperature popup shows a rainfall alert
Popup titled **"2 m temperature at Malkangiri"** displays *"⚠ Very heavy
rainfall (142.7 mm)"* (`03b-cell-temperature.png`). Either show the alert for
the variable on screen, or label it as "all alerts for this place".

---

## Should fix

### 5. The six outlook cards all say "24°"
They show the **national mean** temperature — the average of −18.5 °C in Ladakh
and +35.3 °C in Rajasthan. It genuinely sits at 23.8–24.4 °C all week, so it
rounds to 24° six times in a row, which reads as a frozen display.

It is not a bug, but it describes nowhere. Options: show the national **range**
(−18° to 35°), show the **hottest** value (heat is the hazard), or show the
**searched location's** value once one is selected — which is what "My location"
implies anyway. The same applies to the rainfall mean on each card.

### 6. The strongest argument is only visible in a popup
The rainfall → temperature weight flip (AIFS leads rain, IFS leads temperature)
is the answer to *"why not just use AIFS?"*. It is now only visible by clicking
a cell, switching variable, and clicking again. The national per-lead weights
chart ("Who is driving this forecast") still computes correctly but is hidden
by `#pane-forecast .dock{display:none!important}`.

Consider bringing a small version of that chart back, or showing the per-variable
split somewhere persistent.

### 7. The "Weights by spell and lead" matrix is all "B"
**Model weights tab** (`04-reliability-map.png`). The matrix is the rainfall-only
table, so every cell is ECMWF AIFS and it undersells the per-variable story. It
also labels models with single letters — "B" means nothing to a judge. Use short
names or colour chips, and follow the Rainfall/Temperature toggle.

### 8. "+ ML correction (offline only)" ranks first on the scorecard
**Model comparisons.** It is the best-scoring row, so it sorts to the top — and
the first thing a judge reads is a number the product does not produce. Keep it
visible for honesty, but move it below a divider or into a footnote so the eye
lands on *"Blend (ours, live product)"* first.

### 9. The staleness warning was removed
The old header showed *"Run issued 20 Sept 00Z · yesterday"* in amber. The
redesign dropped it, so if the server refresh fails the page silently shows old
data. With a 3-hour refresh this is less likely, but a one-line indicator costs
nothing.

### 10. Temperature win is not on the scorecard
Only rainfall is scored. The blend beats ECMWF AIFS by **50% on temperature** —
the single most persuasive number in the project — and it is not on screen.

---

## Polish

| # | Issue | Where |
|---|---|---|
| 11 | 7 px horizontal page overflow at 1920 px — a horizontal scrollbar appears | whole page |
| 12 | No favicon; the browser tab shows a blank icon | `<head>` |
| 13 | "Mapbox GL" engine label floats on its own line under the Model weights heading | Model weights tab |
| 14 | Extremes shows the top 60 but does not say "top 60 of 534" | Extremes tab |
| 15 | Extremes text reads *"at T."* for today — *"today"* reads better | Extremes subtitles |
| 16 | Body font is **Inter**. The team earlier asked to move away from a font that "looks AI-generated"; Inter is the most common default in generated dashboards. Worth a deliberate decision rather than a default | global |

---

## What works well

- **The redesign reads much more like a finished product.** The outlook cards,
  plain-English summary and named-place popups are a real improvement.
- **Named places in popups** — "Rainfall at Malkangiri" beats any coordinate.
- **The reliability map has genuine spatial structure** — IFS across the
  Himalayan belt and Punjab, GFS and GEM pockets. It is no longer one colour.
- **The temperature inversion still works** — rainfall AIFS 83%, temperature
  IFS 66% — and the summary line names the right model for each variable.
- **Scorecard and verdict are correct** and computed from the data.
- **The Docker refresh** turns this from a script into something that can
  actually sit on a server.
