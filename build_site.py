"""Build index.html and season2_chart.png from the scrobbles in data/.

Usage:
    python build_site.py   # same as: python update_data.py --build-only
"""

import time
from collections import Counter
from datetime import datetime, timedelta
from html import escape
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
from matplotlib.transforms import offset_copy  # noqa: E402

import config  # noqa: E402
import metrics  # noqa: E402
import store  # noqa: E402

CHART_FILE = "season2_chart.png"
SEASON1_PLOT = "season1/season1_final.png"
SEASON1_TEXT = (
    "{me} started scrobbling on 7 Apr 2026, 16,567 scrobbles behind. "
    "At 112 a day against {her}'s 29, {me} caught up on <b>22 Oct 2026</b>."
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def local(uts):
    return datetime.fromtimestamp(uts, tz=config.TZ)


def fmt_date(uts):
    d = local(uts)
    return f"{d.day} {d:%b}"


def fmt_lag(seconds):
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} min"
    if seconds < 48 * 3600:
        return f"{round(seconds / 3600)} h"
    return f"{round(seconds / 86400)} days"


def name(user):
    return escape(config.NAMES[user])


def swatch(user):
    return f'<span class="sw" style="background:{config.COLORS[user]}"></span>'


def who(user):
    return f"{swatch(user)}{name(user)}"


def arrow(a, b):
    return f'<span class="nowrap">{who(a)} → {who(b)}</span>'


