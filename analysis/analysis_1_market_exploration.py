"""
Analysis 1: What Are Prediction Markets Actually Predicting?
============================================================
Based on the Polymarket Prediction Market Project Validation Summary (Section 1).

This script:
  1. Fetches resolved markets from the Polymarket Gamma API
  2. Validates schema and cleans data (per plan recommendation: "fetch 100 markets,
     fully validate schema, manually inspect 20 histories")
  3. Fetches price history for a sample of markets via the CLOB API
  4. Produces exploratory output files:
     - Market metadata summary (CSV + JSON)
     - Schema validation report
     - Category distribution analysis
     - Price history samples for timeline visualization
     - Basic calibration statistics (final price vs outcome)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import requests
import seaborn as sns

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 0.5  # seconds between API calls to be polite
MAX_RETRIES = 3
RETRY_BACKOFF = 2


def api_get(url, params=None, retries=MAX_RETRIES):
    """Make a GET request with retry logic and backoff."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            wait = RETRY_BACKOFF ** attempt
            print(f"  [retry {attempt+1}/{retries}] {e} — waiting {wait}s")
            time.sleep(wait)
    print(f"  [FAILED] Could not fetch {url} after {retries} attempts")
    return None


# ── Step 1: Fetch resolved markets ──────────────────────────────────────────

def fetch_resolved_markets(target_count=200):
    """
    Fetch resolved (closed) markets from Gamma API using offset pagination.
    We request more than we need to allow for filtering.
    """
    print(f"\n{'='*70}")
    print("STEP 1: Fetching resolved markets from Polymarket Gamma API")
    print(f"{'='*70}")

    markets = []
    offset = 0
    limit = 100
    max_pages = 10

    for page in range(max_pages):
        print(f"  Fetching page {page+1} (offset={offset}, limit={limit})...")
        data = api_get(
            f"{GAMMA_API}/markets",
            params={
                "closed": "true",
                "limit": limit,
                "offset": offset,
                "order": "volume_num",
                "ascending": "false",
                "end_date_min": "2023-01-01",
            },
        )
        if not data:
            print("  No data returned, stopping pagination.")
            break

        if isinstance(data, list):
            batch = data
        elif isinstance(data, dict) and "data" in data:
            batch = data["data"]
        else:
            print(f"  Unexpected response shape: {type(data)}")
            break

        if not batch:
            print("  Empty page, stopping.")
            break

        markets.extend(batch)
        print(f"  Got {len(batch)} markets (total so far: {len(markets)})")

        if len(markets) >= target_count:
            break

        offset += limit
        time.sleep(REQUEST_DELAY)

    print(f"\n  Total raw markets fetched: {len(markets)}")
    return markets


# ── Step 2: Schema validation & cleaning ────────────────────────────────────

