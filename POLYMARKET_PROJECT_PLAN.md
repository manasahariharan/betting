# "How Crowds Get Probability Wrong"

**A Scrollytelling Data Story on Behavioral Biases in Prediction Markets**

Deliverable: GitHub Pages URL · Stack: Python + Observable Plot + Scrollama.js · Target: 2 weekends · Status: Planning

---

## The Story

One scrollable HTML page, NYT/Pudding-style, built around three connected analyses:

1. **Main analysis** — Static calibration: are Polymarket crowds well-calibrated overall, and does miscalibration vary by category?
2. **Deep dive 1** — Longshot bias: do bettors systematically overprice low-probability events?
3. **Deep dive 2** — Calibration dynamics: does crowd accuracy improve as a market approaches resolution?

### Resume line

> "Built scrollytelling data story testing overconfidence, favorite–longshot bias, and calibration dynamics across 600+ resolved Polymarket markets; applied stratified sampling, Brier Skill Score, log-odds regression, and relative-time snapshot analysis; deployed as interactive narrative on GitHub Pages."

---

## Research Context

The empirical picture on Polymarket calibration is contested. Framing the project as testing hypotheses against existing literature — rather than asserting known results — is both more honest and more impressive to a DS interviewer.

| Finding | Source |
|---------|--------|
| No evidence of general longshot bias at market level; tendency to overtrade YES; prices track realized probabilities and slightly outperform bookmaker odds | Reichenbach & Walther (2025), Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket, SSRN 5910522. Dataset: 124M trades, Nov 2021–Sep 2025 |
| Extreme longshots (very low probability) appear to perform consistently well — reverse of classic longshot bias | Reichenbach & Walther (2025), ibid. |
| Dominant miscalibration pattern across Kalshi + Polymarket is persistent underconfidence in political markets — prices compressed toward 50%; domain-level bias replicates on Polymarket but trade-size amplification does not | Le, N.A. (2026), Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets, arXiv:2602.19520. Dataset: 292M trades, 327K contracts |
| Classic favorite–longshot bias worsens with time to expiration; markets are reasonably well calibrated near close but significantly biased for events far in the future | Page, L. & Clemen, R.T. (2013), Do Prediction Markets Produce Well-Calibrated Probability Forecasts?, The Economic Journal, 123(568), 491–513. DOI: 10.1111/j.1468-0297.2012.02561.x |
| Prediction markets improve in accuracy as resolution approaches; accuracy increases as markets come closer to closing | Multiple sources: Page & Clemen (2013); Kalshi accuracy analysis in Makers and Takers: The Economics of the Kalshi Prediction Market (2025), UCD Centre for Economic Research WP2025_19 |
| BSS is not strictly proper as a skill score; however Murphy (1973) proved it is asymptotically proper with large samples | Murphy, A.H. (1973), A New Vector Partition of the Probability Score, Journal of Applied Meteorology and Climatology, 12(4), 595–600 |
| Calibration plot (reliability diagram) decomposes Brier score into reliability and resolution components; logistic regression on log-odds produces a calibration slope interpretable as over/underconfidence | Murphy (1973); Le (2026) — uses log-odds slope as primary calibration measure throughout |

**Your project's contribution:** Most existing work uses final prices only. Testing calibration at multiple relative time points in a market's lifetime — on a stratified, representative sample — directly engages the Page & Clemen (2013) dynamics hypothesis on a newer, larger platform.

---

## Sampling Strategy

### Problem with sorting by volume

Sorting by volume and taking the top N oversamples liquid, high-attention markets (elections, major crypto price levels, major sports) where sophisticated arbitrageurs are most active. This produces a sample biased toward better-calibrated markets, understating the platform's typical miscalibration. The effect is directional: you would make Polymarket look more accurate than it typically is for an average user.

### Stratified sampling by category

```
Full population (all resolved binary markets, volume ≥ $1k)
→ compute category proportions from full population
→ stratified sample, n=600, proportional per category
→ analysis dataset
```

Minimum volume floor ($1k) is a quality filter applied before computing proportions — not a selection criterion. Categories with fewer than 20 sampled markets are merged into "other" for category-level analysis only; they remain in the full-sample calibration.

