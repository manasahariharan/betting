"""
Analysis 2 (Deep Dive 1): Longshot Bias
========================================
From POLYMARKET_PROJECT_PLAN.md, "Analysis 2 (Deep Dive 1): Longshot Bias".

Question: Do Polymarket bettors systematically overprice low-probability events
          (price <= 0.15) and underprice heavy favorites (price >= 0.85)?
          Does this vary by category and market volume?

Inputs (from Analysis 1):
  data/markets_clean.csv   — 1,000 stratified-sampled markets with
                             `final_yes_price` (CLOB second-to-last 12hr tick)
                             and `resolved_yes`. ~806 have prices.

What we compute:
  1. Tail calibration buckets (fine 0.01-width in [0, 0.15] and [0.85, 1.0])
  2. Mean overpricing (pp) — plain-English complement to slope
  3. Log-odds (calibration) slope + intercept with bootstrap 95% CIs
     - Full sample, longshot subset, favorite subset
  4. Volume stratification: median split (primary) + tertile (robustness)
  5. Per-category longshot bias — slope when n_longshot >= 15, else
     overpricing pp only
  6. Hall of Shame: 25 most confidently wrong markets
  7. Hidden Gems: 15 markets priced <= 0.10 that resolved YES

Outputs (in /workspace/output):
  - longshot_data.json
  - longshot_volume.json
  - longshot_category.json
  - hall_of_shame.json
  - hidden_gems.json

Methodology notes baked in:
  - Log-odds regression uses unpenalised logistic regression
    (penalty=None) so the slope is the MLE, not an L2-shrunken estimate.
  - Prices clipped to [0.01, 0.99] before log-odds.
  - Bootstrap is market-level resampling (B=500, seed=42). Limitations
    discussed in the summary; a category-stratified bootstrap is reported
    as a robustness check.
  - Language follows the project plan's "Future Improvements" guidance:
    we say "consistent with" and "appears", not "proves" or "demonstrates".
"""

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=FutureWarning,
                        module="sklearn")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Thresholds
LONGSHOT_MAX = 0.15        # "longshot" = final price <= 0.15
FAVORITE_MIN = 0.85        # "favorite" = final price >= 0.85
HIDDEN_GEM_MAX = 0.10      # "hidden gem" = priced <= 0.10 and resolved YES
CLIP_LOW, CLIP_HIGH = 0.01, 0.99
MIN_CATEGORY_LONGSHOT_N = 15
BOOTSTRAP_B = 500
BOOTSTRAP_SEED = 42

# Polymarket public URL pattern for human-readable links
POLY_URL = "https://polymarket.com/event/{slug}"


# ─── Helpers ────────────────────────────────────────────────────────────────


def log_odds(p):
    """Log-odds with clipping to keep finite at the boundary."""
    p = np.clip(np.asarray(p, dtype=float), CLIP_LOW, CLIP_HIGH)
    return np.log(p / (1 - p))


SEPARATION_MINORITY_THRESHOLD = 0.05  # < 5% of either class → unstable MLE


def has_separation_issue(outcomes):
    """True if the subset is too imbalanced for a stable logistic fit."""
    y = np.asarray(outcomes, dtype=int)
    if len(y) == 0:
        return True
    p1 = y.mean()
    return min(p1, 1 - p1) < SEPARATION_MINORITY_THRESHOLD


def fit_log_odds_slope(prices, outcomes):
    """
    Logistic regression of resolved_yes ~ log_odds(price).
    Returns (slope, intercept). Uses unpenalised MLE so the slope is
    not L2-shrunk (the plan's interpretation assumes MLE).
    """
    if len(prices) < 5 or len(set(outcomes)) < 2:
        return float("nan"), float("nan")
    x = log_odds(prices).reshape(-1, 1)
    y = np.asarray(outcomes, dtype=int)
    # C=1e9 ≈ no regularisation. Equivalent to MLE; sklearn 1.8 deprecated
    # penalty=None in favour of large C / l1_ratio knobs.
    model = LogisticRegression(C=1e9, solver="lbfgs", max_iter=5000)
    model.fit(x, y)
    return float(model.coef_[0, 0]), float(model.intercept_[0])


