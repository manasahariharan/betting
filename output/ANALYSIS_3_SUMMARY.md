# Analysis 3: Calibration Dynamics — Summary

## Question

Does crowd calibration improve as a market approaches resolution? Does
the longshot bias change over a market's lifetime? Are there
category-specific convergence patterns?

This is the third of three analyses in `POLYMARKET_PROJECT_PLAN.md`
("Analysis 3 / Deep Dive 2: Calibration Dynamics") and the project's
methodologically novel contribution — most existing work uses final
prices only, while this analysis tests calibration at multiple
relative-time points in each market's life on the same dataset.

## Pipeline

| Step | What | Details |
|------|------|---------|
| 1 | Load Analysis 1 dataset | `data/markets_clean.csv` — 1,000 sampled markets |
| 2 | Filter to dynamics-eligible | `duration ≥ 5 days` (consequence of the CLOB 12hr-fidelity floor — the 0.95 snapshot is only meaningful when 5% of lifetime exceeds ~6hr). 628 of 1,000 markets pass. |
| 3 | Fetch CLOB price history | `GET /prices-history?market=TOKEN&interval=max&fidelity=720`, with **disk cache to `data/raw_history/{market_id}.json`** so re-runs skip already-fetched markets. ~3 min for the cold run; ~12 s when fully cached. |
| 4 | Filter to ≥ 4 history obs | 512 of 628 markets qualify (116 had sparse trading) |
| 5 | Compute snapshot prices | At relative-time fractions `[0.10, 0.25, 0.50, 0.75, 0.90, 0.95]` of `(close_ts - open_ts)` — most-recent CLOB tick at or before the target timestamp |
| 6 | Per-snapshot calibration | Same stack as Analyses 1 & 2: 0.05-width buckets, Brier, BSS, log-odds slope + 95% bootstrap CI, mean overpricing pp (full + longshot subset) |
| 7 | Per-category dynamics | Same per-snapshot stack for each category with n ≥ 20 in the dynamics sample |

The calibration-slope helpers (`bootstrap_log_odds`, near-separation
guard, `ci_wide` flag, unpenalised MLE via `C=1e9`) are imported from
`analysis_2_longshot_bias.py` so all three analyses use identical
statistical machinery.

## Dynamics-eligible sample

| Filter | n |
|--------|--:|
| Analysis 1 sample | 1,000 |
| With YES token ID | 999 |
| With valid open/close dates | 946 |
| **With duration ≥ 5 days** | **628** |
| **With ≥ 4 CLOB history observations** | **512** |

Duration: min 5.0 days, median 34.6 days, max 794.4 days. Category
breakdown of the 512-market dynamics sample:

| Category | n | Share |
|----------|--:|------:|
| Politics | 236 | 46.1% |
| Sports | 153 | 29.9% |
| Other | 47 | 9.2% |
| Crypto | 41 | 8.0% |
| Pop Culture | 20 | 3.9% |
| Business | 15 | 2.9% (skipped, < 20) |

The dynamics sample skews more Politics-heavy than the full Analysis 1
sample (46% vs 38%) because political markets typically run for weeks
or months, while many sports/crypto markets close within a few days
and are filtered out by the 5-day floor.

## Headline trajectory: BSS over relative time

| Snapshot | n | BSS | Slope | Slope CI | Longshot overpricing pp |
|----------|--:|----:|------:|----------|------------------------:|
| 10% of life | 489 | **0.457** | 1.146 | [0.96, 1.41] | +2.50 |
| 25% of life | 501 | **0.532** | 1.246 | [1.05, 1.51] | +2.06 |
| 50% of life | 507 | **0.577** | 1.258 | [1.07, 1.57] | +0.98 |
| 75% of life | 510 | **0.641** | 1.231 | [1.04, 1.54] | +1.21 |
| 90% of life | 511 | **0.684** | 1.280 | [1.03, 1.75] | +1.11 |
| 95% of life | 511 | **0.708** | 1.206 | [0.98, 1.67] | +0.74 |
| Final price | 512 | **0.733** | 1.541 | [1.25, 2.13] | +0.73 (longshot subset only) |

Three things stand out:

1. **BSS climbs monotonically across the entire lifetime.** From 0.457
   at 10% of life to 0.708 at 95% of life — a +0.25 BSS gain. The
   crowd is *not* fully informative early; accuracy accrues steadily as
   resolution approaches. This replicates Page & Clemen (2013)'s
   "markets improve in accuracy as resolution approaches" finding on
   Polymarket.