**Failure mode:** The Gamma API category field is inconsistently labeled ("Sports", "sport", "sports", null). **Mitigation:** lowercase + manual canonical mapping applied at parse time; null categories assigned to "other."

---

## APIs

### Gamma API — market discovery and metadata

| Property | Value |
|----------|-------|
| Base URL | `https://gamma-api.polymarket.com` |
| Auth | None |
| Rate limits | 4,000 req/10s general; `/markets` 300 req/10s |
| Key endpoint | `GET /markets?closed=true&limit=100&offset=N` |
| Returns | `question`, `category`, `outcomePrices`, `volume`, `startDate`, `endDate`, `clobTokenIds` |
| Use for | Full resolved market population; final prices; token IDs for CLOB |
| Resolution detection | Post-resolution `outcomePrices` collapses to `["1.0","0.0"]` or `["0.0","1.0"]`; use YES token price > 0.95 as resolved YES flag |

**Failure mode:** `outcomePrices` is a JSON-stringified list, not a native array. **Mitigation:** parse defensively with try/except; validate YES index against outcomes array before extracting price.

**Failure mode:** Pagination returns empty batch before all markets are fetched if API returns fewer than `limit`. **Mitigation:** stop on empty batch, not on reaching N pages.

### CLOB API — price history

| Property | Value |
|----------|-------|
| Base URL | `https://clob.polymarket.com` |
| Auth | None for read endpoints |
| Rate limits | 1,500 req/10s for market data endpoints |
| Key endpoint | `GET /prices-history?token_id=TOKEN_ID&interval=MAX` |
| Returns | `{history: [{t: unix_timestamp, p: price}, ...]}` |
| Use for | Calibration dynamics: price snapshots at relative time points |

