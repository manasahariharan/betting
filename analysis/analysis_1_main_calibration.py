"""
Analysis 1: Main Calibration
=============================
From POLYMARKET_PROJECT_PLAN.md, "Analysis 1: Main Calibration" section.

Question: Are Polymarket crowd predictions well-calibrated overall?
         Does miscalibration vary by category?

Pipeline:
  1. Fetch resolved events from /events endpoint (has category field)
  2. Extract child markets, filter to binary resolved with volume >= $10k
  3. Collect ~10k market population, record categories
  4. Stratified sample of 600, proportional by category
  5. Fetch CLOB price history for sampled markets (fail fast on errors)
  6. Calibration analysis: 0.05-width bins, Brier Score, BSS
  7. By-category calibration (n >= 30)

Outputs:
  - calibration_data.json — calibration buckets, BSS, n, full-sample
  - category_data.json   — per-category calibration curves and BSS
  - markets_clean.csv    — full cleaned dataset
"""

import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 0.3
MAX_RETRIES = 3


def api_get(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 401 or resp.status_code == 403:
                print(f"\n  FATAL: Authentication error ({resp.status_code}) on {url}")
                print(f"  Response: {resp.text[:300]}")
                sys.exit(1)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            print(f"    [retry {attempt+1}/{MAX_RETRIES}] {e} — waiting {wait}s")
            time.sleep(wait)
    print(f"    [FAILED] {url}")
    return None


# ─── Step 1: Fetch events and extract markets ───────────────────────────────

def fetch_population(target_markets=10000, min_volume=10000):
    """
    Fetch closed events from /events, extract child markets.
    The /events endpoint provides the category field directly.
    """
    print("=" * 70)
    print(f"STEP 1: Fetching events (target ~{target_markets} markets, vol >= ${min_volume:,})")
    print("=" * 70)

    all_rows = []
    offset = 0
    limit = 100
    page = 0
    events_seen = 0

    while len(all_rows) < target_markets:
        page += 1
        if page % 10 == 1:
            print(f"  Page {page} (offset={offset}, markets so far: {len(all_rows)})...")

        data = api_get(
            f"{GAMMA_API}/events",
            params={
                "closed": "true",
                "limit": limit,
                "offset": offset,
            },
        )

        if not data:
            print("  API returned None, stopping.")
            break

        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            print(f"  Empty batch at offset {offset}, done.")
            break

        for event in batch:
            events_seen += 1
            category = (event.get("category") or "").strip()
            if not category:
                category = "Other"

            markets = event.get("markets", [])
            for m in markets:
                row = parse_market(m, category)
                if row and row["volume"] >= min_volume:
                    all_rows.append(row)

        offset += limit
        time.sleep(REQUEST_DELAY)

    print(f"\n  Events scanned: {events_seen}")
    print(f"  Markets qualifying (binary, resolved, vol >= ${min_volume:,}): {len(all_rows)}")

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("  FATAL: No qualifying markets found.")
        sys.exit(1)

    cat_counts = df["category"].value_counts()
    print(f"\n  Category distribution:")
    for cat, n in cat_counts.items():
        print(f"    {cat:20s}: {n:5d} ({n/len(df)*100:.1f}%)")

    return df


def parse_market(m, category):
    """Parse a single market dict into a clean row. Returns None if invalid."""
    # Binary check
    outcomes_raw = m.get("outcomes", "")
    if isinstance(outcomes_raw, str):
        try:
            outcomes = json.loads(outcomes_raw)
        except (json.JSONDecodeError, TypeError):
            return None
    elif isinstance(outcomes_raw, list):
        outcomes = outcomes_raw
    else:
        return None

    if len(outcomes) != 2:
        return None

    # Parse outcomePrices
    prices_raw = m.get("outcomePrices", "")
    if isinstance(prices_raw, str):
        try:
            prices = [float(p) for p in json.loads(prices_raw)]
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    elif isinstance(prices_raw, list):
        try:
            prices = [float(p) for p in prices_raw]
        except (ValueError, TypeError):
            return None
    else:
        return None

    if len(prices) != 2:
        return None

    # Resolution detection: outcomePrices near [1,0] or [0,1]
    yp, np_ = prices
    if yp > 0.95 and np_ < 0.05:
        resolved_yes = 1
    elif np_ > 0.95 and yp < 0.05:
        resolved_yes = 0
    else:
        return None

    # Volume
    try:
        volume = float(m.get("volume", 0) or 0)
    except (ValueError, TypeError):
        return None

    # YES token ID
    clob_ids_raw = m.get("clobTokenIds", "")
    yes_token_id = None
    if isinstance(clob_ids_raw, str):
        try:
            clob_ids = json.loads(clob_ids_raw)
            if isinstance(clob_ids, list) and clob_ids:
                yes_token_id = str(clob_ids[0])
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(clob_ids_raw, list) and clob_ids_raw:
        yes_token_id = str(clob_ids_raw[0])

    return {
        "market_id": m.get("id"),
        "question": (m.get("question") or "")[:200],
        "slug": m.get("slug", ""),
        "category": category,
        "volume": volume,
        "start_date": m.get("startDate") or m.get("createdAt"),
        "end_date": m.get("endDate"),
        "resolved_yes": resolved_yes,
        "yes_token_id": yes_token_id,
    }


# ─── Step 2: Stratified sample ──────────────────────────────────────────────

def stratified_sample(df, target_n=600, min_category_n=20):
    """
    Plan: stratified sample, n=600, proportional per category.
    Categories with < 20 sampled markets merged into "other" for
    category-level analysis only.
    """
    print("\n" + "=" * 70)
    print(f"STEP 2: Stratified sample (n={target_n})")
    print("=" * 70)

    pop_cats = df["category"].value_counts()
    pop_props = pop_cats / len(df)

    actual_n = min(target_n, len(df))
    parts = []
    for cat in pop_cats.index:
        cat_df = df[df["category"] == cat]
        n_cat = max(1, round(pop_props[cat] * actual_n))
        n_cat = min(n_cat, len(cat_df))
        parts.append(cat_df.sample(n=n_cat, random_state=42))

    sample = pd.concat(parts, ignore_index=True)
    sample_cats = sample["category"].value_counts()

    print(f"  Sample size: {len(sample)}")
    for cat, n in sample_cats.items():
        print(f"    {cat:20s}: {n:4d}")

    # Merge small categories for category-level analysis
    small = [c for c, n in sample_cats.items() if n < min_category_n and c != "Other"]
    if small:
        print(f"\n  Merging into 'Other' for category analysis: {small}")
    sample["category_analysis"] = sample["category"].apply(
        lambda c: "Other" if c in small else c
    )

    sanity = {
        "population_size": len(df),
        "sample_size": len(sample),
        "population_proportions": {k: round(v, 4) for k, v in pop_props.items()},
        "sample_counts": sample_cats.to_dict(),
    }

    return sample, sanity


# ─── Step 3: Fetch CLOB prices ──────────────────────────────────────────────

def fetch_clob_prices(sample):
    """
    Fetch last trading price from CLOB API for each sampled market.
    Fail fast on auth errors.
    """
    print("\n" + "=" * 70)
    print(f"STEP 3: Fetching CLOB price history for {len(sample)} markets")
    print("=" * 70)

    eligible = sample[sample["yes_token_id"].notna()]
    print(f"  Markets with YES token IDs: {len(eligible)}/{len(sample)}")

    final_prices = {}
    success = 0
    fail = 0

    for idx, row in eligible.iterrows():
        token_id = row["yes_token_id"]

        data = api_get(
            f"{CLOB_API}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": 720},
        )

        if data and "history" in data and len(data["history"]) >= 1:
            history = data["history"]
            # Second-to-last price avoids settlement-contaminated final tick
            price = history[-2]["p"] if len(history) >= 3 else history[-1]["p"]
            final_prices[row["market_id"]] = float(price)
            success += 1
        else:
            fail += 1

        total = success + fail
        if total % 50 == 0:
            print(f"  Progress: {total}/{len(eligible)} ({success} ok, {fail} no data)")

        time.sleep(0.25)

    print(f"\n  Done: {success} prices, {fail} failed")

    sample = sample.copy()
    sample["final_yes_price"] = sample["market_id"].map(final_prices)
    have = sample["final_yes_price"].notna().sum()
    print(f"  Markets with CLOB prices: {have}/{len(sample)}")

    return sample


