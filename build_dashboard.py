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

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "dashboard_template.html"
PAYLOAD = ROOT / "data" / "dashboard_data.json"
OUT = ROOT / "dashboard.html"
TOKEN = "/*__NWP_DATA__*/null"


def main():
    html = TEMPLATE.read_text(encoding="utf-8")
    data = PAYLOAD.read_text(encoding="utf-8")

    if TOKEN not in html:
        raise SystemExit("placeholder %r not found in %s" % (TOKEN, TEMPLATE.name))

    # A literal "</script>" inside embedded JSON would close the host <script>
    # tag early and break the page. Escaping the slash keeps the JSON valid.
    data = data.replace("</", "<\\/")

    OUT.write_text(html.replace(TOKEN, data), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print("wrote %s  (%.0f KB, self-contained)" % (OUT, kb))


if __name__ == "__main__":
    main()