def validate_and_clean(markets):
    """
    Validate schema, flag issues, clean data.
    Per plan: "Before building anything — fetch 100 markets, fully validate schema,
    manually inspect 20 histories."
    """
    print(f"\n{'='*70}")
    print("STEP 2: Schema validation & data cleaning")
    print(f"{'='*70}")

    expected_fields = [
        "id", "question", "slug", "conditionId",
        "endDate", "volume", "liquidity",
        "outcomes", "outcomePrices", "closed",
    ]

    report = {
        "total_fetched": len(markets),
        "fields_checked": expected_fields,
        "missing_fields": {},
        "type_issues": [],
        "cleaned_count": 0,
        "dropped_reasons": {},
    }

    cleaned = []
    for i, m in enumerate(markets):
        missing = [f for f in expected_fields if f not in m or m[f] is None]
        if missing:
            report["missing_fields"][m.get("id", f"index_{i}")] = missing

        drop_reason = None
        if not m.get("conditionId"):
            drop_reason = "no_conditionId"
        elif not m.get("outcomes"):
            drop_reason = "no_outcomes"
        elif not m.get("outcomePrices"):
            drop_reason = "no_outcomePrices"
        elif not m.get("closed"):
            drop_reason = "not_closed"

        if drop_reason:
            report["dropped_reasons"][drop_reason] = report["dropped_reasons"].get(drop_reason, 0) + 1
            continue

        # Parse outcomePrices — may be string or list
        prices = m.get("outcomePrices", "")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except json.JSONDecodeError:
                report["type_issues"].append({"id": m.get("id"), "field": "outcomePrices", "issue": "unparseable"})
                continue
        m["_parsed_prices"] = [float(p) for p in prices]

        # Parse outcomes similarly
        outcomes = m.get("outcomes", "")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                report["type_issues"].append({"id": m.get("id"), "field": "outcomes", "issue": "unparseable"})
                continue
        m["_parsed_outcomes"] = outcomes

        # Determine resolution from outcomePrices:
        # Resolved markets typically have prices like ["1","0"] (YES won) or ["0","1"] (NO won)
        # Both-zero prices indicate settled/old markets where we can still infer from resolvedBy
        m["_yes_price"] = m["_parsed_prices"][0] if len(m["_parsed_prices"]) > 0 else None
        m["_resolved_yes"] = None

        prices_tuple = tuple(m["_parsed_prices"]) if len(m["_parsed_prices"]) == 2 else None
        if prices_tuple == (1.0, 0.0):
            m["_resolved_yes"] = True
        elif prices_tuple == (0.0, 1.0):
            m["_resolved_yes"] = False
        elif prices_tuple == (0.0, 0.0):
            # Old settled markets — still include them but mark outcome unknown
            # unless we can infer from resolution field
            if m.get("resolution"):
                res = str(m["resolution"]).strip().lower()
                if res == "yes":
                    m["_resolved_yes"] = True
                elif res == "no":
                    m["_resolved_yes"] = False
        elif m.get("resolution"):
            res = str(m["resolution"]).strip().lower()
            if res == "yes":
                m["_resolved_yes"] = True
            elif res == "no":
                m["_resolved_yes"] = False

        cleaned.append(m)

    report["cleaned_count"] = len(cleaned)

    print(f"  Markets after cleaning: {len(cleaned)}/{len(markets)}")
    print(f"  Dropped reasons: {report['dropped_reasons']}")
    print(f"  Markets with missing fields: {len(report['missing_fields'])}")
    print(f"  Type issues found: {len(report['type_issues'])}")

    # Save validation report
    report_path = OUTPUT_DIR / "schema_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Saved validation report → {report_path}")

    return cleaned, report


# ── Step 3: Build structured DataFrame ──────────────────────────────────────