# ─── Step 4: Calibration analysis ───────────────────────────────────────────

def compute_calibration(df, label="full_sample"):
    """0.05-width bins, Brier Score, BSS."""
    bins = np.arange(0, 1.001, 0.05)
    centers = (bins[:-1] + bins[1:]) / 2

    df = df.copy()
    df["bin_idx"] = np.digitize(df["final_yes_price"], bins) - 1
    df["bin_idx"] = df["bin_idx"].clip(0, len(centers) - 1)

    buckets = []
    for i, c in enumerate(centers):
        b = df[df["bin_idx"] == i]
        n = len(b)
        buckets.append({
            "bin_lower": round(float(bins[i]), 3),
            "bin_upper": round(float(bins[i + 1]), 3),
            "bin_center": round(float(c), 3),
            "mean_predicted": round(float(b["final_yes_price"].mean()), 5) if n else None,
            "mean_actual": round(float(b["resolved_yes"].mean()), 5) if n else None,
            "n": int(n),
        })

    predicted = df["final_yes_price"].values
    actual = df["resolved_yes"].values
    bs = float(np.mean((predicted - actual) ** 2))
    bs_base = float(np.var(actual))
    bss = 1 - (bs / bs_base) if bs_base > 0 else None

    return {
        "label": label,
        "n_markets": int(len(df)),
        "n_resolved_yes": int(actual.sum()),
        "n_resolved_no": int(len(actual) - actual.sum()),
        "base_rate": round(float(actual.mean()), 5),
        "brier_score": round(bs, 6),
        "brier_score_baseline": round(bs_base, 6),
        "bss": round(bss, 6) if bss is not None else None,
        "buckets": buckets,
    }


