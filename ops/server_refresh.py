"""Refresh and publish the dashboard from a server-side container."""

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("SITE_DIR", "/srv/site"))
INTERVAL = max(60, int(os.environ.get("REFRESH_INTERVAL_SECONDS", "10800")))


def publish():
    """Build a new snapshot, then atomically replace the served page."""
    subprocess.run(
        [sys.executable, str(ROOT / "run_daily.py"), "--publish"],
        cwd=ROOT,
        check=True,
    )
    source = ROOT / "dashboard.html"
    temporary = SITE / ".dashboard.html.tmp"
    shutil.copy2(source, temporary)
    os.replace(temporary, SITE / "dashboard.html")
    print("Published dashboard at %s" % datetime.now().astimezone().isoformat(), flush=True)


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    # Keep a usable page available while the first live forecast is being fetched.
    initial = ROOT / "dashboard.html"
    served = SITE / "dashboard.html"
    if initial.exists() and not served.exists():
        shutil.copy2(initial, served)

    next_run = time.monotonic()
    while True:
        try:
            publish()
        except Exception as exc:
            # Keep the last good dashboard online and retry at the next interval.
            print("Dashboard refresh failed: %s" % exc, file=sys.stderr, flush=True)
        next_run += INTERVAL
        # Keep a steady cadence without ever overlapping refresh jobs. If a
        # long fetch overruns its slot, begin the next run as soon as it ends.
        time.sleep(max(0, next_run - time.monotonic()))


if __name__ == "__main__":
    main()