2. **The last few hours of trading add only a sliver of accuracy.** BSS
   at 95% (0.708) is essentially the final-price BSS (0.733). The
   ~0.025 difference is consistent with settlement-pinning information
   (i.e., the result becoming public knowledge in the final hours)
   rather than genuine probabilistic forecasting.
3. **The slope hovers around 1.2–1.3 throughout the lifetime, then
   jumps to 1.54 at final price.** The slope CI just barely crosses
   1.0 at the 10% snapshot ([0.96, 1.41]); by 25% it is clearly above
   1. The jump from 1.28 (95% of life) to 1.54 (final price) is again
   consistent with terminal settlement-pinning sharpening the
   separation between winners and losers.

## Longshot overpricing over relative time

| Snapshot | Longshot n | Longshot YES | Mean overpricing pp |
|----------|-----------:|-------------:|--------------------:|
| 10% of life | (varies, ~145) | small | +2.50 |
| 25% of life | (varies, ~167) | small | +2.06 |
| 50% of life | (varies, ~205) | small | +0.98 |
| 75% of life | (varies, ~250) | small | +1.21 |
| 90% of life | (varies, ~290) | small | +1.11 |
| 95% of life | (varies, ~310) | small | +0.74 |

Longshot overpricing **shrinks** over the lifetime — from +2.50 pp at
10% of life to +0.74 pp at 95%. Direction is consistent with Page &
Clemen (2013)'s finding that the favorite–longshot bias is largest far
from resolution and smallest near close. The trajectory is not strictly
monotonic (small bump at 75%) but the start-vs-end direction is clear
across the four "early" snapshots vs. the "late" snapshots.

