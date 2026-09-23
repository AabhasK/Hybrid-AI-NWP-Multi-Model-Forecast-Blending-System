#!/bin/zsh
# Refresh the operational forecast and rebuild the self-contained dashboard.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "/Users/Ashit/SIH/Hybrid-AI-NWP-Multi-Model-Forecast-Blending-System"
python3 run_daily.py --publish
