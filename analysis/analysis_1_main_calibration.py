"""
Analysis 1: Main Calibration
=============================
From POLYMARKET_PROJECT_PLAN.md, "Analysis 1: Main Calibration" section.

Question: Are Polymarket crowd predictions well-calibrated overall?
         Does miscalibration vary by category?

Pipeline:
  1. Fetch resolved binary markets from /markets?include_tag=true
     (tags carry category data; the category field itself is empty on most markets)
  2. Filter to volume >= $10k, collect ~10k market population
  3. Derive canonical category from tag slugs
  4. Stratified sample of 1000, proportional by category
  5. Fetch CLOB price history for sampled markets
  6. Calibration: 0.05-width bins, Brier Score, BSS
  7. By-category calibration (n >= 30)

Outputs:
  - calibration_data.json — calibration buckets, BSS, n, full-sample
  - category_data.json   — per-category calibration curves and BSS
  - markets_clean.csv    — full cleaned dataset
"""

import json
import sys
import time
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

MAX_RETRIES = 3

# ─── Tag-based category mapping ─────────────────────────────────────────────
# Priority-ordered: first match wins. Checked against the set of tag slugs
# on each market.

CATEGORY_RULES = [
    # Sports — broad bucket including esports
    ({"sports", "nfl", "nba", "mlb", "nhl", "soccer", "football", "baseball",
      "hockey", "tennis", "golf", "mma", "ufc", "boxing", "cricket",
      "premier-league", "EPL", "champions-league", "europa-league",
      "la-liga", "serie-a", "bundesliga", "cfb", "cfp",
      "margin-of-victory", "todays-sports", "games", "euro-2024",
      "major-league-baseball", "player-transfers", "team-transfers",
      "dota-2", "csgo", "valorant", "league-of-legends", "esports",
      "nba-playoffs", "world-cup", "olympics", "super-bowl",
      "world-series", "stanley-cup", "chess"}, "Sports"),

    # Politics
    ({"politics", "us-election", "elections", "us-politics",
      "presidential-election", "us-presidential-election",
      "us-elections", "election", "2024-election", "election-2024",
      "global-elections", "swing-states", "potus",
      "republican-party", "republicans", "democrat", "senate-1",
      "governor", "trump", "biden", "kamala", "trump-presidency",
      "trump-cabinet", "vance", "mention-markets", "tweets-markets",
      "geopolitics", "ukraine", "russia", "china", "middle-east",
      "gov-shutdown", "pardon"}, "Politics"),

    # Crypto
    ({"crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
      "defi", "nft", "nfts", "token-launch", "stablecoin", "memecoin",
      "crypto-prices", "exchanges", "coinbase", "binance", "xrp",
      "dogecoin", "blockchain"}, "Crypto"),

    # Business & Economics
    ({"finance", "business", "economy", "economy1", "fed-rates",
      "jpow", "jerome-powell", "stock-market", "stocks", "nasdaq",
      "s-and-p", "ipo", "earnings", "revenue", "unemployment",
      "cpi", "inflation", "gdp", "recession", "tariff", "tariffs",
      "business-news", "breaking-news"}, "Business"),

    # Science & Tech
    ({"science", "weather", "climate", "global-warming", "global-temp",
      "ai", "openai", "tech", "spacex", "space", "nasa",
      "earthquake", "hurricane"}, "Science"),

    # Pop Culture & Entertainment
    ({"pop-culture", "entertainment", "movies", "tv", "music",
      "celebrity", "tiktok", "youtube", "streamer", "awards",
      "emmys", "oscars", "grammys", "reality-tv"}, "Pop Culture"),
]


def derive_category(tags):
    """Derive canonical category from a market's tag list."""
    if not tags:
        return "Other"
    slugs = set()
    for t in tags:
        if isinstance(t, dict):
            s = t.get("slug", "")
            if s and s != "all":
                slugs.add(s)
    for match_slugs, category in CATEGORY_RULES:
        if slugs & match_slugs:
            return category
    return "Other"


