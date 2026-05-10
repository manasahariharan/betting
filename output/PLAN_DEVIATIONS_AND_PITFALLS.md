# Plan Deviations & API Pitfalls

What changed from `POLYMARKET_PROJECT_PLAN.md` during implementation, and what to watch out for.

---

## Plan Assumptions That Were Wrong

### 1. Category data location

**Plan says:** Use `category` field from Gamma API markets/events.

**Reality:** The `category` field is `None` on ~83% of markets and events. Category data lives in the **`tags` array**, accessible only with `GET /markets?include_tag=true`. Each market can have 5–15 tags with slugs like `politics`, `sports`, `crypto`, `us-election`, `nfl`, etc.

**Fix:** Derive category from tag slugs using a priority-ordered mapping. First matching rule wins (e.g., a market tagged both `politics` and `sports` goes to the first rule that matches).

### 2. `outcomePrices` is settlement price, not forecast price

**Plan says:** "Bin markets by final YES price" using `outcomePrices` from Gamma API. Also use `YES token price > 0.95` for resolution detection.

**Reality:** `outcomePrices` on resolved markets is the **post-settlement** value — literally `["1","0"]` or `["0","1"]`. It's useful for resolution detection (which the plan correctly describes) but produces a trivially perfect Brier Score of 0.0 if used as the forecast price.

**Fix:** Use `outcomePrices` only for resolution detection. Fetch the actual last trading price from CLOB `/prices-history` for calibration.

### 3. Population size estimate

**Plan says:** "~20–30 pages" to fetch all resolved markets.

**Reality:** 44,000+ closed markets total; ~20,000+ even with volume >= $1k. The platform has grown far beyond the plan's estimate.

**Fix:** Cap raw scans at ~20k markets. With a $10k volume floor, ~10k qualify from ~20k scanned. This is sufficient for a target sample of 1,000.

### 4. `volume_num_min` API parameter

**Plan says:** Use `volume ≥ $1k` as a quality filter. Implies server-side filtering.

**Reality:** The `volume_num_min` query parameter exists in the API spec but **does not work** — it returns the same results regardless of value.

**Fix:** Fetch without volume filter, apply client-side: `if row["volume"] >= min_volume`.

---

## CLOB API Pitfalls

### 5. `interval=max` returns empty at fine fidelity

**Plan documents this:** "granularity below 12 hours is unavailable for resolved/closed markets" (citing GitHub issue #216).

**Confirmed.** Use `fidelity=720` (12-hour intervals). Do not use `fidelity=60` with `interval=max` — it silently returns `{"history": []}`.

### 6. Last price tick may be settlement-contaminated

The final data point in CLOB history can snap to 0 or 1 after resolution. Using it directly as the "forecast price" reintroduces the same problem as using `outcomePrices`.

**Fix:** Use the **second-to-last** price point (`history[-2]`) when history has >= 3 points.

### 7. Older markets have no CLOB history

Markets from ~2020–2022 predate the CLOB orderbook system (they used FPMM/AMM). The CLOB API returns empty history for these. In our run, 194/1,000 sampled markets (19%) had no CLOB data — all were older markets.

**Implication:** Any analysis using CLOB price history has a recency bias. Acknowledge that the calibration sample skews toward 2023+ markets.

---

## Gamma API Pitfalls

### 8. Default pagination order returns oldest markets first

The API returns markets sorted by `id` ascending by default. If you cap at N pages, you get only the oldest markets (2020–2021), which have no CLOB data and no tag metadata.

**Fix:** Either sort by `endDate` descending with `end_date_max`/`end_date_min` filters, or scan enough pages to reach recent markets.

### 9. `outcomePrices` is JSON-stringified

**Plan documents this** as a failure mode: "outcomePrices is a JSON-stringified list, not a native array."

**Confirmed.** Always `json.loads()` with try/except. The same applies to `outcomes` and `clobTokenIds`.

### 10. Tags are only returned with `include_tag=true`

Without this parameter, the `tags` field is `None` on every market. The parameter is not mentioned in most API guides. The OpenAPI spec lists it as an optional boolean query parameter.

### 11. `/events` endpoint has `category` but `/markets` does not

The `/events` endpoint has a `category` string field that is populated on ~17% of events (mostly older ones). The `/markets` endpoint's `category` field is always `None` on recent markets. The events-level categories use a different taxonomy ("Sports", "US-current-affairs", "Coronavirus") than the tag slugs ("sports", "us-election", "politics").

**Recommendation:** Use tags from `/markets?include_tag=true` — they're richer, more consistent, and available on most markets.

---

## Sampling Pitfalls

### 12. Sports and politics dominate

In the $10k+ population: Politics 38.8%, Sports 25.3%, Other 23.2%. A proportional stratified sample will be ~64% politics+sports. Smaller categories (Business 2.7%, Science 1.3%) get < 30 markets in a 1,000-market sample, making category-level calibration unreliable for them.

**Options:** Oversample small categories (breaks proportionality) or merge them into "Other" (current approach).

### 13. "Other" category is still 23.2%

Even with tag-based categorization, ~23% of $10k+ markets don't match any tag rule. These are likely markets with very specific or novel tags not covered by the mapping. The "Other" bucket is heterogeneous.

---

## Recommendations for Future Analyses

1. **Always use `include_tag=true`** when fetching markets
2. **Never use `outcomePrices` as forecast prices** — only for resolution detection
3. **Budget for CLOB fetch time**: ~4 min per 1,000 markets at 0.25s/call
4. **Save raw CLOB responses to disk** after each fetch (plan recommends this for Analysis 3) to avoid re-fetching on re-runs
5. **Pre-filter by date** if CLOB data is needed — markets before ~2023 won't have any
6. **Test API parameters** before relying on them — several documented parameters don't work as expected
