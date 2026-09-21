"""
Independent cross-check against two consumer forecast providers.

These are NOT blend members and must never become them. AccuWeather and
Google Weather are *downstream products*: Google's own documentation
describes its service as "a blend of AI weather models and traditional
forecasting systems", and AccuWeather post-processes the same GFS / ECMWF
output that Blend Desk already weights directly. Feeding either back into
the NNLS would double-count sources that are already in the blend and
break the independence the weighting assumes.

Neither can be verified at lead time in any case. AccuWeather publishes no
historical forecasts at all, and Google's history caps at 24 cached hours,
so there is nothing to fit a skill-based weight against.

What they ARE good for is a sanity check a judge can relate to: does the
blend agree with what a phone app says for a city they know? And when it
does, the follow-up question answers itself - both consumer apps give a
number and nothing else, while Blend Desk can name the model that drove it
and show how that model scored.

Costs ~10 calls per provider per day, which fits inside AccuWeather's
50/day and Google's 10,000/month free tiers.

Run:  python crosscheck.py
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import config

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "crosscheck.json"
LOCCACHE = DATA / "_crosscheck_locations.json"

ACCU_BASE = "http://dataservice.accuweather.com"
GOOGLE_BASE = "https://weather.googleapis.com/v1/forecast/days:lookup"

# A spread across climate zones rather than just the biggest cities: west
# coast monsoon, Gangetic plain, arid northwest, peninsular interior, the
# northeast, and the southern tip.
CITIES = [
    ("Mumbai",     19.076, 72.878),
    ("Delhi",      28.614, 77.209),
    ("Kolkata",    22.573, 88.364),
    ("Chennai",    13.083, 80.270),
    ("Bengaluru",  12.972, 77.594),
    ("Hyderabad",  17.385, 78.487),
    ("Ahmedabad",  23.023, 72.571),
    ("Jaipur",     26.912, 75.787),
    ("Guwahati",   26.144, 91.736),
    ("Kochi",       9.931, 76.267),
]

LEADS = [1, 2, 3, 4, 5]


def fetch(url, tries=3, timeout=30):
    """GET and parse JSON, or return None. A cross-check that cannot be
    reached must never take the dashboard build down with it."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BlendDesk/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 401/403 means a bad or absent key; retrying will not help.
            if e.code in (401, 403):
                print("      HTTP %d - check the key" % e.code)
                return None
            if e.code == 503 and attempt < tries - 1:
                continue
            print("      HTTP %d" % e.code)
            return None
        except Exception as e:
            if attempt == tries - 1:
                print("      %s" % type(e).__name__)
                return None
    return None


# ----------------------------------------------------------------- AccuWeather
def accu_location_keys(key):
    """AccuWeather addresses forecasts by an opaque location key, so each
    city costs one extra lookup. They do not change, so cache them forever
    and spend the daily quota on forecasts instead."""
    cache = {}
    if LOCCACHE.exists():
        cache = json.loads(LOCCACHE.read_text(encoding="utf-8"))
    missing = [c for c in CITIES if c[0] not in cache]
    for name, lat, lon in missing:
        url = "%s/locations/v1/cities/geoposition/search?apikey=%s&q=%.4f,%.4f" % (
            ACCU_BASE, key, lat, lon)
        print("    locating %s" % name)
        j = fetch(url)
        if j and isinstance(j, dict) and j.get("Key"):
            cache[name] = j["Key"]
    if missing:
        LOCCACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache


def accu_forecast(key, loc_key):
    url = "%s/forecasts/v1/daily/5day/%s?apikey=%s&metric=true&details=true" % (
        ACCU_BASE, loc_key, key)
    j = fetch(url)
    if not j or "DailyForecasts" not in j:
        return {}
    out = {}
    for i, d in enumerate(j["DailyForecasts"][:5], start=1):
        # AccuWeather splits precipitation across Day and Night, so a daily
        # total is the sum of both halves - taking only Day undercounts.
        day = (d.get("Day") or {}).get("TotalLiquid") or {}
        night = (d.get("Night") or {}).get("TotalLiquid") or {}
        rain = float(day.get("Value") or 0) + float(night.get("Value") or 0)
        temp = (d.get("Temperature") or {})
        tmax = (temp.get("Maximum") or {}).get("Value")
        tmin = (temp.get("Minimum") or {}).get("Value")
        t2m = None
        if tmax is not None and tmin is not None:
            t2m = (float(tmax) + float(tmin)) / 2.0
        out[i] = {"rain": round(rain, 1),
                  "t2m": round(t2m, 1) if t2m is not None else None}
    return out


