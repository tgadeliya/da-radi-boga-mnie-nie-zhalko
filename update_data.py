"""Daily update: fetch new scrobbles for both of us, then rebuild the Season 2 page.

Usage:
    python update_data.py               # fetch + rebuild
    python update_data.py --build-only  # rebuild the page from data/ without calling Last.fm

The first run (no data/<user>/ folder yet) downloads the full history,
~115 API pages per person. After that each run re-reads only the last
OVERLAP_DAYS days, because Last.fm accepts late (offline) scrobbles.
"""

import sys
import time

import build_site
import lastfm
import store
from config import API_KEY, OVERLAP_DAYS, USERS


def update_user(user):
    existing = store.load(user)
    now = int(time.time())

    if not existing:
        print(f"{user}: no stored data — fetching the full history…")
        fresh = lastfm.fetch_scrobbles(user, until_uts=now)
        store.save(user, fresh)
        print(f"{user}: saved {len(fresh)} scrobbles")
        return

    since = existing[-1].uts - OVERLAP_DAYS * 86400
    print(f"{user}: {len(existing)} stored, re-reading the last {OVERLAP_DAYS} days…")
    fresh = lastfm.fetch_scrobbles(user, since_uts=since, until_uts=now)
    merged = store.merge(existing, fresh)
    months = store.save(user, merged, since_uts=since)
    print(f"{user}: +{len(merged) - len(existing)} new, {len(merged)} total "
          f"(rewrote {', '.join(months)})")


def main():
    if "--build-only" not in sys.argv:
        if not API_KEY:
            print("ERROR: LASTFM_API_KEY is not set (add it to .env or export it).")
            sys.exit(1)
        for user in USERS:
            update_user(user)

    build_site.build()


if __name__ == "__main__":
    main()
