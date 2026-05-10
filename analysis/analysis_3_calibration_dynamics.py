"""
Analysis 3 (Deep Dive 2): Calibration Dynamics
===============================================
From POLYMARKET_PROJECT_PLAN.md, "Analysis 3 (Deep Dive 2): Calibration
Dynamics".

Question: Does crowd calibration improve as a market approaches
          resolution? Does the longshot bias change over a market's
          lifetime? Are there category-specific convergence patterns?

Pipeline:
  1. Load Analysis 1's `data/markets_clean.csv` (1,000-market
     stratified sample; 806 with CLOB token IDs and final prices).
  2. Filter to markets with duration >= 5 days (the plan's
     12hr-fidelity floor consequence — the 0.95 snapshot is only
     meaningful when 5% of lifetime exceeds ~6 hours).
  3. Fetch full CLOB price history per market via
     `GET /prices-history?market=TOKEN&interval=max&fidelity=720`.
     Cache raw responses to `data/raw_history/{market_id}.json` so
     re-runs skip already-fetched markets (per the plan's failure-mode
     mitigation and PLAN_DEVIATIONS_AND_PITFALLS.md).
  4. For each market with >= 4 history observations, compute
     snapshot prices at relative-time fractions
     [0.10, 0.25, 0.50, 0.75, 0.90, 0.95] of (close - open).
  5. At each snapshot:
       - calibration buckets (0.05-width)
       - Brier score and BSS (vs Var(resolved_yes) baseline)
       - log-odds (calibration) slope + 95% bootstrap CI
       - mean overpricing pp (full + longshot subset)
  6. Per category (n >= 20 in dynamics-eligible sample), repeat the
     per-snapshot stack.
  7. Save dynamics_data.json and dynamics_category.json.

Methodology notes:
  - We import the Analysis 2 helpers (`bootstrap_log_odds`,
    `fit_log_odds_slope`, `has_separation_issue`) so the calibration-
    slope machinery is identical across analyses (same near-separation
    guard, same `ci_wide` flag, same unpenalised MLE).
  - For each snapshot, the "actual" rate is `resolved_yes` (the same
    final outcome). The "predicted" is the most-recent CLOB tick at
    or before the snapshot timestamp.
  - We avoid the second-to-last-tick contamination guard from Analysis
    1 because snapshots are *strictly inside* the market lifetime, not
    at the very end. Settlement-pinning would only bleed into the 0.95
    snapshot for markets that resolved early; we deal with that case
    by reporting per-snapshot n alongside metrics so any dropoff is
    visible.
"""

import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.exceptions import ConvergenceWarning

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")

# Reuse Analysis 2's calibration-slope machinery so both deep dives
# apply the same statistical guards (near-separation handling, ci_wide
# flag, unpenalised MLE via C=1e9).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_2_longshot_bias import (  # noqa: E402
    LONGSHOT_MAX,
    SEPARATION_MINORITY_THRESHOLD,
    bootstrap_log_odds,
    overpricing_pp,
)

CLOB_API = "https://clob.polymarket.com"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_HISTORY_DIR = DATA_DIR / "raw_history"
OUTPUT_DIR = ROOT / "output"
RAW_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_PCTS = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
MIN_DURATION_DAYS = 5
MIN_HISTORY_OBS = 4
MIN_CATEGORY_N = 20
BIN_WIDTH = 0.05

POLITE_DELAY_S = 0.25
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2  # 2s, 4s, 8s, 16s, 32s


# ─── HTTP fetch with disk cache ─────────────────────────────────────────────


def fetch_history(token_id, market_id):
    """
    Fetch CLOB price history for a market's YES token, caching raw JSON
    to data/raw_history/{market_id}.json. Returns the parsed JSON dict
    on success, None on failure. Re-runs skip already-cached markets.
    """
    cache_path = RAW_HISTORY_DIR / f"{market_id}.json"
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            cache_path.unlink(missing_ok=True)  # corrupt — refetch

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                f"{CLOB_API}/prices-history",
                params={
                    "market": token_id,
                    "interval": "max",
                    "fidelity": 720,  # 12-hour ticks; required for
                                      # closed markets per GH#216
                },
                timeout=30,
            )
            if resp.status_code == 429:
                wait = (RETRY_BACKOFF_BASE ** (attempt + 1)
                        + np.random.uniform(0, 1))
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403):
                print(f"  FATAL: CLOB auth error {resp.status_code} on "
                      f"market {market_id}")
                return None
            resp.raise_for_status()
            data = resp.json()
            with open(cache_path, "w") as f:
                json.dump(data, f)
            return data
        except requests.exceptions.RequestException as e:
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            print(f"    [retry {attempt+1}/{MAX_RETRIES}] {e} — {wait}s")
            time.sleep(wait)
    return None


