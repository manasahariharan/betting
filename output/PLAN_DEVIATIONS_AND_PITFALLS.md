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

---

## Analysis 2 (Longshot Bias) findings & pitfalls

### 14. Reuse Analysis 1's CSV — do not re-hit the API

`data/markets_clean.csv` already contains the stratified sample with
`final_yes_price` (CLOB second-to-last 12hr tick) and `resolved_yes`.
Analysis 2 reads it directly and makes zero new HTTP calls. This sidesteps
every API pitfall above.

### 15. `sklearn.linear_model.LogisticRegression(penalty=None)` is deprecated in 1.8

The plan's pseudocode `LogisticRegression().fit(...)` uses the default
L2 penalty, which **shrinks the slope toward zero** — exactly what we
do not want when reporting calibration slope. The right move is
`LogisticRegression(C=1e9, solver="lbfgs", max_iter=5000)` — equivalent
unpenalised MLE without the deprecated `penalty=None` argument. Suppress
`FutureWarning` and `ConvergenceWarning` from sklearn so the run log
isn't drowned by ~15,000 warning lines from the bootstrap loop.

### 16. Logistic MLE diverges on near-separated subsets

Both tails are extremely separated:

- Longshots (price ≤ 0.15): only 3/420 resolved YES (≈0.7%)
- Favorites (price ≥ 0.85): 93/94 resolved YES (≈99%)

Fitting an unpenalised logistic regression on either subset produces a
slope of 200+ and a meaningless intercept of -450. **Detect minority-class
share < 5% before fitting** and return `slope: null` with an explicit
`warning` field. Report `mean_overpricing_pp` instead — it remains
well-defined and is what the plan recommends as the plain-English summary.

### 17. Per-category longshot subsets are all near-separated

In our 806-market sample, *every* category's longshot subset has minority
class < 5% (most have 0 YES events). Per-category longshot slopes are
therefore unfittable. The plan anticipated this in its failure-mode
table; the right output is per-category overpricing pp plus a fallback
"full-category" slope as context.

### 18. Bootstrap CIs blow up on small subsets

For categories with n < 60, the bootstrap can resample into degenerate
cases where the slope estimate flies to ±100. Add a `ci_wide: true` flag
when `slope_ci_upper - slope_ci_lower > 2.0`. Downstream visualisation
should fade or warn on these.

### 19. Hidden gems are essentially absent

Only **1 market in our 806-sample** was priced ≤ 0.10 and resolved YES
(the Matt Gaetz Congressman exit). The plan's "top 15" target is
unachievable; report this as a finding rather than padding the list.

### 20. Bootstrap independence assumption is dubious for correlated markets

Many Polymarket events spawn multiple markets (e.g. Senate races,
multiple election outcomes for the same race). The plan flags this
(pitfall #5 in "Future Improvements"). We compute a **category-stratified
bootstrap** on the full sample as a robustness check and document the
limitation in the JSON `methodology.bootstrap` field. Findings are
qualitatively unchanged between regular and stratified bootstrap.

---

## Analysis 3 (Calibration Dynamics) findings & pitfalls

### 21. Reuse Analysis 2's calibration helpers

Both deep dives need the same statistical machinery (log-odds slope,
bootstrap CIs, near-separation guard, `ci_wide` flag, unpenalised MLE
via `C=1e9`). The cleanest pattern is to import them once from
`analysis_2_longshot_bias.py` rather than maintain two copies. This
also means an A2-branch fix automatically helps A3.

### 22. `yes_token_id` is a 77-digit integer — read as string, never as float

The CSV column looks like
`56996626423612221170851800107812812093281585719288720435408011284737463763133`.
`pd.read_csv` parses it as `float64` by default, which only carries
~15 decimal digits of precision. Coercing back via `int(float(x))` then
`str(...)` silently produces a *different* token ID. The CLOB API
happily returns `{"history": []}` for the wrong token — no error, no
warning. This was the most painful bug in the chain because there is no
visible failure signal.

**Fix:** read with `dtype={"yes_token_id": str}` and never coerce
through `float()`. Same applies to any other long ID columns.

### 23. pandas 3.0 datetime → unix-seconds conversion is fragile

The natural `df["dt"].astype("int64") // 10**9` works on pandas 2.x
because datetime arrays default to `unit="ns"`. **In pandas 3.0,
datetime arrays may use `unit="us"` or `"ms"`**, in which case the
division silently over-divides by 10³ or 10⁶. Result: timestamps come
out 1,000–1,000,000× smaller than they should be, and any downstream
comparison against unix-second values fails silently.

**Fix:** use the per-row `.timestamp()` accessor, which always returns
seconds since epoch:

```python
df["open_ts"] = df["open_dt"].apply(lambda x: int(x.timestamp()))
```

Slower than vectorised int conversion, but unambiguous.

### 24. Save raw CLOB responses to a per-market disk cache

The plan recommended this and it pays off twice over for Analysis 3:
the cold run is ~3 min for 628 markets at a polite 0.25s/call, but the
warm run (cache populated) is ~12 s. The on-disk footprint is ~4 MB
across 628 files. Add `data/raw_history/` to `.gitignore` — it's a
cache, not a deliverable.

### 25. Snapshot computation needs unix seconds, not nanoseconds

When pulling the most-recent CLOB tick at or before a target time,
`history[i]["t"]` from the API is a unix-second integer. Make sure
`open_ts`, `close_ts`, and `target_ts` are also unix seconds, not
nanoseconds, milliseconds, or microseconds. (This is just a corollary
of #23.)

### 26. ≥ 4 history observations filter — 18% of dynamics-eligible markets fail

Even after the 5-day duration filter, 116 of 628 markets (18%) have
fewer than 4 CLOB observations — sparse trading on otherwise-eligible
markets. Plan anticipated this; the filter brings the dynamics sample
to 512.

### 27. Late-snapshot slopes blow up because of near-separation, not "more underconfidence"

At the 90% and 95% snapshots, the slope estimate can jump dramatically
(Crypto goes from 1.81 → 22.83 → 16.45). This is **not** evidence that
markets become more underconfident near close. It reflects the data
approaching perfect separation as winners and losers diverge, which
makes the logistic MLE diverge. The bootstrap CI captures the
instability and the `ci_wide` flag is set in the JSON.

**Read late-snapshot BSS as the honest dynamics signal.** Treat the
slope at 90%+ as a near-separation artifact and report it with the
explicit caveat (or skip it visually in any chart that shows the slope
trajectory).

### 28. Per-snapshot BSS denominators differ slightly across snapshots

Because `Var(resolved_yes)` is computed on the markets that have a
non-null price at *that* snapshot (489 at 10%, 511 at 95%), the
baseline shifts slightly. For the BSS *trajectory* this shouldn't
matter much in practice, but it is a real apples-vs-apples nit.
Documented in `methodology.bss_caveat`. A more rigorous version would
fix the denominator to the full 512-market `Var(resolved_yes)` and
recompute BSS at each snapshot using only that subset's prices —
optional refinement.

### 29. Sports markets gain almost no calibration accuracy over their lifetime

A surprising category-level finding: BSS for Sports goes from 0.37
(10% of life) to 0.45 (95% of life), a +0.08 gain. Politics goes from
0.51 to 0.81, a +0.30 gain. Most sports markets resolve on a single
discrete event (a game) where information arrives at game time, not
gradually. The relative-time normalisation can't fix this — it
standardises chronology, not information arrival. This is a *real
finding*, but it reinforces the plan's pitfall #3 caveat that
"50%-elapsed" snapshots aren't semantically comparable across
categories.
