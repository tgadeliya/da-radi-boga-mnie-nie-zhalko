"""Cleaner plot: rate-based projections for саша, actual data for я."""

import json
from pathlib import Path
from datetime import date, timedelta
from collections import Counter

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.family"] = "DejaVu Sans"

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "scrobble_data.json") as f:
    data = json.load(f)

my_dates = [date.fromisoformat(d) for d in data["Lib0n"]]
friend_dates = [date.fromisoformat(d) for d in data["dymovaleksandra"]]

MY_START = min(my_dates)           # 2026-04-07
TODAY = max(max(my_dates), max(friend_dates))
FRIEND_FIRST = min(friend_dates)   # 2024-09-17


def cumulative_series(dates):
    counts = Counter(dates)
    sorted_days = sorted(counts.keys())
    running = 0
    xs, ys = [], []
    for d in sorted_days:
        running += counts[d]
        xs.append(d)
        ys.append(running)
    return xs, ys


my_cx, my_cy = cumulative_series(my_dates)
fr_cx, fr_cy = cumulative_series(friend_dates)

# --- Key numbers ---
my_total = my_cy[-1]
my_days_active = (TODAY - MY_START).days + 1
my_rate = my_total / my_days_active

# саша at MY_START
friend_at_mystart = 0
for d, c in zip(fr_cx, fr_cy):
    if d < MY_START:
        friend_at_mystart = c
    else:
        break
friend_total = fr_cy[-1]

friend_days_before = (MY_START - FRIEND_FIRST).days
friend_rate_before = friend_at_mystart / friend_days_before
friend_rate_after = (friend_total - friend_at_mystart) / my_days_active

print(f"я: {my_total} over {my_days_active} days = {my_rate:.1f}/day")
print(f"саша before я: 0 → {friend_at_mystart} over {friend_days_before} days = {friend_rate_before:.1f}/day")
print(f"саша after я:  {friend_at_mystart} → {friend_total} over {my_days_active} days = {friend_rate_after:.1f}/day")

# --- Build rate-based line segments ---

# Line 1 (pre-я): straight line from (FRIEND_FIRST, 0) to (MY_START, friend_at_mystart)
pre_dates = [FRIEND_FIRST, MY_START]
pre_ys = [0, friend_at_mystart]

# Line 2 (post-я): straight line from (MY_START, friend_at_mystart) to (TODAY, friend_total)
post_dates = [MY_START, TODAY]
post_ys = [friend_at_mystart, friend_total]

# --- Projections into the future ---
PROJECTION_DAYS = 700
proj_end = TODAY + timedelta(days=PROJECTION_DAYS)
proj_range = [TODAY + timedelta(days=i) for i in range(PROJECTION_DAYS + 1)]

# саша: two projections from TODAY
fr_proj_before_y = [friend_total + friend_rate_before * i for i in range(PROJECTION_DAYS + 1)]
fr_proj_after_y = [friend_total + friend_rate_after * i for i in range(PROJECTION_DAYS + 1)]

# я projection from TODAY
my_proj_y = [my_total + my_rate * i for i in range(PROJECTION_DAYS + 1)]

# --- Crossover detection ---
def find_crossover(me_ys, friend_ys, dates):
    for i in range(1, len(me_ys)):
        if me_ys[i] >= friend_ys[i] and me_ys[i-1] < friend_ys[i-1]:
            return dates[i], me_ys[i]
    return None, None

cross_before = find_crossover(my_proj_y, fr_proj_before_y, proj_range)
cross_after = find_crossover(my_proj_y, fr_proj_after_y, proj_range)

# --- Plot ---
X_START = date(2025, 8, 1)  # start a bit before to show the pre-я slope

fig, ax = plt.subplots(figsize=(14, 7))

FRIEND_PRE = "#ff9896"
FRIEND_POST = "#8b0000"
ME_COLOR = "#1f77b4"
PROJ_ME = "#7fb8e0"