def run_calibration(sample):
    print("\n" + "=" * 70)
    print("STEP 4: Calibration analysis")
    print("=" * 70)

    cal = sample[sample["final_yes_price"].notna()].copy()
    print(f"  Markets with CLOB prices: {len(cal)}")

    if len(cal) < 20:
        print("  WARNING: Very few markets. Calibration unreliable.")

    result = compute_calibration(cal)

    print(f"  N={result['n_markets']}  YES={result['n_resolved_yes']}  "
          f"NO={result['n_resolved_no']}  base_rate={result['base_rate']:.4f}")
    print(f"  Brier={result['brier_score']:.6f}  BSS={result['bss']}")

    print(f"\n  {'Bin':>10s}  {'Pred':>8s}  {'Actual':>8s}  {'N':>5s}")
    print(f"  {'-'*36}")
    for b in result["buckets"]:
        if b["n"] > 0:
            print(f"  {b['bin_lower']:.2f}-{b['bin_upper']:.2f}"
                  f"  {b['mean_predicted']:8.4f}  {b['mean_actual']:8.4f}  {b['n']:5d}")

    sparse = sum(1 for b in result["buckets"] if 0 < b["n"] < 10)
    if sparse:
        print(f"\n  {sparse} buckets have n < 10 (flagged for charts)")

    return result


def run_category_calibration(sample):
    print("\n" + "=" * 70)
    print("STEP 5: By-category calibration")
    print("=" * 70)

    cal = sample[sample["final_yes_price"].notna()].copy()
    results = {}

    for cat in sorted(cal["category_analysis"].unique()):
        cat_df = cal[cal["category_analysis"] == cat]
        if len(cat_df) < 30:
            print(f"  {cat:20s}: n={len(cat_df):4d} — SKIPPED (< 30)")
            continue
        r = compute_calibration(cat_df, label=cat)
        results[cat] = r
        print(f"  {cat:20s}: n={r['n_markets']:4d}  BSS={r['bss']}  "
              f"base_rate={r['base_rate']:.3f}")

    return results


# ─── Step 5: Save outputs ───────────────────────────────────────────────────

def save_outputs(cal_result, cat_results, sanity, sample):
    print("\n" + "=" * 70)
    print("STEP 6: Saving outputs")
    print("=" * 70)

    # markets_clean.csv
    csv_path = DATA_DIR / "markets_clean.csv"
    sample.to_csv(csv_path, index=False)
    print(f"  {csv_path} ({csv_path.stat().st_size / 1024:.1f} KB)")

    # calibration_data.json
    cal_out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": "Analysis 1: Main Calibration — full-sample",
        "methodology": {
            "bin_width": 0.05,
            "bs_formula": "mean((predicted - actual)^2)",
            "bss_formula": "1 - BS / Var(resolved_yes)",
            "bss_caveat": "Not strictly proper; asymptotically proper (Murphy 1973)",
            "price_source": "CLOB prices-history, second-to-last 12hr tick",
        },
        "sampling": sanity,
        **cal_result,
    }
    cal_path = OUTPUT_DIR / "calibration_data.json"
    with open(cal_path, "w") as f:
        json.dump(cal_out, f, indent=2)
    print(f"  {cal_path} ({cal_path.stat().st_size / 1024:.1f} KB)")

    # category_data.json
    cat_out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": "Analysis 1: Per-category calibration",
        "methodology": {"min_category_n": 30},
        "categories": cat_results,
    }
    cat_path = OUTPUT_DIR / "category_data.json"
    with open(cat_path, "w") as f:
        json.dump(cat_out, f, indent=2)
    print(f"  {cat_path} ({cat_path.stat().st_size / 1024:.1f} KB)")


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    print("\n" + "█" * 70)
    print("  ANALYSIS 1: MAIN CALIBRATION")
    print("█" * 70)
    t0 = datetime.now(timezone.utc)
    print(f"  Started: {t0.isoformat()}")

    df = fetch_population(target_markets=10000, min_volume=10000)
    sample, sanity = stratified_sample(df, target_n=600)
    sample = fetch_clob_prices(sample)
    sample.to_csv(DATA_DIR / "markets_clean.csv", index=False)
    cal = run_calibration(sample)
    cats = run_category_calibration(sample)
    save_outputs(cal, cats, sanity, sample)

    t1 = datetime.now(timezone.utc)
    print(f"\n  Completed: {t1.isoformat()} ({(t1-t0).total_seconds():.0f}s)")
    print("█" * 70)


if __name__ == "__main__":
    main()
