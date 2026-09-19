"""
Configuration and credentials.

Every key here is OPTIONAL. The pipeline runs end to end with none of them
set - that is deliberate, so the project is never blocked on a credential.
Each key that IS set upgrades one specific thing, and `python config.py`
prints exactly what is active and what each missing key would buy.

Values are read from a `.env` file beside this script, falling back to real
environment variables. `.env` is gitignored; `.env.example` is the template.
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"


def _load_env(path=ENV_FILE):
    """
    Minimal .env reader - deliberately no python-dotenv dependency, so the
    project keeps running on a bare Anaconda install with nothing to pip.
    Supports KEY=value, # comments, blank lines and optional surrounding
    quotes. Real environment variables win over the file.
    """
    values = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            values[key] = val
    for key in list(values):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


_ENV = _load_env()


def get(key, default=""):
    return (_ENV.get(key) or os.environ.get(key) or default).strip()


# Settings whose value is legitimately a URL. Everything else that looks like
# one is a paste error: an endpoint is not a credential, and sending one as
# the other breaks every request silently rather than failing loudly.
URL_SETTINGS = {"CDS_API_URL", "IMD_API_BASE"}


def is_set(key):
    """True only for a value that is present and plausibly a credential."""
    v = get(key)
    if not v or v.lower().startswith(("your_", "paste_", "xxx", "<")):
        return False
    if key not in URL_SETTINGS and (
            v.lower().startswith(("http://", "https://")) or "/" in v):
        print("  ! %s looks like a URL, not a key - ignoring it. "
              "See .env.example." % key)
        return False
    return True


# --------------------------------------------------------------------------
# Keys, and what each one actually changes
# --------------------------------------------------------------------------
KEYS = [
    {
        "name": "MAPBOX_TOKEN",
        "what": "Mapbox GL basemap + terrain DEM in the dashboard",
        "without": "falls back to MapLibre GL + OpenFreeMap vector tiles (keyless)",
        "where": "https://account.mapbox.com/access-tokens/  (public token, starts pk.)",
        "free": "50,000 map loads/month",
    },
    {
        "name": "OPENMETEO_API_KEY",
        "what": "lifts the forecast-archive rate limit, so a full year of "
                "multi-model history fetches in one pass",
        "without": "free tier, ~10k weighted calls/day - the fetcher waits out "
                   "the hourly quota and resumes, which works but is slow",
        "where": "https://open-meteo.com/en/pricing",
        "free": "non-commercial use is free without a key",
    },
    {
        "name": "CDS_API_KEY",
        "what": "pulls ERA5 truth straight from Copernicus instead of the mirror",
        "without": "ERA5 comes from the Open-Meteo archive - the same ECMWF "
                   "product, no key, no queue",
        "where": "https://cds.climate.copernicus.eu/profile",
        "free": "yes, registration required",
    },
    {
        "name": "IMD_API_KEY",
        "what": "swaps ERA5 for IMD gridded rainfall as the verification truth, "
                "which removes the AIFS/ERA5 circularity noted in DATA_NOTE.md",
        "without": "verification stays against ERA5",
        "where": "IMD Pune / MoES data request, or a mentor with access",
        "free": "institutional",
    },
]

MAPBOX_TOKEN = get("MAPBOX_TOKEN")
OPENMETEO_API_KEY = get("OPENMETEO_API_KEY")
CDS_API_KEY = get("CDS_API_KEY")
CDS_API_URL = get("CDS_API_URL", "https://cds.climate.copernicus.eu/api")
IMD_API_BASE = get("IMD_API_BASE", "https://mausam.imd.gov.in/api")
IMD_API_KEY = get("IMD_API_KEY")

# Open-Meteo routes paid keys through a different host
OPENMETEO_HOST = ("https://customer-api.open-meteo.com"
                  if is_set("OPENMETEO_API_KEY") else "https://api.open-meteo.com")
OPENMETEO_PREV_HOST = ("https://customer-previous-runs-api.open-meteo.com"
                       if is_set("OPENMETEO_API_KEY") else
                       "https://previous-runs-api.open-meteo.com")
OPENMETEO_ARCHIVE_HOST = ("https://customer-archive-api.open-meteo.com"
                          if is_set("OPENMETEO_API_KEY") else
                          "https://archive-api.open-meteo.com")


def openmeteo_suffix():
    """Append the key to a query string when one is configured."""
    return "&apikey=" + OPENMETEO_API_KEY if is_set("OPENMETEO_API_KEY") else ""


def report():
    print("=" * 68)
    print(" Configuration  (.env %s)" % ("found" if ENV_FILE.exists() else "not present"))
    print("=" * 68)
    for k in KEYS:
        on = is_set(k["name"])
        print("\n  [%s] %s" % ("SET " if on else "    ", k["name"]))
        print("        %s" % k["what"])
        if not on:
            print("        not set -> %s" % k["without"])
            print("        get one: %s" % k["where"])
    n = sum(1 for k in KEYS if is_set(k["name"]))
    print("\n%d of %d keys configured. The pipeline runs either way." % (n, len(KEYS)))
    print("Copy .env.example to .env and fill in what you have.\n")


if __name__ == "__main__":
    report()
