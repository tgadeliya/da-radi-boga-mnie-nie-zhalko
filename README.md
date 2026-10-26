Я забыл как ручками делать деплой поэтому пишу этот коммент
x2

## Season 2 · who shapes whose taste

Season 1 (the scrobble-count race) ended on 22 Oct 2026, when Lib0n overtook dymovaleksandra.
Everything from it is frozen in `season1/`.

Season 2 compares our two listening timelines with each other, which last.fm itself never does:

- **кто кого подсадил** — artists one of us started playing within 30 days after the other played them,
  and then played at least 3 times. The follower's first play must come after a 30-day warm-up
  (before that, a "first play" may just be an old favourite that hadn't been scrobbled yet).
- **эхо** — who is the household DJ. A "start" is a play of a track you haven't played in 30 days.
  An echo is one person's start of a track 15 min – 72 h after the other person's start of it.
  Both sides must be starts, so looping a track every day doesn't make you the DJ.
- **территории** — in the last 30 days, every artist we both played at least twice is a territory.
  It belongs to whoever gives it a bigger share of *their own* listening, so listening more
  doesn't win the map. "This week" shows what changed hands in the last 7 days.

All thresholds are in `config.py`.

### How it runs

A GitHub Action runs `update_data.py` every day at 03:00 UTC:

1. fetches new scrobbles (artist, album, track, time) into `data/<user>/<YYYY-MM>.csv`.
   The first run downloads both full histories; later runs re-read the last 14 days,
   because Last.fm accepts offline scrobbles up to two weeks late;
2. rebuilds `index.html` and `season2_chart.png`;
3. commits whatever changed.

### Locally

```
echo "LASTFM_API_KEY=..." > .env
uv run python update_data.py               # fetch + rebuild
uv run python update_data.py --build-only  # rebuild from data/ only
uv run python -m unittest discover -s tests
```

| File | What it does |
|---|---|
| `lastfm.py` | API client: fetches full scrobbles, retries transient errors |
| `store.py` | reads/writes the monthly CSV files |
| `metrics.py` | the three Season 2 metrics (pure functions) |
| `build_site.py` | builds the page and the chart |
| `update_data.py` | daily entry point: fetch, then build |
| `config.py` | users, names, colours, metric thresholds |