**Critical constraint:** For resolved/closed markets, granularity below 12 hours is unavailable regardless of market activity (confirmed GitHub issue #216, py-clob-client). Use `interval=MAX` to get the coarsest, most complete series. T-1h and T-6h snapshots are not retrievable for closed markets.

**Failure mode:** CLOB returns empty history for some markets (sparse trading, very short markets). **Mitigation:** require ≥ 4 observations in history to include a market in dynamics analysis; mark as `None` otherwise.

**Failure mode:** 429 rate limit errors during bulk fetch of 600 markets. **Mitigation:** exponential backoff with jitter; save raw history to disk after each successful fetch so re-runs don't re-fetch.

### API usage by analysis

| Analysis | API | Est. calls |
|----------|-----|------------|
| Full resolved population fetch | Gamma | ~20–30 pages |
| Final prices + metadata | Gamma | Same batch, no extra calls |
| Price history for dynamics | CLOB | ~600 calls (~10–15 min at polite rate) |

---

## Analysis 1: Main Calibration

### Question

Are Polymarket crowd predictions well-calibrated overall? Does miscalibration vary by category?

### Methods

**Calibration plot (reliability diagram):** Bin markets by final YES price into 0.05-width buckets. For each bucket, compute actual resolution rate. Plot predicted (x) vs. actual (y). Diagonal = perfect calibration.

This is the primary visual for the scrollytelling page. It shows the shape of miscalibration across the full probability range — something no single scalar metric can capture. Murphy (1973) decomposition shows the calibration component of the Brier score is exactly what the reliability diagram visualises.

**Brier Score and Brier Skill Score (BSS):**

```
BS  = mean((predicted - actual)²)
BSS = 1 - BS_model / BS_baseline
```

where `BS_baseline = Var(resolved_yes)`

`Var(resolved_yes)` is algebraically equivalent to the Brier score of a forecaster that always predicts the sample base rate — a valid identity from Murphy (1973), not a shortcut. BSS > 0 = better than naive baseline; BSS < 0 = worse.

**Important caveat (Murphy 1973):** BSS is not strictly proper as a skill score — it is asymptotically proper only with large samples. With ~600 markets this is acceptable; acknowledge in methodology.

Use BSS as the headline summary number in the hero section. It is interpretable to a non-technical reader.

**By-category calibration:** Same calibration plot per category (n ≥ 30 after stratified sample). Directly engages Le (2026)'s finding that calibration is domain-specific, not a platform-wide property.

### Failure modes

| Failure mode | Mitigation |
|--------------|------------|
| Final price reflects outcome signal leaking in, not genuine forecast | Acknowledged in methodology; calibration dynamics deep dive directly tests this by comparing calibration at earlier time points |
| Sparse buckets at extremes (few markets priced at 0.02 or 0.98) | Report n per bucket in JSON; shade or omit buckets with n < 10 in charts |
| Stratified sample happens to be unrepresentative by chance | Report full-population category proportions alongside sample proportions as a sanity check |
| Category n < 30 after sampling | Merge into "other" for category chart; keep in full-sample analysis |

### Outputs

- `calibration_data.json` — calibration buckets, BSS, n, full-sample
- `category_data.json` — per-category calibration curves and BSS

---

## Analysis 2 (Deep Dive 1): Longshot Bias

### Question

Do Polymarket bettors systematically overprice low-probability events (≤15%) and underprice heavy favorites (≥85%)? Does this vary by category and market volume?

### Why not BSS for tail subgroups

BSS has a **baseline sensitivity problem** for subgroup comparisons: `Var(resolved_yes)` on a longshot subset with 8% base rate ≈ 0.074, vs. ~0.25 for the full dataset. A BSS of 0.1 on longshots and 0.1 on favorites does not mean the crowd is equally (mis)calibrated — the denominators are on different scales. Cross-subgroup BSS comparisons are not valid.

### Log-odds regression (calibration slope)

Fit logistic regression of `resolved_yes` on `log_odds(final_price)`:

```python
log_odds_X = log(p / (1 - p))        # clip p to [0.01, 0.99] first
LogisticRegression().fit(log_odds_X.reshape(-1, 1), resolved_yes)
# returns: slope, intercept
```

Interpretation (from Le 2026, who uses this as primary calibration measure):

- **Slope = 1.0, intercept = 0** → perfect calibration
- **Slope < 1.0** → overconfident (prices too extreme from 50%)
- **Slope > 1.0** → underconfident (prices compressed toward 50%) — the classic favorite–longshot bias direction
- **Intercept ≠ 0** → systematic directional bias

This is base-rate-invariant: the slope is on a consistent scale regardless of subset base rate, making cross-group comparison valid. Use bootstrap CIs (500 resamples) to test whether slope differs significantly from 1.0.

### Why both calibration plot and log-odds slope

- **Calibration plot:** shows shape of miscalibration across the tail — primary visual
- **Log-odds slope:** single inferential number, base-rate-invariant, comparable across subgroups — used for category and volume comparisons where calibration plot becomes cluttered

### Mean overpricing (pp)

```python
overpricing_pp = mean(final_price - resolved_yes) × 100
```

Plain-English complement to the slope. Suitable for the scrollytelling narrative ("bettors overpaid by X percentage points on average").

### Volume stratification

Split longshot markets at the median volume into high/low tiers. Run log-odds regression separately per tier. Tests whether sophisticated money corrects the bias — directly connected to the microstructure argument that informed traders move prices toward truth (Le 2026; Page & Clemen 2013).

### Why not log loss

Log loss penalises confident wrong predictions exponentially vs. Brier's quadratic penalty. A log loss skill score has the same baseline sensitivity problem as BSS. For this project: BSS for full-dataset headline (interpretable), log-odds regression for subgroup comparisons (base-rate-invariant). Log loss adds no materially different information.

### Failure modes

| Failure mode | Mitigation |
|--------------|------------|
| Longshot subset may have very few resolved YES events (e.g. 8% base rate × 90 markets ≈ 7 YES events) — bootstrap CI will be very wide | Report n and resolved YES count alongside every slope; flag in narrative if CI crosses 1.0 widely |
| Reverse longshot bias is empirically possible on Polymarket (Reichenbach & Walther 2025 find extreme longshots perform well) | Frame as two-sided test; report slope direction without prejudging; show actual calibration plot before summarising with slope |
| Log-odds undefined at p = 0 or p = 1 | Clip `final_price` to [0.01, 0.99] before computing log-odds |
| Volume median split is arbitrary threshold | Report exact threshold in methodology; run tertile split as robustness check and note if findings change |
| Category-level longshot subsets may be too small for stable regression | Require n ≥ 15 longshot markets per category; otherwise report only mean overpricing pp, not slope |

### Outputs

- `longshot_data.json` — tail calibration buckets, overpricing pp, log-odds slope + bootstrap CI
- `longshot_volume.json` — volume-stratified calibration and slopes
- `longshot_category.json` — per-category longshot bias summary
- `hall_of_shame.json` — top 25 most confidently wrong markets
- `hidden_gems.json` — top 15 markets priced ≤10% that resolved YES

---

## Analysis 3 (Deep Dive 2): Calibration Dynamics

### Question

Does crowd calibration improve as a market approaches resolution? Does the longshot bias change over a market's lifetime? Are there category-specific convergence patterns?

### Why this is analytically distinct

Static calibration studies use a single price snapshot — usually final price. This conflates genuine probabilistic forecasting with resolution signal leaking into the price near close. Testing calibration at multiple points in a market's life answers *when* the crowd becomes accurate, not just *whether* it is accurate overall. Page & Clemen (2013) found the favorite–longshot bias worsens with time to expiration and that markets are significantly biased far from resolution but well-calibrated near close — your project tests whether this holds on Polymarket specifically, using the Le (2026) log-odds slope framework for each time slice.

### Relative time normalisation

Markets have different durations (3 days to 6 months). Wall-clock snapshots (T-24h, T-48h) are not comparable across markets of different length.

**Solution:** Express snapshots as fractions of total market lifetime elapsed:

```python
snapshots = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
# 0.10 = 10% of market life elapsed (early)
# 0.95 = 95% of market life elapsed (near close)

def get_snapshot_price(history, open_ts, close_ts, pct):
    target_ts = open_ts + pct * (close_ts - open_ts)
    before = [(t, p) for t, p in history if t <= target_ts]
    return before[-1][1] if before else None
```

A 3-day and a 6-month market are now on the same relative timeline. The x-axis of the dynamics chart is "% of market life elapsed."

### Critical constraint: 12hr minimum granularity

The CLOB `/prices-history` endpoint returns data at ≥ 12hr granularity for resolved/closed markets (confirmed GitHub issue #216, py-clob-client). Sub-12hr snapshots are not retrievable. Consequence: the 90% and 95% relative-time snapshots are only reliable for markets lasting ≥ 5 days (so that 5% of lifetime ≥ ~6hrs). Apply a minimum market duration of 5 days for inclusion in dynamics analysis. This reduces the dynamics-eligible sample from ~600 to ~300–400 markets.

### What to compute at each snapshot

For each relative time point, you have a `(snapshot_price, resolved_yes)` pair per qualifying market. Run the same analytical stack as the main analysis:

```python
snapshot_results[pct] = {
    "calibration_buckets": [...],
    "bss":                 float,
    "log_odds_slope":      float,
    "log_odds_ci":         [low, high],
    "n_markets":           int,
    "mean_overpricing_pp": float   # longshot subset at this time point
}
```

Three dynamics curves stacked across time:

- **BSS over relative time** — does overall accuracy improve as resolution approaches?
- **Log-odds slope over relative time** — does over/underconfidence change direction or magnitude? (Tests Page & Clemen 2013 directly)
- **Longshot overpricing over relative time** — does the longshot bias get corrected near close, or worsen?

### Category dynamics

Run snapshot analysis per category (n ≥ 20 markets with full history). Key comparison: do sports markets (clear binary outcomes, well-understood by bettors) converge faster than political markets (ambiguous, susceptible to herding as described in Le 2026)?

### Failure modes

| Failure mode | Mitigation |
|--------------|------------|
| ≥12hr granularity floor for closed markets — sub-12hr snapshots unavailable | Use relative time normalisation; enforce minimum 5-day market duration filter |
| Early snapshots (10% of life) are noisy — sparse trading, few price points | Report n per snapshot; treat early-time points as indicative with wider uncertainty bands in chart |
| Markets with sparse early trading have no price at early relative times | Require ≥ 4 observations in full history to qualify; mark individual snapshots as `None` if no observation before target timestamp |
| CLOB 600-market bulk fetch takes 10–15 min; partial failure loses progress | Save raw CLOB response to `data/raw_history/{market_id}.json` after each successful fetch; on re-run, skip already-fetched markets |
| Dynamics sample (≥5 day markets) may differ systematically from full sample | Report dynamics-sample BSS alongside full-sample BSS as a sanity check; note any material difference in methodology |
| Log-odds slope is unstable at early time slices when prices cluster near 0.5 (low-information regime) | Report CI width alongside slope; flag time slices where CI crosses 1.0 by more than 0.3 |

### Outputs

- `dynamics_data.json` — calibration metrics at each relative time snapshot, full dynamics sample
- `dynamics_category.json` — dynamics broken out by category

---

## Frontend: Scrollytelling Page Structure

### Narrative Architecture (3-Section Structure)

The page is organized around three sections that each answer a different question at a different level of abstraction. This avoids conceptual overlap between static calibration, dynamics, category comparisons, and longshot analysis — everything flows through one coherent narrative arc.

| Section | Question |
|---------|----------|
| Section 1 | What are these probabilities? |
| Section 2 | How do these probabilities behave? |
| Section 3 | Where do they break down? |

Each section increases abstraction, broadens scope, and naturally motivates the next question.

---

### SECTION 1 — "What Are Prediction Markets Actually Predicting?"

#### Purpose

Introduce:
- what a market probability means,
- how probabilities evolve,
- and what the project is investigating.

This section establishes the investigative framing:

> "Can these probabilities be interpreted as meaningful forecasts?"

#### Main Questions
- What does a market probability represent?
- Why might prediction markets be interesting to analyze?
- What kinds of mistakes might they make?

#### Visualization

**Main Visual:** Single market timeline — probability evolves over time toward resolution.

Potential annotations:
- News/event markers
- Large swings
- Final outcome

#### Scroll Mechanics

Sticky chart with progressive reveals:
1. Market opens
2. Probabilities fluctuate
3. Event occurs
4. Market resolves

Very lightweight interactions.

**Goal:** Orient the reader, teach the visual language, create curiosity.

**Data source:** `dynamics_data.json` (one illustrative market)

---

### SECTION 2 — "How Do Market Probabilities Behave?" (Analytical Centerpiece)

#### Purpose

This is where the core analysis lives. Calibration, category comparisons, and dynamics all live inside **one coherent visualization system.** Instead of separate sections for each, they become scroll steps within a single persistent chart.

#### Main Questions
- Do market probabilities align with outcomes?
- Does this relationship change over market lifetime?
- Do some categories behave differently?

Importantly: these are **open questions**, not predetermined findings.

#### Visualization System

**Core Visual:** Single calibration chart framework reused throughout the entire section.

The chart itself stays structurally constant:
- Diagonal reference line
- Calibration curve
- Uncertainty band

What changes: the subset/time slice being shown.

#### Scroll Narrative (Steps within Section 2)

**Step 1 — Overall Market**

Show aggregate calibration.

> "At a high level, how closely do probabilities match outcomes?"

**Step 2 — Early vs Late Market Life**

Same chart transitions between early, middle, and late snapshots.

> "Do probabilities behave differently earlier in a market's life?"

This becomes the main narrative arc.

**Step 3 — Category Comparisons**

Allow transitions/toggles between politics, sports, crypto, etc.

> "Do different kinds of markets converge differently?"

#### Supporting Visual (Optional)

Small line chart below: calibration slope over relative time. This acts as a summary metric, not the main visual focus.

#### Scroll Mechanics

One persistent sticky chart container throughout the section. As text scrolls:
- Data subsets change
- Annotations update
- Curves transition smoothly

**Data sources:** `calibration_data.json`, `category_data.json`, `dynamics_data.json`

---

### SECTION 3 — "Where Were Markets Most Surprised?"

#### Purpose

This becomes the ending/exploration section — more human and memorable.

#### Main Questions
- Which events diverged most from market expectations?
- Were there persistent longshot effects?
- Which events produced the largest reversals?

#### Visualization

**Main Visual:** Card/grid layout of notable markets.

Examples:
- Large forecast misses
- Surprising YES resolutions
- Dramatic reversals

Each card includes:
- Sparkline
- Probability path
- Final outcome
- Category

#### Longshot Analysis Lives Here Naturally

Instead of making longshot bias a separate technical/econometric section, integrate it into the "surprising outcomes" framing:

> "Some of the largest surprises came from markets that spent most of their lifetime below 10%."

This preserves the interesting findings without the conceptual clutter.

#### Scroll Mechanics

Lighter interactions:
- Staggered reveals
- Hover expansion
- Fade-ins

No heavy sticky behavior needed. The project should feel less dense by this point.

**Data sources:** `hall_of_shame.json`, `hidden_gems.json`, `longshot_data.json`, `longshot_volume.json`

---

### Chart Set (Aligned to 3-Section Structure)

| # | Chart | Data source |
|---|-------|-------------|
| 1 | **Market timeline** — Single market probability evolution (sticky, progressive reveals) | `dynamics_data.json` |
| 2 | **Unified calibration chart** — One persistent chart transitioning through: overall → early/mid/late snapshots → category comparisons | `calibration_data.json`, `category_data.json`, `dynamics_data.json` |
| 3 | **Calibration slope over relative time** (optional supporting small line chart) | `dynamics_data.json` |
| 4 | **Surprise cards** — Grid layout of notable markets with sparklines and outcomes | `hall_of_shame.json`, `hidden_gems.json` |

### Tech stack

| Tool | Purpose | CDN |
|------|---------|-----|
| Scrollama v3 | Scroll triggers (IntersectionObserver-based, no scroll event polling) | unpkg.com/scrollama |
| Observable Plot | All charts | cdn.jsdelivr.net/npm/@observablehq/plot |
| D3 v7 | Data loading, transitions | cdn.jsdelivr.net/npm/d3 |

No npm, no build step. Single `index.html` + `data/` folder of static JSON.

---

## Pipeline Output Files

| File | Contents | Used by |
|------|----------|---------|
| `markets_clean.csv` | Full cleaned dataset | Local exploration |
| `calibration_data.json` | Calibration buckets, BSS, n | Section 2 (Step 1), hero stats |
| `category_data.json` | Per-category calibration + BSS | Section 2 (Step 3) |
| `longshot_data.json` | Tail buckets, overpricing pp, slope + CI | Section 3 |
| `longshot_volume.json` | Volume-stratified tail calibration | Section 3 |
| `longshot_category.json` | Per-category longshot bias summary | Section 3 text |
| `hall_of_shame.json` | Top 25 most confidently wrong markets | Section 3 |
| `hidden_gems.json` | Top 15 longshots (≤10%) that resolved YES | Section 3 |
| `dynamics_data.json` | Calibration metrics at each relative time snapshot | Sections 1, 2 |
| `dynamics_category.json` | Dynamics by category | Section 2 (Step 3) |

---

## Timeline

### Weekend 1 — Data Pipeline (~7–9 hrs)

| Task | Time |
|------|------|
| Fetch full resolved population + compute stratified sample | 1–2 hrs |
| Parse + clean, build `markets_clean.csv` | 1 hr |
| Main calibration analysis → `calibration_data.json`, `category_data.json` | 1 hr |
| Longshot bias analysis → longshot JSON files, hall of shame, hidden gems | 1–2 hrs |
| CLOB price history fetch for 600 markets (~10–15 min runtime, save raw to disk) | 30 min setup + wait |
| Dynamics analysis → `dynamics_data.json`, `dynamics_category.json` | 1–2 hrs |
| Sanity check all outputs | 30 min |

### Weekend 2 — Frontend (~9–10 hrs)

| Task | Time |
|------|------|
| HTML skeleton + Scrollama setup | 1 hr |
| Section 1 — Market timeline (sticky, progressive reveals) | 1.5 hrs |
| Section 2 — Unified calibration chart with scroll-step transitions (overall → snapshots → categories) | 3 hrs |
| Section 2 — Supporting calibration slope line chart (optional) | 45 min |
| Section 3 — Surprise cards with sparklines | 1.5 hrs |
| Narrative copy + styling | 1.5 hrs |
| GitHub Pages deploy + test | 30 min |

**Scope management:** Ship MVP first (intro timeline + one calibration chart with scroll steps + surprise cards). Layer polish (category transitions, smooth animations, storytelling refinements) after deployment. The deployed artifact matters more than perfect completeness. The 3-section structure is much more achievable than larger multi-section proposals.

---

## Deployment

```
repo: polymarket-overconfidence/
  docs/
    index.html
    data/
      *.json
```

Enable GitHub Pages from `/docs`. Permanent URL: `https://yourusername.github.io/polymarket-overconfidence`

---

## What Makes This Stand Out

- **Stratified sample** makes calibration claims representative of the platform, not just its most liquid markets
- **Log-odds regression with bootstrap CIs** solves the base-rate sensitivity problem of BSS for tail subgroup comparisons — directly adopts Le (2026)'s methodology
- **Relative-time calibration dynamics** is methodologically novel on Polymarket — directly tests the Page & Clemen (2013) time-to-expiration hypothesis on a newer, larger platform
- **Engages contested literature explicitly** — Reichenbach & Walther (2025) find no longshot bias; Le (2026) finds underconfidence in politics; Page & Clemen (2013) find bias worsens with time. Your project tests all three on the same dataset
- **Scrollytelling format** is rare in DS portfolios and signals product sense beyond notebooks
- **One permanent URL** — easy to pull up mid-interview

---

## References

1. Reichenbach, F. & Walther, M. (2025). Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket. SSRN Working Paper 5910522. https://ssrn.com/abstract=5910522
2. Le, N.A. (2026). Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets. arXiv:2602.19520. https://arxiv.org/abs/2602.19520
3. Page, L. & Clemen, R.T. (2013). Do Prediction Markets Produce Well-Calibrated Probability Forecasts? The Economic Journal, 123(568), 491–513. DOI: 10.1111/j.1468-0297.2012.02561.x
4. Murphy, A.H. (1973). A New Vector Partition of the Probability Score. Journal of Applied Meteorology and Climatology, 12(4), 595–600.
5. Polymarket CLOB API — sub-12hr granularity constraint for resolved markets: https://github.com/Polymarket/py-clob-client/issues/216
6. Polymarket Gamma API rate limits and endpoints: https://agentbets.ai/guides/polymarket-gamma-api-guide/ (March 2026)
7. Polymarket API architecture overview: https://chainstack.com/polymarket-api-for-developers/

Stack: Python (requests, pandas, numpy, scikit-learn) · Observable Plot · Scrollama.js · GitHub Pages

---

## Potential Future Improvements and Caveats

This section documents known limitations and high-value enhancements that could strengthen the project in future iterations.

### Statistical Caveats

#### 1. Market Prices Are Not IID Forecasts

Polymarket markets are **not** independent probabilistic forecasts from a stable process. They vary massively in information structure, event ambiguity, insider-information risk, resolution quality, liquidity, market duration, trader composition, and endogenous attention effects. Aggregate calibration curves are therefore mixtures of heterogeneous mechanisms rather than clean evidence about "crowd probability estimation."

**Language guidance:**
- Avoid: "Polymarket crowds are calibrated" or "crowds systematically overprice longshots"
- Prefer: "Across this sampled set of Polymarket markets…", "Observed pricing behavior is consistent with…", "Calibration varies materially by market domain…"

#### 2. Final Prices Are Not Pure Forecasts

Final prices are often contaminated by resolution certainty (known outcome waiting for settlement), oracle timing effects, mechanical pinning near 0/1, settlement conventions, and post-information arbitrage. Reliability diagrams, Brier scores, and calibration slopes may partly measure "how fast information enters the market" rather than "forecasting quality."

**Strongest improvement:** Anchor the main narrative around **dynamics** (how calibration evolves over market lifetime) rather than final-price calibration. Frame the project as "When do prediction markets become calibrated?" rather than the overstudied "Are markets calibrated?"

#### 3. Relative-Time Normalization Has a Hidden Failure Mode

The normalization `pct_elapsed = (t - open) / (close - open)` assumes information arrival scales proportionally with market lifetime. In reality, information arrival patterns differ by domain: elections concentrate information near the end, sports at game start, crypto thresholds continuously, geopolitical events in bursty/jump processes. A 50%-elapsed snapshot is not semantically comparable across market types.

**Acknowledge explicitly:** "Relative-time normalization standardizes chronology, not information arrival." Optional enhancement: augment with volatility-adjusted or trading-activity-normalized time.

#### 4. Longshot-Bias Interpretation Is More Fragile Than Expected

Unlike traditional betting markets, prediction markets have no bookmaker vig, endogenous liquidity, strategic trading and manipulation incentives, tokenized microstructure, and asymmetric participation. Observing slope > 1 or low-probability overpricing does not necessarily imply "behavioral bias" — it may reflect adverse selection, liquidity premia, thin order books, or attention asymmetry.

**Language guidance:**
- Avoid: "bettors are irrational", "crowds are overconfident"
- Prefer: "pricing behavior is consistent with underconfidence", "observed probabilities are compressed toward 50%", "results are compatible with favorite–longshot dynamics"

#### 5. Bootstrap CIs May Be Unstable

With highly imbalanced outcomes, clustered domains, correlated markets, and sparse tails, naive bootstrap resampling may produce unstable or overconfident intervals. At minimum, state: "Confidence intervals assume market-level independence and may understate uncertainty due to correlated event structure." Better: use stratified bootstrap by category.

#### 6. Representative Sampling Claim Is Overstated

Proportional stratified sampling weights by market count, not economic importance, trading activity, or participant exposure. The sample represents "the distribution of listed markets" — not necessarily "the distribution of forecasting activity."

**Enhancement:** Compare equal-market weighting vs. volume-weighted calibration to materially strengthen the project.

#### 7. Data Cleaning Complexity Is Underestimated

Likely issues include duplicated or re-resolved markets, ambiguous resolution wording, missing timestamps and malformed token relationships, merged/split markets and liquidity spikes, and token inversion issues (YES/NO mapping). Before building anything — fetch 100 markets, fully validate schema, manually inspect 20 histories.

### Language & Framing Guidelines

| Avoid | Prefer |
|-------|--------|
| "proves" | "suggests" |
| "demonstrates" | "appears" |
| "shows conclusively" | "consistent with" |
| "markets are" | "may indicate" |
| "traders systematically" | "one possible interpretation" |
| "behavioral biases" | "probabilistic forecast evaluation" |

Resume framing should emphasize "calibration dynamics in decentralized forecasting markets" over "behavioral biases" — sounds more senior/technical.

### Potential Analytical Enhancements

1. **Make dynamics the centerpiece** (most novel, most defensible) — this is already reflected in the narrative structure
2. **Add uncertainty visualization everywhere** — confidence bands, sample sizes, sparse-bin fading
3. **Add sharpness analysis** — forecast entropy distribution or distance-from-0.5 histogram to answer: "Are markets confidently informative, or merely cautious?" This pairs naturally with the underconfidence discussion and is the single highest-value analytical addition
4. **Compare equal-weighted vs volume-weighted calibration** to test whether results change when weighting by economic significance
5. **Be explicit about inferential limitations throughout** — every chart annotation should preserve statistical texture

### Potential Visualization Enhancements

1. **Open with a concrete surprising example** in the hero section rather than abstract metrics (BSS and market counts don't hook readers)
2. **Use small multiples or step-through snapshots** instead of morphing curve animations (morphing is hard to interpret; viewers can't track changes; sparse bin jitter causes visual noise)
3. **Design mobile-first** — fewer bins, no hover dependence, static labels; calibration plots break on small screens
4. **Add micro-explainer visuals** for key concepts (calibration, slope, compression) that are not intuitive to general readers
5. **Add accessibility considerations** — avoid color-only encoding, ensure explicit labels, provide reduced-motion alternatives, maintain high contrast
