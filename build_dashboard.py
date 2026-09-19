"""
Step 5 - Inline the exported payload into a standalone dashboard.

dashboard_template.html carries a `/*__NWP_DATA__*/null` placeholder. This
swaps it for the real JSON so that dashboard.html is a SINGLE FILE with no
fetch, no server and no build tooling: double-click it and it runs.

(Chart.js, Leaflet and the webfont still load from CDN, so the basemap tiles
and typeface need a network connection. Everything that carries meaning - the
grid cells, every chart, every number - is embedded and renders offline.)

Run:  python build_dashboard.py
"""

from pathlib import Path

import config

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "dashboard_template.html"
PAYLOAD = ROOT / "data" / "dashboard_data.json"
OUT = ROOT / "dashboard.html"
TOKEN = "/*__NWP_DATA__*/null"
MAPBOX_LINE = "const MAPBOX_TOKEN = '';"


def main():
    html = TEMPLATE.read_text(encoding="utf-8")
    data = PAYLOAD.read_text(encoding="utf-8")

    if TOKEN not in html:
        raise SystemExit("placeholder %r not found in %s" % (TOKEN, TEMPLATE.name))

    # A literal "</script>" inside embedded JSON would close the host <script>
    # tag early and break the page. Escaping the slash keeps the JSON valid.
    data = data.replace("</", "<\\/")
    html = html.replace(TOKEN, data)

    # The token lives in .env and is injected at build time, so it is never
    # committed with the template. Without one the page uses its MapLibre +
    # OpenFreeMap fallback, which needs no key.
    if config.is_set("MAPBOX_TOKEN"):
        if MAPBOX_LINE not in html:
            raise SystemExit("could not find the Mapbox token line to substitute")
        html = html.replace(MAPBOX_LINE,
                            "const MAPBOX_TOKEN = '%s';" % config.MAPBOX_TOKEN)
        basemap = "Mapbox GL (token from .env)"
    else:
        basemap = "MapLibre GL + OpenFreeMap (no MAPBOX_TOKEN set)"

    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print("wrote %s  (%.0f KB, self-contained)" % (OUT, kb))
    print("basemap: %s" % basemap)


if __name__ == "__main__":
    main()