def _rgba(hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def make_chart(conversions, echoes, start_uts, now_uts, path):
    users = list(config.USERS)
    start = local(start_uts).date()
    today = local(now_uts).date()

    def cumulative(events, user_of):
        out = {}
        for u in users:
            days = Counter(local(e.at).date() for e in events if user_of(e) == u)
            xs, ys, total = [start], [0], 0
            for d in sorted(days):
                total += days[d]
                xs.append(d)
                ys.append(total)
            xs.append(today)
            ys.append(total)
            out[u] = (xs, ys)
        return out

    panels = [
        ("кто кого подсадил · artists the other got hooked on",
         cumulative(conversions, lambda c: c.leader)),
        ("эхо · tracks the other picked up within 3 days",
         cumulative(echoes, lambda e: e.dj)),
    ]

    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, (title, series) in zip(axes, panels):
        for u in users:
            xs, ys = series[u]
            ax.step(xs, ys, where="post", color=config.COLORS[u], linewidth=2,
                    solid_joinstyle="round", solid_capstyle="round", label=config.NAMES[u])
            ax.plot([xs[-1]], [ys[-1]], "o", color=config.COLORS[u], markersize=8,
                    markeredgecolor="white", markeredgewidth=2, zorder=5)
        # Direct labels at the line ends, nudged apart if they would collide.
        ends = sorted((series[u][1][-1], u) for u in users)
        top = max(1, ends[-1][0])
        min_gap = top * 0.1
        label_at = offset_copy(ax.transData, fig=fig, x=9, units="points")
        last_y = None
        for y, u in ends:
            ypos = y if last_y is None or y - last_y >= min_gap else last_y + min_gap
            last_y = ypos
            ax.text(today, ypos, f"{config.NAMES[u]}  {y}", transform=label_at,
                    va="center", fontsize=10, color="#222", clip_on=False)
        ax.set_title(title, fontsize=11, loc="left", color="#222")
        ax.set_ylim(0, top * 1.15)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.grid(True, axis="y", color="#e3e3e3", linewidth=1)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#bbb")
        ax.tick_params(colors="#555", labelsize=9)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_xlim(start, today + timedelta(days=max(8, (today - start).days // 6)))
    axes[0].legend(loc="upper left", frameon=False, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _score_row(label, sub, counts, users):
    best = max(counts.values())
    winners = [u for u in users if counts[u] == best]
    cells = []
    for u in users:
        lead = counts[u] == best and len(winners) == 1
        cells.append(f'<td class="num{" lead" if lead else ""}">{counts[u]}</td>')
    return (f'<tr><th>{label}<small>{sub}</small></th>{"".join(cells)}</tr>',
            winners[0] if len(winners) == 1 else None)


def render(by_user, now):
    users = list(config.USERS)
    me, her = users
    start = metrics.shared_start(by_user)

    conv = metrics.find_conversions(by_user)
    echoes = metrics.find_echoes(by_user)
    together = metrics.find_together(by_user)
    terr, exclusive = metrics.find_territories(by_user, now)
    captured, fronts = metrics.territory_changes(by_user, now)

    conv_by = Counter(c.leader for c in conv)
    echo_by = Counter(e.dj for e in echoes)
    terr_by = Counter(t.owner for t in terr if t.owner)

    rows, round_winners = [], []
    for label, sub, counts in [
        ("кто кого подсадил", "artists the other got hooked on", conv_by),
        ("эхо", "tracks the other picked up", echo_by),
        ("территории", f"contested artists owned, last {config.TERRITORY_WINDOW_DAYS} days", terr_by),
    ]:
        row, winner = _score_row(label, sub, {u: counts.get(u, 0) for u in users}, users)
        rows.append(row)
        round_winners.append(winner)
    wins = Counter(w for w in round_winners if w)
    if wins.get(me, 0) > wins.get(her, 0):
        verdict = f"{name(me)} leads Season 2, {wins[me]}–{wins.get(her, 0)}"
        cat = '<img src="happy_cat.gif" alt="">'
    elif wins.get(her, 0) > wins.get(me, 0):
        verdict = f"{name(her)} leads Season 2, {wins[her]}–{wins.get(me, 0)}"
        cat = '<img src="crying_cat.png" alt="">'
    else:
        verdict = "Season 2 is level"
        cat = ""

    # --- кто кого подсадил ---
    conv_lines = []
    for leader in users:
        follower = her if leader == me else me
        mine = [c for c in conv if c.leader == leader]
        line = f"{who(leader)} got {who(follower)} hooked on <b>{len(mine)}</b> artists"
        if mine:
            top = max(mine, key=lambda c: c.follower_plays)
            line += (f" — the biggest one: <b>{escape(top.artist)}</b> "
                     f"({top.follower_plays} plays since {fmt_date(top.at)})")
        conv_lines.append(f"<li>{line}.</li>")
    conv_rows = "".join(
        f"<tr><td>{fmt_date(c.at)}</td><td><b>{escape(c.artist)}</b></td>"
        f"<td>{arrow(c.leader, c.follower)}</td><td class='num'>{c.follower_plays}</td>"
        f"<td class='num'>{fmt_lag(c.lag)}</td></tr>"
        for c in reversed(conv[-12:])
    ) or "<tr><td colspan=5 class='empty'>nobody has hooked anybody yet</td></tr>"

    # --- эхо ---
    echo_lines = []
    for dj in users:
        listener = her if dj == me else me
        mine = [e for e in echoes if e.dj == dj]
        line = f"{who(listener)} picked up <b>{len(mine)}</b> tracks from {who(dj)}"
        if mine:
            line += f", usually after <b>{fmt_lag(median(e.lag for e in mine))}</b>"
        echo_lines.append(f"<li>{line}.</li>")
    if together:
        echo_lines.append(
            f"<li>{len(together)} tracks were scrobbled on both accounts at the same moment "
            f"(within {config.TOGETHER_MINUTES} min) — that's listening together, not an echo.</li>")
    echo_rows = "".join(
        f"<tr><td>{fmt_date(e.at)}</td><td><b>{escape(e.track)}</b> "
        f"<span class='muted'>— {escape(e.artist)}</span></td>"
        f"<td>{arrow(e.dj, e.listener)}</td><td class='num'>{fmt_lag(e.lag)}</td></tr>"
        for e in reversed(echoes[-12:])
    ) or "<tr><td colspan=4 class='empty'>no echoes yet</td></tr>"

    # --- территории ---
    draws = sum(1 for t in terr if not t.owner)
    terr_summary = (
        f"<b>{len(terr)}</b> artists you both played at least {config.TERRITORY_MIN_PLAYS} times "
        f"in the last {config.TERRITORY_WINDOW_DAYS} days. "
        f"{who(me)} owns <b>{terr_by.get(me, 0)}</b>, {who(her)} owns <b>{terr_by.get(her, 0)}</b>"
        + (f", {draws} draw{'s' if draws != 1 else ''}" if draws else "") + "."
    )
    tiles = []
    for t in terr[:60]:
        margin = abs(t.shares[me] - t.shares[her]) / max(t.shares.values())
        if t.owner:
            color = config.COLORS[t.owner]
            style = f"background:{_rgba(color, 0.10 + 0.35 * margin)};border-left-color:{color}"
        else:
            style = "background:#eee;border-left-color:#999"
        shares = " · ".join(f"{escape(config.NAMES[u][0])} {t.shares[u] * 100:.1f}%" for u in users)
        tip = "; ".join(f"{config.NAMES[u]}: {t.plays[u]} plays, {t.shares[u] * 100:.1f}% of listening"
                        for u in users)
        tiles.append(f'<span class="tile" style="{style}" title="{escape(tip)}">'
                     f'{escape(t.artist)}<small>{shares}</small></span>')
    tiles_html = "".join(tiles) or "<p class='empty'>no contested artists right now</p>"
    news = [f"<li>{who(t.owner)} took <b>{escape(t.artist)}</b> from {who(prev)}</li>"
            for t, prev in captured[:8]]
    if fronts:
        names_ = ", ".join(escape(t.artist) for t in fronts[:6])
        more = f" and {len(fronts) - 6} more" if len(fronts) > 6 else ""
        news.append(f"<li>new contested artists: {names_}{more}</li>")
    news_html = "".join(news) or "<li class='muted'>quiet week on the map</li>"
    exclusive_html = (
        f"Not on the map (only one of you plays them): {exclusive[me]} artists only {name(me)}, "
        f"{exclusive[her]} only {name(her)}."
    )

    season1 = SEASON1_TEXT.format(me=name(me), her=name(her))
    updated = local(now).strftime("%Y-%m-%d %H:%M")
    tracked_from = fmt_date(start)
    counted_from = fmt_date(start + config.WARMUP_DAYS * metrics.DAY)

    return PAGE.format(
        score_head="".join(f"<th>{who(u)}</th>" for u in users),
        score_rows="".join(rows),
        verdict=verdict,
        cat=cat,
        chart=f"{CHART_FILE}?v={local(now):%Y%m%d%H%M}",  # new URL each build, so browsers don't show a cached chart
        conv_lines="".join(conv_lines),
        conv_rows=conv_rows,
        echo_lines="".join(echo_lines),
        echo_rows=echo_rows,
        terr_summary=terr_summary,
        tiles=tiles_html,
        news=news_html,
        exclusive=exclusive_html,
        season1=season1,
        season1_plot=SEASON1_PLOT,
        tracked_from=tracked_from,
        counted_from=counted_from,
        c=config,
        me=name(me),
        her=name(her),
        updated=updated,
        style=STYLE,
    )


def build(by_user=None, now=None, out_dir=config.BASE_DIR):
    by_user = by_user or {u: store.load(u) for u in config.USERS}
    now = now or int(time.time())
    if any(not rows for rows in by_user.values()):
        (out_dir / "index.html").write_text(
            PLACEHOLDER.format(style=STYLE, season1_plot=SEASON1_PLOT,
                               season1=SEASON1_TEXT.format(me=name(config.MY_USER),
                                                           her=name(config.FRIEND_USER))),
            encoding="utf-8")
        print("No scrobbles stored yet — wrote a placeholder page. Run update_data.py to fetch.")
        return
    start = metrics.shared_start(by_user)
    make_chart(metrics.find_conversions(by_user), metrics.find_echoes(by_user),
               start + config.WARMUP_DAYS * metrics.DAY, now, out_dir / CHART_FILE)
    (out_dir / "index.html").write_text(render(by_user, now), encoding="utf-8")
    print(f"Built {out_dir / 'index.html'} and {CHART_FILE}")


STYLE = """  :root {
    --orange: #FF6600;
    --cream: #FFF8E7;
    --ink: #111111;
    --muted: #666;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--cream);
    font-family: Verdana, Arial, sans-serif;
    font-size: 12px;
    color: var(--ink);
    line-height: 1.6;
    padding: 40px 20px;
  }
  .frame {
    max-width: 860px;
    margin: 0 auto;
    border: 3px solid var(--ink);
    padding: 48px 56px;
    position: relative;
  }
  .frame::before, .frame::after {
    content: ""; position: absolute; width: 14px; height: 14px; background: var(--orange);
  }
  .frame::before { top: -3px; left: -3px; }
  .frame::after { bottom: -3px; right: -3px; }
  .kicker {
    font-family: "Courier New", monospace; font-size: 11px; letter-spacing: 2px;
    color: var(--orange); text-transform: uppercase; margin-bottom: 12px;
  }
  h1 { font-size: 42px; letter-spacing: 1px; line-height: 1.1; margin-bottom: 12px; }
  .tagline {
    font-size: 13px; color: var(--muted); font-style: italic;
    margin-bottom: 32px; padding-bottom: 20px; border-bottom: 1px solid rgba(0,0,0,.15);
  }
  .card { background: #fff; border: 1px solid var(--ink); margin-bottom: 32px; }
  .card-header {
    background: #ddd; border-bottom: 1px solid var(--ink); padding: 6px 12px;
    font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    text-align: center;
  }
  .card-body { padding: 16px 18px; }
  .card-body img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
  .rule { color: var(--muted); font-size: 11px; margin-bottom: 10px; }
  ul.facts { list-style: none; margin-bottom: 14px; }
  ul.facts li { margin-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 4px 6px; text-align: left; vertical-align: top; }
  tr + tr td { border-top: 1px solid #eee; }
  .list th { font-size: 10px; text-transform: uppercase; color: var(--muted); font-weight: normal; }
  .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .empty, .muted { color: var(--muted); }
  .empty { text-align: center; font-style: italic; padding: 12px; }
  .nowrap { white-space: nowrap; }
  .sw {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    margin-right: 4px; vertical-align: 0;
  }
  .score th, .score td { padding: 10px 8px; }
  .score thead th { text-align: right; font-size: 13px; }
  .score tbody th { font-size: 15px; }
  .score tbody th small { display: block; font-size: 11px; font-weight: normal; color: var(--muted); }
  .score td.num { font-size: 30px; font-weight: bold; color: #bbb; width: 120px; }
  .score td.num.lead { color: var(--ink); }
  .verdict {
    text-align: center; margin: 8px 0 32px; padding: 20px 16px;
    border-top: 3px solid var(--ink); border-bottom: 3px solid var(--ink);
    font-size: 26px; font-weight: bold;
  }
  .verdict img { display: block; margin: 16px auto 0; max-width: 260px; width: 100%; border: 1px solid var(--ink); }
  .tiles { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
  .tile {
    border-left: 4px solid; border-radius: 3px; padding: 4px 8px 3px;
    font-weight: bold; line-height: 1.3;
  }
  .tile small { display: block; font-weight: normal; font-size: 10px; color: #333; }
  details { margin-top: 8px; }
  summary { cursor: pointer; font-weight: bold; }
  details p { margin-top: 8px; }
  .updated {
    margin-top: 24px; font-family: "Courier New", monospace; font-size: 10px;
    color: var(--muted); letter-spacing: 1px; text-align: right;
  }
  @media (max-width: 640px) {
    body { padding: 16px 10px; }
    .frame { padding: 28px 16px; }
    h1 { font-size: 30px; }
    .verdict { font-size: 20px; }
    .score td.num { font-size: 22px; width: 60px; }
  }
  .scroll { overflow-x: auto; }
"""


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>да ради Бога</title>
<style>
{style}</style>
</head>
<body>
<div class="frame">

  <div class="kicker">season 2 · who shapes whose taste</div>
  <h1>да ради Бога</h1>
  <h1>мне не жалко</h1>
  <div class="tagline">Season 1 was about how much. Season 2 is about who gets whom hooked.</div>

  <div class="card">
    <div class="card-header">::  scoreboard  ::</div>
    <div class="card-body">
      <table class="score">
        <thead><tr><th></th>{score_head}</tr></thead>
        <tbody>{score_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="verdict">{verdict}{cat}</div>

  <div class="card">
    <div class="card-header">::  over time  ::</div>
    <div class="card-body"><img src="{chart}" alt="Cumulative conversions and echoes for each of us"></div>
  </div>

  <div class="card">
    <div class="card-header">::  кто кого подсадил  ::</div>
    <div class="card-body">
      <p class="rule">An artist counts when one of us started playing it within {c.CONVERSION_LAG_DAYS} days
        after the other played it, and then played it at least {c.CONVERSION_MIN_PLAYS} times.</p>
      <ul class="facts">{conv_lines}</ul>
      <div class="scroll"><table class="list">
        <thead><tr><th>hooked on</th><th>artist</th><th>who → whom</th><th class="num">plays since</th><th class="num">after</th></tr></thead>
        <tbody>{conv_rows}</tbody>
      </table></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">::  эхо  ::</div>
    <div class="card-body">
      <p class="rule">A track counts when one of us starts playing it (first time in {c.ECHO_FRESH_DAYS}+ days)
        within {c.ECHO_WINDOW_HOURS} hours after the other started it. Who is the household DJ?</p>
      <ul class="facts">{echo_lines}</ul>
      <div class="scroll"><table class="list">
        <thead><tr><th>date</th><th>track</th><th>from → to</th><th class="num">after</th></tr></thead>
        <tbody>{echo_rows}</tbody>
      </table></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">::  территории  ::</div>
    <div class="card-body">
      <p class="rule">Every artist you both play is a territory. It belongs to whoever gives it a bigger share
        of <i>their own</i> listening, so listening more doesn't win the map.</p>
      <p>{terr_summary}</p>
      <div class="tiles">{tiles}</div>
      <p><b>This week</b></p>
      <ul class="facts">{news}</ul>
      <p class="muted">{exclusive}</p>
    </div>
  </div>

  <div class="card">
    <div class="card-header">::  season 1 archive · scrobble race  ::</div>
    <div class="card-body">
      <p style="margin-bottom:12px">{season1}</p>
      <img src="{season1_plot}" alt="Season 1: cumulative scrobbles until the crossover">
    </div>
  </div>

  <details>
    <summary>How the rules work</summary>
    <p>Both of us are tracked from {tracked_from}. The first {c.WARMUP_DAYS} days are a warm-up:
      a "first play" in that month might just be an old favourite that hadn't been scrobbled yet,
      so conversions and echoes count from {counted_from}.</p>
    <p><b>кто кого подсадил:</b> the follower's first-ever play of the artist comes after the leader played it
      in the previous {c.CONVERSION_LAG_DAYS} days; the follower then plays it at least {c.CONVERSION_MIN_PLAYS} times.
      If we both found the artist in the same {c.TOGETHER_MINUTES} minutes, nobody gets the point.</p>
    <p><b>эхо:</b> a "start" is a play of a track you haven't played in {c.ECHO_FRESH_DAYS} days. The listener's start
      must come {c.TOGETHER_MINUTES} minutes to {c.ECHO_WINDOW_HOURS} hours after the DJ's start. Both sides must be starts,
      so a track one of us loops every day doesn't make that person the DJ whenever the other plays it.</p>
    <p><b>территории:</b> last {c.TERRITORY_WINDOW_DAYS} days only, artists both played at least {c.TERRITORY_MIN_PLAYS}
      times. Owner = higher percentage of their own scrobbles. "This week" compares with the map from 7 days ago.</p>
    <p>Artist names ignore case and "feat." parts. Days are counted in Minsk time.</p>
  </details>

  <p class="updated">last updated: {updated}</p>

</div>
</body>
</html>
"""


PLACEHOLDER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>да ради Бога</title>
<style>
{style}</style>
</head>
<body>
<div class="frame">
  <div class="kicker">season 2 · who shapes whose taste</div>
  <h1>да ради Бога</h1>
  <h1>мне не жалко</h1>
  <div class="tagline">Season 2 starts with the next daily update: the bot is downloading both full histories.</div>
  <div class="card">
    <div class="card-header">::  season 1 archive · scrobble race  ::</div>
    <div class="card-body">
      <p style="margin-bottom:12px">{season1}</p>
      <img src="{season1_plot}" alt="Season 1: cumulative scrobbles until the crossover">
      <div class="verdict" style="border:0;margin:16px 0 0"><img src="happy_cat.gif" alt=""></div>
    </div>
  </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    build()
