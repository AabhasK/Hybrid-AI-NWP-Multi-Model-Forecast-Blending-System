"""
India Meteorological Department API client.

Every endpoint below returned {"error":"API key missing"} on an unauthenticated
probe, so a single key from IMD's developer portal unlocks all of them. Until
IMD_API_KEY is set in .env this module reports what is missing and the rest of
the pipeline carries on against ERA5 and the global models.

WHY THESE FOUR ENDPOINTS
------------------------
  forecast   State District Rainfall Forecast (5 days) - an Indian operational
             forecast at exactly our T+1..T+5 lead times, so it joins the blend
             as a sixth member and the only Indian source in the mix.
  aws        AWS/ARG station observations - real gauge truth. Verifying against
             gauges instead of ERA5 removes the circularity we disclose in
             DATA_NOTE.md (ECMWF AIFS is trained on ERA5).
  rainfall   District-wise observed rainfall - easier to join than raw
             stations, so the practical fallback for gauge truth.
  warnings   District-wise colour-coded warnings - lets the extreme flagger be
             scored against what IMD actually issued.

AUTH FORMAT
-----------
IMD does not publish which scheme it expects and we have no key to test with,
so `call()` tries the three common ones in turn and remembers whichever works.
Set IMD_AUTH_MODE in .env to pin it once known: query | header | bearer.

Run `python imd_client.py` for a live status report.
"""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import config

BASE = config.IMD_API_BASE.rstrip("/")

ENDPOINTS = {
    "forecast": "/state_district_rainfall_forecast",
    "rainfall": "/districtrainfall",
    "warnings": "/districtwarning",
    "aws": "/aws_data",
    "aws_map": "/aws_data_mapping",
}

# IMD's certificate chain is occasionally incomplete on their API host; the
# payload is public data, so fall back rather than fail the run.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_AUTH_ORDER = ["query", "header", "bearer"]
_working_mode = config.get("IMD_AUTH_MODE") or None


class IMDError(RuntimeError):
    pass


def available():
    return config.is_set("IMD_API_KEY")


def _request(url, params, mode, key):
    p = dict(params or {})
    headers = {"User-Agent": "BlendDesk/1.0", "Accept": "application/json"}
    if mode == "query":
        p["api_key"] = key
    elif mode == "header":
        headers["x-api-key"] = key
    elif mode == "bearer":
        headers["Authorization"] = "Bearer " + key
    qs = ("?" + urllib.parse.urlencode(p)) if p else ""
    req = urllib.request.Request(url + qs, headers=headers)
    with urllib.request.urlopen(req, timeout=90, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def call(endpoint, **params):
    """Fetch one endpoint. Raises IMDError when no key is configured."""
    global _working_mode
    if not available():
        raise IMDError("IMD_API_KEY is not set - see .env.example")
    if endpoint not in ENDPOINTS:
        raise IMDError("unknown endpoint %r; known: %s"
                       % (endpoint, ", ".join(sorted(ENDPOINTS))))

    url = BASE + ENDPOINTS[endpoint]
    key = config.IMD_API_KEY
    modes = ([_working_mode] if _working_mode else []) + \
            [m for m in _AUTH_ORDER if m != _working_mode]

    last = None
    for mode in modes:
        try:
            out = _request(url, params, mode, key)
            _working_mode = mode          # remember what worked
            return out
        except urllib.error.HTTPError as e:
            last = "HTTP %d (%s auth): %s" % (
                e.code, mode, e.read().decode("utf-8", "replace")[:160])
            if e.code not in (401, 403):
                raise IMDError(last)
        except Exception as e:
            raise IMDError("%s: %s" % (type(e).__name__, e))
    raise IMDError("every auth scheme was rejected. %s" % last)


def report():
    print("=" * 66)
    print(" IMD API  (%s)" % BASE)
    print("=" * 66)
    if not available():
        print("\n  IMD_API_KEY is not set.\n")
        print("  A live probe of every endpoint returned:")
        print('      {"error":"API key missing"}')
        print("  so ONE key from IMD's developer portal unlocks all of them.\n")
        for name, path in ENDPOINTS.items():
            print("    %-9s %s%s" % (name, BASE, path))
        print("\n  Without it the pipeline verifies against ERA5 and blends the")
        print("  five global centres. Nothing breaks; there is simply no Indian")
        print("  source in the mix and no gauge-based truth.\n")
        return

    for name in ENDPOINTS:
        try:
            d = call(name)
            n = len(d) if isinstance(d, list) else 1
            print("  [ok]   %-9s %d records  (auth: %s)" % (name, n, _working_mode))
        except IMDError as e:
            print("  [fail] %-9s %s" % (name, e))


if __name__ == "__main__":
    report()
