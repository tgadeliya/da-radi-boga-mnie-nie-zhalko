"""
Last.fm Catch-up Analysis
-------------------------
Fetches all scrobbles for two users, saves to scrobble_data.json,
then analyses when you'll catch up to a friend's scrobble count.

Credentials are read from a .env file in the same directory:
    LASTFM_API_KEY=your_key_here
    MY_USER=Lib0n
    FRIEND_USER=dymovaleksandra
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "scrobble_data.json"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.environ.get("LASTFM_API_KEY", "")
MY_USER = os.environ.get("MY_USER", "Lib0n")
FRIEND_USER = os.environ.get("FRIEND_USER", "dymovaleksandra")
MY_ACTIVE_DAYS_WINDOW = 21  # used for the text analysis section

API_ROOT = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "ScrobbleCatchupAnalysis/1.0"

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_call(method, params, max_retries=4):
    all_params = {
        "method": method,
        "api_key": API_KEY,
        "format": "json",
        **params,
    }
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


def get_user_info(username):
    data = api_call("user.getInfo", {"user": username})
    user = data["user"]
    return {
        "name": user["name"],
        "playcount": int(user["playcount"]),
        "registered": datetime.fromtimestamp(
            int(user["registered"]["unixtime"]), tz=timezone.utc
        ),
    }


def fetch_all_scrobbles(username):
    """Fetch every scrobble date for a user; returns list of ISO date strings."""
    dates = []
    page = 1
    total_pages = None
    while True:
        data = api_call(
            "user.getRecentTracks",
            {"user": username, "limit": 200, "page": page},
        )
        tracks = data.get("recenttracks", {}).get("track", [])
        for t in tracks:
            if "date" not in t:
                continue  # skip currently-playing track
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

    print()  # newline after the carriage-return progress
    return dates


def count_scrobbles_since(username, since_dt):
    since_ts = int(since_dt.timestamp())
    total = 0
    page = 1
    while True:
        data = api_call(
            "user.getRecentTracks",
            {"user": username, "limit": 200, "from": since_ts, "page": page},
        )
        tracks = data.get("recenttracks", {}).get("track", [])
        counted = [t for t in tracks if "date" in t]
        total += len(counted)
        attr = data["recenttracks"].get("@attr", {})
        total_pages = int(attr.get("totalPages", 1))
        if page >= total_pages or not counted:
            break
        page += 1
        time.sleep(0.25)
    return total


def daily_scrobbles_by_day(username, since_dt):
    since_ts = int(since_dt.timestamp())
    by_day = {}
    page = 1
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
            day = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            by_day[day] = by_day.get(day, 0) + 1
        attr = data["recenttracks"].get("@attr", {})
        total_pages = int(attr.get("totalPages", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)
    return by_day


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not API_KEY:
        print("ERROR: LASTFM_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    print("Fetching account info…\n")
    me = get_user_info(MY_USER)
    friend = get_user_info(FRIEND_USER)

    print(f"  {me['name']}: {me['playcount']:,} scrobbles "
          f"(registered {me['registered'].date()})")
    print(f"  {friend['name']}: {friend['playcount']:,} scrobbles "
          f"(registered {friend['registered'].date()})")
    print()

    # --- Fetch ALL scrobbles for both users and save to JSON ---
    print(f"Fetching ALL scrobbles for {MY_USER}…")
    my_dates = fetch_all_scrobbles(MY_USER)
    print(f"  → {len(my_dates)} scrobbles\n")

    print(f"Fetching ALL scrobbles for {FRIEND_USER}…")
    friend_dates = fetch_all_scrobbles(FRIEND_USER)
    print(f"  → {len(friend_dates)} scrobbles\n")

    data_out = {MY_USER: my_dates, FRIEND_USER: friend_dates}
    with open(DATA_FILE, "w") as f:
        json.dump(data_out, f)
    print(f"Saved scrobble data to {DATA_FILE}\n")

    # --- Text analysis ---
    now = datetime.now(timezone.utc)
    my_window_start = now - timedelta(days=MY_ACTIVE_DAYS_WINDOW)

    print(f"Counting your scrobbles in the last {MY_ACTIVE_DAYS_WINDOW} days…")
    my_recent = count_scrobbles_since(MY_USER, my_window_start)
    my_rate = my_recent / MY_ACTIVE_DAYS_WINDOW
    print(f"  You scrobbled {my_recent} tracks in {MY_ACTIVE_DAYS_WINDOW} days "
          f"→ {my_rate:.1f}/day\n")

    friend_lifetime_days = (now - friend["registered"]).days
    friend_lifetime_rate = friend["playcount"] / friend_lifetime_days
    print(f"  Friend lifetime average: "
          f"{friend['playcount']:,} / {friend_lifetime_days} days "
          f"= {friend_lifetime_rate:.1f}/day")

    print(f"Counting friend's scrobbles in the last {MY_ACTIVE_DAYS_WINDOW} days…")
    friend_recent = count_scrobbles_since(FRIEND_USER, my_window_start)
    friend_recent_rate = friend_recent / MY_ACTIVE_DAYS_WINDOW
    print(f"  Friend recent rate (last {MY_ACTIVE_DAYS_WINDOW} days): "
          f"{friend_recent} scrobbles → {friend_recent_rate:.1f}/day\n")

    gap = friend["playcount"] - me["playcount"]
    print(f"Gap to close: {gap:,} scrobbles\n")

    print("=" * 60)
    print("SCENARIOS")
    print("=" * 60)

    scenarios = [
        ("Friend stops, you keep your current rate",
         my_rate, 0),
        ("Friend keeps lifetime avg, you keep current rate",
         my_rate, friend_lifetime_rate),
        ("Friend keeps recent rate, you keep current rate",
         my_rate, friend_recent_rate),
        ("Friend keeps recent rate, your rate drops 30%",
         my_rate * 0.7, friend_recent_rate),
    ]

    for label, my_r, friend_r in scenarios:
        net = my_r - friend_r
        print(f"\n  {label}")
        print(f"    You: {my_r:.1f}/day  |  Friend: {friend_r:.1f}/day  "
              f"|  Net closing: {net:.1f}/day")
        if net <= 0:
            print("    ❌ You never catch up at this rate (gap grows).")
        else:
            days = gap / net
            years = days / 365.25
            catch_date = now + timedelta(days=days)
            print(f"    ✅ {days:,.0f} days ({years:.1f} years) "
                  f"→ around {catch_date.date()}")

    print("\n" + "=" * 60)
    print("YOUR DAILY SCROBBLES (last 21 days)")
    print("=" * 60)
    my_days = daily_scrobbles_by_day(MY_USER, my_window_start)
    for day in sorted(my_days.keys()):
        bar = "█" * min(my_days[day], 80)
        print(f"  {day}  {my_days[day]:>4}  {bar}")


if __name__ == "__main__":
    main()
