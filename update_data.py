"""Incremental Last.fm update: fetch only new scrobbles since the last recorded date,
merge into scrobble_data.json, and regenerate both plots.

Usage:
    python update_data.py
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "scrobble_data.json"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.environ.get("LASTFM_API_KEY", "")
MY_USER = os.environ.get("MY_USER", "Lib0n")
FRIEND_USER = os.environ.get("FRIEND_USER", "dymovaleksandra")
API_ROOT = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "ScrobbleCatchupAnalysis/1.0"


def api_call(method, params, max_retries=4):
    all_params = {"method": method, "api_key": API_KEY, "format": "json", **params}
    url = f"{API_ROOT}?{urlencode(all_params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise last_err


def fetch_scrobbles_since(username, since_date):
    """Return list of ISO date strings for all scrobbles on or after since_date."""
    since_ts = int(datetime(since_date.year, since_date.month, since_date.day,
                             tzinfo=timezone.utc).timestamp())
    dates = []
    page = 1
    total_pages = None
    while True:
        data = api_call(
            "user.getRecentTracks",
            {"user": username, "limit": 200, "from": since_ts, "page": page},
        )
        tracks = data.get("recenttracks", {}).get("track", [])
        for t in tracks:
            if "date" not in t:
                continue
            ts = int(t["date"]["uts"])
            day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            dates.append(day)
        attr = data["recenttracks"].get("@attr", {})
        if total_pages is None:
            total_pages = int(attr.get("totalPages", 1))
        print(f"    page {page}/{total_pages}  ({len(dates)} scrobbles so far)…", end="\r")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)
    print()
    return dates


def merge_incremental(existing_dates, username):
    """Fetch new scrobbles for username and merge with existing list."""
    if not existing_dates:
        print(f"  No existing data for {username} — cannot do incremental update.")
        return existing_dates

    # Go back 1 day from the latest recorded date to handle any edge-of-day gaps.
    max_date = date.fromisoformat(max(existing_dates))
    fetch_from = max_date - timedelta(days=1)

    print(f"  Last entry: {max_date}, fetching from {fetch_from}…")
    new_dates = fetch_scrobbles_since(username, fetch_from)
    print(f"  Fetched {len(new_dates)} scrobbles from API")

    # Drop existing entries that overlap with the re-fetched window, then append.
    fetch_from_str = fetch_from.isoformat()
    kept = [d for d in existing_dates if d < fetch_from_str]
    merged = kept + new_dates
    print(f"  {len(kept)} kept + {len(new_dates)} new = {len(merged)} total")
    return merged


def _patch_html(data):
    my_dates = sorted(date.fromisoformat(d) for d in data[MY_USER])
    friend_dates = sorted(date.fromisoformat(d) for d in data[FRIEND_USER])

    my_start = my_dates[0]
    today = max(my_dates[-1], friend_dates[-1])
    days_active = (today - my_start).days + 1

    my_total = len(my_dates)
    my_rate = my_total / days_active

    friend_total = len(friend_dates)
    friend_at_mystart = sum(1 for d in friend_dates if d < my_start)
    friend_rate_after = (friend_total - friend_at_mystart) / days_active

    gap = friend_total - my_total
    net = my_rate - friend_rate_after
    if net > 0:
        catch_date = today + timedelta(days=gap / net)
        verdict = f"you'll catch her around {catch_date.strftime('%B %Y')}."
    else:
        verdict = "you won't catch her."

    print(f"  my rate: {my_rate:.0f}/day, friend rate: {friend_rate_after:.0f}/day → {verdict}")

    def sub(text, marker, value):
        return re.sub(
            rf"<!-- {marker} -->.*?<!-- /{marker} -->",
            f"<!-- {marker} -->{value}<!-- /{marker} -->",
            text,
            flags=re.DOTALL,
        )

    index_html = BASE_DIR / "index.html"
    html = index_html.read_text()
    html = sub(html, "MY_RATE", round(my_rate))
    html = sub(html, "FRIEND_RATE", round(friend_rate_after))
    html = sub(html, "VERDICT_MSG", verdict)
    html = sub(html, "UPDATED_DATE", date.today().isoformat())
    index_html.write_text(html)


def main():
    if not API_KEY:
        print("ERROR: LASTFM_API_KEY is not set.")
        sys.exit(1)

    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run lastfm_catchup.py --force for the initial fetch.")
        sys.exit(1)

    with open(DATA_FILE) as f:
        data = json.load(f)

    print(f"Loaded: {len(data.get(MY_USER, []))} scrobbles for {MY_USER}, "
          f"{len(data.get(FRIEND_USER, []))} for {FRIEND_USER}\n")

    print(f"Updating {MY_USER}…")
    data[MY_USER] = merge_incremental(data.get(MY_USER, []), MY_USER)

    print(f"\nUpdating {FRIEND_USER}…")
    data[FRIEND_USER] = merge_incremental(data.get(FRIEND_USER, []), FRIEND_USER)

    with open(DATA_FILE, "w") as f:
        json.dump(data, f)
    print(f"\nSaved updated data to {DATA_FILE}")

    for label, script in [
        ("Generating rates plot", BASE_DIR / "make_rates_plot.py"),
        ("Generating final plot", BASE_DIR / "make_final_plot.py"),
    ]:
        print(f"\n{label}…")
        result = subprocess.run([sys.executable, str(script)], cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"ERROR: {script.name} failed (exit {result.returncode})")
            sys.exit(result.returncode)

    _patch_html(data)
    print(f"Updated index.html")

    print("\nDone.")


if __name__ == "__main__":
    main()