# ─── Snapshot extraction ────────────────────────────────────────────────────


def get_snapshot_price(history, open_ts, close_ts, pct):
    """
    Most-recent CLOB price at or before the relative-time target
    timestamp. Returns None if no observation exists before the target.
    """
    target = open_ts + pct * (close_ts - open_ts)
    eligible = [(t, p) for t, p in history if t <= target]
    if not eligible:
        return None
    return float(eligible[-1][1])


# ─── Step 1: load and filter ────────────────────────────────────────────────


def load_dynamics_sample():
    print("=" * 70)
    print("STEP 1: Load + filter dynamics-eligible markets")
    print("=" * 70)

    csv_path = DATA_DIR / "markets_clean.csv"
    if not csv_path.exists():
        print(f"  FATAL: {csv_path} not found. Run Analysis 1 first.")
        sys.exit(1)

    # yes_token_id is a 77-digit integer that float() truncates; force
    # string dtype so we keep all digits.
    df = pd.read_csv(csv_path, dtype={"yes_token_id": str})
    print(f"  Loaded {len(df)} rows from markets_clean.csv")

    n0 = len(df)
    df = df[df["yes_token_id"].notna() & (df["yes_token_id"] != "nan")].copy()
    print(f"  With yes_token_id: {len(df)} ({n0 - len(df)} dropped)")

    df["open_dt"] = pd.to_datetime(df["start_date"], errors="coerce",
                                   utc=True)
    df["close_dt"] = pd.to_datetime(df["end_date"], errors="coerce",
                                    utc=True)
    df = df[df["open_dt"].notna() & df["close_dt"].notna()].copy()
    df["duration_days"] = (
        (df["close_dt"] - df["open_dt"]).dt.total_seconds() / 86400
    )
    print(f"  With valid open/close dates: {len(df)}")

    df = df[df["duration_days"] >= MIN_DURATION_DAYS].copy()
    print(f"  With duration >= {MIN_DURATION_DAYS} days: {len(df)} "
          "(dynamics-eligible)")

    # pandas 3.0 datetime arrays may use unit='us' or 'ns', so dividing
    # an int64 cast by 10**9 is fragile. Use the per-row .timestamp()
    # accessor which always returns seconds since epoch.
    df["open_ts"] = df["open_dt"].apply(lambda x: int(x.timestamp()))
    df["close_ts"] = df["close_dt"].apply(lambda x: int(x.timestamp()))

    return df


# ─── Step 2: bulk CLOB fetch ────────────────────────────────────────────────


def fetch_all_histories(df):
    print("\n" + "=" * 70)
    print(f"STEP 2: Fetch CLOB price history "
          f"({len(df)} markets, fidelity=720)")
    print("=" * 70)

    cached_at_start = sum(
        1 for mid in df["market_id"]
        if (RAW_HISTORY_DIR / f"{mid}.json").exists()
    )
    print(f"  Already cached on disk: {cached_at_start}/{len(df)}")
    print(f"  To fetch: {len(df) - cached_at_start} (then "
          f"~{(len(df) - cached_at_start) * POLITE_DELAY_S / 60:.1f} min "
          "with polite delay)")

    histories = {}
    new_fetches = 0
    cache_hits = 0
    failures = 0

    for i, row in enumerate(df.itertuples(), start=1):
        mid = row.market_id
        was_cached = (RAW_HISTORY_DIR / f"{mid}.json").exists()
        data = fetch_history(row.yes_token_id, mid)
        if data is None:
            failures += 1
            continue
        h = data.get("history") or []
        histories[mid] = [(int(p["t"]), float(p["p"])) for p in h]
        if was_cached:
            cache_hits += 1
        else:
            new_fetches += 1
            time.sleep(POLITE_DELAY_S)

        if i % 100 == 0:
            print(f"  Progress: {i}/{len(df)}  "
                  f"(cache_hits={cache_hits}, new={new_fetches}, "
                  f"fail={failures})")

    print(f"\n  Done: {len(histories)} histories collected "
          f"({cache_hits} from cache, {new_fetches} new fetches, "
          f"{failures} failures)")

    n_obs = pd.Series({mid: len(h) for mid, h in histories.items()})
    df = df.copy()
    df["history"] = df["market_id"].map(histories)
    df["n_history_obs"] = df["market_id"].map(n_obs).fillna(0).astype(int)

    qualifying = df[df["n_history_obs"] >= MIN_HISTORY_OBS].copy()
    print(f"  With >= {MIN_HISTORY_OBS} observations: "
          f"{len(qualifying)}/{len(df)}")
    return qualifying


