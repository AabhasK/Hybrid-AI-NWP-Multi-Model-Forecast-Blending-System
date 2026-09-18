"""
Step 2 - Synthetic multi-model forecast generation + metadata table.

Takes ERA5 ground truth and produces four forecast sources with deliberately
DISTINCT, physically-motivated error signatures, for lead times 1-5 days:

  Model A  "physics NWP proxy"    - systematic dry bias that deepens with lead;
                                    sharp at short lead; benefits from resolved
                                    orography (relatively better over the Ghats).
  Model B  "AI/ML model proxy"    - near-zero bias, higher variance, degrades
                                    only slowly with lead, but destabilises
                                    badly across monsoon regime transitions.
  Model C  "ensemble mean proxy"  - smoothed/conservative: shrunk toward local
                                    climatology, very low noise, structurally
                                    underestimates extremes.
  Model D  "persistence baseline" - naive carry-forward of the last observation
                                    available at issue time. The skill reference.

CRITICAL REALISM CONSTRAINT
---------------------------
A/B/C additionally share a common error component representing analysis /
initial-condition error that every operational system inherits. Without it the
four sources would have independent noise and any blender could average its way
to an implausibly perfect forecast. The shared term is what caps blend skill at
the 10-30% RMSE reduction range that real multi-model studies report.

Output: data/forecasts.parquet  (the training set)
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).parent
DATA = ROOT / "data"
RNG = np.random.default_rng(20260918)

LEADS = [1, 2, 3, 4, 5]

# Regime thresholds on standardised domain-mean rainfall anomaly
ACTIVE_Z = 0.50
BREAK_Z = -0.50

# Heavy-rain (extreme) definition used later by the classifier
EXTREME_MM = 40.0

MODELS = ["a", "b", "c", "d"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def smooth_field(shape, sigma, rng):
    """Spatially correlated N(0,1) field - forecast errors are not white noise."""
    f = rng.standard_normal(shape)
    f = gaussian_filter(f, sigma=sigma, mode="nearest")
    s = f.std()
    return f / s if s > 1e-9 else f


def build_grid_index(truth):
    cells = truth[["cell_id", "lat", "lon", "elevation_m"]].drop_duplicates("cell_id")
    cells = cells.sort_values(["lat", "lon"]).reset_index(drop=True)
    lats = np.sort(cells.lat.unique())
    lons = np.sort(cells.lon.unique())
    idx = {}
    for c, la, lo in zip(cells.cell_id, cells.lat, cells.lon):
        idx[c] = (int(np.where(lats == la)[0][0]), int(np.where(lons == lo)[0][0]))
    return cells, lats, lons, idx


def classify_regime(truth):
    """Active / break / normal monsoon from the standardised domain-mean anomaly."""
    dom = truth.groupby("date").rain_mm.mean().sort_index()
    z = (dom - dom.mean()) / dom.std()
    labels = np.where(z >= ACTIVE_Z, "active", np.where(z <= BREAK_Z, "break", "normal"))
    regime = pd.Series(labels, index=dom.index, name="regime")
    return dom, z.rename("domain_rain_z"), regime


PHASE = {6: "early_monsoon", 7: "peak_monsoon", 8: "late_monsoon"}


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


# --------------------------------------------------------------------------
def main():
    truth = pd.read_parquet(DATA / "era5_truth.parquet")
    cells, lats, lons, ii = build_grid_index(truth)
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(truth.date.unique())))
    nlat, nlon, nt = len(lats), len(lons), len(dates)

    dom_rain, dom_z, regime = classify_regime(truth)
    regime_prev = regime.shift(1).bfill()
    is_transition = regime.values != regime_prev.values

    print("grid %dx%d = %d cells, %d days" % (nlat, nlon, len(cells), nt))
    print("regime day counts:", regime.value_counts().to_dict())
    print("regime transition days:", int(is_transition.sum()))

    # ---- reshape truth into (time, lat, lon) cubes ------------------------
    t_idx = {d: k for k, d in enumerate(dates)}
    rain = np.full((nt, nlat, nlon), np.nan)
    temp = np.full((nt, nlat, nlon), np.nan)
    elev = np.zeros((nlat, nlon))
    cell_of = np.empty((nlat, nlon), dtype=object)

    for r in truth.itertuples(index=False):
        i, j = ii[r.cell_id]
        rain[t_idx[r.date], i, j] = r.rain_mm
        temp[t_idx[r.date], i, j] = r.t2m_mean
        elev[i, j] = r.elevation_m
        cell_of[i, j] = r.cell_id

    # ---- climatology: per-cell seasonal level x smooth domain-wide cycle ---
    cell_mean_rain = np.nanmean(rain, axis=0)
    dom_series = np.nanmean(rain, axis=(1, 2))
    dom_smooth = pd.Series(dom_series).rolling(15, center=True, min_periods=1).mean().values
    shape_factor = dom_smooth / dom_series.mean()
    clim_rain = cell_mean_rain[None, :, :] * shape_factor[:, None, None]

    cell_mean_temp = np.nanmean(temp, axis=0)
    dom_t = np.nanmean(temp, axis=(1, 2))
    dom_t_smooth = pd.Series(dom_t).rolling(15, center=True, min_periods=1).mean().values
    clim_temp = cell_mean_temp[None, :, :] + (dom_t_smooth - dom_t.mean())[:, None, None]

    # orography weight: 0 in the plains -> 1 on the Ghats crest
    oro = (elev - elev.min()) / max(elev.max() - elev.min(), 1.0)

    def rain_scale(x):
        """Rainfall forecast error grows with rainfall amount (heteroscedastic)."""
        return 0.30 + 0.70 * np.sqrt(np.maximum(x, 0.0))

    rs = rain_scale(rain)
    frames = []

    for lead in LEADS:
        # ---- shared analysis / initial-condition error (A, B, C alike) ----
        shared_r = np.stack([smooth_field((nlat, nlon), 1.6, RNG) for _ in range(nt)])
        shared_t = np.stack([smooth_field((nlat, nlon), 2.0, RNG) for _ in range(nt)])
        shared_rain_err = (0.55 + 0.30 * lead) * shared_r * rs
        shared_temp_err = (0.24 + 0.13 * lead) * shared_t

        eps_a = np.stack([smooth_field((nlat, nlon), 1.2, RNG) for _ in range(nt)])
        eps_b = np.stack([smooth_field((nlat, nlon), 0.8, RNG) for _ in range(nt)])
        eps_c = np.stack([smooth_field((nlat, nlon), 2.2, RNG) for _ in range(nt)])
        ept_a = np.stack([smooth_field((nlat, nlon), 1.4, RNG) for _ in range(nt)])
        ept_b = np.stack([smooth_field((nlat, nlon), 1.0, RNG) for _ in range(nt)])
        ept_c = np.stack([smooth_field((nlat, nlon), 2.4, RNG) for _ in range(nt)])

        # ================= MODEL A - physics NWP proxy =====================
        # dry bias deepening with lead, partially offset over resolved orography
        # sharp at short lead, resolves orography -> relatively better on the Ghats
        bias_a = (1.00 - 0.072 * lead) + 0.050 * oro[None, :, :]
        sig_a = (0.16 + 0.44 * lead) * (1.0 - 0.34 * oro[None, :, :])
        fc_a = bias_a * rain + sig_a * eps_a * rs + shared_rain_err
        t_a = temp - (0.18 + 0.11 * lead) + (0.16 + 0.15 * lead) * ept_a + shared_temp_err

        # ================= MODEL B - AI/ML proxy ===========================
        # near-unbiased, flat lead decay (its long-lead edge), but fragile at
        # regime transitions and weaker where terrain drives the signal
        trans = np.where(is_transition, 2.30, 1.0)[:, None, None]
        oro_pen = 1.0 + 0.55 * oro[None, :, :]
        sig_b = (0.92 + 0.035 * lead) * trans * oro_pen
        fc_b = (1.005 - 0.012 * lead) * rain + sig_b * eps_b * rs + shared_rain_err
        t_b = temp + 0.04 + (0.34 + 0.05 * lead) * np.sqrt(trans) * oro_pen * ept_b + shared_temp_err

        # ================= MODEL C - ensemble mean proxy ===================
        # shrink toward climatology: calm and reliable, blind to extremes.
        # NOTE the shared-error factor is 0.85, not lower: an ensemble mean
        # averages away model-PRIVATE error, but analysis/initial-condition
        # error is common to every member and does not cancel.
        alpha = 0.76 - 0.078 * lead
        fc_c = alpha * rain + (1 - alpha) * clim_rain + (0.36 + 0.11 * lead) * eps_c * rs
        fc_c = fc_c + 0.85 * shared_rain_err
        at = 0.85 - 0.045 * lead
        t_c = at * temp + (1 - at) * clim_temp + (0.18 + 0.07 * lead) * ept_c + 0.85 * shared_temp_err

        # ================= MODEL D - persistence baseline ==================
        fc_d = np.empty_like(rain)
        t_d = np.empty_like(temp)
        fc_d[lead:] = rain[:-lead]
        t_d[lead:] = temp[:-lead]
        fc_d[:lead] = clim_rain[:lead]
        t_d[:lead] = clim_temp[:lead]

        for arr in (fc_a, fc_b, fc_c, fc_d):
            np.clip(arr, 0.0, None, out=arr)

        # ---- flatten this lead into long format ---------------------------
        n_cell = nlat * nlon
        flat_cells = cell_of.ravel()
        flat_lat = np.repeat(lats, nlon)
        flat_lon = np.tile(lons, nlat)
        flat_elev = elev.ravel()

        for k, d in enumerate(dates):
            ts = pd.Timestamp(d)
            frames.append(
                pd.DataFrame(
                    {
                        "cell_id": flat_cells,
                        "lat": flat_lat,
                        "lon": flat_lon,
                        "elevation_m": flat_elev,
                        "date": np.repeat(ts, n_cell),
                        "lead_time": lead,
                        "season": PHASE[ts.month],
                        "regime": regime.loc[d],
                        "regime_transition": bool(is_transition[k]),
                        "domain_rain_z": float(dom_z.loc[d]),
                        "truth_rain": rain[k].ravel(),
                        "truth_t2m": temp[k].ravel(),
                        "clim_rain": clim_rain[k].ravel(),
                        "clim_t2m": clim_temp[k].ravel(),
                        "model_a_rain": fc_a[k].ravel(),
                        "model_b_rain": fc_b[k].ravel(),
                        "model_c_rain": fc_c[k].ravel(),
                        "model_d_rain": fc_d[k].ravel(),
                        "model_a_t2m": t_a[k].ravel(),
                        "model_b_t2m": t_b[k].ravel(),
                        "model_c_t2m": t_c[k].ravel(),
                        "model_d_t2m": t_d[k].ravel(),
                    }
                )
            )
        print("  lead %dd generated" % lead)

    df = pd.concat(frames, ignore_index=True)
    df["is_extreme"] = (df.truth_rain >= EXTREME_MM).astype(int)
    df["doy"] = df.date.dt.dayofyear
    df = df.sort_values(["date", "lead_time", "cell_id"]).reset_index(drop=True)

    out = DATA / "forecasts.parquet"
    df.to_parquet(out, index=False)

    # ---- sanity report: do the four signatures look as designed? ----------
    print("\n--- per-model error signature (all leads pooled) --------------")
    print("%-7s%10s%8s%7s%12s" % ("model", "bias(mm)", "RMSE", "corr", "ext.recall"))
    ext = df.is_extreme == 1
    for m in MODELS:
        f = df["model_%s_rain" % m]
        print(
            "%-7s%10.2f%8.2f%7.3f%12.3f"
            % (
                m.upper(),
                (f - df.truth_rain).mean(),
                rmse(f, df.truth_rain),
                np.corrcoef(f, df.truth_rain)[0, 1],
                (f[ext] >= EXTREME_MM).mean(),
            )
        )

    print("\n--- rainfall RMSE by lead time -------------------------------")
    print("%-6s%8s%8s%8s%8s" % ("lead", "A", "B", "C", "D"))
    for lead, g in df.groupby("lead_time"):
        vals = [rmse(g["model_%s_rain" % m], g.truth_rain) for m in MODELS]
        print("%-6d%8.2f%8.2f%8.2f%8.2f" % (lead, *vals))

    print("\n--- rainfall RMSE by regime (lead 3) -------------------------")
    g3 = df[df.lead_time == 3]
    print("%-10s%8s%8s%8s%8s" % ("regime", "A", "B", "C", "D"))
    for reg, g in g3.groupby("regime"):
        vals = [rmse(g["model_%s_rain" % m], g.truth_rain) for m in MODELS]
        print("%-10s%8.2f%8.2f%8.2f%8.2f" % (reg, *vals))

    print("\n--- rainfall RMSE by terrain (lead 2) ------------------------")
    g2 = df[df.lead_time == 2].copy()
    g2["terrain"] = np.where(g2.elevation_m >= 400, "ghats(>=400m)", "plains(<400m)")
    print("%-16s%8s%8s%8s%8s" % ("terrain", "A", "B", "C", "D"))
    for terr, g in g2.groupby("terrain"):
        vals = [rmse(g["model_%s_rain" % m], g.truth_rain) for m in MODELS]
        print("%-16s%8.2f%8.2f%8.2f%8.2f" % (terr, *vals))

    print("\n--- best single model per (lead x regime) --------------------")
    print("%-6s%12s%12s%12s" % ("lead", "active", "break", "normal"))
    for lead, gl in df.groupby("lead_time"):
        cells_out = []
        for reg in ("active", "break", "normal"):
            g = gl[gl.regime == reg]
            scores = {m.upper(): rmse(g["model_%s_rain" % m], g.truth_rain) for m in MODELS}
            best = min(scores, key=scores.get)
            cells_out.append("%s (%.2f)" % (best, scores[best]))
        print("%-6d%12s%12s%12s" % (lead, *cells_out))

    print("\nrows: %d   extreme cell-days (>=%dmm): %d" % (len(df), EXTREME_MM, df.is_extreme.sum()))
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