# Pre-start rate line (actual + projection continuation)
ax.plot(pre_dates, pre_ys, color=FRIEND_PRE, linewidth=2.5,
        label=f"саша pre-start pace ({friend_rate_before:.0f}/day)")
# Its projection extending from today (no separate legend)
ax.plot(proj_range, fr_proj_before_y, color=FRIEND_PRE, linewidth=2,
        linestyle="--")

# Post-start rate line (actual)
ax.plot(post_dates, post_ys, color=FRIEND_POST, linewidth=2.8,
        label=f"саша post-start pace ({friend_rate_after:.0f}/day)")
# Its projection (no separate legend)
ax.plot(proj_range, fr_proj_after_y, color=FRIEND_POST, linewidth=2,
        linestyle="--")

# Me: actual (solid, thick) + projection (dashed)
ax.plot(my_cx, my_cy, color=ME_COLOR, linewidth=3,
        label=f"тима pace ({my_rate:.0f}/day)", zorder=5)
ax.plot(proj_range, my_proj_y, color=PROJ_ME, linewidth=2,
        linestyle="--")

# Dummy lines for solid/dashed legend distinction
ax.plot([], [], color="#666", linewidth=2, label="actual (solid)")
ax.plot([], [], color="#666", linewidth=2, linestyle="--", label="projection (dashed)")

# Vertical line at я start
ax.axvline(MY_START, color="#444", linestyle=":", linewidth=1.8, alpha=0.9, zorder=3)

# Vertical line at today (subtle)
ax.axvline(TODAY, color="#888", linestyle="-", linewidth=0.8, alpha=0.4, zorder=3)

# Mark the slope change point
ax.plot([MY_START], [friend_at_mystart], "o",
        color="white", markersize=10,
        markeredgecolor=FRIEND_POST, markeredgewidth=2.5, zorder=6)

# Set axis limits
ax.set_xlim(X_START, proj_end)
ax.set_ylim(bottom=-1000)

# Annotations — placed after limits are set
ymin, ymax = ax.get_ylim()

ax.text(MY_START + timedelta(days=8), ymax * 0.92,
        "тима started scrobbling\n(2026-04-07)",
        fontsize=10.5, color="#222", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="#555", alpha=0.95))

ax.text(TODAY + timedelta(days=5), ymax * 0.04,
        "today", fontsize=9, color="#666", style="italic")

# Crossover point(s)
for cross_date, cross_y in [cross_before, cross_after]:
    if cross_date is not None:
        ax.plot([cross_date], [cross_y], "o", color="#2ca02c",
                markersize=11, markeredgecolor="white",
                markeredgewidth=1.8, zorder=7)
        ax.annotate(
            f"catch up:\n{cross_date.strftime('%b %Y')}",
            xy=(cross_date, cross_y),
            xytext=(12, -30), textcoords="offset points",
            fontsize=10, color="#1a7c1a", fontweight="bold",
        )

# If recent-rate crossover never happens, annotate that
if cross_after[0] is None:
    ax.annotate(
        "тима never catches up\nat саша's post-start rate",
        xy=(proj_end, fr_proj_after_y[-1]),
        xytext=(-220, -30), textcoords="offset points",
        fontsize=10, color=FRIEND_POST, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=FRIEND_POST, alpha=0.6),
    )

# Styling
ax.set_xlabel("Date", fontsize=11)
ax.set_ylabel("Cumulative scrobbles", fontsize=11)
ax.set_title("тима vs саша — scrobble rates and projections", fontsize=14, pad=15)
ax.grid(True, alpha=0.3)
ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))

plt.tight_layout()
plt.savefig(BASE_DIR / "plot_rates.png", dpi=140, bbox_inches="tight")
print("\nSaved plot_rates.png")

print(f"\nCrossovers:")
print(f"  vs pre-я rate ({friend_rate_before:.0f}/day): {cross_before[0]}")
print(f"  vs post-я rate ({friend_rate_after:.0f}/day): {cross_after[0] or 'never'}")