def build_dataframe(cleaned_markets):
    """Convert cleaned market list to a structured DataFrame."""
    print(f"\n{'='*70}")
    print("STEP 3: Building structured DataFrame")
    print(f"{'='*70}")

    rows = []
    for m in cleaned_markets:
        tags = m.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []

        # Extract category from tags or groupItemTitle
        category = "unknown"
        if m.get("groupItemTitle"):
            category = str(m["groupItemTitle"]).lower()
        elif tags:
            if isinstance(tags[0], dict):
                category = tags[0].get("label", tags[0].get("slug", "unknown")).lower()
            else:
                category = str(tags[0]).lower()

        # Broad category bucketing
        cat_lower = category.lower()
        broad_category = "other"
        for keyword, bucket in [
            ("politic", "politics"), ("election", "politics"), ("president", "politics"),
            ("trump", "politics"), ("biden", "politics"), ("congress", "politics"),
            ("sport", "sports"), ("nba", "sports"), ("nfl", "sports"),
            ("soccer", "sports"), ("football", "sports"), ("mlb", "sports"),
            ("crypto", "crypto"), ("bitcoin", "crypto"), ("ethereum", "crypto"),
            ("btc", "crypto"), ("eth", "crypto"), ("defi", "crypto"),
            ("econ", "economics"), ("fed", "economics"), ("inflation", "economics"),
            ("rate", "economics"), ("gdp", "economics"),
            ("ai", "tech/ai"), ("tech", "tech/ai"), ("apple", "tech/ai"),
            ("google", "tech/ai"), ("openai", "tech/ai"),
            ("war", "geopolitics"), ("conflict", "geopolitics"), ("ukraine", "geopolitics"),
            ("china", "geopolitics"), ("russia", "geopolitics"),
        ]:
            if keyword in cat_lower or keyword in m.get("question", "").lower():
                broad_category = bucket
                break

        volume_raw = m.get("volume", 0)
        try:
            volume = float(volume_raw) if volume_raw else 0
        except (ValueError, TypeError):
            volume = 0

        liquidity_raw = m.get("liquidity", 0)
        try:
            liquidity = float(liquidity_raw) if liquidity_raw else 0
        except (ValueError, TypeError):
            liquidity = 0

        # Determine binary outcome (resolved YES = 1, NO = 0)
        outcome_binary = None
        if m.get("_resolved_yes") is True:
            outcome_binary = 1
        elif m.get("_resolved_yes") is False:
            outcome_binary = 0

        rows.append({
            "market_id": m.get("id"),
            "condition_id": m.get("conditionId"),
            "question": m.get("question", "")[:200],
            "slug": m.get("slug", ""),
            "start_date": m.get("startDate") or m.get("createdAt"),
            "end_date": m.get("endDate"),
            "volume": volume,
            "liquidity": liquidity,
            "category_raw": category,
            "broad_category": broad_category,
            "outcomes": str(m.get("_parsed_outcomes", [])),
            "final_yes_price": m.get("_yes_price"),
            "resolved_yes": m.get("_resolved_yes"),
            "outcome_binary": outcome_binary,
            "resolution": m.get("resolution", ""),
            "num_outcomes": len(m.get("_parsed_outcomes", [])),
            "clob_token_ids": m.get("clobTokenIds", ""),
        })

    df = pd.DataFrame(rows)

    # Parse dates
    for col in ["start_date", "end_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    df["duration_hours"] = (df["end_date"] - df["start_date"]).dt.total_seconds() / 3600
    df["duration_days"] = df["duration_hours"] / 24

    print(f"  DataFrame shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Binary outcomes available: {df['outcome_binary'].notna().sum()}/{len(df)}")

    # Save to CSV
    csv_path = DATA_DIR / "markets_cleaned.csv"
    df.to_csv(csv_path, index=False)
    print(f"  Saved cleaned markets → {csv_path}")

    return df


# ── Step 4: Category distribution & summary statistics ──────────────────────

def analyze_categories(df):
    """Produce category distribution analysis and summary stats."""
    print(f"\n{'='*70}")
    print("STEP 4: Category distribution & summary statistics")
    print(f"{'='*70}")

    cat_counts = df["broad_category"].value_counts()
    print(f"\n  Category distribution:")
    for cat, count in cat_counts.items():
        print(f"    {cat:20s}: {count:4d} ({count/len(df)*100:.1f}%)")

    # Summary statistics
    summary = {
        "total_markets": len(df),
        "binary_markets": int(df["outcome_binary"].notna().sum()),
        "resolved_yes_count": int((df["outcome_binary"] == 1).sum()),
        "resolved_no_count": int((df["outcome_binary"] == 0).sum()),
        "base_rate_yes": float((df["outcome_binary"] == 1).mean()) if df["outcome_binary"].notna().any() else None,
        "median_volume": float(df["volume"].median()),
        "mean_volume": float(df["volume"].mean()),
        "median_duration_days": float(df["duration_days"].median()) if df["duration_days"].notna().any() else None,
        "category_counts": cat_counts.to_dict(),
        "date_range_start": str(df["start_date"].min()),
        "date_range_end": str(df["end_date"].max()),
    }

    summary_path = OUTPUT_DIR / "market_summary_statistics.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Saved summary statistics → {summary_path}")

    # Category distribution chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    cat_counts.plot(kind="barh", ax=ax, color=sns.color_palette("viridis", len(cat_counts)))
    ax.set_xlabel("Number of Markets")
    ax.set_title("Market Count by Category")
    ax.invert_yaxis()

    ax = axes[1]
    vol_by_cat = df.groupby("broad_category")["volume"].sum().sort_values(ascending=True)
    vol_by_cat.plot(kind="barh", ax=ax, color=sns.color_palette("magma", len(vol_by_cat)))
    ax.set_xlabel("Total Volume ($)")
    ax.set_title("Total Volume by Category")
    ax.invert_yaxis()

    plt.tight_layout()
    chart_path = OUTPUT_DIR / "category_distribution.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved category chart → {chart_path}")

    return summary


