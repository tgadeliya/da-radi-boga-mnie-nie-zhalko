"""Generate the refined plot with broken axis, Russian labels, and projections."""

import json
from datetime import date, datetime, timedelta
from collections import Counter

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import ConnectionPatch

# Ensure Cyrillic renders
plt.rcParams["font.family"] = "DejaVu Sans"

with open("/home/claude/lastfm/scrobble_data.json") as f:
    data = json.load(f)

my_dates = [date.fromisoformat(d) for d in data["Lib0n"]]
friend_dates = [date.fromisoformat(d) for d in data["dymovaleksandra"]]

MY_START = min(my_dates)  # 2026-04-07
TODAY = max(max(my_dates), max(friend_dates))


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

# --- Compute rates ---
# My rate: scrobbles since I started / days since I started
my_total = my_cy[-1]
my_days_active = (TODAY - MY_START).days + 1
my_rate = my_total / my_days_active

# Friend's rate BEFORE my start: scrobbles she had on MY_START / her days active until then
friend_before_mystart = 0
for d, c in zip(fr_cx, fr_cy):
    if d < MY_START:
        friend_before_mystart = c
    else:
        break
friend_first_day = min(friend_dates)
friend_days_before = (MY_START - friend_first_day).days
friend_rate_before = friend_before_mystart / friend_days_before if friend_days_before > 0 else 0

# Friend's rate AFTER my start: scrobbles in the window since MY_START
friend_scrobbles_after = sum(1 for d in friend_dates if d >= MY_START)
friend_days_after = (TODAY - MY_START).days + 1
friend_rate_after = friend_scrobbles_after / friend_days_after

# Friend's current total
friend_total = fr_cy[-1]

print(f"My rate (since {MY_START}): {my_rate:.1f}/day over {my_days_active} days")
print(f"Friend rate BEFORE my start: {friend_rate_before:.1f}/day "
      f"({friend_before_mystart} scrobbles over {friend_days_before} days)")
print(f"Friend rate AFTER my start: {friend_rate_after:.1f}/day "
      f"({friend_scrobbles_after} scrobbles over {friend_days_after} days)")
print(f"My total: {my_total}, Friend total: {friend_total}, gap: {friend_total - my_total}")

# --- Projection horizon ---
# Project far enough to see crossover in optimistic scenarios, but not forever
PROJECTION_DAYS = 800
proj_end = TODAY + timedelta(days=PROJECTION_DAYS)
proj_dates = [TODAY + timedelta(days=i) for i in range(PROJECTION_DAYS + 1)]

# Projection lines
my_proj_y = [my_total + my_rate * i for i in range(PROJECTION_DAYS + 1)]
fr_proj_before_y = [friend_total + friend_rate_before * i for i in range(PROJECTION_DAYS + 1)]
fr_proj_after_y = [friend_total + friend_rate_after * i for i in range(PROJECTION_DAYS + 1)]

# --- Broken axis plot ---
# Left panel: a narrow slice showing friend's early history starting from her first scrobble
# Right panel: comparison zone from ~2 weeks before MY_START through projection
LEFT_START = friend_first_day
LEFT_END = friend_first_day + timedelta(days=60)  # show ~2 months of her early history
RIGHT_START = MY_START - timedelta(days=14)
RIGHT_END = proj_end

# Width ratios reflect visual importance: small left panel, big right panel
fig, (axL, axR) = plt.subplots(
    1, 2, sharey=True,
    gridspec_kw={"width_ratios": [1, 5], "wspace": 0.04},
    figsize=(14, 7),
)

FRIEND_COLOR = "#d62728"
ME_COLOR = "#1f77b4"
PROJ_FRIEND_BEFORE = "#ff9896"   # lighter red
PROJ_FRIEND_AFTER = "#8b0000"    # darker red
PROJ_ME = "#7fb8e0"              # lighter blue

# --- LEFT PANEL: friend's early history ---
axL.plot(fr_cx, fr_cy, color=FRIEND_COLOR, linewidth=2, label="саша (friend)")
axL.set_xlim(LEFT_START, LEFT_END)
axL.xaxis.set_major_locator(mdates.MonthLocator())
axL.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
axL.grid(True, alpha=0.3)
axL.set_ylabel("Cumulative scrobbles", fontsize=11)

# --- RIGHT PANEL: comparison zone + projections ---
# Actual data (solid, thick)
axR.plot(fr_cx, fr_cy, color=FRIEND_COLOR, linewidth=3, label="саша (friend) — actual", zorder=4)
axR.plot(my_cx, my_cy, color=ME_COLOR, linewidth=3, label="я (me) — actual", zorder=4)