def bootstrap_log_odds(prices, outcomes, b=BOOTSTRAP_B,
                       seed=BOOTSTRAP_SEED, strata=None):
    """
    Bootstrap (slope, intercept) CIs.
      - If `strata` is None: simple market-level resampling with replacement.
      - If `strata` is provided: stratified bootstrap, resampling with
        replacement *within* each stratum (preserves category mix).
    Returns dict with point estimate (computed on full data), CI bounds,
    and the share of resamples whose slope is below 1 (overconfident
    direction).
    """
    prices = np.asarray(prices, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    n = len(prices)

    # Near-perfect separation makes the MLE diverge (slope → ∞). Flag and
    # skip rather than reporting a meaningless astronomical slope.
    if has_separation_issue(outcomes):
        return {
            "slope": None,
            "intercept": None,
            "slope_ci_lower": None,
            "slope_ci_upper": None,
            "intercept_ci_lower": None,
            "intercept_ci_upper": None,
            "p_slope_lt_1": None,
            "n_bootstrap": 0,
            "stratified": strata is not None,
            "warning": (f"minority-class share below "
                        f"{SEPARATION_MINORITY_THRESHOLD:.0%} — "
                        "logistic MLE is unstable / diverges; "
                        "slope omitted (use mean overpricing pp instead)"),
        }

    point_slope, point_int = fit_log_odds_slope(prices, outcomes)

    if not np.isfinite(point_slope):
        return {
            "slope": None,
            "intercept": None,
            "slope_ci_lower": None,
            "slope_ci_upper": None,
            "intercept_ci_lower": None,
            "intercept_ci_upper": None,
            "p_slope_lt_1": None,
            "n_bootstrap": 0,
            "stratified": strata is not None,
        }

    rng = np.random.default_rng(seed)
    slopes, intercepts = [], []

    if strata is None:
        idx_pool = np.arange(n)
    else:
        strata = np.asarray(strata)
        unique_strata = np.unique(strata)
        stratum_idx = {s: np.where(strata == s)[0] for s in unique_strata}

    for _ in range(b):
        if strata is None:
            sel = rng.integers(0, n, n)
        else:
            sel_parts = [
                rng.choice(stratum_idx[s], size=len(stratum_idx[s]),
                           replace=True)
                for s in unique_strata
            ]
            sel = np.concatenate(sel_parts)
        s, i = fit_log_odds_slope(prices[sel], outcomes[sel])
        if np.isfinite(s):
            slopes.append(s)
            intercepts.append(i)

    if not slopes:
        return {
            "slope": round(point_slope, 5),
            "intercept": round(point_int, 5),
            "slope_ci_lower": None,
            "slope_ci_upper": None,
            "intercept_ci_lower": None,
            "intercept_ci_upper": None,
            "p_slope_lt_1": None,
            "n_bootstrap": 0,
            "stratified": strata is not None,
        }

    slopes_arr = np.asarray(slopes)
    ints_arr = np.asarray(intercepts)
    slope_lo = float(np.percentile(slopes_arr, 2.5))
    slope_hi = float(np.percentile(slopes_arr, 97.5))
    return {
        "slope": round(point_slope, 5),
        "intercept": round(point_int, 5),
        "slope_ci_lower": round(slope_lo, 5),
        "slope_ci_upper": round(slope_hi, 5),
        "intercept_ci_lower": round(float(np.percentile(ints_arr, 2.5)), 5),
        "intercept_ci_upper": round(float(np.percentile(ints_arr, 97.5)), 5),
        "p_slope_lt_1": round(float((slopes_arr < 1).mean()), 4),
        "n_bootstrap": int(len(slopes)),
        "stratified": strata is not None,
        # CI width > 2 is wide for a calibration slope (point estimates
        # typically lie in [0.5, 2]). Treat as a reliability flag for
        # downstream consumers.
        "ci_wide": bool((slope_hi - slope_lo) > 2.0),
    }


def overpricing_pp(prices, outcomes):
    """
    Mean overpricing in percentage points: mean(price - resolved_yes) * 100.
    Positive  => crowd assigned more probability than the outcome rate
                 (overpriced).
    Negative  => crowd assigned less probability than the outcome rate
                 (underpriced).
    """
    if len(prices) == 0:
        return None
    return round(float(np.mean(np.asarray(prices) - np.asarray(outcomes))) * 100, 4)


def tail_buckets(df, bin_edges):
    """Build calibration buckets at custom edges."""
    out = []
    p = df["final_yes_price"].values
    y = df["resolved_yes"].values
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        # Right-open bin, except last bin includes 1.0
        if hi == bin_edges[-1]:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n > 0:
            out.append({
                "bin_lower": round(float(lo), 4),
                "bin_upper": round(float(hi), 4),
                "bin_center": round(float((lo + hi) / 2), 4),
                "mean_predicted": round(float(p[mask].mean()), 5),
                "mean_actual": round(float(y[mask].mean()), 5),
                "n": n,
            })
        else:
            out.append({
                "bin_lower": round(float(lo), 4),
                "bin_upper": round(float(hi), 4),
                "bin_center": round(float((lo + hi) / 2), 4),
                "mean_predicted": None,
                "mean_actual": None,
                "n": 0,
            })
    return out


def market_record(row):
    """Compact serialisable record for hall-of-shame / hidden-gems."""
    slug = row.get("slug") or ""
    return {
        "market_id": (str(row["market_id"])
                      if pd.notna(row["market_id"]) else None),
        "question": row["question"],
        "slug": slug,
        "url": POLY_URL.format(slug=slug) if slug else None,
        "category": row["category"],
        "volume": round(float(row["volume"]), 2),
        "final_yes_price": round(float(row["final_yes_price"]), 5),
        "resolved_yes": int(row["resolved_yes"]),
        "end_date": row.get("end_date"),
    }


# ─── Step 1: load and prepare ───────────────────────────────────────────────


def load_dataset():
    print("=" * 70)
    print("STEP 1: Load Analysis 1 dataset")
    print("=" * 70)

    csv_path = DATA_DIR / "markets_clean.csv"
    if not csv_path.exists():
        print(f"  FATAL: {csv_path} not found. Run Analysis 1 first.")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"  Loaded {len(df)} rows from {csv_path.name}")

    n_total = len(df)
    df = df[df["final_yes_price"].notna()].copy()
    print(f"  With CLOB price: {len(df)}/{n_total}")

    df["final_yes_price"] = df["final_yes_price"].astype(float)
    df["resolved_yes"] = df["resolved_yes"].astype(int)
    df["volume"] = df["volume"].astype(float)
    if "category_analysis" not in df.columns:
        df["category_analysis"] = df["category"]

    print(f"  Base rate: {df['resolved_yes'].mean():.4f} "
          f"({df['resolved_yes'].sum()} YES / {len(df)})")
    return df