# ── Step 5: Fetch price histories for sample markets ────────────────────────

def fetch_price_histories(df, sample_size=20):
    """
    Fetch price history for a stratified sample of markets.
    Per plan: "manually inspect 20 histories."
    """
    print(f"\n{'='*70}")
    print(f"STEP 5: Fetching price histories for {sample_size} sample markets")
    print(f"{'='*70}")

    def extract_yes_token(clob_ids_raw):
        if not clob_ids_raw or clob_ids_raw == "nan":
            return None
        if isinstance(clob_ids_raw, str):
            try:
                clob_ids_raw = json.loads(clob_ids_raw)
            except Exception:
                # Try bracket-less comma-separated
                return None
        if isinstance(clob_ids_raw, list) and len(clob_ids_raw) > 0:
            return str(clob_ids_raw[0])
        return None

    df["_yes_token"] = df["clob_token_ids"].apply(extract_yes_token)

    # Filter to markets with valid token IDs and sufficient volume
    eligible = df[df["_yes_token"].notna() & (df["volume"] > 1000)].copy()
    print(f"  Markets with valid YES token IDs and volume > $1000: {len(eligible)}")

    if len(eligible) == 0:
        print("  No eligible markets for price history. Trying condition_id fallback...")
        eligible = df[df["condition_id"].notna()].copy()
        if len(eligible) == 0:
            print("  No markets available for price history fetching.")
            return {}

    # Stratified sample: pick markets across categories and volume tiers
    if len(eligible) <= sample_size:
        sample = eligible
    else:
        try:
            per_cat = max(1, sample_size // max(1, eligible["broad_category"].nunique()))
            parts = []
            for cat, grp in eligible.groupby("broad_category"):
                parts.append(grp.nlargest(per_cat, "volume"))
            sample = pd.concat(parts).head(sample_size)
        except Exception:
            sample = eligible.nlargest(sample_size, "volume")

    print(f"  Sampling {len(sample)} markets for price history...")

    histories = {}
    success_count = 0
    fail_count = 0

    for idx, row in sample.iterrows():
        token_id = row.get("_yes_token") or row.get("condition_id")
        market_id = row["market_id"]
        question = row["question"][:60]

        print(f"  [{success_count+fail_count+1}/{len(sample)}] Fetching: {question}...")

        # For resolved markets, interval:"max" returns empty at fine fidelity.
        # Strategy: first try 12-hour fidelity (fast, reliable for all markets),
        # then optionally refine with chunked hourly requests for short-duration markets.
        all_history = []

        # Fast path: 12-hour fidelity with interval:max
        data = api_get(
            f"{CLOB_API}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": 720},
        )
        if data and "history" in data:
            all_history = data["history"]

        # For markets under 60 days, try hourly fidelity with chunking for more detail
        if len(all_history) < 5:
            start_date_val = row.get("start_date")
            end_date_val = row.get("end_date")

            if pd.notna(start_date_val) and pd.notna(end_date_val):
                start_ts = int(pd.Timestamp(start_date_val).timestamp())
                end_ts = int(pd.Timestamp(end_date_val).timestamp())
                duration_days = (end_ts - start_ts) / 86400

                if duration_days <= 90:
                    chunk_seconds = 15 * 86400
                    cur_start = start_ts
                    chunked = []
                    while cur_start < end_ts:
                        cur_end = min(cur_start + chunk_seconds, end_ts)
                        d = api_get(
                            f"{CLOB_API}/prices-history",
                            params={
                                "market": token_id,
                                "startTs": cur_start,
                                "endTs": cur_end,
                                "fidelity": 60,
                            },
                        )
                        if d and "history" in d:
                            chunked.extend(d["history"])
                        cur_start = cur_end
                        time.sleep(0.2)
                    if chunked:
                        all_history = chunked

        if all_history:
            histories[market_id] = {
                "question": row["question"],
                "category": row["broad_category"],
                "volume": row["volume"],
                "resolved_yes": row["resolved_yes"],
                "outcome_binary": row["outcome_binary"],
                "final_yes_price": row["final_yes_price"],
                "history": all_history,
                "num_price_points": len(all_history),
            }
            success_count += 1
            print(f"    ✓ Got {len(all_history)} price points")
        else:
            fail_count += 1
            print(f"    ✗ No history returned")

        time.sleep(REQUEST_DELAY)

    print(f"\n  Price histories fetched: {success_count} success, {fail_count} failed")

    # Save raw histories
    histories_path = DATA_DIR / "price_histories_sample.json"
    with open(histories_path, "w") as f:
        json.dump(histories, f, indent=2, default=str)
    print(f"  Saved price histories → {histories_path}")

    return histories


