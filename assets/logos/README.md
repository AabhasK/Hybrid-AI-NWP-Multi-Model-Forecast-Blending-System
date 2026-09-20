# Source logos

Drop logo files here and `build_dashboard.py` inlines them into
`dashboard.html` as base64 data URIs, so the deliverable stays a single file.

**Filename must match the slug exactly** (the extension may be any of
`.svg .png .jpg .webp`; SVG is preferred, transparent PNG is fine):

| File | Used for | Where to get it |
|---|---|---|
| `ecmwf.*` | ECMWF IFS **and** ECMWF AIFS (one logo covers both) | ecmwf.int press/media kit |
| `noaa.*` | NOAA GFS | noaa.gov logo guidelines |
| `dwd.*` | DWD ICON | dwd.de |
| `eccc.*` | Environment and Climate Change Canada GEM | canada.ca |
| `copernicus.*` | ERA5 verification truth (Copernicus C3S) | climate.copernicus.eu |

Any logo that is missing falls back to a text monogram, so the strip never
shows a broken image. Add them in any order.

**Sizing:** the slot is 34×34 px and uses `object-fit:contain`, so any aspect
ratio works. Prefer a square or near-square crop. Light-on-dark reads best —
the panel background is `#171613`.

**Not logos of the blended sources, but worth having for the deck:**
MoES / NCMRWF, SIH 2026, and the team's college mark. Those belong in the PPT
rather than the dashboard, so keep them out of this folder.
