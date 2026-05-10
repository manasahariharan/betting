# Analysis 2: Longshot Bias — Summary

## Question

Do Polymarket bettors systematically overprice low-probability events
(price ≤ 0.15) and underprice heavy favorites (price ≥ 0.85)? Does this
vary by category and market volume?

This is the second of three analyses planned in
`POLYMARKET_PROJECT_PLAN.md` ("Analysis 2 / Deep Dive 1: Longshot Bias").

## Pipeline

| Step | What | Details |
|------|------|---------|
| 1 | Load Analysis 1 dataset | `data/markets_clean.csv` — 1,000 stratified-sampled markets, 806 with CLOB prices |
| 2 | Tail calibration | Fine-grained 0.01-width buckets in `[0, 0.15]` and `[0.85, 1.0]` |
| 3 | Log-odds regression | Logistic regression of `resolved_yes` on `log(p/(1-p))`, prices clipped to `[0.01, 0.99]`, unpenalised MLE (`C=1e9`) |
| 4 | Bootstrap CIs | B=500 market-level resamples (seed=42); also category-stratified bootstrap for the full sample as a robustness check |
| 5 | Volume stratification | Median split (primary) + tertile (robustness) |
| 6 | Per-category | Slope per category when `n_longshots ≥ 15`, otherwise overpricing pp only |
| 7 | Hall of shame / hidden gems | Top 25 most confidently wrong + top 15 longshots that resolved YES |

**No new API calls were made.** Analysis 2 reads the cleaned CSV
produced by Analysis 1 — this is the right move per the
`PLAN_DEVIATIONS_AND_PITFALLS.md` recommendations (avoid re-fetching,
budget for one CLOB pass).

## Headline Numbers (full sample, n=806)

| Metric | Value | 95% CI |
|--------|------:|--------|
| Log-odds slope | **1.350** | [1.181, 1.591] |
| Log-odds intercept | 0.015 | [-0.267, 0.287] |
| Mean overpricing (pp) | +0.19 | — |
| Stratified-bootstrap slope (robustness) | 1.350 | [1.180, 1.617] |

Slope > 1 with a CI that does not cross 1.0. **In log-odds space, the
crowd's prices appear compressed toward 50%** relative to realised
outcomes. This is the direction predicted by the classic
favorite–longshot bias *and* by Le (2026)'s underconfidence finding for
political prediction markets — but it is the opposite of what
Reichenbach & Walther (2025) report for their full Polymarket panel.

The slope is invariant to the sample base rate, which makes the
underconfidence reading robust to the heavy NO skew in the dataset
(244 YES / 806 ≈ 30% YES).

## Tail Behaviour

### Longshots (price ≤ 0.15) — n=420

| Bucket | Predicted | Actual | n |
|--------|-----------|--------|--:|
| 0.00–0.01 | 0.003 | 0.000 |  276 |
| 0.01–0.02 | 0.014 | 0.000 |   46 |
| 0.02–0.03 | 0.024 | 0.000 |   16 |
| 0.03–0.05 | 0.037 | 0.045 |   22 |
| 0.05–0.07 | 0.059 | 0.000 |   17 |
| 0.07–0.10 | 0.086 | 0.000 |   13 |
| 0.10–0.15 | 0.126 | 0.067 |   30 |

- **n YES = 3 / 420** (base rate ≈ 0.7%).
- **Mean overpricing = +1.30 pp** — small. The crowd's longshots
  resolve at roughly the rate they're priced (slightly *over*-priced if
  anything, but the magnitude is on the order of 1pp).
- **No subgroup slope reported** for longshots: the minority class
  share is < 5%, so the logistic MLE diverges (the script flags this
  with a `warning` field and returns `null`).
- Very few "hidden gems": only **1 market in the entire sample**
  priced ≤ 0.10 actually resolved YES (the Matt Gaetz Congressman exit
  at price 0.034). This is the strongest single piece of evidence
  *against* a classical longshot bias on Polymarket — extreme longshots
  are not systematically over-bought.

### Favorites (price ≥ 0.85) — n=94

