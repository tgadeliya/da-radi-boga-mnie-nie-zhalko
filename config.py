"""Shared settings for the Season 2 pipeline.

Everything can be overridden with environment variables (or a local .env file).
"""

import os
from datetime import timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.environ.get("LASTFM_API_KEY", "")
MY_USER = os.environ.get("MY_USER", "Lib0n")
FRIEND_USER = os.environ.get("FRIEND_USER", "dymovaleksandra")
USERS = (MY_USER, FRIEND_USER)

NAMES = {
    MY_USER: os.environ.get("MY_NAME", "Tsimur"),
    FRIEND_USER: os.environ.get("FRIEND_NAME", "Sasha"),
}
COLORS = {
    MY_USER: "#1f77b4",      # same blue as the Season 1 plots
    FRIEND_USER: "#b22222",  # same family of reds as the Season 1 plots
}

# Days are counted in local time, not UTC (a track at 01:30 belongs to that night).
try:
    TZ = ZoneInfo("Europe/Minsk")
except ZoneInfoNotFoundError:
    TZ = timezone(timedelta(hours=3))  # Minsk has been UTC+3 all year since 2011

# --- Fetching -------------------------------------------------------------
# Last.fm accepts scrobbles up to 14 days late (offline phone scrobbles),
# so every daily run re-reads the last 14 days and merges.
OVERLAP_DAYS = 14

# --- Metric rules (see README for what they mean) ---------------------------
WARMUP_DAYS = 30        # ignore "first plays" in the first month both of us are tracked
CONVERSION_LAG_DAYS = 30  # follower must start within this many days of the leader's last play
CONVERSION_MIN_PLAYS = 3  # follower must play the artist at least this many times
ECHO_WINDOW_HOURS = 72    # the listener must start the track within 3 days of the DJ starting it
ECHO_FRESH_DAYS = 30      # a "start" = a play of a track you haven't played in 30 days
TOGETHER_MINUTES = 15     # same track within 15 min = listening together, not an echo
TERRITORY_WINDOW_DAYS = 30
TERRITORY_MIN_PLAYS = 2   # both must play an artist at least twice for it to be contested
