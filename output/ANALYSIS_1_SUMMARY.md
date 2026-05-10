# Analysis 1: Main Calibration — Summary

## Question

Are Polymarket crowd predictions well-calibrated overall? Does miscalibration vary by category?

## Pipeline

| Step | What | Details |
|------|------|---------|
| 1 | Fetch markets | `GET /markets?closed=true&include_tag=true` from Gamma API |
| 2 | Filter | Binary outcomes, resolved (outcomePrices near 0/1), volume >= $10k |
| 3 | Categorize | Derive category from tag slugs (Sports, Politics, Crypto, Business, Science, Pop Culture) |
| 4 | Sample | Stratified sample of 1,000, proportional by category |
| 5 | CLOB prices | Fetch last trading price via `GET /prices-history?interval=max&fidelity=720` |
| 6 | Calibrate | 0.05-width bins, Brier Score, BSS, per-category breakdown |

## Data Collected

| Metric | Value |
|--------|-------|
| Raw markets scanned | 19,900 |
| Qualifying (binary, resolved, vol >= $10k) | 10,016 |
| Stratified sample | 1,000 |
| CLOB prices fetched | 806 (81% success) |
| CLOB failures (older pre-CLOB markets) | 194 |
| Date range | Dec 2020 – Jun 2025 |

## Population Category Distribution

| Category | Count | % of Population |
|----------|------:|----------------:|
| Politics | 3,887 | 38.8% |
| Sports | 2,534 | 25.3% |
| Other | 2,321 | 23.2% |
| Crypto | 574 | 5.7% |
| Pop Culture | 299 | 3.0% |
| Business | 271 | 2.7% |
| Science | 130 | 1.3% |

Categories are derived from market tag slugs via `/markets?include_tag=true`. The API's `category` field is empty on most markets — tags are the correct source.

## Calibration Results

### Overall (806 markets)

| Metric | Value |
|--------|-------|
| **Brier Score** | **0.080** |
| **BSS** | **0.621** |
| Resolved YES | 244 (30.3%) |
| Resolved NO | 562 (69.7%) |

BSS = 0.621 means the crowd outperforms the naive base-rate baseline by 62%. BSS is not strictly proper but is asymptotically proper with large samples (Murphy 1973).

### Calibration Table

| Bin | Predicted | Actual | N |
|-----|-----------|--------|---|
| 0.00–0.05 | 0.007 | 0.003 | 360 |
| 0.05–0.10 | 0.070 | 0.000 | 30 |
| 0.10–0.15 | 0.126 | 0.067 | 30 |
| 0.15–0.20 | 0.173 | 0.118 | 17 |
| 0.20–0.25 | 0.228 | 0.231 | 13 |
| 0.25–0.30 | 0.276 | 0.304 | 23 |
| 0.30–0.35 | 0.325 | 0.235 | 17 |
| 0.35–0.40 | 0.376 | 0.333 | 21 |
| 0.40–0.45 | 0.424 | 0.333 | 24 |
| 0.45–0.50 | 0.474 | 0.647 | 17 |
| 0.50–0.55 | 0.510 | 0.543 | 46 |
| 0.55–0.60 | 0.572 | 0.478 | 23 |
| 0.60–0.65 | 0.627 | 0.706 | 17 |
| 0.65–0.70 | 0.672 | 0.833 | 18 |
| 0.70–0.75 | 0.719 | 0.643 | 14 |
| 0.75–0.80 | 0.770 | 0.704 | 27 |
| 0.80–0.85 | 0.830 | 1.000 | 15 |
| 0.85–0.90 | 0.878 | 0.909 | 11 |
| 0.90–0.95 | 0.928 | 1.000 | 18 |
| 0.95–1.00 | 0.987 | 1.000 | 65 |

### By-Category BSS

| Category | N | BSS | Base Rate | Interpretation |
|----------|---|-----|-----------|----------------|
| **Crypto** | 57 | **0.843** | 0.298 | Best calibrated |
| **Politics** | 382 | **0.667** | 0.314 | Well calibrated |
| **Other** | 58 | **0.648** | 0.414 | Well calibrated |
| **Sports** | 253 | **0.482** | 0.289 | Moderately calibrated |
| Business | 27 | — | — | Too few markets (< 30) |
| Pop Culture | 29 | — | — | Too few markets (< 30) |

## Key Findings

1. **Polymarket crowds are substantially better than naive baseline** (BSS = 0.621). Prices carry real forecasting information.

2. **Crypto is the best-calibrated category** (BSS = 0.843). This may be because crypto markets have continuous price feeds and active arbitrageurs keeping probabilities aligned.

3. **Sports is the least well-calibrated** (BSS = 0.482). Sports markets may have more noise from recreational bettors, or the binary-outcome structure of many sports markets (spread bets, over/unders) may compress around 50%.

4. **Heavy concentration at extreme probabilities**: 360 of 806 markets (45%) have last trading prices below 0.05. The distribution is heavily skewed toward confident NO outcomes.

5. **Mid-range bins are noisy**: Bins between 0.15 and 0.70 have small samples and show more deviation from the diagonal — consistent with the plan's caveat about sparse bins.

## Issues Encountered and Mitigations

| Issue | Mitigation |
|-------|------------|
| API `category` field is empty on most markets | Used `tags` array via `include_tag=true` — tags have rich labels (Politics, Sports, Crypto, etc.) |
| API `volume_num_min` filter doesn't work | Applied volume filter client-side after fetching |
| 44k+ total closed markets — too many to fetch all | Capped at ~20k raw scans, targeting 10k qualifying markets |
| `outcomePrices` are post-settlement (0/1), not forecast prices | Fetched pre-resolution prices from CLOB `/prices-history` endpoint |
| CLOB returns empty for resolved markets at < 12hr fidelity | Used `fidelity=720` (12hr) per documented constraint (GitHub issue #216) |
| 194/1000 markets had no CLOB price history | Older pre-CLOB markets excluded; analysis uses the 806 that succeeded |
| Settlement-contaminated final price tick | Used second-to-last price point to avoid post-resolution contamination |

## Output Files

| File | Size | Contents |
|------|------|----------|
| `output/calibration_data.json` | 4.4 KB | Full-sample calibration buckets, BSS, Brier, sampling metadata |
| `output/category_data.json` | 16.4 KB | Per-category calibration for Crypto, Politics, Other, Sports |
| `data/markets_clean.csv` | 308 KB | 1,000 sampled markets with tags, categories, CLOB prices |
| `output/analysis_1_run.log` | — | Full execution log |
