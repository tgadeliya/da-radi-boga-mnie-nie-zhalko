"""Scrobbles on disk: data/<user>/<YYYY-MM>.csv, one file per month (UTC).

Monthly files keep the daily git commits small: a normal day only touches the
current month's file instead of rewriting the whole history.
"""

import csv
from datetime import datetime, timezone

from config import DATA_DIR
from lastfm import Scrobble

FIELDS = ["uts", "artist", "album", "track"]


def month_key(uts):
    return datetime.fromtimestamp(uts, tz=timezone.utc).strftime("%Y-%m")


def user_dir(user, data_dir=DATA_DIR):
    return data_dir / user


def load(user, data_dir=DATA_DIR):
    """Every stored scrobble of `user`, oldest first."""
    rows = []
    for path in sorted(user_dir(user, data_dir).glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(Scrobble(int(r["uts"]), r["artist"], r["album"], r["track"]))
    rows.sort(key=lambda s: s.uts)
    return rows


def merge(existing, fresh):
    """Union of both lists without duplicates, oldest first.

    We never drop stored rows: if the API returns a short page by mistake,
    nothing is lost.
    """
    return sorted(set(existing) | set(fresh), key=lambda s: (s.uts, s.artist, s.track))


def save(user, scrobbles, since_uts=None, data_dir=DATA_DIR):
    """Write monthly files. With `since_uts`, only months from that point on are rewritten."""
    folder = user_dir(user, data_dir)
    folder.mkdir(parents=True, exist_ok=True)

    first_month = month_key(since_uts) if since_uts is not None else None
    by_month = {}
    for s in scrobbles:
        key = month_key(s.uts)
        if first_month is None or key >= first_month:
            by_month.setdefault(key, []).append(s)

    for key, rows in by_month.items():
        rows.sort(key=lambda s: (s.uts, s.artist, s.track))
        with open(folder / f"{key}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            w.writerows(rows)
    return sorted(by_month)