| Bucket | Predicted | Actual | n |
|--------|-----------|--------|--:|
| 0.85–0.90 | 0.878 | 0.909 | 11 |
| 0.90–0.93 | 0.916 | 1.000 | 10 |
| 0.93–0.95 | 0.941 | 1.000 |  6 |
| 0.95–0.97 | 0.959 | 1.000 | 11 |
| 0.97–0.98 | 0.976 | 1.000 |  5 |
| 0.98–0.99 | 0.986 | 1.000 | 15 |
| 0.99–1.00 | 0.996 | 1.000 | 36 |

- **n YES = 93 / 94** (base rate ≈ 98.9%).
- **Mean underpricing = -2.64 pp** — modestly *underpriced*, in
  the favorite–longshot direction (favorites resolve YES at a slightly
  higher rate than the crowd assigns).
- Subgroup slope omitted for the same separation reason.

The asymmetry — longshots near-perfectly calibrated, favorites
under-priced by ~2.6 pp — is what drives the full-sample slope above 1.

## By-Category (longshot subset)

| Category | n total | n longshots | YES | Overpricing pp | Full-cat slope (CI) | Notes |
|----------|--------:|------------:|----:|---------------:|---------------------|-------|
| **Politics** | 382 | 208 |  2 | +1.04 | **1.27** [1.06, 1.63] | Underconfident; CI excludes 1 |
| **Sports**   | 253 | 109 |  1 | +1.52 | **1.50** [1.19, 2.10] | Most underconfident of the major categories |
| Crypto       |  57 |  36 |  0 | +1.00 | 3.39 [1.77, 65.4] | CI very wide (small n) — flagged |
| Other        |  58 |  26 |  0 | +2.59 | 40.1 [5.2, 64.2]  | CI very wide — flagged |
| Business     |  27 |  16 |  0 | +1.47 | 1.40 [0.90, 84.1] | CI very wide — flagged |
| Pop Culture  |  29 |  25 |  0 | +1.53 | 0.72 [0.34, 23.3] | CI very wide — flagged |

- The two large-n categories (Politics and Sports) both show
  **slopes > 1 with CIs that exclude 1.0**. Underconfidence is the
  consistent direction in this dataset — most pronounced in Sports.
- Smaller categories produce wildly wide CIs and the JSON marks them
  with `ci_wide: true`. Treat their point slopes as indicative only.
- All longshot subgroups have minority-class share under 5%, so the
  longshot-only slope is not estimable; per the plan, only mean
  overpricing pp is reported in those cases.

## Volume Stratification

Median volume in the price-bearing sample = **$58,610.96**.

| Tier | n | Full-tier slope (CI) | Full-tier overpricing pp | Longshot overpricing pp |
|------|--:|----------------------|-------------------------:|------------------------:|
| **Low-vol** (≤ median)  | 403 | **1.51** [1.28, 1.98] | **+1.93** | **+3.09** |
| **High-vol** (> median) | 403 | **1.23** [1.04, 1.55] | **−1.54** | **−0.03** |

- Both tiers' slopes are above 1; **the low-volume tier is more
  underconfident** than the high-volume tier — exactly the pattern
  predicted by the microstructure argument that informed traders move
  prices toward truth (Le 2026; Page & Clemen 2013).
- The longshot-overpricing gap is even sharper: low-volume markets
  overprice longshots by ~3 pp, high-volume markets are essentially flat
  at 0 pp.
- **Tertile robustness:** the trend holds — overpricing pp on
  longshots goes from +3.38 (low) → +0.73 (mid) → +0.24 (high). High-
  volume markets do not exhibit longshot overpricing in this sample.

## Hall of Shame & Hidden Gems

- **Hall of Shame** (top 25 most confidently wrong; sorted by
  `|price − resolved|`): dominated by Politics (16/25), with a long
  tail of Sports, Pop Culture and Business misses. The single biggest
  miss is "Matt Gaetz out as Congressman in 2024?" priced at 0.034 and
  resolving YES (a 96.6 pp miss).
- **Hidden Gems** (priced ≤ 0.10 and resolved YES): only **1 in the
  entire 806-market sample**. This is consistent with the calibration
  table: bins below 0.10 hold 360 markets and just one of them flipped
  YES.