# Projections (dashed)
axR.plot(proj_dates, fr_proj_after_y, color=PROJ_FRIEND_AFTER, linewidth=1.8,
         linestyle="--", label=f"саша projection — recent rate ({friend_rate_after:.0f}/day)")
axR.plot(proj_dates, fr_proj_before_y, color=PROJ_FRIEND_BEFORE, linewidth=1.8,
         linestyle="--", label=f"саша projection — pre-я rate ({friend_rate_before:.0f}/day)")
axR.plot(proj_dates, my_proj_y, color=PROJ_ME, linewidth=1.8,
         linestyle="--", label=f"я projection — current rate ({my_rate:.0f}/day)")

# Vertical line at my start
axR.axvline(MY_START, color="#555", linestyle=":", linewidth=1.8, alpha=0.9, zorder=3)

# Vertical line at "today"
axR.axvline(TODAY, color="#888", linestyle="-", linewidth=0.8, alpha=0.5, zorder=3)

axR.set_xlim(RIGHT_START, RIGHT_END)
axR.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
axR.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
axR.grid(True, alpha=0.3)
axR.legend(loc="lower right", fontsize=10, framealpha=0.95)

# Find crossover points in projections (where я line crosses саша lines)
def find_crossover(me_ys, friend_ys, dates):
    for i in range(1, len(me_ys)):
        if me_ys[i] >= friend_ys[i] and me_ys[i-1] < friend_ys[i-1]:
            return dates[i], me_ys[i]
    return None, None

cross1 = find_crossover(my_proj_y, fr_proj_before_y, proj_dates)
cross2 = find_crossover(my_proj_y, fr_proj_after_y, proj_dates)

for cross_date, cross_y in [cross1, cross2]:
    if cross_date is not None:
        axR.plot([cross_date], [cross_y], "o", color="green",
                 markersize=9, markeredgecolor="white", markeredgewidth=1.5, zorder=5)
        axR.annotate(
            f"catch up:\n{cross_date.strftime('%b %Y')}",
            xy=(cross_date, cross_y),
            xytext=(10, -25), textcoords="offset points",
            fontsize=9, color="green", fontweight="bold",
        )

# --- Hide spines at the break and draw slashes ---
axL.spines["right"].set_visible(False)
axR.spines["left"].set_visible(False)
axR.tick_params(axis="y", left=False)

# Diagonal break marks
d = 0.015
kwargs = dict(transform=axL.transAxes, color="k", clip_on=False, linewidth=1.2)
axL.plot((1 - d, 1 + d), (-d, +d), **kwargs)
axL.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
kwargs.update(transform=axR.transAxes)
# Adjust d for the right panel because width is different
d_r = d * (1 / 5)  # scale by inverse width ratio
axR.plot((-d_r, +d_r), (-d, +d), **kwargs)
axR.plot((-d_r, +d_r), (1 - d, 1 + d), **kwargs)

# --- Title and final touches ---
fig.suptitle("я vs саша — cumulative scrobbles with projections",
             fontsize=14, y=0.98)

# Format y-axis with commas
for ax in (axL, axR):
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))

# Now that y-limits are settled, add the vertical line labels at top of plot
ymin, ymax = axR.get_ylim()
label_y = ymax * 0.92
axR.text(MY_START + timedelta(days=5), label_y,
         "я started scrobbling\n(2026-04-07)",
         fontsize=10, color="#333", fontweight="bold",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                   edgecolor="#555", alpha=0.9))
axR.text(TODAY + timedelta(days=5), ymax * 0.05,
         "today", fontsize=9, color="#666", style="italic")

# Shared x-axis label
fig.text(0.5, 0.02, "Date", ha="center", fontsize=11)

plt.tight_layout(rect=[0, 0.03, 1, 0.96])
plt.savefig("/home/claude/lastfm/plot_final.png", dpi=140, bbox_inches="tight")
print("\nSaved plot_final.png")

# Print projections
print(f"\nProjection analysis:")
print(f"  я current: {my_total:,} @ {my_rate:.1f}/day")
print(f"  саша current: {friend_total:,}")
print(f"  саша pre-я rate: {friend_rate_before:.1f}/day")
print(f"  саша recent rate: {friend_rate_after:.1f}/day")
for label, cross in [("vs pre-я rate", cross1), ("vs recent rate", cross2)]:
    if cross[0] is None:
        gap_at_end = fr_proj_after_y[-1] - my_proj_y[-1] if "recent" in label else fr_proj_before_y[-1] - my_proj_y[-1]
        print(f"  Crossover {label}: never (gap at {PROJECTION_DAYS}d: {gap_at_end:,.0f})")
    else:
        print(f"  Crossover {label}: {cross[0]} @ {cross[1]:,.0f} scrobbles")