# ─── Step 2: full + tail log-odds slope ─────────────────────────────────────


def analyse_longshot(df):
    print("\n" + "=" * 70)
    print("STEP 2: Tail calibration & log-odds regression")
    print("=" * 70)

    longshots = df[df["final_yes_price"] <= LONGSHOT_MAX].copy()
    favorites = df[df["final_yes_price"] >= FAVORITE_MIN].copy()
    print(f"  Longshots (p <= {LONGSHOT_MAX}): n={len(longshots)}, "
          f"YES={int(longshots['resolved_yes'].sum())}")
    print(f"  Favorites (p >= {FAVORITE_MIN}): n={len(favorites)}, "
          f"YES={int(favorites['resolved_yes'].sum())}")

    # Tail buckets — finer grain than the 0.05 main calibration plot
    longshot_edges = [0.00, 0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15]
    favorite_edges = [0.85, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99, 1.00]
    longshot_bk = tail_buckets(longshots, longshot_edges)
    favorite_bk = tail_buckets(favorites, favorite_edges)

    # Log-odds regressions (with bootstrap CIs)
    full_lo = bootstrap_log_odds(
        df["final_yes_price"].values,
        df["resolved_yes"].values,
    )
    full_lo_strat = bootstrap_log_odds(
        df["final_yes_price"].values,
        df["resolved_yes"].values,
        strata=df["category_analysis"].values,
    )
    long_lo = bootstrap_log_odds(
        longshots["final_yes_price"].values,
        longshots["resolved_yes"].values,
    )
    fav_lo = bootstrap_log_odds(
        favorites["final_yes_price"].values,
        favorites["resolved_yes"].values,
    )

    print(f"  Full-sample slope: {full_lo['slope']} "
          f"95% CI [{full_lo['slope_ci_lower']}, {full_lo['slope_ci_upper']}]")
    print(f"  Full-sample slope (cat-stratified bootstrap): "
          f"{full_lo_strat['slope']} "
          f"CI [{full_lo_strat['slope_ci_lower']}, "
          f"{full_lo_strat['slope_ci_upper']}]")

    longshot_pp = overpricing_pp(
        longshots["final_yes_price"].values,
        longshots["resolved_yes"].values,
    )
    favorite_pp = overpricing_pp(
        favorites["final_yes_price"].values,
        favorites["resolved_yes"].values,
    )
    full_pp = overpricing_pp(
        df["final_yes_price"].values,
        df["resolved_yes"].values,
    )
    print(f"  Mean overpricing pp — longshots: {longshot_pp}, "
          f"favorites: {favorite_pp}, full: {full_pp}")

    return {
        "thresholds": {
            "longshot_max": LONGSHOT_MAX,
            "favorite_min": FAVORITE_MIN,
            "log_odds_clip": [CLIP_LOW, CLIP_HIGH],
        },
        "full_sample": {
            "n_markets": int(len(df)),
            "n_resolved_yes": int(df["resolved_yes"].sum()),
            "base_rate": round(float(df["resolved_yes"].mean()), 5),
            "mean_overpricing_pp": full_pp,
            "log_odds": full_lo,
            "log_odds_stratified": full_lo_strat,
        },
        "longshots": {
            "definition": f"final_yes_price <= {LONGSHOT_MAX}",
            "n_markets": int(len(longshots)),
            "n_resolved_yes": int(longshots["resolved_yes"].sum()),
            "base_rate": (round(float(longshots["resolved_yes"].mean()), 5)
                          if len(longshots) else None),
            "mean_overpricing_pp": longshot_pp,
            "log_odds": long_lo,
            "calibration_buckets": longshot_bk,
        },
        "favorites": {
            "definition": f"final_yes_price >= {FAVORITE_MIN}",
            "n_markets": int(len(favorites)),
            "n_resolved_yes": int(favorites["resolved_yes"].sum()),
            "base_rate": (round(float(favorites["resolved_yes"].mean()), 5)
                          if len(favorites) else None),
            "mean_overpricing_pp": favorite_pp,
            "log_odds": fav_lo,
            "calibration_buckets": favorite_bk,
        },
    }