# ── Step 6: Single market timeline visualization (Section 1 hero chart) ─────

def plot_market_timelines(histories):
    """
    Plot probability evolution timelines for notable markets.
    This is the core visual for Section 1 of the plan.
    """
    print(f"\n{'='*70}")
    print("STEP 6: Plotting market timeline visualizations")
    print(f"{'='*70}")

    if not histories:
        print("  No histories available, skipping timeline plots.")
        return

    # Pick the most interesting markets (longest histories, diverse categories)
    sorted_markets = sorted(
        histories.items(),
        key=lambda x: x[1]["num_price_points"],
        reverse=True,
    )

    # Plot individual timelines for top markets
    n_plots = min(6, len(sorted_markets))
    fig, axes = plt.subplots(n_plots, 1, figsize=(12, 4 * n_plots))
    if n_plots == 1:
        axes = [axes]

    for i, (market_id, info) in enumerate(sorted_markets[:n_plots]):
        ax = axes[i]
        history = info["history"]

        timestamps = [datetime.fromtimestamp(p["t"], tz=timezone.utc) for p in history]
        prices = [p["p"] for p in history]

        ax.plot(timestamps, prices, linewidth=1.2, color="steelblue", alpha=0.9)
        ax.fill_between(timestamps, prices, alpha=0.1, color="steelblue")

        # Mark resolution
        outcome = info.get("outcome_binary")
        if outcome is not None:
            ax.axhline(y=outcome, color="green" if outcome == 1 else "red",
                       linestyle="--", alpha=0.5, label=f"Resolved: {'YES' if outcome == 1 else 'NO'}")

        ax.set_ylim(-0.05, 1.05)
        ax.set_ylabel("Probability")
        ax.set_title(
            f"{info['question'][:80]}\n"
            f"[{info['category']}] Vol: ${info['volume']:,.0f} | "
            f"{info['num_price_points']} price points",
            fontsize=9,
        )
        ax.legend(fontsize=8, loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    timeline_path = OUTPUT_DIR / "market_timelines.png"
    plt.savefig(timeline_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved timeline chart → {timeline_path}")

    # Overlay plot: multiple markets on one chart (normalized time)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = sns.color_palette("husl", min(8, len(sorted_markets)))

    for i, (market_id, info) in enumerate(sorted_markets[:8]):
        history = info["history"]
        if len(history) < 2:
            continue

        ts = [p["t"] for p in history]
        prices = [p["p"] for p in history]
        t_min, t_max = min(ts), max(ts)
        if t_max == t_min:
            continue

        pct_elapsed = [(t - t_min) / (t_max - t_min) for t in ts]

        label = info["question"][:45] + "..."
        ax.plot(pct_elapsed, prices, linewidth=1.0, alpha=0.7, color=colors[i % len(colors)], label=label)

    ax.plot([0, 1], [0.5, 0.5], "--", color="gray", alpha=0.3)
    ax.set_xlabel("Market Lifetime (% elapsed)")
    ax.set_ylabel("YES Probability")
    ax.set_title("Probability Evolution Over Normalized Market Lifetime")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1, 1))
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    overlay_path = OUTPUT_DIR / "market_timelines_overlay.png"
    plt.savefig(overlay_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved overlay chart → {overlay_path}")


# ── Step 7: Basic calibration preview ───────────────────────────────────────

def basic_calibration_analysis(df):
    """
    Compute basic calibration statistics using final prices vs outcomes.
    This is a preview for Section 2's deeper analysis.

    Per plan caveats: "Final prices are often contaminated by resolution certainty"
    and "Market prices are not IID forecasts" — we note these limitations.
    """
    print(f"\n{'='*70}")
    print("STEP 7: Basic calibration preview (final price vs outcome)")
    print(f"{'='*70}")

    cal_df = df[df["outcome_binary"].notna() & df["final_yes_price"].notna()].copy()
    print(f"  Markets with both price and outcome: {len(cal_df)}")

    if len(cal_df) < 10:
        print("  Insufficient data for calibration analysis.")
        return

    # Bin by predicted probability
    bins = np.arange(0, 1.05, 0.1)
    bin_labels = [f"{b:.1f}-{b+0.1:.1f}" for b in bins[:-1]]
    cal_df["prob_bin"] = pd.cut(cal_df["final_yes_price"], bins=bins, labels=bin_labels, include_lowest=True)

    cal_table = cal_df.groupby("prob_bin", observed=True).agg(
        mean_predicted=("final_yes_price", "mean"),
        mean_outcome=("outcome_binary", "mean"),
        count=("outcome_binary", "count"),
    ).reset_index()

    print(f"\n  Calibration table (predicted vs observed):")
    print(f"  {'Bin':>12s}  {'Predicted':>10s}  {'Observed':>10s}  {'N':>5s}")
    print(f"  {'-'*42}")
    for _, row in cal_table.iterrows():
        print(f"  {row['prob_bin']:>12s}  {row['mean_predicted']:10.3f}  {row['mean_outcome']:10.3f}  {row['count']:5.0f}")

    cal_table.to_csv(OUTPUT_DIR / "calibration_preview.csv", index=False)
    print(f"\n  Saved calibration table → {OUTPUT_DIR / 'calibration_preview.csv'}")

    # Brier score
    brier = ((cal_df["final_yes_price"] - cal_df["outcome_binary"]) ** 2).mean()
    print(f"\n  Brier Score (final prices): {brier:.4f}")
    print(f"  (Reference: 0.25 = always predicting 0.5, 0.0 = perfect)")

    # Calibration plot
    fig, ax = plt.subplots(figsize=(8, 8))

    valid = cal_table[cal_table["count"] >= 3]
    ax.plot([0, 1], [0, 1], "--", color="gray", alpha=0.5, label="Perfect calibration")
    ax.scatter(
        valid["mean_predicted"], valid["mean_outcome"],
        s=valid["count"] * 5, alpha=0.7, c="steelblue", edgecolors="white",
        label="Observed (size = count)",
    )

    for _, row in valid.iterrows():
        ax.annotate(
            f"n={row['count']:.0f}",
            (row["mean_predicted"], row["mean_outcome"]),
            fontsize=7, alpha=0.6,
            textcoords="offset points", xytext=(5, 5),
        )

    ax.set_xlabel("Mean Predicted Probability (Final YES Price)")
    ax.set_ylabel("Observed Outcome Rate")
    ax.set_title(
        f"Calibration Preview (N={len(cal_df)} markets)\n"
        f"Brier Score: {brier:.4f}\n"
        "⚠ Caveat: Final prices may reflect resolution certainty, not forecast quality",
        fontsize=10,
    )
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_aspect("equal")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    cal_path = OUTPUT_DIR / "calibration_preview.png"
    plt.savefig(cal_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved calibration chart → {cal_path}")

    # Sharpness analysis (per plan recommendation #6)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(cal_df["final_yes_price"], bins=20, color="steelblue", alpha=0.7, edgecolor="white")
    ax.axvline(x=0.5, color="red", linestyle="--", alpha=0.5, label="50% (maximally uncertain)")
    ax.set_xlabel("Final YES Price")
    ax.set_ylabel("Count")
    ax.set_title(
        "Sharpness: Distribution of Final Forecast Probabilities\n"
        '"Are markets confidently informative, or merely cautious?"'
    )
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    sharp_path = OUTPUT_DIR / "sharpness_distribution.png"
    plt.savefig(sharp_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved sharpness chart → {sharp_path}")

    return {"brier_score": brier, "n_markets": len(cal_df)}


# ── Step 8: Generate analysis report ────────────────────────────────────────

def generate_report(df, summary, cal_results, histories):
    """Generate a text summary report of all findings."""
    print(f"\n{'='*70}")
    print("STEP 8: Generating analysis report")
    print(f"{'='*70}")

    report_lines = [
        "=" * 70,
        "ANALYSIS 1 REPORT: What Are Prediction Markets Actually Predicting?",
        "=" * 70,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "─" * 70,
        "DATA COLLECTION SUMMARY",
        "─" * 70,
        f"  Total markets fetched: {summary['total_markets']}",
        f"  Binary markets with outcomes: {summary['binary_markets']}",
        f"  Resolved YES: {summary['resolved_yes_count']}",
        f"  Resolved NO: {summary['resolved_no_count']}",
        f"  Base rate (YES): {summary['base_rate_yes']:.3f}" if summary.get('base_rate_yes') else "  Base rate: N/A",
        f"  Date range: {summary['date_range_start']} to {summary['date_range_end']}",
        f"  Median volume: ${summary['median_volume']:,.2f}",
        f"  Median duration: {summary['median_duration_days']:.1f} days" if summary.get('median_duration_days') else "",
        "",
        "─" * 70,
        "CATEGORY DISTRIBUTION",
        "─" * 70,
    ]
    for cat, count in summary.get("category_counts", {}).items():
        report_lines.append(f"  {cat:20s}: {count:4d}")

    report_lines.extend([
        "",
        "─" * 70,
        "PRICE HISTORY SAMPLING",
        "─" * 70,
        f"  Markets sampled for price history: {len(histories)}",
        f"  Total price points collected: {sum(h['num_price_points'] for h in histories.values())}",
    ])

    if cal_results:
        report_lines.extend([
            "",
            "─" * 70,
            "CALIBRATION PREVIEW",
            "─" * 70,
            f"  Brier Score: {cal_results['brier_score']:.4f}",
            f"  Markets in calibration: {cal_results['n_markets']}",
            "  NOTE: Final prices may reflect resolution certainty (see plan caveats).",
            "  A full dynamics-based calibration analysis is needed for Section 2.",
        ])

    report_lines.extend([
        "",
        "─" * 70,
        "STATISTICAL CAVEATS (from Validation Plan)",
        "─" * 70,
        "  1. Market prices are NOT IID forecasts",
        "  2. Final prices may reflect resolution certainty, not forecast quality",
        "  3. Relative-time normalization standardizes chronology, not information",
        "  4. Longshot-bias interpretation is fragile in prediction markets",
        "  5. Bootstrap CIs assume market-level independence",
        "  6. Representative sampling weights by market count, not economic importance",
        "",
        "─" * 70,
        "OUTPUT FILES GENERATED",
        "─" * 70,
    ])

    output_files = list(OUTPUT_DIR.glob("*")) + list(DATA_DIR.glob("*"))
    for f in sorted(output_files):
        size = f.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        report_lines.append(f"  {f.name:45s} {size_str:>10s}")

    report_lines.extend(["", "=" * 70, "END OF REPORT", "=" * 70])

    report_text = "\n".join(report_lines)
    report_path = OUTPUT_DIR / "analysis_1_report.txt"
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"  Saved report → {report_path}")
    print(f"\n{report_text}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "█" * 70)
    print("  POLYMARKET ANALYSIS 1: What Are Prediction Markets Actually Predicting?")
    print("█" * 70)
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Data directory: {DATA_DIR}")

    # Step 1: Fetch
    raw_markets = fetch_resolved_markets(target_count=200)
    if not raw_markets:
        print("\nFATAL: Could not fetch any markets. Check network/API availability.")
        sys.exit(1)

    # Step 2: Validate & clean
    cleaned, val_report = validate_and_clean(raw_markets)
    if not cleaned:
        print("\nFATAL: No markets survived cleaning. Check data quality.")
        sys.exit(1)

    # Step 3: Build DataFrame
    df = build_dataframe(cleaned)

    # Step 4: Category analysis
    summary = analyze_categories(df)

    # Step 5: Fetch price histories
    histories = fetch_price_histories(df, sample_size=20)

    # Step 6: Timeline visualizations
    plot_market_timelines(histories)

    # Step 7: Basic calibration
    cal_results = basic_calibration_analysis(df)

    # Step 8: Report
    generate_report(df, summary, cal_results, histories)

    print(f"\n  Completed: {datetime.now(timezone.utc).isoformat()}")
    print("█" * 70)


if __name__ == "__main__":
    main()