# ─── Step 3: build snapshot table ───────────────────────────────────────────


def build_snapshot_table(df):
    print("\n" + "=" * 70)
    print(f"STEP 3: Compute snapshot prices at "
          f"{[f'{p:.2f}' for p in SNAPSHOT_PCTS]}")
    print("=" * 70)

    rows = []
    for r in df.itertuples():
        rec = {
            "market_id": r.market_id,
            "category": r.category,
            "category_analysis": getattr(r, "category_analysis",
                                          r.category),
            "volume": r.volume,
            "duration_days": r.duration_days,
            "n_history_obs": r.n_history_obs,
            "resolved_yes": r.resolved_yes,
            "final_yes_price": r.final_yes_price,
        }
        for pct in SNAPSHOT_PCTS:
            rec[f"snap_{int(pct*100):02d}"] = get_snapshot_price(
                r.history, r.open_ts, r.close_ts, pct
            )
        rows.append(rec)

    snap_df = pd.DataFrame(rows)

    print("  Snapshot coverage (markets with non-null price):")
    for pct in SNAPSHOT_PCTS:
        col = f"snap_{int(pct*100):02d}"
        n = snap_df[col].notna().sum()
        print(f"    {pct:.2f}: {n}/{len(snap_df)}  ({n/len(snap_df)*100:.1f}%)")

    return snap_df


# ─── Step 4: per-snapshot calibration ───────────────────────────────────────


def calibration_buckets(prices, outcomes, width=BIN_WIDTH):
    bins = np.arange(0, 1.0 + width / 2, width)
    centers = (bins[:-1] + bins[1:]) / 2
    p = np.asarray(prices, dtype=float)
    y = np.asarray(outcomes, dtype=int)
    idx = np.clip(np.digitize(p, bins) - 1, 0, len(centers) - 1)
    out = []
    for i, c in enumerate(centers):
        mask = idx == i
        n = int(mask.sum())
        out.append({
            "bin_lower": round(float(bins[i]), 3),
            "bin_upper": round(float(bins[i + 1]), 3),
            "bin_center": round(float(c), 3),
            "mean_predicted": (round(float(p[mask].mean()), 5)
                              if n else None),
            "mean_actual": (round(float(y[mask].mean()), 5)
                            if n else None),
            "n": n,
        })
    return out


