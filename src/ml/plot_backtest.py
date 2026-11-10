"""Render the walk-forward backtest chart for the README.

Numbers are transcribed from the committed results table in README.md
(14 monthly folds, Jul 2025 - Aug 2026, 7-day purge, RMSE as % of mean demand).
Deliberately NOT recomputed here: the chart must not be able to disagree with
the table it sits next to. If the backtest is re-run, update both together.

Output: docs/backtest.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, MultipleLocator

# --- data (README.md results table) ------------------------------------------
LEADS    = [0, 1, 2, 3, 4, 5, 6, 7]
BASELINE = [10.96, 10.96, 10.96, 10.96, 10.96, 10.96, 10.96, 12.04]
MODEL    = [5.72, 6.94, 7.11, 7.32, 7.63, 7.82, 8.02, 8.51]

# --- design tokens (dataviz reference palette, light mode) -------------------
SURFACE    = "#fcfcfb"
INK        = "#0b0b0b"   # text-primary
INK_2      = "#52514e"   # text-secondary
AXIS       = "#c3c2b7"   # axis / grid
C_MODEL    = "#2a78d6"   # categorical slot 1
C_BASELINE = "#898781"   # muted - a benchmark, not a peer series

LINE_W = 2.0             # spec: 2px lines
MARKER = 6               # pt; ~17px at dpi 200

def main() -> None:
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # Shade the gap. Blue, not neutral: the band IS the model's margin over the
    # baseline, and the narrowing to the right is the honest half of the story.
    ax.fill_between(LEADS, MODEL, BASELINE, color=C_MODEL, alpha=0.10, lw=0, zorder=1)

    ax.plot(LEADS, BASELINE, color=C_BASELINE, lw=LINE_W, marker="o",
            markersize=MARKER, zorder=2, clip_on=False)
    ax.plot(LEADS, MODEL, color=C_MODEL, lw=LINE_W, marker="o",
            markersize=MARKER, zorder=3, clip_on=False)

    # Direct end-labels in ink, not series colour; proximity carries identity.
    ax.text(7.18, BASELINE[-1], "  Seasonal-naive", color=INK_2, fontsize=10,
            va="center", ha="left")
    ax.text(7.18, MODEL[-1], "  LightGBM", color=INK_2, fontsize=10,
            va="center", ha="left")

    # Two selective annotations: the widest and narrowest points of the gap.
    ax.text(0.16, (MODEL[0] + BASELINE[0]) / 2, "−47.8%", color=INK_2,
            fontsize=10, va="center", ha="left")
    ax.text(6.0, (MODEL[6] + BASELINE[6]) / 2, "−26.8%", color=INK_2,
            fontsize=10, va="center", ha="center")

    # --- axes --------------------------------------------------------------
    ax.set_xlim(-0.3, 8.9)
    ax.set_ylim(0, 13)                      # zero-based: it's a percentage
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.set_xticks(LEADS)
    ax.tick_params(axis="both", colors=INK_2, labelsize=10, length=0)
    ax.set_xlabel("Forecast lead (days ahead)", color=INK_2, fontsize=10, labelpad=8)

    # recessive chrome: solid grid, horizontal only, behind the marks
    ax.grid(axis="y", color=AXIS, lw=0.8, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)

    ax.set_title("Walk-forward backtest: forecast error by lead",
                 color=INK, fontsize=14, loc="left", pad=28)
    ax.text(0, 1.035, "RMSE as % of mean demand  ·  14 monthly folds, "
            "Jul 2025 – Aug 2026  ·  7-day purge between train and test",
            transform=ax.transAxes, color=INK_2, fontsize=9.5, va="bottom")

    fig.tight_layout()
    fig.savefig("docs/backtest.png", facecolor=SURFACE, bbox_inches="tight")
    print("wrote docs/backtest.png")

if __name__ == "__main__":
    main()