# ─── Step 3: volume stratification ──────────────────────────────────────────


def analyse_volume(df):
    print("\n" + "=" * 70)
    print("STEP 3: Volume stratification")
    print("=" * 70)

    median_v = float(df["volume"].median())
    print(f"  Median volume: ${median_v:,.2f}")

    low = df[df["volume"] <= median_v].copy()
    high = df[df["volume"] > median_v].copy()
    print(f"  Low-vol (<= median):  n={len(low)}, "
          f"longshots={int((low['final_yes_price'] <= LONGSHOT_MAX).sum())}")
    print(f"  High-vol (> median):  n={len(high)}, "
          f"longshots={int((high['final_yes_price'] <= LONGSHOT_MAX).sum())}")

    median_split = {
        "median_volume": round(median_v, 2),
        "tiers": {},
    }
    for tier_name, tier_df in [("low", low), ("high", high)]:
        ls = tier_df[tier_df["final_yes_price"] <= LONGSHOT_MAX]
        fav = tier_df[tier_df["final_yes_price"] >= FAVORITE_MIN]
        full_lo = bootstrap_log_odds(
            tier_df["final_yes_price"].values,
            tier_df["resolved_yes"].values,
        )
        long_lo = bootstrap_log_odds(
            ls["final_yes_price"].values,
            ls["resolved_yes"].values,
        )
        median_split["tiers"][tier_name] = {
            "n_markets": int(len(tier_df)),
            "volume_range": [
                round(float(tier_df["volume"].min()), 2),
                round(float(tier_df["volume"].max()), 2),
            ],
            "full_log_odds": full_lo,
            "full_overpricing_pp": overpricing_pp(
                tier_df["final_yes_price"].values,
                tier_df["resolved_yes"].values,
            ),
            "longshot": {
                "n_markets": int(len(ls)),
                "n_resolved_yes": int(ls["resolved_yes"].sum()),
                "mean_overpricing_pp": overpricing_pp(
                    ls["final_yes_price"].values,
                    ls["resolved_yes"].values,
                ),
                "log_odds": long_lo,
            },
            "favorite": {
                "n_markets": int(len(fav)),
                "n_resolved_yes": int(fav["resolved_yes"].sum()),
                "mean_overpricing_pp": overpricing_pp(
                    fav["final_yes_price"].values,
                    fav["resolved_yes"].values,
                ),
            },
        }

    # Tertile robustness check
    tert, tert_edges = pd.qcut(
        df["volume"], q=3, labels=["low", "mid", "high"],
        duplicates="drop", retbins=True,
    )
    tertile_split = {
        "thresholds": {
            "low_upper": round(float(tert_edges[1]), 2),
            "mid_upper": round(float(tert_edges[2]), 2),
        },
        "tiers": {},
    }
    for label in ["low", "mid", "high"]:
        tier_df = df[tert == label]
        if tier_df.empty:
            continue
        ls = tier_df[tier_df["final_yes_price"] <= LONGSHOT_MAX]
        long_lo = bootstrap_log_odds(
            ls["final_yes_price"].values,
            ls["resolved_yes"].values,
        )
        tertile_split["tiers"][label] = {
            "n_markets": int(len(tier_df)),
            "volume_range": [
                round(float(tier_df["volume"].min()), 2),
                round(float(tier_df["volume"].max()), 2),
            ],
            "longshot": {
                "n_markets": int(len(ls)),
                "n_resolved_yes": int(ls["resolved_yes"].sum()),
                "mean_overpricing_pp": overpricing_pp(
                    ls["final_yes_price"].values,
                    ls["resolved_yes"].values,
                ),
                "log_odds": long_lo,
            },
        }

    print("  Median-split tiers:")
    for t, d in median_split["tiers"].items():
        ls = d["longshot"]
        full = d["full_log_odds"]
        print(f"    {t:5s}: n={d['n_markets']:4d}  full_slope="
              f"{full['slope']}  longshot_pp={ls['mean_overpricing_pp']}")

    return {"median_split": median_split, "tertile_split": tertile_split}