def snapshot_metrics(snap_df, snap_col, label, min_n=30):
    """
    Compute the full calibration stack at a single snapshot column.
    `min_n` is the minimum number of markets with a non-null snapshot
    price required to fit any metrics (default 30 for the full-sample
    pass; per-category breakouts use 20 to match the plan's category
    threshold).
    """
    sub = snap_df.dropna(subset=[snap_col]).copy()
    n = len(sub)
    if n < min_n:
        return {
            "label": label,
            "n_markets": n,
            "skipped": (f"n < {min_n} markets with a price at this "
                        "snapshot"),
        }

    pred = sub[snap_col].values.astype(float)
    actual = sub["resolved_yes"].values.astype(int)

    bs = float(np.mean((pred - actual) ** 2))
    bs_base = float(np.var(actual))
    bss = (1 - bs / bs_base) if bs_base > 0 else None

    lo = bootstrap_log_odds(pred, actual)

    ls_mask = pred <= LONGSHOT_MAX
    ls_n = int(ls_mask.sum())
    ls_yes = int(actual[ls_mask].sum()) if ls_n else 0
    ls_pp = (overpricing_pp(pred[ls_mask], actual[ls_mask])
             if ls_n else None)

    return {
        "label": label,
        "n_markets": n,
        "n_resolved_yes": int(actual.sum()),
        "base_rate": round(float(actual.mean()), 5),
        "brier_score": round(bs, 6),
        "brier_score_baseline": round(bs_base, 6),
        "bss": round(bss, 6) if bss is not None else None,
        "log_odds": lo,
        "mean_overpricing_pp": overpricing_pp(pred, actual),
        "longshot": {
            "definition": f"snapshot_price <= {LONGSHOT_MAX}",
            "n_markets": ls_n,
            "n_resolved_yes": ls_yes,
            "mean_overpricing_pp": ls_pp,
        },
        "calibration_buckets": calibration_buckets(pred, actual),
    }


def per_snapshot_full_sample(snap_df):
    print("\n" + "=" * 70)
    print("STEP 4: Per-snapshot calibration (full dynamics sample)")
    print("=" * 70)

    final_metrics = snapshot_metrics(snap_df, "final_yes_price",
                                     "final (Analysis 1 sanity check)")
    print(f"  final            n={final_metrics.get('n_markets')}  "
          f"BSS={final_metrics.get('bss')}  "
          f"slope={final_metrics.get('log_odds', {}).get('slope')}")

    snapshots = {}
    for pct in SNAPSHOT_PCTS:
        col = f"snap_{int(pct*100):02d}"
        m = snapshot_metrics(snap_df, col, f"pct_{int(pct*100):02d}")
        snapshots[f"{pct:.2f}"] = m
        if "skipped" in m:
            print(f"  pct={pct:.2f}        {m['skipped']}")
            continue
        slope = m["log_odds"]["slope"]
        ci = (m["log_odds"]["slope_ci_lower"],
              m["log_odds"]["slope_ci_upper"])
        print(f"  pct={pct:.2f}  n={m['n_markets']:4d}  "
              f"BSS={m['bss']:.4f}  slope={slope}  "
              f"CI=[{ci[0]}, {ci[1]}]  "
              f"longshot_pp={m['longshot']['mean_overpricing_pp']}")

    return final_metrics, snapshots


# ─── Step 5: per-category dynamics ──────────────────────────────────────────


def per_category_dynamics(snap_df):
    print("\n" + "=" * 70)
    print(f"STEP 5: Per-category dynamics (n >= {MIN_CATEGORY_N})")
    print("=" * 70)

    out = {}
    for cat in sorted(snap_df["category_analysis"].unique()):
        cat_df = snap_df[snap_df["category_analysis"] == cat]
        if len(cat_df) < MIN_CATEGORY_N:
            print(f"  {cat:15s}  n={len(cat_df):4d}  SKIPPED "
                  f"(< {MIN_CATEGORY_N})")
            continue

        cat_snapshots = {}
        for pct in SNAPSHOT_PCTS:
            col = f"snap_{int(pct*100):02d}"
            cat_snapshots[f"{pct:.2f}"] = snapshot_metrics(
                cat_df, col, f"{cat}_pct_{int(pct*100):02d}",
                min_n=MIN_CATEGORY_N,
            )
        out[cat] = {
            "n_markets_in_dynamics_sample": int(len(cat_df)),
            "snapshots": cat_snapshots,
        }
        # Console: show slope trajectory (skipped → "—")
        traj = []
        for pct in SNAPSHOT_PCTS:
            m = cat_snapshots[f"{pct:.2f}"]
            if "skipped" in m or m["log_odds"]["slope"] is None:
                traj.append("    —")
            else:
                traj.append(f"{m['log_odds']['slope']:6.2f}")
        print(f"  {cat:15s}  n={len(cat_df):4d}  slopes "
              f"[10/25/50/75/90/95%]: {' '.join(traj)}")

    return out


# ─── Save ───────────────────────────────────────────────────────────────────


