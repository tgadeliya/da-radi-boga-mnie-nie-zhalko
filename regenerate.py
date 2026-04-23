"""Fetch fresh scrobble data and regenerate all plots."""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
PYTHON = sys.executable

steps = [
    ("Fetching scrobble data", BASE_DIR / "lastfm_catchup.py"),
    ("Generating rates plot",  BASE_DIR / "make_rates_plot.py"),
    ("Generating final plot",  BASE_DIR / "make_final_plot.py"),
]

for label, script in steps:
    print(f"\n{'='*60}")
    print(f"  {label}…")
    print(f"{'='*60}")
    result = subprocess.run([PYTHON, str(script)], cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"\nERROR: {script.name} failed (exit {result.returncode})")
        sys.exit(result.returncode)

print(f"\n{'='*60}")
print("  All done. Open index.html in your browser.")
print(f"{'='*60}\n")
