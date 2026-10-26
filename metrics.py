"""Season 2 metrics.

All functions are pure: they take {user: [Scrobble, ...]} sorted oldest first
and return plain data. Rules and thresholds live in config.py; the README
explains them in words.
"""

import re
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass

import config

DAY = 86400

# "Artist feat. Someone" counts as "Artist".
_FEAT = re.compile(r"\s+[(\[]?(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)


def clean_artist(name):
    return _FEAT.sub("", name).strip()


def _norm(text):
    return " ".join(text.casefold().split())


def artist_key(s):
    return _norm(clean_artist(s.artist))


def track_key(s):
    return (artist_key(s), _norm(s.track))


def shared_start(by_user):
    """First moment both of us are tracked (= the later of our first scrobbles)."""
    firsts = [rows[0].uts for rows in by_user.values() if rows]
    if len(firsts) < len(by_user) or not firsts:
        return None
    return max(firsts)


def _index(rows, keyfunc):
    idx = defaultdict(list)
    for s in rows:
        key = keyfunc(s)
        if key and key != ("", ""):
            idx[key].append(s.uts)  # rows are sorted, so each list is sorted too
    return idx


def _display_names(by_user, keyfunc, labelfunc):
    """For each key, the most common original spelling."""
    seen = defaultdict(Counter)
    for rows in by_user.values():
        for s in rows:
            seen[keyfunc(s)][labelfunc(s)] += 1
    return {k: c.most_common(1)[0][0] for k, c in seen.items()}


# ---------------------------------------------------------------------------
# 1. Кто кого подсадил — conversions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Conversion:
    artist: str
    leader: str          # who was playing it first
    follower: str        # who got hooked
    at: int              # follower's first play
    lag: int             # seconds since the leader's last play before that
    follower_plays: int  # how many times the follower has played it since


def find_conversions(
    by_user,
    *,
    warmup_days=config.WARMUP_DAYS,
    lag_days=config.CONVERSION_LAG_DAYS,
    min_plays=config.CONVERSION_MIN_PLAYS,
    together_minutes=config.TOGETHER_MINUTES,
):
    """Artists that one of us started playing shortly after the other played them.

    An artist X counts as "leader hooked follower" when:
      * the follower's first-ever play of X is after the warm-up period
        (before that, a "first play" may just be an old favourite);
      * the leader played X during the `lag_days` before that first play;
      * the follower has played X at least `min_plays` times;
      * we didn't both discover X in the same listening session.
    """
    start = shared_start(by_user)
    if start is None:
        return []
    counted_from = start + warmup_days * DAY
    together = together_minutes * 60
    names = _display_names(by_user, artist_key, lambda s: clean_artist(s.artist))
    idx = {u: _index(rows, artist_key) for u, rows in by_user.items()}

    out = []
    for follower in by_user:
        for leader in by_user:
            if leader == follower:
                continue
            for key, f_plays in idx[follower].items():
                first = f_plays[0]
                if first < counted_from or len(f_plays) < min_plays:
                    continue
                l_plays = idx[leader].get(key)
                if not l_plays:
                    continue
                i = bisect_left(l_plays, first)
                if i == 0:
                    continue  # the leader hadn't played it yet
                if first - l_plays[0] < together:
                    continue  # discovered it together
                lag = first - l_plays[i - 1]
                if lag > lag_days * DAY:
                    continue
                out.append(Conversion(names[key], leader, follower, first, lag, len(f_plays)))
    out.sort(key=lambda c: c.at)
    return out


# ---------------------------------------------------------------------------
# 2. Эхо — who is the household DJ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Echo:
    artist: str
    track: str
    dj: str        # started playing it first
    listener: str  # started playing it after
    at: int        # listener's play
    lag: int       # seconds after the DJ started playing it


def _fresh_starts(plays, fresh):
    """Plays that come after a gap of more than `fresh` seconds (or are the first ever)."""
    starts, prev = [], None
    for t in plays:
        if prev is None or t - prev > fresh:
            starts.append(t)
        prev = t
    return starts


def find_echoes(
    by_user,
    *,
    window_hours=config.ECHO_WINDOW_HOURS,
    fresh_days=config.ECHO_FRESH_DAYS,
    together_minutes=config.TOGETHER_MINUTES,
    warmup_days=config.WARMUP_DAYS,
):
    """Track-level pick-ups.

    A "start" is a play of a track you haven't played in `fresh_days`.
    An echo is the listener's start that comes `together_minutes`..`window_hours`
    after the DJ's start of the same track. Both sides must be starts: a track
    one of us loops every day isn't "brought home" each time the other plays it.
    Starts closer than `together_minutes` are "listening together", not echoes.
    """
    start = shared_start(by_user)
    if start is None:
        return []
    counted_from = start + warmup_days * DAY
    window = window_hours * 3600
    fresh = fresh_days * DAY
    together = together_minutes * 60
    names = _display_names(by_user, track_key, lambda s: (clean_artist(s.artist), s.track))
    starts = {
        u: {k: _fresh_starts(v, fresh) for k, v in _index(rows, track_key).items()}
        for u, rows in by_user.items()
    }

    out = []
    for listener in by_user:
        for dj in by_user:
            if dj == listener:
                continue
            for key, l_starts in starts[listener].items():
                d_starts = starts[dj].get(key)
                if not d_starts:
                    continue
                for t in l_starts:
                    if t < counted_from:
                        continue
                    i = bisect_left(d_starts, t)
                    if i == 0:
                        continue
                    lag = t - d_starts[i - 1]
                    if together <= lag <= window:
                        artist, track = names[key]
                        out.append(Echo(artist, track, dj, listener, t, lag))
    out.sort(key=lambda e: e.at)
    return out


@dataclass(frozen=True)
class Together:
    artist: str
    track: str
    at: int


def find_together(by_user, *, minutes=config.TOGETHER_MINUTES):
    """Tracks both accounts scrobbled within a few minutes of each other."""
    if len(by_user) != 2:
        return []
    (a, a_rows), (b, b_rows) = by_user.items()
    win = minutes * 60
    names = _display_names(by_user, track_key, lambda s: (clean_artist(s.artist), s.track))
    ia, ib = _index(a_rows, track_key), _index(b_rows, track_key)
    out = []
    for key, a_plays in ia.items():
        b_plays = ib.get(key)
        if not b_plays:
            continue
        for t in a_plays:
            i = bisect_left(b_plays, t - win)
            if i < len(b_plays) and b_plays[i] <= t + win:
                artist, track = names[key]
                out.append(Together(artist, track, t))
    out.sort(key=lambda x: x.at)
    return out


# ---------------------------------------------------------------------------
# 3. Территории — territory war
# ---------------------------------------------------------------------------

@dataclass
class Territory:
    key: str
    artist: str
    owner: str | None  # None = exact draw
    plays: dict        # user -> plays in the window
    shares: dict       # user -> share of that user's own listening in the window


def find_territories(
    by_user,
    end_uts,
    *,
    window_days=config.TERRITORY_WINDOW_DAYS,
    min_plays=config.TERRITORY_MIN_PLAYS,
):
    """Contested artists in the window ending at `end_uts`, and who owns each.

    The owner is whoever gives the artist a bigger share of *their own*
    listening, so playing four times more music doesn't win territories.
    Returns (territories sorted by importance, {user: number of exclusive artists}).
    """
    begin = end_uts - window_days * DAY
    counts = {
        u: Counter(k for s in rows if begin < s.uts <= end_uts and (k := artist_key(s)))
        for u, rows in by_user.items()
    }
    totals = {u: sum(c.values()) for u, c in counts.items()}
    names = _display_names(by_user, artist_key, lambda s: clean_artist(s.artist))

    qualified = {u: {k for k, n in c.items() if n >= min_plays} for u, c in counts.items()}
    contested = set.intersection(*qualified.values()) if qualified else set()

    out = []
    for key in contested:
        shares = {u: counts[u][key] / totals[u] for u in by_user}
        best = max(shares.values())
        leaders = [u for u, v in shares.items() if v == best]
        owner = leaders[0] if len(leaders) == 1 else None
        out.append(Territory(key, names[key], owner, {u: counts[u][key] for u in by_user}, shares))
    out.sort(key=lambda t: (-sum(t.shares.values()), t.key))

    exclusive = {
        u: sum(1 for k in qualified[u] if all(counts[o][k] == 0 for o in by_user if o != u))
        for u in by_user
    }
    return out, exclusive


def territory_changes(by_user, end_uts, *, days_back=7, **kwargs):
    """What happened on the map in the last `days_back` days.

    Returns (captured, new_fronts): captured is a list of (territory, previous_owner).
    """
    now, _ = find_territories(by_user, end_uts, **kwargs)
    before, _ = find_territories(by_user, end_uts - days_back * DAY, **kwargs)
    prev_owner = {t.key: t.owner for t in before}
    captured = [
        (t, prev_owner[t.key])
        for t in now
        if t.key in prev_owner and t.owner and prev_owner[t.key] and t.owner != prev_owner[t.key]
    ]
    new_fronts = [t for t in now if t.key not in prev_owner]
    return captured, new_fronts