def common_meta(extra=None):
    base = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": ("Analysis 1 stratified sample "
                   "(data/markets_clean.csv) + CLOB price history "
                   "fetched per market and cached to "
                   "data/raw_history/{market_id}.json"),
        "methodology": {
            "snapshot_pcts": SNAPSHOT_PCTS,
            "snapshot_definition": (
                "fraction of (close_ts - open_ts) elapsed; price at "
                "each snapshot is the most-recent CLOB tick at or "
                "before the target timestamp"
            ),
            "min_duration_days": MIN_DURATION_DAYS,
            "min_history_obs": MIN_HISTORY_OBS,
            "min_duration_rationale": (
                "CLOB returns >= 12hr granularity for closed markets "
                "(GitHub issue #216 / py-clob-client). Snapshots at "
                "0.95 of lifetime are only meaningful when 5% of the "
                "market lifetime exceeds ~6hr — i.e., total duration "
                ">= 5 days."
            ),
            "calibration_bin_width": BIN_WIDTH,
            "bss_formula": "1 - mean((p - y)^2) / Var(y)",
            "bss_caveat": (
                "Not strictly proper as a skill score; asymptotically "
                "proper with large samples (Murphy 1973). Per-snapshot "
                "BSS denominators differ slightly because Var(y) is "
                "computed on the markets that have a price at that "
                "snapshot."
            ),
            "log_odds_regression": (
                "logistic regression of resolved_yes on "
                "log(p / (1 - p)); prices clipped to [0.01, 0.99]; "
                "unpenalised MLE (LogisticRegression(C=1e9)). Slope "
                "reported as null when minority-class share < "
                f"{SEPARATION_MINORITY_THRESHOLD:.0%} (MLE diverges)."
            ),
            "bootstrap": (
                "B=500, market-level resampling with replacement, "
                "seed=42; 95% CI as the 2.5/97.5 percentiles. "
                "Same machinery as Analysis 2."
            ),
            "language_note": (
                "Phrasing follows POLYMARKET_PROJECT_PLAN.md "
                "\"Future Improvements\" guidance: 'consistent with', "
                "'appears', 'one possible interpretation' — not "
                "'proves' or 'demonstrates'. Relative-time "
                "normalisation standardises chronology, not "
                "information arrival."
            ),
        },
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
    print("  ANALYSIS 3: CALIBRATION DYNAMICS (DEEP DIVE 2)")
    print("█" * 70)
    t0 = datetime.now(timezone.utc)
    print(f"  Started: {t0.isoformat()}")

    df = load_dynamics_sample()
    df = fetch_all_histories(df)
    snap_df = build_snapshot_table(df)
    final_metrics, snapshots = per_snapshot_full_sample(snap_df)
    by_cat = per_category_dynamics(snap_df)

    print("\n" + "=" * 70)
    print("STEP 6: Save outputs")
    print("=" * 70)

    save(common_meta({
        "description": (
            "Calibration metrics at each relative-time snapshot for "
            "the dynamics-eligible sample (markets with duration >= "
            f"{MIN_DURATION_DAYS} days and >= {MIN_HISTORY_OBS} CLOB "
            "history observations)"
        ),
        "dynamics_sample": {
            "n_markets": int(len(snap_df)),
            "duration_days": {
                "min": round(float(snap_df["duration_days"].min()), 2),
                "median": round(float(snap_df["duration_days"].median()), 2),
                "max": round(float(snap_df["duration_days"].max()), 2),
            },
            "categories": (
                snap_df["category_analysis"].value_counts().to_dict()
            ),
        },
        "final_price_sanity_check": final_metrics,
        "snapshots": snapshots,
    }), "dynamics_data.json")

    save(common_meta({
        "description": (
            "Per-category calibration dynamics. Each category that has "
            f">= {MIN_CATEGORY_N} markets in the dynamics sample "
            "reports the same per-snapshot stack as the full sample."
        ),
        "min_category_n": MIN_CATEGORY_N,
        "categories": by_cat,
    }), "dynamics_category.json")

    t1 = datetime.now(timezone.utc)
    print(f"\n  Completed: {t1.isoformat()} "
          f"({(t1 - t0).total_seconds():.1f}s)")
    print("█" * 70)


if __name__ == "__main__":
    main()