# ─── Step 4: per-category longshot ──────────────────────────────────────────


def analyse_categories(df):
    print("\n" + "=" * 70)
    print("STEP 4: Per-category longshot bias")
    print("=" * 70)

    by_cat = {}
    for cat in sorted(df["category_analysis"].unique()):
        cat_df = df[df["category_analysis"] == cat]
        ls = cat_df[cat_df["final_yes_price"] <= LONGSHOT_MAX]
        n_ls = len(ls)
        n_yes = int(ls["resolved_yes"].sum()) if n_ls else 0
        opp = overpricing_pp(
            ls["final_yes_price"].values,
            ls["resolved_yes"].values,
        ) if n_ls else None

        if n_ls >= MIN_CATEGORY_LONGSHOT_N:
            lo = bootstrap_log_odds(
                ls["final_yes_price"].values,
                ls["resolved_yes"].values,
            )
            full_lo = bootstrap_log_odds(
                cat_df["final_yes_price"].values,
                cat_df["resolved_yes"].values,
            )
            slope_status = "fitted"
        else:
            lo = None
            full_lo = None
            slope_status = (f"n<{MIN_CATEGORY_LONGSHOT_N} — slope omitted, "
                            f"only mean overpricing reported")

        by_cat[cat] = {
            "n_markets_total": int(len(cat_df)),
            "n_longshots": int(n_ls),
            "n_longshots_resolved_yes": n_yes,
            "longshot_base_rate": (round(n_yes / n_ls, 4)
                                   if n_ls else None),
            "longshot_overpricing_pp": opp,
            "longshot_log_odds": lo,
            "full_log_odds": full_lo,
            "slope_status": slope_status,
        }

        print(f"  {cat:15s} total={len(cat_df):4d}  "
              f"longshots={n_ls:3d}  YES={n_yes:2d}  "
              f"overpricing_pp={opp}  "
              f"slope={'-' if lo is None else lo['slope']}")

    return {
        "min_longshot_n_for_slope": MIN_CATEGORY_LONGSHOT_N,
        "categories": by_cat,
    }