This is the most striking single finding of the analysis. The "Section
3" framing in the plan ("Some of the largest surprises came from
markets that spent most of their lifetime below 10%") will need to lean
on the Matt Gaetz example specifically rather than a population of low-
priced YES outcomes.

## Interpretation (cautious)

Phrasing follows the plan's "Future Improvements" guidance —
"consistent with", "appears", "compatible with" — not "proves" or
"demonstrates".

1. **Across the price range, prices appear compressed toward 50%**
   (slope ≈ 1.35, CI [1.18, 1.59]). This is the classic favorite–
   longshot pattern direction and is consistent with Le (2026)'s
   underconfidence finding for political markets.
2. **The asymmetric driver is the favorite tail, not the longshot
   tail.** Longshots are essentially well calibrated (≤1 pp
   overpriced); favorites are ~2.6 pp underpriced.
3. **Higher-volume markets are closer to calibration than lower-volume
   markets** (slope 1.23 vs 1.51; longshot overpricing 0 pp vs 3 pp).
   This is consistent with — though not proof of — the microstructure
   story that informed traders correct mispricing in liquid markets.
4. **Per-category, Politics and Sports both look underconfident**;
   smaller categories don't have enough mid-range mass to fit a stable
   slope.
5. **Caveat**: pricing behaviour at extremes can also reflect
   adverse selection, settlement-pinning, or attention asymmetry — not
   only behavioural bias (per the plan's pitfall #4).

## Issues Encountered and Mitigations

| Issue | Mitigation |
|-------|------------|
| sklearn 1.8 deprecated `LogisticRegression(penalty=None)` | Use `C=1e9` instead — equivalent unpenalised MLE; suppress sklearn `FutureWarning`/`ConvergenceWarning` to keep the run log readable |
| Logistic MLE diverges on near-separated subsets (favorites are 93/94 YES; longshots are 3/420 YES) | Detect minority-class share < 5% before fitting; return `slope: null` with an explicit `warning` field; only report mean overpricing pp for these subsets |
| Tail subset slopes have astronomical bootstrap CIs when n is small | Add an explicit `ci_wide: true` flag (CI width > 2) to every bootstrap output; downstream visualisation can fade or warn on these |
| Bootstrap independence assumption is dubious for correlated markets (e.g. multiple Senate-race markets) | Report a category-stratified bootstrap on the full sample as a robustness check; document the limitation in the JSON `methodology.bootstrap` field |
| Only 1 hidden gem in the dataset | Document that this is itself a finding (against classical longshot bias on Polymarket); the Section 3 narrative will need to highlight the single Matt Gaetz example rather than a list |
| Per-category longshot subsets all have minority share < 5% → no per-category longshot slope is fittable | Plan anticipated this ("Category-level longshot subsets may be too small for stable regression"); we report `longshot_overpricing_pp` per category and `full_log_odds` slope per category as a substitute |

## Output Files

| File | Size | Contents |
|------|------|----------|
| `output/longshot_data.json` | 6.2 KB | Tail calibration buckets, overpricing pp, full/longshot/favorite log-odds slopes with CIs (regular + category-stratified bootstrap) |
| `output/longshot_volume.json` | 6.5 KB | Median-split (primary) + tertile (robustness) volume stratification, with full-tier and longshot-tier slopes/overpricing |
| `output/longshot_category.json` | 7.6 KB | Per-category longshot bias: counts, overpricing pp, longshot-subset slope (omitted for separation), full-category slope as fallback |
| `output/hall_of_shame.json` | 10.2 KB | Top 25 most confidently wrong markets, with question text, slug, URL, volume, category, end date |
| `output/hidden_gems.json` | 0.6 KB | Single market in our sample priced ≤ 0.10 that resolved YES |
| `output/analysis_2_run.log` | — | Full execution log (clean — warnings filtered) |

## Reproducibility

```bash
pip install -r requirements.txt
# Analysis 1 must already have produced data/markets_clean.csv
python analysis/analysis_2_longshot_bias.py
```

Random seed is `42` for both the stratified sampler in Analysis 1 and
the bootstrap in Analysis 2. Bootstrap B=500 — a deliberate compromise
between CI stability and runtime; results are insensitive to B in
spot-checks. Total wall-clock time for Analysis 2 alone is ~5 seconds.