# --------------------------------------------------------------------- Google
def google_forecast(key, lat, lon):
    q = urllib.parse.urlencode({
        "key": key, "location.latitude": "%.4f" % lat,
        "location.longitude": "%.4f" % lon, "days": 6, "pageSize": 6})
    j = fetch("%s?%s" % (GOOGLE_BASE, q))
    if not j or "forecastDays" not in j:
        return {}
    out = {}
    for i, d in enumerate(j["forecastDays"][:6], start=0):
        if i == 0:
            continue                      # day 0 is today; our leads start at T+1
        # Same day/night split as AccuWeather.
        tot = 0.0
        for half in ("daytimeForecast", "nighttimeForecast"):
            qpf = (((d.get(half) or {}).get("precipitation") or {}).get("qpf") or {})
            tot += float(qpf.get("quantity") or 0)
        tmax = (d.get("maxTemperature") or {}).get("degrees")
        tmin = (d.get("minTemperature") or {}).get("degrees")
        t2m = None
        if tmax is not None and tmin is not None:
            t2m = (float(tmax) + float(tmin)) / 2.0
        out[i] = {"rain": round(tot, 1),
                  "t2m": round(t2m, 1) if t2m is not None else None}
    return out


# ----------------------------------------------------------------- our numbers
def our_forecast():
    """Read the blend for the same cities from the live run, so the panel
    compares like with like rather than re-deriving anything."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    f = DATA / "live_blend.parquet"
    if not f.exists():
        print("  no live_blend.parquet yet - run run_daily.py first")
        return {}
    df = pd.read_parquet(f)
    out = {}
    for name, lat, lon in CITIES:
        d2 = (df["lat"] - lat) ** 2 + (df["lon"] - lon) ** 2
        cell = df.loc[d2.idxmin(), "cell_id"] if "cell_id" in df.columns else None
        sub = df[df["cell_id"] == cell] if cell is not None else df.loc[[d2.idxmin()]]
        per = {}
        for L in LEADS:
            row = sub[sub["lead_time"] == L] if "lead_time" in sub.columns else sub
            if len(row) == 0:
                continue
            r = row.iloc[0]
            per[L] = {"rain": round(float(r.get("blend_rain", 0)), 1),
                      "t2m": round(float(r.get("blend_t2m", 0)), 1)}
        out[name] = per
    return out


def main():
    DATA.mkdir(exist_ok=True)
    accu_key = config.get("ACCUWEATHER_API_KEY")
    goog_key = config.get("GOOGLE_WEATHER_API_KEY")
    # A pasted endpoint URL is the most common way these slots get filled in
    # wrongly, so reject that shape rather than firing a doomed request.
    accu_on = bool(accu_key) and not accu_key.lower().startswith("http")
    goog_on = bool(goog_key) and not goog_key.lower().startswith("http")

    print("cross-check providers: AccuWeather %s | Google Weather %s"
          % ("on" if accu_on else "OFF (no key)", "on" if goog_on else "OFF (no key)"))
    if not (accu_on or goog_on):
        print("nothing to do - add ACCUWEATHER_API_KEY / GOOGLE_WEATHER_API_KEY to .env")
        print("the dashboard simply omits the panel when this file is absent")
        return

    ours = our_forecast()
    loc = accu_location_keys(accu_key) if accu_on else {}

    cities = []
    for name, lat, lon in CITIES:
        print("  %s" % name)
        rec = {"city": name, "lat": lat, "lon": lon,
               "ours": ours.get(name, {}), "accuweather": {}, "google": {}}
        if accu_on and name in loc:
            rec["accuweather"] = accu_forecast(accu_key, loc[name])
        if goog_on:
            rec["google"] = google_forecast(goog_key, lat, lon)
        cities.append(rec)

    today = date.today()
    payload = {
        "issued": today.isoformat(),
        "valid": {str(L): (today + timedelta(days=L)).isoformat() for L in LEADS},
        "providers": [p for p, on in
                      (("accuweather", accu_on), ("google", goog_on)) if on],
        "cities": cities,
        # Displayed verbatim by the dashboard. AccuWeather's free tier
        # requires visible attribution wherever their data appears.
        "note": ("Independent consumer forecasts, shown for comparison only. "
                 "Neither is a blend member: both are downstream products of "
                 "the same global models Blend Desk already weights, and "
                 "neither publishes forecasts at lead time that could be "
                 "verified against ERA5."),
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("wrote %s  (%d cities, providers: %s)"
          % (OUT, len(cities), ", ".join(payload["providers"]) or "none"))


if __name__ == "__main__":
    main()