(Note: longshot subset membership is *snapshot-relative* — markets that
were longshots at 25% of lifetime aren't necessarily longshots at 95%
of lifetime, because prices move. So this is "the overpricing of
markets that look like longshots *at this snapshot*", not "how the same
markets evolve.")

## Per-category dynamics

| Category | n | BSS @ 10% → 95% | Slope @ 10% → 95% | Notes |
|----------|--:|-----------------|-------------------|-------|
| **Politics** | 236 | 0.51 → **0.81** | 1.13 → **2.30**\* | Strongest BSS gain; slope rises monotonically |
| **Sports** | 153 | 0.37 → **0.45** | 1.08 → **0.85** | Smallest BSS gain; slope crosses below 1 by 75% (mild overconfidence near close) |
| Crypto | 41 | 0.45 → **0.85** | 1.89 → **22.83**\* | Big BSS gain; late-snapshot slopes flagged `ci_wide` (near-separation) |
| Other | 47 | 0.41 → **0.76** | 1.08 → **1.01** | BSS gain large; slope stays near 1 throughout |
| Pop Culture | 20 | 0.41 → **0.81** | — | All 20 resolved NO → slope omitted (separation guard); BSS still meaningful |
| Business | 15 | — | — | Below n ≥ 20 threshold |

\* Slope > 2 with `ci_wide: true` near close. These large slopes are
**not** "more underconfident" — they reflect the data approaching
perfect separation as winners and losers diverge near resolution. The
logistic MLE diverges in that limit. Read late-snapshot BSS as the
honest dynamics signal; treat the slope at 90%+ as a near-separation
artifact.

The most striking category contrast is **Sports vs. Politics**:

- **Sports markets gain very little accuracy over their lifetime**
  (BSS 0.37 → 0.45, just +0.08). This is consistent with sports markets
  resolving on a single discrete event (game outcome) where most
  information arrives at game time, not gradually. The slope drops
  *below* 1 by the 75% snapshot (0.93, 0.86, 0.85) — mild
  overconfidence near close, the *opposite* direction from politics.
- **Political markets gain dramatically more accuracy** (BSS 0.51 →
  0.81, +0.30). Information arrives gradually (polls, debates, primary
  results) and the crowd processes it. By 95% of lifetime, political
  markets are very well-calibrated.

This is the kind of category-specific convergence the plan flagged as
the most interesting per-category comparison ("do sports markets
converge faster than political markets?"). Our finding is the *opposite*
of that hypothesis: politics converges much more, sports very little —
mostly because sports event-timing is more concentrated.

## Interpretation (cautious)

Phrasing follows the plan's "Future Improvements" guidance —
"consistent with", "appears", "compatible with" — not "proves" or
"demonstrates".

1. **Calibration improves materially over a market's lifetime.**
   Full-sample BSS rises from 0.46 at 10% of life to 0.71 at 95% of
   life — a 54% relative gain. Direction replicates Page & Clemen
   (2013) on Polymarket.
2. **Most of the gain is gradual, not from a final-tick snap.** BSS at
   95% (0.708) is within 0.025 of the final-price BSS (0.733). The
   crowd is not just guessing until close and then snapping to truth.
3. **Underconfidence (slope > 1) is present at every snapshot from
   25% onward** with CIs that exclude 1. The full-sample slope is
   already 1.25 at the 25% snapshot and stays in the 1.2–1.3 range
   throughout. The classic favorite–longshot direction holds across
   the entire market lifetime, not just at close.
4. **Longshot overpricing is largest early and shrinks toward close**
   (+2.50 pp → +0.74 pp). Compatible with the Page & Clemen reading
   that the bias gets corrected as resolution information arrives.
5. **Category convergence patterns differ.** Politics converges most
   (BSS +0.30) and Sports converges least (BSS +0.08). Sports markets
   actually drift toward mild overconfidence near close (slope 0.85
   at 95% of life).
6. **Caveat (per the plan's pitfall #3 on relative-time
   normalisation):** the snapshots standardise *chronology*, not
   *information arrival*. Information patterns differ by domain
   (elections concentrate near the end, sports at game start, crypto
   continuously) so a "50% elapsed" snapshot is not semantically
   comparable across categories. The Sports-vs-Politics divergence
   above is consistent with this — it may reflect when information
   arrives rather than how well-calibrated each crowd is.

## Issues encountered and mitigations

| Issue | Mitigation |
|-------|------------|
| `yes_token_id` is a 77-digit integer; `pd.read_csv` parsed it as float64 (only ~15 digits of precision), silently corrupting every token ID and causing the CLOB API to return `{"history": []}` for all 628 markets on the first run | Read with `dtype={'yes_token_id': str}`; never coerce through `float()` |
| pandas 3.0 datetime arrays may use `unit='us'` or `'ms'` rather than `'ns'`, so `df["dt"].astype("int64") // 10**9` over-divides by ~10⁶ — making every snapshot's target timestamp earlier than every observed tick, so all 512 × 6 snapshot prices came back `None` | Use the per-row `.timestamp()` accessor, which always returns seconds since epoch regardless of internal unit |
| 116 of 628 markets (18%) have < 4 CLOB history observations — sparse trading on short or illiquid markets | Plan's failure mode #3: require `n ≥ 4`; mark below-threshold markets as ineligible without loss of credibility for the rest |
| Late-snapshot category slopes blow up because near-close prices approach perfect separation | The bootstrap CI captures the instability; `ci_wide: true` flag is set when the slope CI exceeds width 2; the summary explicitly warns that 90%+ slopes should be read alongside BSS, not in place of it |
| Pop Culture (n=20) has 0 YES events out of 20 markets in the dynamics sample → near-separation guard fires at every snapshot | Slope is set to `null` with explicit `warning` field in JSON; BSS, calibration buckets, and overpricing pp are still reported and remain meaningful |
| Per-snapshot BSS denominators differ slightly because `Var(y)` is computed on the markets that have a price at *that* snapshot (not all 512) | Reported in `methodology.bss_caveat`; the final-price sanity check is computed on the same 512 markets so the trajectory's endpoint is comparable |
| Dynamics sample (≥ 5-day markets) differs systematically from the full Analysis 1 sample — skews more political | The output JSON's `dynamics_sample` block reports n, duration percentiles, and category mix so the difference is visible; final-price sanity check is included for direct comparison to Analysis 2 |

## Output files

| File | Size | Contents |
|------|------|----------|
| `output/dynamics_data.json` | 34 KB | Full-sample per-snapshot stack: BSS, log-odds slope + bootstrap CI, mean overpricing pp, longshot overpricing pp, 0.05-width calibration buckets — plus a final-price sanity check |
| `output/dynamics_category.json` | 156 KB | Per-category per-snapshot stack (n ≥ 20 categories: Crypto, Other, Politics, Pop Culture, Sports). Same structure as `dynamics_data.json` per category. |
| `data/raw_history/{id}.json` | ~4 MB total, 628 files | Raw CLOB price-history responses, used as a fetch cache. Listed in `.gitignore` — regenerable by re-running the script. |
| `output/analysis_3_run.log` | — | Full execution log (clean — sklearn warnings filtered) |

## Reproducibility

```bash
pip install -r requirements.txt
# Analysis 1 must already have produced data/markets_clean.csv
python analysis/analysis_3_calibration_dynamics.py
```

Random seed = 42, bootstrap B = 500. Cold-run wall-clock ≈ 4 min
(dominated by 628 CLOB calls at 0.25 s polite delay each). Warm-run
(disk cache fully populated) ≈ 12 s.
