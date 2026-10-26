"""Frozen Season 1 result: cumulative scrobbles until the crossover, no projections.

Run once (python season1/make_season1_final.py); the PNG is committed and
the daily job doesn't touch it.
"""

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.transforms import offset_copy  # noqa: E402

BASE_DIR = Path(__file__).parent
ME, HER = "Lib0n", "dymovaleksandra"
NAMES = {ME: "Tsimur", HER: "Sasha"}
COLORS = {ME: "#1f77b4", HER: "#b22222"}
X_START = date(2026, 1, 1)

data = json.loads((BASE_DIR / "scrobble_data.json").read_text())
counts = {u: Counter(date.fromisoformat(d) for d in data[u]) for u in (ME, HER)}
first = min(min(c) for c in counts.values())
last = max(max(c) for c in counts.values())

days, cum = [], {ME: [], HER: []}
running = {ME: 0, HER: 0}
cross = None
d = first
while d <= last:
    for u in (ME, HER):
        running[u] += counts[u][d]
    if d >= X_START:
        days.append(d)
        for u in (ME, HER):
            cum[u].append(running[u])
    if cross is None and running[ME] > 0 and running[ME] >= running[HER]:
        cross = (d, running[ME])
    d += timedelta(days=1)

plt.rcParams["font.family"] = "DejaVu Sans"
fig, ax = plt.subplots(figsize=(11, 4.6))
start_me = min(counts[ME])
leader = ME if cum[ME][-1] >= cum[HER][-1] else HER
for u in (HER, ME):
    # Tsimur's line starts on his first day, not as a flat zero before it.
    ys = [y if (u != ME or d >= start_me) else float("nan") for d, y in zip(days, cum[u])]
    ax.plot(days, ys, color=COLORS[u], linewidth=2, label=NAMES[u],
            solid_capstyle="round", solid_joinstyle="round")
    # End labels: leader slightly above, the other slightly below, so they never overlap.
    nudge = offset_copy(ax.transData, fig=fig, x=8, y=8 if u == leader else -8, units="points")
    ax.text(days[-1], cum[u][-1], f"{NAMES[u]}  {cum[u][-1]:,}", transform=nudge,
            va="center", fontsize=10, color="#222")

if cross:
    cd, cy = cross
    ax.plot([cd], [cy], "o", color="#222", markersize=9, markeredgecolor="white",
            markeredgewidth=2, zorder=5)
    ax.annotate(f"{cd.day} {cd:%b %Y}\n{NAMES[ME]} overtakes", xy=(cd, cy),
                xytext=(-190, 26), textcoords="offset points", fontsize=10,
                color="#222", fontweight="bold",
                arrowprops=dict(arrowstyle="-", color="#888", linewidth=1))

ax.set_ylim(0, max(cum[ME][-1], cum[HER][-1]) * 1.15)
ax.axvline(start_me, color="#999", linewidth=1, linestyle=":")
ax.text(start_me + timedelta(days=3), ax.get_ylim()[1] * 0.93,
        f"{NAMES[ME]} starts scrobbling\n{start_me.day} {start_me:%b %Y}",
        fontsize=9, color="#555")

ax.set_title("Season 1 · scrobble race · final", fontsize=12, loc="left", color="#222")
ax.legend(loc="upper left", frameon=False, fontsize=10, bbox_to_anchor=(0, 0.82))
ax.grid(True, axis="y", color="#e3e3e3", linewidth=1)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color("#bbb")
ax.tick_params(colors="#555", labelsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x / 1000:.0f}K" if x else "0"))
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
ax.set_xlim(X_START, last + timedelta(days=40))

fig.tight_layout()
fig.savefig(BASE_DIR / "season1_final.png", dpi=140, facecolor="white")
print(f"Crossover: {cross}. Saved season1_final.png")