# ─── Step 5: hall of shame & hidden gems ────────────────────────────────────


def hall_of_shame(df, top_n=25):
    print("\n" + "=" * 70)
    print(f"STEP 5: Hall of Shame (top {top_n} most confidently wrong)")
    print("=" * 70)

    df = df.copy()
    df["miss_pp"] = (df["final_yes_price"] - df["resolved_yes"]).abs() * 100
    df = df.sort_values("miss_pp", ascending=False).head(top_n)
    records = [market_record(r) for _, r in df.iterrows()]
    for i, r in enumerate(records[:10], 1):
        miss = (r["final_yes_price"] - r["resolved_yes"]) * 100
        print(f"  {i:2d}. ({miss:+6.1f}pp) [{r['category']:11s}] "
              f"{r['question'][:75]}")
    return records


def hidden_gems(df, top_n=15):
    print("\n" + "=" * 70)
    print(f"STEP 6: Hidden Gems (top {top_n} longshots that resolved YES)")
    print("=" * 70)

    gems = df[
        (df["final_yes_price"] <= HIDDEN_GEM_MAX)
        & (df["resolved_yes"] == 1)
    ].copy()
    print(f"  Eligible (priced <= {HIDDEN_GEM_MAX}, resolved YES): "
          f"{len(gems)}")
    gems = gems.sort_values("final_yes_price", ascending=True).head(top_n)
    records = [market_record(r) for _, r in gems.iterrows()]
    for i, r in enumerate(records[:10], 1):
        print(f"  {i:2d}. (priced {r['final_yes_price']:.3f}) "
              f"[{r['category']:11s}] {r['question'][:70]}")
    return records


# ─── Save ───────────────────────────────────────────────────────────────────


