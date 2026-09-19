# Data sources

Team **Stash&Rebase** · SIH26081

Every source below was probed live from this machine; the status column records
what the probe returned, not what documentation claims. Re-verify with the
command in each section.

---

## 1. Forecast members (what gets blended)

All retrieved from Open-Meteo's **Previous Runs API** for training and its
**Forecast API** for the daily run. Both are free and need **no API key** for
non-commercial use.

| Role | Model id | Centre | Type | Archive at lead times |
|---|---|---|---|---|
| A | `ecmwf_ifs025` | ECMWF | Physics NWP | verified, 504/504 |
| B | `ecmwf_aifs025_single` | ECMWF | **AI / data-driven** | verified, 504/504 |
| C | `gfs_seamless` | NOAA | Physics NWP | verified |
| D | `icon_seamless` | DWD (Germany) | Physics NWP | verified |
| E | `gem_seamless` | Environment Canada | Physics NWP | verified |
| *(pending)* | `jma_seamless` | JMA (Japan) | Physics NWP | verified, 504/504 |
| *(pending)* | `ukmo_seamless` | UK Met Office | Physics NWP | verified, 504/504 |
| *(pending)* | `meteofrance_arpege_world` | Météo-France | Physics NWP | verified, 504/504 |
| *(pending)* | `cma_grapes_global` | CMA (China) | Physics NWP | verified, 504/504 |

*pending* = confirmed available, not yet in the trained blend (requires
re-running the archive fetch; see `docs/DECISIONS.md` D14).

**Confirmed NOT usable:**

| id | Why |
|---|---|
| `ecmwf_aifs025` | Serves live forecasts but returns **all-null** for every `_previous_dayN` variable — no previous-runs archive. Use `ecmwf_aifs025_single`. |
| `gfs_graphcast025` | Resolves, but the lead-time archive is empty. |
| `bom_access_global` | Empty archive over India. |
| `knmi_harmonie_arome_europe`, `ncep_nbm_conus` | Regional; "No data is available for this location". |
| `wind_gusts_10m` (any model) | All-null on the previous-runs archive, so gusts cannot be verified at lead time. High-wind guidance therefore uses daily-max 10 m wind, which ERA5 does verify. |

**Re-verify:**
```bash
python -c "import json,urllib.request as u; print(json.load(u.urlopen(
 'https://previous-runs-api.open-meteo.com/v1/forecast?latitude=19&longitude=75.5'
 '&hourly=precipitation_previous_day3&past_days=20&forecast_days=1&models=jma_seamless'))['hourly'].keys())"
```

---

## 2. Verification truth

| Source | Resolution | Key needed | Status | Role |
|---|---|---|---|---|
| **ERA5** (via Open-Meteo archive) | point-sampled | no | in use | primary truth |
| **ERA5** (via Copernicus CDS) | 0.25° gridded | yes — configured | authenticated | first-party alternative |
| **IMD gridded rainfall** (via `imdlib`) | 0.25° | **no** | verified, 2025 | gauge-based truth |
| **CHIRPS** (UCSB) | 0.05° | no | reachable | second gauge option |

### The circularity caveat — and its fix

**ECMWF AIFS is trained on ERA5, and we verify against ERA5.** Part of AIFS's
margin over IFS is it being rewarded for having learned the analysis we score
it against. AIFS genuinely is better here and published results agree, but the
evaluation flatters it.

The fix is gauge-based truth, and it does **not** require the IMD API:

```bash
pip install imdlib
python -c "import imdlib as imd; d=imd.get_data('rain',2025,2025,fn_format='yearwise',file_dir='data/_imd'); print(d.get_xarray())"
# -> time 365, lat 129, lon 135, covering 6.5-38.5N, 66.5-100E
```

`imdlib` pulls IMD's own gridded rainfall from IMD Pune's public data portal —
the same underlying gauge product the paid API would serve.

