"""Tests for the Season 2 pipeline. Run: uv run python -m unittest discover -s tests"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import metrics  # noqa: E402
import store  # noqa: E402
from lastfm import Scrobble, parse_tracks  # noqa: E402

DAY = 86400
HOUR = 3600
T0 = 1_775_520_000  # 2026-04-07 00:00 UTC
ME, HER = "me", "her"


def s(day, artist, track="song", hour=12, minute=0):
    return Scrobble(T0 + day * DAY + hour * HOUR + minute * 60, artist, "", track)


def data(me_rows, her_rows):
    # Both users get an early "anchor" scrobble so the shared start is T0.
    me = sorted([s(0, "anchor me", hour=0)] + me_rows)
    her = sorted([s(-100, "anchor her")] + her_rows)
    return {ME: me, HER: her}


class ConversionTests(unittest.TestCase):
    def test_counts_follower_who_starts_after_leader(self):
        d = data(
            [s(45, "Molchat Doma"), s(46, "Molchat Doma"), s(50, "Molchat Doma")],
            [s(40, "Molchat Doma")],
        )
        conv = metrics.find_conversions(d)
        self.assertEqual(len(conv), 1)
        c = conv[0]
        self.assertEqual((c.leader, c.follower, c.artist), (HER, ME, "Molchat Doma"))
        self.assertEqual(c.lag, 5 * DAY)
        self.assertEqual(c.follower_plays, 3)

    def test_ignores_first_plays_during_warmup(self):
        d = data([s(20, "X"), s(21, "X"), s(22, "X")], [s(10, "X")])
        self.assertEqual(metrics.find_conversions(d), [])

    def test_leader_must_have_played_recently(self):
        d = data([s(80, "X"), s(81, "X"), s(82, "X")], [s(40, "X")])  # 40 days gap
        self.assertEqual(metrics.find_conversions(d), [])

    def test_follower_must_get_hooked(self):
        d = data([s(45, "X"), s(46, "X")], [s(40, "X")])  # only 2 plays
        self.assertEqual(metrics.find_conversions(d), [])

    def test_discovered_together_does_not_count(self):
        d = data(
            [s(45, "X", minute=5), s(46, "X"), s(47, "X")],
            [s(45, "X", minute=0)],
        )
        self.assertEqual(metrics.find_conversions(d), [])

    def test_feat_and_case_are_merged(self):
        d = data(
            [s(45, "boris grebenshikov"), s(46, "Boris Grebenshikov feat. Someone"), s(47, "BORIS GREBENSHIKOV")],
            [s(44, "Boris Grebenshikov")],
        )
        self.assertEqual(len(metrics.find_conversions(d)), 1)


class EchoTests(unittest.TestCase):
    def test_echo_counted_once_per_fresh_pickup(self):
        d = data(
            [s(50, "A", "t1", hour=18), s(51, "A", "t1"), s(52, "A", "t1")],
            [s(50, "A", "t1", hour=10)],
        )
        echoes = metrics.find_echoes(d)
        self.assertEqual(len(echoes), 1)
        self.assertEqual((echoes[0].dj, echoes[0].listener, echoes[0].lag), (HER, ME, 8 * HOUR))

    def test_too_late_is_not_an_echo(self):
        d = data([s(55, "A", "t1")], [s(50, "A", "t1")])
        self.assertEqual(metrics.find_echoes(d), [])

    def test_same_moment_is_together_not_echo(self):
        d = data([s(50, "A", "t1", minute=3)], [s(50, "A", "t1", minute=0)])
        self.assertEqual(metrics.find_echoes(d), [])
        self.assertEqual(len(metrics.find_together(d)), 1)

    def test_dj_who_loops_a_track_gets_no_credit(self):
        # I play t1 every day; Sasha plays it once. She didn't "pick it up from me today".
        d = data([s(day, "A", "t1") for day in range(20, 60)], [s(50, "A", "t1", hour=18)])
        self.assertEqual(metrics.find_echoes(d), [])

    def test_not_fresh_for_listener(self):
        d = data(
            [s(40, "A", "t1"), s(50, "A", "t1", hour=18)],  # me: played it 10 days ago
            [s(50, "A", "t1", hour=10)],
        )
        self.assertEqual(metrics.find_echoes(d), [])


class TerritoryTests(unittest.TestCase):
    def test_owner_is_decided_by_share_not_raw_plays(self):
        me = [s(60, "Shared", minute=i) for i in range(10)] + [s(60, f"filler{i}") for i in range(90)]
        her = [s(60, "Shared", minute=i) for i in range(5)] + [s(60, "other", minute=i) for i in range(5)]
        d = data(me, her)
        terr, exclusive = metrics.find_territories(d, T0 + 61 * DAY)
        self.assertEqual(len(terr), 1)
        # me: 10/100 = 10%, her: 5/10 = 50% -> hers, even with fewer plays
        self.assertEqual(terr[0].owner, HER)
        self.assertEqual(terr[0].plays, {ME: 10, HER: 5})
        self.assertEqual(exclusive[HER], 1)  # "other"

    def test_capture_is_reported(self):
        # A week ago: me 5/50 = 10% Z, her 5/10 = 50% Z -> hers.
        me = [s(40, "Z", minute=i) for i in range(5)] + [s(40, "F", minute=i) for i in range(45)]
        her = [s(40, "Z", minute=i) for i in range(5)] + [s(40, "q", minute=i) for i in range(5)]
        # This week I binge Z: 65/110 = 59% > her 50% -> mine.
        me += [s(58, "Z", minute=i) for i in range(60)]
        d = data(me, her)
        captured, _ = metrics.territory_changes(d, T0 + 60 * DAY, days_back=7)
        self.assertEqual([(t.artist, t.owner, prev) for t, prev in captured], [("Z", ME, HER)])


class StoreAndParseTests(unittest.TestCase):
    def test_roundtrip_with_awkward_names(self):
        rows = [
            Scrobble(T0, 'Комсомольск', 'Альбом, "в кавычках"', "Песня 1"),
            Scrobble(T0 + 40 * DAY, "AC/DC", "", "T.N.T."),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            store.save(ME, rows, data_dir=Path(tmp))
            self.assertEqual(len(list((Path(tmp) / ME).glob("*.csv"))), 2)
            self.assertEqual(store.load(ME, data_dir=Path(tmp)), rows)

    def test_merge_keeps_old_rows_and_drops_duplicates(self):
        a, b, c = (Scrobble(T0 + i, "x", "", "y") for i in range(3))
        self.assertEqual(store.merge([a, b], [b, c]), [a, b, c])
        self.assertEqual(store.merge([a, b, c], []), [a, b, c])

    def test_parse_single_track_and_now_playing(self):
        page = {"recenttracks": {"track": {
            "artist": {"#text": "Artist", "mbid": ""}, "album": {"#text": "Alb"},
            "name": "Song", "date": {"uts": "1775520000"},
        }}}
        self.assertEqual(parse_tracks(page), [Scrobble(1775520000, "Artist", "Alb", "Song")])
        playing = {"recenttracks": {"track": [{
            "artist": {"#text": "A"}, "album": {"#text": ""}, "name": "N",
            "@attr": {"nowplaying": "true"},
        }]}}
        self.assertEqual(parse_tracks(playing), [])


if __name__ == "__main__":
    unittest.main()
