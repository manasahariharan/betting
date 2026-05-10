"""
Plot generation for Analyses 1, 2, 3
=====================================
Reads the JSON outputs already produced by the three analysis scripts
and generates static PNGs into output/plots/. No new computation —
just visualisation. Keeps the analysis scripts and the plotting code
cleanly separated.

Plots produced:
  1. calibration_overall.png            — Analysis 1, full-sample
  2. calibration_by_category.png        — Analysis 1, per category (small multiples)
  3. tail_zoom_longshot_favorite.png    — Analysis 2, tail calibration zoom
  4. calibration_dynamics_snapshots.png — Analysis 3, calibration plot at each snapshot
  5. bss_trajectory.png                 — Analysis 3, BSS over relative time
  6. slope_trajectory.png               — Analysis 3, slope + CI over time, with near-separation caveat
  7. longshot_overpricing_trajectory.png — Analysis 3, longshot pp over time
  8. category_bss_trajectories.png      — Analysis 3, BSS trajectory per category
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
PLOTS_DIR = OUTPUT_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Common style
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 140,
    "savefig.bbox": "tight",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
})

# Consistent category colours across plots
CATEGORY_COLOURS = {
    "Politics":    "#1f77b4",
    "Sports":      "#ff7f0e",
    "Crypto":      "#2ca02c",
    "Other":       "#7f7f7f",
    "Pop Culture": "#9467bd",
    "Business":    "#d62728",
    "Science":     "#8c564b",
}

SNAPSHOT_LABEL_FMT = "{:.0%} of life"


# ─── Helpers ────────────────────────────────────────────────────────────────


def load_json(name):
    with open(OUTPUT_DIR / name) as f:
        return json.load(f)


def plot_calibration_curve(ax, buckets, label=None, colour=None,
                           min_n=1, marker="o", show_n_in_size=True):
    """Generic calibration curve: predicted vs actual, point size ~ n."""
    xs, ys, ns = [], [], []
    for b in buckets:
        if b.get("n", 0) >= min_n and b.get("mean_predicted") is not None:
            xs.append(b["mean_predicted"])
            ys.append(b["mean_actual"])
            ns.append(b["n"])
    xs = np.array(xs)
    ys = np.array(ys)
    ns = np.array(ns)

    sizes = (10 + 60 * np.sqrt(ns / max(ns.max(), 1))
             if show_n_in_size and len(ns) else 30)

    ax.scatter(xs, ys, s=sizes, color=colour, alpha=0.75,
               edgecolor="white", linewidth=0.5, zorder=3, label=label,
               marker=marker)
    return xs, ys, ns


def add_diagonal(ax):
    ax.plot([0, 1], [0, 1], color="black", linestyle=":", linewidth=1,
            alpha=0.5, zorder=1, label="Perfect calibration")


def annotate_summary(ax, text, loc=(0.04, 0.96), fontsize=9):
    ax.text(loc[0], loc[1], text, transform=ax.transAxes, va="top",
            ha="left", fontsize=fontsize,
            bbox=dict(boxstyle="round,pad=0.4", fc="white",
                      ec="#cccccc", alpha=0.9))


# ─── Plot 1: overall calibration (Analysis 1) ───────────────────────────────


def plot_calibration_overall():
    cal = load_json("calibration_data.json")
    fig, ax = plt.subplots(figsize=(7, 6.5))

    add_diagonal(ax)
    plot_calibration_curve(ax, cal["buckets"], colour="#1f77b4")

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Predicted probability (final crowd price)")
    ax.set_ylabel("Realised resolution rate")
    ax.set_title("Polymarket calibration — final prices, full sample\n"
                 f"n = {cal['n_markets']} resolved binary markets, "
                 f"BSS = {cal['bss']:.3f}")
    ax.legend(loc="lower right", frameon=False)

    summary = (
        f"Brier score: {cal['brier_score']:.4f}\n"
        f"Brier baseline (Var(y)): {cal['brier_score_baseline']:.4f}\n"
        f"Base rate (resolved YES): {cal['base_rate']:.1%}\n"
        f"Bin width: 0.05 — point size ∝ √n"
    )
    annotate_summary(ax, summary)

    fig.savefig(PLOTS_DIR / "calibration_overall.png")
    plt.close(fig)
    print("  calibration_overall.png")


# ─── Plot 2: per-category calibration (small multiples) ─────────────────────


def plot_calibration_by_category():
    cat = load_json("category_data.json")
    cats = list(cat["categories"].items())
    n = len(cats)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(6.5 * cols, 5.6 * rows),
                             sharex=True, sharey=True)
    axes = np.atleast_2d(axes).flatten()

    for i, (name, body) in enumerate(cats):
        ax = axes[i]
        add_diagonal(ax)
        colour = CATEGORY_COLOURS.get(name, None)
        plot_calibration_curve(ax, body["buckets"], colour=colour)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_title(f"{name}  (n = {body['n_markets']}, "
                     f"BSS = {body['bss']:.3f})")
        if i % cols == 0:
            ax.set_ylabel("Realised rate")
        if i // cols == rows - 1:
            ax.set_xlabel("Predicted probability")

    for j in range(n, rows * cols):
        axes[j].set_visible(False)

    fig.suptitle("Calibration by category — Polymarket final prices",
                 fontsize=14, y=1.01)
    fig.savefig(PLOTS_DIR / "calibration_by_category.png")
    plt.close(fig)
    print("  calibration_by_category.png")


# ─── Plot 3: tail zoom (Analysis 2) ─────────────────────────────────────────


def plot_tail_zoom():
    ls = load_json("longshot_data.json")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6))

    # Longshot panel
    ax = axes[0]
    ax.plot([0, 0.15], [0, 0.15], color="black", linestyle=":",
            linewidth=1, alpha=0.5, zorder=1, label="Perfect calibration")
    plot_calibration_curve(ax, ls["longshots"]["calibration_buckets"],
                           colour="#1f77b4", label="Longshots")
    ax.set_xlim(-0.005, 0.16)
    ax.set_ylim(-0.005, 0.16)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Realised rate")
    ax.set_title(f"Longshot tail (price ≤ 0.15) — n = "
                 f"{ls['longshots']['n_markets']}, "
                 f"YES = {ls['longshots']['n_resolved_yes']}")
    annotate_summary(
        ax,
        f"Mean overpricing: "
        f"{ls['longshots']['mean_overpricing_pp']:+.2f} pp\n"
        f"Slope: omitted (separation guard;\n"
        f"  minority class < 5%)\n"
        f"Bin centres at non-uniform widths"
    )
    ax.legend(loc="lower right", frameon=False)

    # Favorite panel
    ax = axes[1]
    ax.plot([0.85, 1.0], [0.85, 1.0], color="black", linestyle=":",
            linewidth=1, alpha=0.5, zorder=1, label="Perfect calibration")
    plot_calibration_curve(ax, ls["favorites"]["calibration_buckets"],
                           colour="#d62728", label="Favorites")
    ax.set_xlim(0.84, 1.005)
    ax.set_ylim(0.84, 1.005)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Realised rate")
    ax.set_title(f"Favorite tail (price ≥ 0.85) — n = "
                 f"{ls['favorites']['n_markets']}, "
                 f"YES = {ls['favorites']['n_resolved_yes']}")
    annotate_summary(
        ax,
        f"Mean underpricing: "
        f"{ls['favorites']['mean_overpricing_pp']:+.2f} pp\n"
        f"Every bucket above 0.90 resolved\n"
        f"  100% YES (consistent direction)"
    )
    ax.legend(loc="lower right", frameon=False)

    fig.suptitle("Tail calibration — Analysis 2 (Longshot Bias)",
                 fontsize=14, y=1.02)
    fig.savefig(PLOTS_DIR / "tail_zoom_longshot_favorite.png")
    plt.close(fig)
    print("  tail_zoom_longshot_favorite.png")


# ─── Plot 4: dynamics snapshots (small multiples) ───────────────────────────


def plot_dynamics_snapshots():
    dyn = load_json("dynamics_data.json")
    snaps = dyn["snapshots"]
    keys = list(snaps.keys())  # in plan order: 0.10 ... 0.95
    n = len(keys)
    cols = 3
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 5.0 * rows),
                             sharex=True, sharey=True)
    axes = np.atleast_2d(axes).flatten()

    for i, k in enumerate(keys):
        s = snaps[k]
        ax = axes[i]
        add_diagonal(ax)
        if "skipped" in s:
            ax.text(0.5, 0.5, f"SKIPPED\n({s['skipped']})",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=11, color="grey")
            ax.set_title(SNAPSHOT_LABEL_FMT.format(float(k)))
            continue

        cmap = plt.cm.viridis(0.15 + 0.7 * (i / max(n - 1, 1)))
        plot_calibration_curve(ax, s["calibration_buckets"], colour=cmap)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        slope = s["log_odds"]["slope"]
        slope_str = f"{slope:.2f}" if slope is not None else "—"
        ax.set_title(f"{SNAPSHOT_LABEL_FMT.format(float(k))} "
                     f"(n = {s['n_markets']}, "
                     f"BSS = {s['bss']:.3f}, slope = {slope_str})")
        if i % cols == 0:
            ax.set_ylabel("Realised rate")
        if i // cols == rows - 1:
            ax.set_xlabel("Predicted probability at this snapshot")

    for j in range(n, rows * cols):
        axes[j].set_visible(False)

    fig.suptitle(
        "Calibration evolution over a market's lifetime\n"
        f"Dynamics-eligible sample: {dyn['dynamics_sample']['n_markets']} "
        "markets with duration ≥ 5 days and ≥ 4 CLOB observations",
        fontsize=14, y=1.005,
    )
    fig.savefig(PLOTS_DIR / "calibration_dynamics_snapshots.png")
    plt.close(fig)
    print("  calibration_dynamics_snapshots.png")


# ─── Plot 5: BSS trajectory ─────────────────────────────────────────────────


def _snapshot_series(snaps, field_path):
    """Pull a list of values across snapshots given a dotted field path."""
    xs, ys = [], []
    for k, s in snaps.items():
        if "skipped" in s:
            continue
        v = s
        for p in field_path:
            v = v.get(p) if isinstance(v, dict) else None
            if v is None:
                break
        if v is not None:
            xs.append(float(k))
            ys.append(v)
    return np.array(xs), np.array(ys)


def plot_bss_trajectory():
    dyn = load_json("dynamics_data.json")
    snaps = dyn["snapshots"]
    final = dyn["final_price_sanity_check"]

    xs, ys = _snapshot_series(snaps, ["bss"])

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.plot(xs, ys, marker="o", color="#1f77b4", linewidth=2.2,
            label="BSS at relative-time snapshot")
    # Final-price reference
    ax.axhline(final["bss"], color="grey", linestyle="--", linewidth=1,
               label=f"Final-price BSS = {final['bss']:.3f}")

    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.3f}", (x, y),
                    textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=9, color="#1f77b4")

    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, max(ys.max(), final["bss"]) * 1.12)
    ax.set_xlabel("Relative time elapsed (% of market life)")
    ax.set_ylabel("Brier Skill Score")
    ax.set_title(
        "Calibration improves monotonically across a market's lifetime\n"
        f"Full dynamics sample, n ≈ "
        f"{dyn['dynamics_sample']['n_markets']} (varies slightly by snapshot)"
    )
    ax.set_xticks([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0])
    ax.set_xticklabels(["10%", "25%", "50%", "75%", "90%", "95%", "final"])
    ax.legend(loc="lower right", frameon=False)
    annotate_summary(
        ax,
        f"+{(ys[-1] - ys[0]):.3f} BSS gain across the lifetime\n"
        f"({(ys[-1] / ys[0] - 1) * 100:.0f}% relative improvement)\n"
        "BSS at 95% is within 0.025 of the final-price\n"
        "  BSS — most accuracy gain is gradual, not\n"
        "  a final-tick snap.",
    )
    fig.savefig(PLOTS_DIR / "bss_trajectory.png")
    plt.close(fig)
    print("  bss_trajectory.png")


# ─── Plot 6: slope trajectory with CI ───────────────────────────────────────


def plot_slope_trajectory():
    dyn = load_json("dynamics_data.json")
    snaps = dyn["snapshots"]
    final = dyn["final_price_sanity_check"]

    xs, slopes, lo, hi = [], [], [], []
    for k, s in snaps.items():
        if "skipped" in s or s["log_odds"]["slope"] is None:
            continue
        xs.append(float(k))
        slopes.append(s["log_odds"]["slope"])
        lo.append(s["log_odds"]["slope_ci_lower"])
        hi.append(s["log_odds"]["slope_ci_upper"])
    xs = np.array(xs)
    slopes = np.array(slopes)
    lo = np.array(lo)
    hi = np.array(hi)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    ax.fill_between(xs, lo, hi, alpha=0.2, color="#1f77b4",
                    label="95% bootstrap CI")
    ax.plot(xs, slopes, marker="o", color="#1f77b4", linewidth=2.2,
            label="Calibration slope")
    ax.axhline(1.0, color="black", linestyle=":", linewidth=1,
               alpha=0.6, label="Perfect calibration (slope = 1)")
    final_slope = final["log_odds"]["slope"]
    ax.scatter([1.0], [final_slope], color="grey", marker="D",
               s=80, zorder=4, label=f"Final-price slope = {final_slope:.2f}")

    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Relative time elapsed (% of market life)")
    ax.set_ylabel("Log-odds calibration slope")
    ax.set_title(
        "Calibration slope over a market's lifetime\n"
        "Late-snapshot slope inflation is mostly a near-separation artifact"
    )
    ax.set_xticks([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0])
    ax.set_xticklabels(["10%", "25%", "50%", "75%", "90%", "95%", "final"])

    # Caveat band over the inflation region
    ax.axvspan(0.85, 1.05, color="red", alpha=0.05, zorder=0,
               label="Near-separation regime\n(slope reading degraded)")

    # Y-axis headroom for the annotation box
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(min(ymin, 0.9), max(ymax, 1.85))

    ax.legend(loc="lower left", frameon=False, fontsize=9)
    annotate_summary(
        ax,
        "slope = 1 → perfect calibration\n"
        "slope > 1 → underconfident (compressed toward 50%)\n"
        "slope < 1 → overconfident (too extreme)\n\n"
        "Late-snapshot slope > 1 is mostly the sigmoid-fitting\n"
        "  artifact of near-separable data — read BSS instead\n"
        "  for the honest dynamics signal.",
        loc=(0.04, 0.98), fontsize=8.5,
    )
    fig.savefig(PLOTS_DIR / "slope_trajectory.png")
    plt.close(fig)
    print("  slope_trajectory.png")


# ─── Plot 7: longshot overpricing trajectory ────────────────────────────────


def plot_longshot_trajectory():
    dyn = load_json("dynamics_data.json")
    snaps = dyn["snapshots"]

    xs, ys = _snapshot_series(snaps,
                              ["longshot", "mean_overpricing_pp"])

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.plot(xs, ys, marker="o", color="#ff7f0e", linewidth=2.2,
            label="Longshot subset overpricing pp")
    ax.axhline(0.0, color="black", linestyle=":", linewidth=1, alpha=0.5,
               label="Perfectly calibrated longshots")

    for x, y in zip(xs, ys):
        ax.annotate(f"{y:+.2f}", (x, y),
                    textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=9, color="#ff7f0e")

    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Relative time elapsed (% of market life)")
    ax.set_ylabel("Mean longshot overpricing (pp)")
    ax.set_title(
        "Longshot overpricing shrinks as resolution approaches\n"
        "Longshot subset = markets with snapshot price ≤ 0.15 "
        "(membership is snapshot-relative)"
    )
    ax.set_xticks([0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
    ax.set_xticklabels(["10%", "25%", "50%", "75%", "90%", "95%"])
    ax.legend(loc="upper right", frameon=False)
    annotate_summary(
        ax,
        "Direction consistent with Page & Clemen (2013):\n"
        "favorite-longshot bias largest far from\n"
        "  resolution, smallest near close.",
        loc=(0.04, 0.18),
    )
    fig.savefig(PLOTS_DIR / "longshot_overpricing_trajectory.png")
    plt.close(fig)
    print("  longshot_overpricing_trajectory.png")


# ─── Plot 8: per-category BSS trajectories ──────────────────────────────────


def plot_category_bss_trajectories():
    cats = load_json("dynamics_category.json")["categories"]

    fig, ax = plt.subplots(figsize=(9, 5.8))
    for name, body in cats.items():
        snaps = body["snapshots"]
        xs, ys = _snapshot_series(snaps, ["bss"])
        if len(xs) < 2:
            continue
        colour = CATEGORY_COLOURS.get(name, None)
        ax.plot(xs, ys, marker="o", linewidth=2.0, color=colour,
                label=f"{name}  (n = {body['n_markets_in_dynamics_sample']})")

    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Relative time elapsed (% of market life)")
    ax.set_ylabel("Brier Skill Score")
    ax.set_title(
        "BSS trajectory by category\n"
        "Politics gains the most accuracy across its lifetime; "
        "Sports gains the least"
    )
    ax.set_xticks([0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
    ax.set_xticklabels(["10%", "25%", "50%", "75%", "90%", "95%"])
    ax.legend(loc="lower right", frameon=False)

    fig.savefig(PLOTS_DIR / "category_bss_trajectories.png")
    plt.close(fig)
    print("  category_bss_trajectories.png")


# ─── Main ───────────────────────────────────────────────────────────────────


def main():
    print(f"Generating plots into {PLOTS_DIR}/ ...")
    plot_calibration_overall()
    plot_calibration_by_category()
    plot_tail_zoom()
    plot_dynamics_snapshots()
    plot_bss_trajectory()
    plot_slope_trajectory()
    plot_longshot_trajectory()
    plot_category_bss_trajectories()
    print("Done.")


if __name__ == "__main__":
    main()
