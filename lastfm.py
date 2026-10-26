"""Small Last.fm API client: fetch full scrobbles (time, artist, album, track)."""

import json
import time
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import API_KEY

API_ROOT = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "da-radi-boga-mnie-nie-zhalko/2.0"
PAGE_SIZE = 200

# Last.fm error codes that are worth retrying (operation failed, service offline,
# temporarily unavailable, rate limit exceeded).
TRANSIENT_ERRORS = {8, 11, 16, 29}


class Scrobble(NamedTuple):
    uts: int      # unix timestamp, UTC
    artist: str
    album: str
    track: str


class LastfmError(Exception):
    def __init__(self, code, message):
        super().__init__(f"Last.fm error {code}: {message}")
        self.code = code


def api_call(method, params, max_retries=5):
    query = urlencode({"method": method, "api_key": API_KEY, "format": "json", **params})
    req = Request(f"{API_ROOT}?{query}", headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(max_retries):
        try:
            try:
                with urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except HTTPError as e:
                # Last.fm sends its error details as JSON even on 4xx/5xx.
                try:
                    data = json.loads(e.read().decode("utf-8"))
                except (ValueError, OSError):
                    raise e from None
            if "error" in data:
                raise LastfmError(data["error"], data.get("message", ""))
            return data
        except LastfmError as e:
            if e.code not in TRANSIENT_ERRORS:
                raise  # bad key, unknown user, ... — retrying won't help
            last_err = e
        except (HTTPError, URLError, TimeoutError, ValueError) as e:
            last_err = e
        time.sleep(2 ** attempt)
    raise last_err


def _text(value):
    """Artist/album come as {"#text": ...} (or {"name": ...} in extended mode)."""
    if isinstance(value, dict):
        return (value.get("#text") or value.get("name") or "").strip()
    return (value or "").strip()


def parse_tracks(data):
    """Turn one getRecentTracks response page into Scrobbles (skips 'now playing')."""
    tracks = data.get("recenttracks", {}).get("track", [])
    if isinstance(tracks, dict):  # Last.fm returns a bare object when there is one track
        tracks = [tracks]
    out = []
    for t in tracks:
        if "date" not in t or t.get("@attr", {}).get("nowplaying"):
            continue
        out.append(Scrobble(
            uts=int(t["date"]["uts"]),
            artist=_text(t.get("artist")),
            album=_text(t.get("album")),
            track=(t.get("name") or "").strip(),
        ))
    return out


def fetch_scrobbles(user, since_uts=None, until_uts=None):
    """All scrobbles of `user` between since_uts and until_uts, oldest first.

    `until_uts` is pinned at the start, so new scrobbles arriving during a long
    fetch don't shift the pages under us.
    """
    until_uts = until_uts or int(time.time())
    params = {"user": user, "limit": PAGE_SIZE, "to": until_uts}
    if since_uts:
        params["from"] = since_uts

    out = []
    page = 1
    while True:
        data = api_call("user.getRecentTracks", {**params, "page": page})
        out.extend(parse_tracks(data))
        attr = data.get("recenttracks", {}).get("@attr", {})
        total_pages = int(attr.get("totalPages") or 1)
        print(f"    {user}: page {page}/{total_pages} ({len(out)} scrobbles)", end="\r")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)
    print()
    out.sort(key=lambda s: s.uts)
    return out