def common_meta(extra=None):
    base = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": "Analysis 1 output: data/markets_clean.csv "
                  "(stratified sample of resolved Polymarket markets, "
                  "final_yes_price = CLOB second-to-last 12hr tick)",
        "methodology": {
            "longshot_threshold": LONGSHOT_MAX,
            "favorite_threshold": FAVORITE_MIN,
            "log_odds_regression": (
                "logistic regression of resolved_yes on "
                "log(p/(1-p)); prices clipped to "
                f"[{CLIP_LOW}, {CLIP_HIGH}]; unpenalised MLE "
                "(sklearn LogisticRegression with C=1e9). Slope is "
                "reported as null when the subset is near-separated "
                f"(minority class < {SEPARATION_MINORITY_THRESHOLD:.0%}) "
                "because the MLE diverges in that regime; use mean "
                "overpricing pp instead."
            ),
            "bootstrap": (
                f"market-level resampling, B={BOOTSTRAP_B}, "
                f"seed={BOOTSTRAP_SEED}; CIs reported as 2.5%/97.5%. "
                "Independence assumption may understate uncertainty for "
                "markets with correlated event structure (e.g. multiple "
                "markets on the same election)."
            ),
            "interpretation": {
                "slope_eq_1_intercept_eq_0": "perfect calibration",
                "slope_lt_1": ("overconfident — prices more extreme "
                               "than realised frequencies"),
                "slope_gt_1": ("underconfident — prices compressed "
                               "toward 50% (classic favorite-longshot "
                               "pattern direction)"),
            },
            "overpricing_pp": (
                "mean(final_yes_price - resolved_yes) * 100. Positive "
                "= crowd assigned more probability than the realised rate."
            ),
        },
        "language_note": (
            "Phrasing follows POLYMARKET_PROJECT_PLAN.md \"Future "
            "Improvements\" guidance: 'consistent with', 'appears', "
            "'one possible interpretation' — not 'proves' or "
            "'demonstrates'."
        ),
    }
    if extra:
        base.update(extra)
    return base


def save(payload, name):
    p = OUTPUT_DIR / name
    with open(p, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  {p} ({p.stat().st_size / 1024:.1f} KB)")


# ─── Main ───────────────────────────────────────────────────────────────────


def main():
    print("\n" + "█" * 70)
    print("  ANALYSIS 2: LONGSHOT BIAS (DEEP DIVE 1)")
    print("█" * 70)
    t0 = datetime.now(timezone.utc)
    print(f"  Started: {t0.isoformat()}")

    df = load_dataset()

    longshot = analyse_longshot(df)
    volume = analyse_volume(df)
    categories = analyse_categories(df)
    hos = hall_of_shame(df)
    gems = hidden_gems(df)

    print("\n" + "=" * 70)
    print("STEP 7: Save outputs")
    print("=" * 70)

    save(common_meta({
        "description": ("Longshot bias: tail calibration buckets, "
                        "mean overpricing, and log-odds slope with "
                        "bootstrap CIs (full sample, longshot subset, "
                        "favorite subset)"),
        **longshot,
    }), "longshot_data.json")

    save(common_meta({
        "description": ("Volume stratification of longshot bias. "
                        "Median split is the primary; tertile split "
                        "is a robustness check."),
        **volume,
    }), "longshot_volume.json")

    save(common_meta({
        "description": ("Per-category longshot bias. Slope only fitted "
                        f"when n_longshots >= "
                        f"{MIN_CATEGORY_LONGSHOT_N}; otherwise only "
                        "mean overpricing is reported."),
        **categories,
    }), "longshot_category.json")

    save({
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": ("Top 25 markets where the final crowd price "
                        "diverged most from the realised outcome. "
                        "Sorted by |final_yes_price - resolved_yes|."),
        "n_total_with_prices": int(len(df)),
        "markets": hos,
    }, "hall_of_shame.json")

    save({
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": (f"Top 15 markets priced <= {HIDDEN_GEM_MAX} "
                        "that resolved YES. Sorted ascending by final "
                        "price (most surprising first)."),
        "n_eligible": int(((df["final_yes_price"] <= HIDDEN_GEM_MAX)
                           & (df["resolved_yes"] == 1)).sum()),
        "markets": gems,
    }, "hidden_gems.json")

    t1 = datetime.now(timezone.utc)
    print(f"\n  Completed: {t1.isoformat()} "
          f"({(t1 - t0).total_seconds():.1f}s)")
    print("█" * 70)


if __name__ == "__main__":
    main()