def api_get(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code in (401, 403):
                print(f"\n  FATAL: Auth error ({resp.status_code}) on {url}")
                print(f"  Response: {resp.text[:300]}")
                sys.exit(1)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            print(f"    [retry {attempt+1}/{MAX_RETRIES}] {e} — {wait}s")
            time.sleep(wait)
    print(f"    [FAILED] {url}")
    return None


# ─── Step 1: Fetch population ───────────────────────────────────────────────

def _fetch_window(end_date_min_iso, end_date_max_iso,
                  max_raw_scan, min_volume,
                  page_limit=500):
    """
    Fetch one window of closed markets sorted by endDate descending.
    Returns (rows, raw_scanned). Stops when:
      * the API returns an empty / partial batch (end of window), or
      * raw_scanned >= max_raw_scan.

    Sorting endDate desc + end_date_min/max snake_case is what the Gamma
    API actually honours — see PLAN_DEVIATIONS_AND_PITFALLS.md #8.
    Default offset-0 pagination without these filters returns the very
    oldest markets, which all predate the CLOB and have no usable
    forecast price.
    """
    rows = []
    offset = 0
    raw_scanned = 0
    page = 0
    while raw_scanned < max_raw_scan:
        page += 1
        data = api_get(
            f"{GAMMA_API}/markets",
            params={
                "closed": "true",
                "limit": page_limit,
                "offset": offset,
                "include_tag": "true",
                "end_date_min": end_date_min_iso,
                "end_date_max": end_date_max_iso,
                "order": "endDate",
                "ascending": "false",
            },
        )
        if not data:
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break

        for m in batch:
            raw_scanned += 1
            row = parse_market(m)
            if row and row["volume"] >= min_volume:
                rows.append(row)
            if raw_scanned >= max_raw_scan:
                break

        if page % 5 == 1:
            print(f"  Page {page} (offset={offset}, raw_scanned={raw_scanned}, "
                  f"qualifying={len(rows)})...")

        if len(batch) < page_limit:
            print(f"  End of window reached at offset {offset}.")
            break
        offset += page_limit
        time.sleep(0.25)
    return rows, raw_scanned


def fetch_population(
    target_qualifying=2000,
    max_raw_scan=20000,
    min_volume=10000,
    initial_window_days=30,
    fallback_windows_days=(60, 90, 180, 365),
):
    """
    Fetch closed binary markets within a recency window. Pitfalls applied:

      #8: sort endDate desc with snake_case end_date_min/end_date_max
      #4: client-side volume filter (volume_num_min is broken)
      #9, #10: parse outcomePrices/outcomes/clobTokenIds via parse_market
        (which handles include_tag-derived tags)

    Window-extension rule (Q1 from the PR review):
      Try `initial_window_days` first. If the qualifying pool is below
      `target_qualifying`, expand the window through `fallback_windows_days`
      until the pool clears the target or the widest window is reached.
      In our 2026 probe, 30d already yields ~2.3k qualifying so the
      fallback rarely fires — but it's here as a safety net for sparser
      future periods.

    Returns (df, window_used_days, raw_scanned).
    """
    from datetime import timedelta
    print("=" * 70)
    print(f"STEP 1: Fetching recent markets (target_qualifying="
          f"{target_qualifying}, max_raw_scan={max_raw_scan}, "
          f"vol>=${min_volume:,})")
    print("=" * 70)

    now = datetime.now(timezone.utc)
    end_date_max_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    window_used = None
    last_raw_scanned = 0
    for window_days in (initial_window_days, *fallback_windows_days):
        end_date_min_iso = (
            now - timedelta(days=window_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n  Trying window: last {window_days} days "
              f"({end_date_min_iso} -> {end_date_max_iso})")

        rows, last_raw_scanned = _fetch_window(
            end_date_min_iso, end_date_max_iso,
            max_raw_scan, min_volume,
        )
        print(f"  -> raw_scanned={last_raw_scanned}, "
              f"qualifying={len(rows)}")
        if len(rows) >= target_qualifying:
            window_used = window_days
            print(f"  Window {window_days}d hit target "
                  f"({len(rows)} >= {target_qualifying}); using it.")
            break
    else:
        window_used = (initial_window_days, *fallback_windows_days)[-1]
        print(f"  All windows exhausted; using widest "
              f"({window_used}d, qualifying={len(rows)}).")

    df = pd.DataFrame(rows)
    if df.empty:
        print("  FATAL: No qualifying markets.")
        sys.exit(1)

    cats = df["category"].value_counts()
    print(f"\n  Window: {window_used} days · "
          f"raw_scanned: {last_raw_scanned} · "
          f"qualifying: {len(df)}")
    print(f"  Category distribution:")
    for cat, n in cats.items():
        print(f"    {cat:20s}: {n:5d} ({n/len(df)*100:.1f}%)")

    df.attrs["window_days"] = window_used
    df.attrs["raw_scanned"] = last_raw_scanned
    return df


def parse_market(m):
    """Parse a market dict into a row. Returns None if invalid."""
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

    yp, np_ = prices
    if yp > 0.95 and np_ < 0.05:
        resolved_yes = 1
    elif np_ > 0.95 and yp < 0.05:
        resolved_yes = 0
    else:
        return None

    try:
        volume = float(m.get("volume", 0) or 0)
    except (ValueError, TypeError):
        return None

    tags = m.get("tags") or []
    category = derive_category(tags)

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
        "tag_slugs": ",".join(
            t.get("slug", "") for t in tags
            if isinstance(t, dict) and t.get("slug") != "all"
        ),
    }


# ─── Step 2: Stratified sample ──────────────────────────────────────────────

def stratified_sample(df, target_n=1000, min_category_n=20):
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
    print("\n" + "=" * 70)
    print(f"STEP 3: Fetching CLOB price history ({len(sample)} markets)")
    print("=" * 70)

    eligible = sample[sample["yes_token_id"].notna()]
    print(f"  With YES token IDs: {len(eligible)}/{len(sample)}")

    final_prices = {}
    success = 0
    fail = 0

    for idx, row in eligible.iterrows():
        data = api_get(
            f"{CLOB_API}/prices-history",
            params={"market": row["yes_token_id"], "interval": "max", "fidelity": 720},
        )
        if data and "history" in data and len(data["history"]) >= 1:
            h = data["history"]
            price = h[-2]["p"] if len(h) >= 3 else h[-1]["p"]
            final_prices[row["market_id"]] = float(price)
            success += 1
        else:
            fail += 1

        total = success + fail
        if total % 100 == 0:
            print(f"  Progress: {total}/{len(eligible)} ({success} ok, {fail} no data)")
        time.sleep(0.25)

    print(f"\n  Done: {success} prices, {fail} failed")

    sample = sample.copy()
    sample["final_yes_price"] = sample["market_id"].map(final_prices)
    print(f"  Markets with CLOB prices: {sample['final_yes_price'].notna().sum()}/{len(sample)}")
    return sample


# ─── Step 4: Calibration ────────────────────────────────────────────────────

def compute_calibration(df, label="full_sample"):
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

    pred = df["final_yes_price"].values
    actual = df["resolved_yes"].values
    bs = float(np.mean((pred - actual) ** 2))
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
        print(f"\n  {sparse} buckets have n < 10 (flagged)")
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
        print(f"  {cat:20s}: n={r['n_markets']:4d}  BSS={r['bss']:.4f}  "
              f"base_rate={r['base_rate']:.3f}")
    return results


# ─── Step 6: Save ───────────────────────────────────────────────────────────

def save_outputs(cal_result, cat_results, sanity, sample):
    print("\n" + "=" * 70)
    print("STEP 6: Saving outputs")
    print("=" * 70)

    csv_path = DATA_DIR / "markets_clean.csv"
    sample.to_csv(csv_path, index=False)
    print(f"  {csv_path} ({csv_path.stat().st_size / 1024:.1f} KB)")

    cal_out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": "Analysis 1: Main Calibration — full-sample",
        "methodology": {
            "bin_width": 0.05,
            "bs_formula": "mean((predicted - actual)^2)",
            "bss_formula": "1 - BS / Var(resolved_yes)",
            "bss_caveat": "Not strictly proper; asymptotically proper (Murphy 1973)",
            "price_source": "CLOB prices-history, second-to-last 12hr tick",
            "category_source": "Market tags via /markets?include_tag=true",
        },
        "sampling": sanity,
        **cal_result,
    }
    cal_path = OUTPUT_DIR / "calibration_data.json"
    with open(cal_path, "w") as f:
        json.dump(cal_out, f, indent=2)
    print(f"  {cal_path} ({cal_path.stat().st_size / 1024:.1f} KB)")

    cat_out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": "Analysis 1: Per-category calibration",
        "methodology": {"min_category_n": 30, "category_source": "tag slugs"},
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

    df = fetch_population(
        target_qualifying=2000,
        max_raw_scan=20000,
        min_volume=10000,
        initial_window_days=30,
    )
    sample, sanity = stratified_sample(df, target_n=2000)
    # Carry the recency-window metadata through to the JSON output so
    # the docs/index.html can show "last 3 days · ~2.3k qualifying".
    sanity["fetch_window_days"] = df.attrs.get("window_days")
    sanity["raw_scanned"] = df.attrs.get("raw_scanned")
    sample = fetch_clob_prices(sample)
    cal = run_calibration(sample)
    cats = run_category_calibration(sample)
    save_outputs(cal, cats, sanity, sample)

    t1 = datetime.now(timezone.utc)
    print(f"\n  Completed: {t1.isoformat()} ({(t1-t0).total_seconds():.0f}s)")
    print("█" * 70)


if __name__ == "__main__":
    main()