**Known limitation:** the partial current-year file fails with
`mismatch in size of data-length`, so gauge verification runs on complete years.
This does not affect the live forecast.

### CDS (Copernicus) specifics

Authenticated and working. Dataset
`derived-era5-single-levels-daily-statistics` provides daily aggregates
directly — no hourly download or regridding.

- `total_precipitation` → `daily_sum`
- `2m_temperature` → `daily_mean`
- `instantaneous_10m_wind_gust` → `daily_maximum`

Note ERA5 exposes 10 m wind as u/v components; a daily-max wind *speed* cannot
be derived from the daily max of each component separately, which is why the
gust variable is the right choice on this route.

---

## 3. IMD API — ruled out

All five endpoints are live and behind one gateway, every one returning
`{"error":"API key missing"}`:

```
https://api.imd.gov.in/api/v1/state_district_rainfall_forecast
https://api.imd.gov.in/api/v1/aws_data        (+ /aws_data_mapping)
https://api.imd.gov.in/api/v1/districtrainfall
https://api.imd.gov.in/api/v1/districtwarning
```

Registration is at `https://api.imd.gov.in/public/register.php`, but **IMD does
not issue personal API keys** — institutional access only. Ruled out for this
submission.

`imd_client.py` is retained and complete: it wires all five endpoints and
auto-detects the auth scheme (`?api_key=`, `x-api-key`, `Bearer`). If the team
obtains institutional access, setting `IMD_API_KEY` in `.env` is the only
change required. What that would add, in priority order:

1. `state_district_rainfall_forecast` — IMD's own 5-day forecast as a blend
   member, at exactly our T+1…T+5 lead times
2. `aws_data` — station observations
3. `districtwarning` — score our extreme flagger against warnings IMD actually
   issued (no open equivalent exists; this is the one genuine loss)

---

## 4. Geography

| Asset | Source | Notes |
|---|---|---|
| National boundary | DataMeet `india-composite` | Depiction as used by the Government of India |
| State outlines | geohacker/india | 2011 vintage — see renames below |
| District centroids | geohacker/india | 594 districts |
| Basemap | Mapbox GL (token in `.env`) | Falls back to MapLibre + OpenFreeMap, keyless |
| Terrain DEM | Mapbox terrain-dem | Falls back to AWS terrarium tiles, keyless |

**The boundary files are 2011-census vintage.** They carry *Orissa*,
*Uttaranchal*, *Bangalore*, *Gurgaon*, *Allahabad*, and predate **Telangana**
(2014) and **Ladakh** (2019). `00b_build_places.py` renames to current usage,
keeps the old names as search aliases so both work, and adds Telangana and
Ladakh as bounding-box-only entries labelled *"State · approx"* so they are
searchable without claiming a boundary we do not have.

Simplification: 252,604 boundary points → 2,215 (0.9% kept) via
Douglas–Peucker at 0.02°, so the whole country embeds in 79 KB.

---

## 5. Rate limits — the real operational constraint

Open-Meteo prices a request by **locations × variables × days**, capped per
hour on the free tier.

| Task | Cost shape | Outcome |
|---|---|---|
| Daily live run, 4,645 cells × 7 days | cheap per cell | 186 requests, runs in minutes |
| Archive, 286 cells × 120 days × 3 vars × 5 models | expensive | exceeds the hourly quota; the fetcher waits for reset and resumes |

Measured limits, recorded so they are not rediscovered:

- 11 locations × 365 days → server-side timeout
  (`Unexpected error while streaming data: timeout`); 4 locations returns in 2.8s
- Precipitation and temperature in one request pushes generation past 50s and
  the connection drops; split into separate requests it returns in ~3s
- Quota exhaustion returns HTTP 429 with
  `"Hourly API request limit exceeded"` — hourly, not daily, so waiting works

`OPENMETEO_API_KEY` would remove this, but it is a paid plan and the free tier
is sufficient with the wait-and-resume logic in `03_fetch_real_models.py`.
