"""
Last.fm Catch-up Analysis
-------------------------
Calculates when you'll catch up to a friend's scrobble count
given your current scrobbling rate.

Requires a free API key from https://www.last.fm/api/account/create

Usage:
    python lastfm_catchup.py YOUR_API_KEY
"""

import sys
import time
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_ROOT = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "ScrobbleCatchupAnalysis/1.0 tgadeliya@gmail.com"

# Your setup
MY_USER = "Lib0n"
FRIEND_USER = "dymovaleksandra"
# You said you started using it "a couple weeks ago" (~3 weeks).
# We'll measure YOUR rate from actual recent scrobbles, not registration date.
MY_ACTIVE_DAYS_WINDOW = 21  # last 21 days


def api_call(method, params, api_key, max_retries=4):
    """Make a Last.fm API call with retry on 503."""
    all_params = {
        "method": method,
        "api_key": api_key,
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
            wait = 2 ** attempt
            time.sleep(wait)
    raise last_err


def get_user_info(username, api_key):
    """Get total playcount and registration date."""
    data = api_call("user.getInfo", {"user": username}, api_key)
    user = data["user"]
    return {
        "name": user["name"],
        "playcount": int(user["playcount"]),
        "registered": datetime.fromtimestamp(
            int(user["registered"]["unixtime"]), tz=timezone.utc
        ),
    }


def count_scrobbles_since(username, since_dt, api_key):
    """Count scrobbles since a given datetime by paginating recent tracks."""
    since_ts = int(since_dt.timestamp())
    total = 0
    page = 1
    while True:
        data = api_call(
            "user.getRecentTracks",
            {"user": username, "limit": 200, "from": since_ts, "page": page},
            api_key,
        )
        tracks = data.get("recenttracks", {}).get("track", [])
        # Filter out any currently-playing track (no 'date' field)
        counted = [t for t in tracks if "date" in t]
        total += len(counted)

        attr = data["recenttracks"].get("@attr", {})
        total_pages = int(attr.get("totalPages", 1))
        if page >= total_pages or not counted:
            break
        page += 1
        time.sleep(0.25)  # be nice to the API
    return total


def daily_scrobbles_by_day(username, since_dt, api_key):
    """Get per-day scrobble counts for charting."""
    since_ts = int(since_dt.timestamp())
    by_day = {}
    page = 1
    while True:
        data = api_call(
            "user.getRecentTracks",
            {"user": username, "limit": 200, "from": since_ts, "page": page},
            api_key,
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


def analyze(api_key):
    print("Fetching account info...\n")
    me = get_user_info(MY_USER, api_key)
    friend = get_user_info(FRIEND_USER, api_key)

    print(f"  {me['name']}: {me['playcount']:,} scrobbles "
          f"(registered {me['registered'].date()})")
    print(f"  {friend['name']}: {friend['playcount']:,} scrobbles "
          f"(registered {friend['registered'].date()})")
    print()

    # YOUR rate: measured from actual recent activity (last 21 days)
    now = datetime.now(timezone.utc)
    my_window_start = now - timedelta(days=MY_ACTIVE_DAYS_WINDOW)
    print(f"Counting your scrobbles in the last {MY_ACTIVE_DAYS_WINDOW} days...")
    my_recent = count_scrobbles_since(MY_USER, my_window_start, api_key)
    my_rate = my_recent / MY_ACTIVE_DAYS_WINDOW
    print(f"  You scrobbled {my_recent} tracks in {MY_ACTIVE_DAYS_WINDOW} days "
          f"→ {my_rate:.1f}/day\n")

    # FRIEND's rate: we use two measures
    # (a) lifetime average since registration
    friend_lifetime_days = (now - friend["registered"]).days
    friend_lifetime_rate = friend["playcount"] / friend_lifetime_days
    print(f"  Friend lifetime average: "
          f"{friend['playcount']:,} / {friend_lifetime_days} days "
          f"= {friend_lifetime_rate:.1f}/day")

    # (b) recent rate (last 21 days) - better reflects current behavior
    print(f"Counting friend's scrobbles in the last {MY_ACTIVE_DAYS_WINDOW} days...")
    friend_recent = count_scrobbles_since(FRIEND_USER, my_window_start, api_key)
    friend_recent_rate = friend_recent / MY_ACTIVE_DAYS_WINDOW
    print(f"  Friend recent rate (last {MY_ACTIVE_DAYS_WINDOW} days): "
          f"{friend_recent} scrobbles → {friend_recent_rate:.1f}/day\n")

    # The catch-up math
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
            print(f"    ❌ You never catch up at this rate (gap grows).")
        else:
            days = gap / net
            years = days / 365.25
            catch_date = now + timedelta(days=days)
            print(f"    ✅ {days:,.0f} days ({years:.1f} years) "
                  f"→ around {catch_date.date()}")

    # Daily breakdown for you (optional detail)
    print("\n" + "=" * 60)
    print("YOUR DAILY SCROBBLES (last 21 days)")
    print("=" * 60)
    my_days = daily_scrobbles_by_day(MY_USER, my_window_start, api_key)
    for day in sorted(my_days.keys()):
        bar = "█" * min(my_days[day], 80)
        print(f"  {day}  {my_days[day]:>4}  {bar}")

    return {
        "me": me,
        "friend": friend,
        "my_recent_rate": my_rate,
        "friend_lifetime_rate": friend_lifetime_rate,
        "friend_recent_rate": friend_recent_rate,
        "gap": gap,
        "my_days": my_days,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lastfm_catchup.py YOUR_API_KEY")
        print("Get a free key at: https://www.last.fm/api/account/create")
        sys.exit(1)
    analyze(sys.argv[1])
