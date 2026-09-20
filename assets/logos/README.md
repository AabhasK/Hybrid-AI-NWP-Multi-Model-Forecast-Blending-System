# Source logos

Drop logo files here and `build_dashboard.py` inlines them into
`dashboard.html` as base64 data URIs, so the deliverable stays a single file.

## Naming

Matching is **tolerant** — a file only has to *start with* the slug, so
`noaa-gfs.png`, `NOAA.svg` and `noaa_logo.png` all resolve to `noaa`. Case is
ignored. Extensions: `.svg .png .jpg .webp` (SVG preferred).

| Slug | Used for | Status |
|---|---|---|
| `ecmwf` | ECMWF IFS **and** ECMWF AIFS (one logo covers both) | **supplied** |
| `noaa` | NOAA GFS | **supplied** (`noaa-gfs.png`) |
| `dwd` | DWD ICON | **supplied** (`DWD-icon.png`) |
| `openmeteo` / `open-meteo` | Open-Meteo, the retrieval API | **supplied** |
| `eccc` | Environment and Climate Change Canada — EC GEM | **missing** |
| `copernicus` | ERA5 verification truth (Copernicus C3S) | **missing** |

Anything missing falls back to a text monogram, so the strip never shows a
broken image. `eccc` and `copernicus` are the only two outstanding.

## Sizing

The expanded slot is 34×34 px and the collapsed chip is 15×15, both using
`object-fit:contain`, so any aspect ratio works. Prefer a square or near-square
crop. Light-on-dark reads best — the panel background is `#171613`. A large PNG
is fine but inflates `dashboard.html`; keep each file under ~80 KB.

## Not for this folder

MoES / NCMRWF, SIH 2026 and the team's college mark belong in the PPT, not the
dashboard. Keep them out of here or they will be inlined for no reason.
