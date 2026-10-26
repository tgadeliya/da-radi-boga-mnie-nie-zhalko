"""Fetch fresh scrobble data and regenerate all plots.

Usage:
    python regenerate.py               # skip fetch if scrobble_data.json exists
    python regenerate.py --force       # always re-fetch from API
    python regenerate.py --plots-only  # skip fetch entirely, just regenerate plots
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
PYTHON = sys.executable

plots_only = "--plots-only" in sys.argv
force = "--force" in sys.argv

steps = []

if not plots_only:
    fetch_args = ["--force"] if force else []
    steps.append(("Fetching scrobble data", BASE_DIR / "lastfm_catchup.py", fetch_args))

steps += [
    ("Generating rates plot", BASE_DIR / "make_rates_plot.py", []),
    ("Generating final plot", BASE_DIR / "make_final_plot.py", []),
]

for label, script, extra_args in steps:
    print(f"\n{'='*60}")
    print(f"  {label}…")
    print(f"{'='*60}")
    result = subprocess.run([PYTHON, str(script)] + extra_args, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"\nERROR: {script.name} failed (exit {result.returncode})")
        sys.exit(result.returncode)

print(f"\n{'='*60}")
print("  All done. Open index.html in your browser.")
print(f"{'='*60}\n")
