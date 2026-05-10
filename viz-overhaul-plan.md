# Visualization Overhaul Plan — `docs/index.html`

> All line numbers reference the uploaded `index.html` (1212 lines).  
> A companion interactive mockup of all proposed chart states is in `viz-mockup.jsx` — run it in Claude's artifact viewer to click through each scroll step visually before building.

---

## Branch strategy

Work directly on `cursor/frontend-scrollytelling-ef88`. All changes are inside the single `<script>` block (lines 757–1209) and the `<style>` block (lines 8–305). No structural HTML changes are needed except one new section for the category selector (Section 2B) and a `close-date` field in the surprise cards.

---

## Change 1 — Section 1: Replace example market + animate line reveal

### What's wrong
`timelineSteps` (around line 775) is **hardcoded fake data** — 8 points all at ~3.4%, none of which represent real price history. The Matt Gaetz market is a tail-case longshot, which front-loads the "surprise" concept before calibration is introduced. The scrollama callbacks at lines 1172–1185 only toggle two booleans (`timelineVisiblePct`, `timelineShowResolution`) and call `renderTimeline()`, which does a full `el.innerHTML = ""` redraw with no animation.

### New example market
Replace `timelineSteps` with data for **"Will the Fed cut rates before January 2025?"** — a high-volume, well-traveled market that opened near 50%, moved meaningfully in both directions, and resolved YES. Use real price history from `dynamics_category.json` or a dedicated fetch if available; if not, use a realistic synthetic series with the same shape (opens ~48%, dips to ~35% mid-year on sticky inflation data, climbs to ~85% after August CPI print, resolves YES). This teaches "how markets move" rather than "markets can be wrong."

Replace the hardcoded `timelineSteps` array (line 775–783) with:

```js
const timelineSteps = [
  { pct: 0.00, price: 0.48, label: "Open" },
  { pct: 0.08, price: 0.52 },
  { pct: 0.15, price: 0.44 },
  { pct: 0.22, price: 0.41 },
  { pct: 0.30, price: 0.38, note: "Sticky CPI" },
  { pct: 0.40, price: 0.35 },
  { pct: 0.50, price: 0.49 },
  { pct: 0.58, price: 0.61, note: "Inflation cools" },
  { pct: 0.65, price: 0.67 },
  { pct: 0.72, price: 0.74 },
  { pct: 0.80, price: 0.82, note: "Aug CPI print" },
  { pct: 0.88, price: 0.89 },
  { pct: 0.95, price: 0.95 },
  { pct: 1.00, price: 1.00, label: "Resolved YES" },
];
```

Update the four HTML step cards inside `#scrolly-timeline .scrolly__steps` (lines 357–415) to match this market:
- Step `tl-open`: "A market opens at **48%**. The crowd thinks a rate cut is roughly a coin flip."
- Step `tl-mid`: "Through spring, sticky inflation data pushes the price down to **35%**. The market is updating in real time."
- Step `tl-resolve`: "After August's CPI print, the price climbs sharply to **95%**. The Fed cuts in September. Resolved YES."
- Step `tl-question`: unchanged — still pivots to calibration.

### Animated line reveal

Replace `renderTimeline()` (lines 784–832) with a D3-native animated version. The key change: instead of `el.innerHTML = ""` + full redraw, keep a persistent `<svg>` in `#timeline-chart` and mutate it with transitions.

**One-time setup** — call once on init:

```js
function initTimelineChart() {
  const el = document.getElementById("timeline-chart");
  const w = el.clientWidth || 480, h = 320;
  const margin = { top: 20, right: 20, bottom: 40, left: 44 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const svg = d3.select(el).append("svg")
    .attr("width", w).attr("height", h);
  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const xScale = d3.scaleLinear().domain([0, 1]).range([0, iw]);
  const yScale = d3.scaleLinear().domain([0, 1.05]).range([ih, 0]);

  // Grid lines
  g.append("g").attr("class", "tl-grid-y")
    .selectAll("line").data([0, 0.25, 0.5, 0.75, 1]).enter()
    .append("line")
    .attr("x1", 0).attr("x2", iw)
    .attr("y1", d => yScale(d)).attr("y2", d => yScale(d))
    .attr("stroke", "var(--border)").attr("stroke-width", 1);

  // Axes
  g.append("g").attr("class", "tl-axis-x")
    .attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(xScale).ticks(5).tickFormat(d => (d*100)+ "%"))
    .call(ax => ax.select(".domain").remove());
  g.append("g").attr("class", "tl-axis-y")
    .call(d3.axisLeft(yScale).ticks(5).tickFormat(d3.format(".0%")))
    .call(ax => ax.select(".domain").remove());

  // Noise shading rect (hidden initially)
  g.append("rect").attr("class", "tl-noise-zone")
    .attr("x", 0).attr("y", 0).attr("width", iw * 0.65).attr("height", ih)
    .attr("fill", "var(--accent)").attr("opacity", 0);

  // Event vertical line (hidden initially)
  g.append("line").attr("class", "tl-event-line")
    .attr("x1", xScale(0.80)).attr("x2", xScale(0.80))
    .attr("y1", 0).attr("y2", ih)
    .attr("stroke", "var(--orange)").attr("stroke-width", 1.5)
    .attr("stroke-dasharray", "5,3").attr("opacity", 0);
  g.append("text").attr("class", "tl-event-label")
    .attr("x", xScale(0.80) + 5).attr("y", 14)
    .attr("fill", "var(--orange)").attr("font-size", "11px")
    .text("Aug CPI print").attr("opacity", 0);

  // Opening price reference line (hidden initially, step 4)
  g.append("line").attr("class", "tl-open-ref")
    .attr("x1", 0).attr("x2", iw)
    .attr("y1", yScale(0.48)).attr("y2", yScale(0.48))
    .attr("stroke", "var(--orange)").attr("stroke-width", 1)
    .attr("stroke-dasharray", "4,3").attr("opacity", 0);
  g.append("text").attr("class", "tl-open-ref-label")
    .attr("x", 4).attr("y", yScale(0.48) - 5)
    .attr("fill", "var(--orange)").attr("font-size", "10px")
    .text("opened 48%").attr("opacity", 0);

  // Resolution label (hidden initially)
  g.append("text").attr("class", "tl-resolved-label")
    .attr("x", iw - 4).attr("y", yScale(1.00) - 8)
    .attr("fill", "var(--green)").attr("font-size", "10px")
    .attr("text-anchor", "end").text("Resolved YES ✓").attr("opacity", 0);

  // Main path (empty initially)
  g.append("path").attr("class", "tl-line")
    .attr("fill", "none").attr("stroke", "var(--accent)")
    .attr("stroke-width", 2.5).attr("stroke-linejoin", "round");

  // Peak annotation dots group
  g.append("g").attr("class", "tl-peaks");

  // Opening dot
  g.append("circle").attr("class", "tl-open-dot")
    .attr("cx", xScale(0)).attr("cy", yScale(0.48)).attr("r", 6)
    .attr("fill", "var(--accent)").attr("stroke", "var(--bg-card)").attr("stroke-width", 2)
    .attr("opacity", 0);
  g.append("text").attr("class", "tl-open-dot-label")
    .attr("x", xScale(0) + 10).attr("y", yScale(0.48) + 4)
    .attr("fill", "var(--accent)").attr("font-size", "11px").attr("font-weight", 600)
    .text("48%").attr("opacity", 0);

  // Terminal dot
  g.append("circle").attr("class", "tl-terminal-dot")
    .attr("cx", xScale(1)).attr("cy", yScale(1))
    .attr("r", 7).attr("fill", "var(--green)")
    .attr("stroke", "var(--bg-card)").attr("stroke-width", 2).attr("opacity", 0);

  // Store scales on element for use in update function
  el._tlScales = { xScale, yScale, iw, ih };
}
```

**Update function** — called by scrollama instead of `renderTimeline()`:

```js
function updateTimeline(step) {
  const el = document.getElementById("timeline-chart");
  const { xScale, yScale } = el._tlScales;
  const line = d3.line().x(d => xScale(d.pct)).y(d => yScale(d.price)).curve(d3.curveCatmullRom);
  const svg = d3.select(el).select("svg");
  const T = 700; // transition duration ms

  // Which data is visible
  const pctCutoffs = { "tl-open": 0.01, "tl-mid": 0.72, "tl-resolve": 1.0, "tl-question": 1.0 };
  const cutoff = pctCutoffs[step] || 0.01;
  const visible = timelineSteps.filter(d => d.pct <= cutoff);

  // Animate line path
  svg.select(".tl-line").transition().duration(T)
    .attr("d", line(visible));

  // Opening dot — show from step 1
  const showOpen = true;
  svg.select(".tl-open-dot").transition().duration(300).attr("opacity", showOpen ? 1 : 0);
  svg.select(".tl-open-dot-label").transition().duration(300).attr("opacity", showOpen ? 1 : 0);

  // Noise zone shading — step 2+
  svg.select(".tl-noise-zone").transition().duration(T)
    .attr("opacity", step === "tl-mid" || step === "tl-resolve" || step === "tl-question" ? 0.04 : 0);

  // Peak dots — step 2+
  const peakData = step === "tl-open" ? [] : timelineSteps.filter(d => d.note && d.pct <= cutoff);
  const peaks = svg.select(".tl-peaks").selectAll("circle").data(peakData);
  peaks.enter().append("circle")
    .attr("cx", d => xScale(d.pct)).attr("cy", d => yScale(d.price))
    .attr("r", 0).attr("fill", "var(--text-muted)").attr("stroke", "var(--bg-card)").attr("stroke-width", 1.5)
    .transition().duration(400).attr("r", 4);
  peaks.exit().transition().duration(300).attr("r", 0).remove();

  // Event line — step 3+
  const showEvent = step === "tl-resolve" || step === "tl-question";
  svg.select(".tl-event-line").transition().duration(400).attr("opacity", showEvent ? 1 : 0);
  svg.select(".tl-event-label").transition().duration(400).attr("opacity", showEvent ? 1 : 0);

  // Terminal dot — step 3+
  svg.select(".tl-terminal-dot").transition().duration(T)
    .attr("opacity", showEvent ? 1 : 0);
  // Pulse on step 3 entry
  if (step === "tl-resolve") {
    svg.select(".tl-terminal-dot")
      .transition().duration(200).attr("r", 11)
      .transition().duration(300).attr("r", 7);
  }

  // Opening reference line + resolved label — step 4 only
  const showSummary = step === "tl-question";
  svg.select(".tl-open-ref").transition().duration(400).attr("opacity", showSummary ? 0.7 : 0);
  svg.select(".tl-open-ref-label").transition().duration(400).attr("opacity", showSummary ? 1 : 0);
  svg.select(".tl-resolved-label").transition().duration(400).attr("opacity", showSummary ? 1 : 0);
}
```

**Wire into scrollama** — replace the existing callback at lines 1168–1186:

```js
scrollerTimeline.setup({
  step: "#scrolly-timeline .scrolly__step",
  offset: 0.5,
}).onStepEnter(({element}) => {
  document.querySelectorAll("#scrolly-timeline .scrolly__step")
    .forEach(s => s.classList.remove("is-active"));
  element.classList.add("is-active");
  updateTimeline(element.dataset.step);  // ← replaces the old boolean toggles + renderTimeline()
});
```

**Init call** — replace `renderTimeline()` at line 1157 with:

```js
initTimelineChart();
updateTimeline("tl-open");
```

---

## Change 2 — Section 2A: Calibration chart with animated transitions

### What's wrong
`renderCalibration(step)` (lines 895–1020) calls `el.innerHTML = ""` on every scroll step — instant hard swap, no continuity. The dots and line just pop in.

### Fix: transition dots between steps instead of replacing them

The existing `makeCalibrationPlot()` function (lines 835–892) uses Observable Plot, which doesn't support D3 transitions natively. **Switch the calibration chart to raw D3** so transitions can be applied. Keep the same axis structure and data — only the rendering layer changes.

**Replace `makeCalibrationPlot()`** with a persistent D3 chart, similar to the timeline approach:

```js
function initCalibrationChart() {
  const el = document.getElementById("calibration-chart");
  const w = el.clientWidth || 480, h = 420;
  const margin = { top: 20, right: 20, bottom: 50, left: 54 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const xScale = d3.scaleLinear().domain([0, 1]).range([0, iw]);
  const yScale = d3.scaleLinear().domain([0, 1]).range([ih, 0]);

  const svg = d3.select(el).append("svg").attr("width", w).attr("height", h);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  // Grid + axes (static)
  g.append("g").attr("class", "cal-grid-y")
    .selectAll("line").data([0.25, 0.5, 0.75]).enter().append("line")
    .attr("x1", 0).attr("x2", iw)
    .attr("y1", d => yScale(d)).attr("y2", d => yScale(d))
    .attr("stroke", "var(--border)").attr("stroke-width", 1);

  g.append("g").attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(xScale).ticks(5).tickFormat(d3.format(".0%")))
    .call(ax => { ax.select(".domain").remove(); ax.selectAll("text").attr("fill", "var(--text-dim)"); });
  g.append("g")
    .call(d3.axisLeft(yScale).ticks(5).tickFormat(d3.format(".0%")))
    .call(ax => { ax.select(".domain").remove(); ax.selectAll("text").attr("fill", "var(--text-dim)"); });

  // Diagonal reference line (always visible)
  g.append("line").attr("class", "cal-diagonal")
    .attr("x1", xScale(0)).attr("y1", yScale(0))
    .attr("x2", xScale(1)).attr("y2", yScale(1))
    .attr("stroke", "var(--diagonal)").attr("stroke-width", 1.5).attr("stroke-dasharray", "6,4");

  // Underconfidence band (hidden initially, step cal-mid)
  g.append("rect").attr("class", "cal-underconf-band")
    .attr("x", xScale(0.30)).attr("y", 0)
    .attr("width", xScale(0.60) - xScale(0.30)).attr("height", ih)
    .attr("fill", "var(--orange)").attr("opacity", 0);
  g.append("text").attr("class", "cal-underconf-label")
    .attr("x", xScale(0.45)).attr("y", 16).attr("text-anchor", "middle")
    .attr("fill", "var(--orange)").attr("font-size", "11px")
    .text("underconfidence zone").attr("opacity", 0);

  // Good-calibration fill (hidden initially, step cal-final)
  g.append("path").attr("class", "cal-good-fill").attr("fill", "var(--green)").attr("opacity", 0);

  // Connector line between dots
  g.append("path").attr("class", "cal-line")
    .attr("fill", "none").attr("stroke-width", 2).attr("stroke-opacity", 0.5)
    .attr("stroke-linejoin", "round");

  // Dots group
  g.append("g").attr("class", "cal-dots");

  // BSS badge
  const badge = g.append("g").attr("class", "cal-bss-badge")
    .attr("transform", `translate(${iw - 70}, 10)`);
  badge.append("rect").attr("width", 66).attr("height", 28).attr("rx", 5)
    .attr("fill", "var(--bg-card)").attr("stroke", "var(--accent)").attr("stroke-width", 1);
  badge.append("text").attr("class", "cal-bss-label")
    .attr("x", 33).attr("y", 12).attr("text-anchor", "middle")
    .attr("fill", "var(--text-dim)").attr("font-size", "9px").text("BSS");
  badge.append("text").attr("class", "cal-bss-value")
    .attr("x", 33).attr("y", 24).attr("text-anchor", "middle")
    .attr("fill", "var(--accent)").attr("font-size", "12px").attr("font-weight", 700);

  el._calScales = { xScale, yScale, iw, ih };
}
```

**Update function** — replaces `renderCalibration()`:

```js
function updateCalibration(step) {
  const el = document.getElementById("calibration-chart");
  const { xScale, yScale, iw, ih } = el._calScales;
  const svg = d3.select(el).select("svg g");
  const T = 600;

  // Resolve data + color for this step
  const stepConfig = {
    "cal-overall": { data: calibrationData.buckets,                       color: "var(--accent)",  bss: calibrationData.bss },
    "cal-early":   { data: dynamicsData.snapshots["0.10"].calibration_buckets, color: "var(--orange)", bss: dynamicsData.snapshots["0.10"].bss },
    "cal-mid":     { data: dynamicsData.snapshots["0.50"].calibration_buckets, color: "var(--purple)", bss: dynamicsData.snapshots["0.50"].bss },
    "cal-late":    { data: dynamicsData.snapshots["0.90"].calibration_buckets, color: "var(--green)",  bss: dynamicsData.snapshots["0.90"].bss },
    "cal-final":   { data: dynamicsData.final_price_sanity_check.calibration_buckets, color: "var(--accent)", bss: dynamicsData.final_price_sanity_check.bss },
  };
  // cal-category is handled separately (see Change 2B)
  if (step === "cal-category") { renderCategorySelector(); return; }

  const cfg = stepConfig[step];
  const points = bucketsToPoints(cfg.data);  // existing helper, keep as-is
  const sorted = [...points].sort((a, b) => a.predicted - b.predicted);

  const maxN = d3.max(points, d => d.n) || 1;
  const rScale = d => 3 + 5 * Math.sqrt(d.n / maxN);

  // Connector line
  const lineGen = d3.line().x(d => xScale(d.predicted)).y(d => yScale(d.actual)).curve(d3.curveCatmullRom);
  svg.select(".cal-line").transition().duration(T)
    .attr("stroke", cfg.color)
    .attr("d", lineGen(sorted));

  // Dots — key by bin center so D3 can transition existing dots
  const dots = svg.select(".cal-dots").selectAll("circle").data(points, d => d.binCenter);

  dots.enter().append("circle")
    .attr("cx", d => xScale(d.predicted))
    .attr("cy", d => yScale(0.5))   // enter from midpoint, then tween to actual
    .attr("r", 0)
    .attr("fill", cfg.color).attr("fill-opacity", 0.7)
    .attr("stroke", cfg.color).attr("stroke-width", 1)
    .merge(dots)
    .transition().duration(T)
    .attr("cx", d => xScale(d.predicted))
    .attr("cy", d => yScale(d.actual))
    .attr("r", d => rScale(d))
    .attr("fill", cfg.color)
    .attr("stroke", cfg.color);

  dots.exit().transition().duration(300).attr("r", 0).remove();

  // Underconfidence band — only on cal-mid
  svg.select(".cal-underconf-band").transition().duration(400)
    .attr("opacity", step === "cal-mid" ? 0.07 : 0);
  svg.select(".cal-underconf-label").transition().duration(400)
    .attr("opacity", step === "cal-mid" ? 0.8 : 0);

  // Good-calibration fill — only on cal-final
  if (step === "cal-final") {
    const fillPoints = sorted.map(d => [xScale(d.predicted), yScale(d.actual)]);
    const diagPoints = sorted.map(d => [xScale(d.predicted), yScale(d.predicted)]).reverse();
    const pathD = "M" + [...fillPoints, ...diagPoints].map(p => p.join(",")).join("L") + "Z";
    svg.select(".cal-good-fill").transition().duration(T).attr("d", pathD).attr("opacity", 0.06);
  } else {
    svg.select(".cal-good-fill").transition().duration(300).attr("opacity", 0);
  }

  // BSS badge
  svg.select(".cal-bss-value").text((cfg.bss).toFixed(2));
  svg.select(".cal-bss-badge rect").attr("stroke", cfg.color);
  svg.select(".cal-bss-value").attr("fill", cfg.color);
}
```

**Init + wire** — replace lines 1157–1196:

```js
initTimelineChart();
updateTimeline("tl-open");
initCalibrationChart();
updateCalibration("cal-overall");
// ... rest unchanged
scrollerCalibration.onStepEnter(({element}) => {
  document.querySelectorAll("#scrolly-calibration .scrolly__step")
    .forEach(s => s.classList.remove("is-active"));
  element.classList.add("is-active");
  updateCalibration(element.dataset.step);  // ← replaces renderCalibration()
});
```

---

## Change 3 — Section 2B: Replace `cal-category` scroll step with interactive selector

### What's wrong
The last scroll step `cal-category` (HTML lines 490–510, render logic lines 958–1016) shows all category lines statically as a full-redraw. There is no way to explore individual categories or individual markets.

### New design: two-part interactive panel below the scrolly div

**Remove** the `cal-category` scroll step from `#scrolly-calibration .scrolly__steps` entirely (delete the `<div class="scrolly__step" data-step="cal-category">` block, lines ~490–510).

**Add** a new section after `#scrolly-calibration` (after line ~530 in the HTML) and before `#dynamics-section`:

```html
<!-- Category + market selector panel -->
<section id="section-2b-selector">
  <div class="wide-container">
    <div class="section-label">Explore by category</div>
    <h3>Not all categories are equal</h3>
    <p style="max-width:720px;">
      Crypto markets are the best-calibrated (BSS 0.84)—clear binary outcomes,
      quantitative thresholds. Sports lag (BSS 0.48). Politics sits in between (BSS 0.67).
      Select a category to see its calibration curve, then pick a specific market to overlay
      its final price.
    </p>

    <!-- Category toggle buttons -->
    <div class="category-toggles" id="selector-cat-toggles"></div>

    <!-- Category description line -->
    <p id="selector-cat-desc" style="font-size:0.85rem; min-height:1.4em;"></p>

    <!-- Chart -->
    <div class="dynamics-chart-container" style="margin-top:16px;">
      <div id="selector-chart"></div>
    </div>

    <!-- Market search/select -->
    <div style="margin-top:24px;">
      <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:8px;">
        Select a market to overlay its final price on the calibration chart:
      </p>
      <div id="selector-market-list" style="display:flex; flex-direction:column; gap:6px; max-height:320px; overflow-y:auto;"></div>
    </div>
  </div>
</section>
```

**Add CSS** for selected market row (add to `<style>` block):

```css
.selector-market-row {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: border-color 0.2s;
  font-size: 0.85rem;
}
.selector-market-row:hover { border-color: var(--accent-dim); }
.selector-market-row.selected { border-color: var(--accent); background: rgba(88,166,255,0.06); }
.selector-market-outcome {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  flex-shrink: 0;
  margin-left: 12px;
}
```

**JavaScript — `renderCategorySelector()`** (add after `renderCalibration()`):

```js
// Tracks selector state
let selectorActiveCat = "All";
let selectorActiveMarket = null;

function renderCategorySelector() {
  const catEl = document.getElementById("selector-cat-toggles");
  const descEl = document.getElementById("selector-cat-desc");
  const catDescs = {
    "All":      "All 806 markets — solid overall calibration.",
    "Crypto":   "BSS 0.84 — clearest binary thresholds, quantitative outcomes.",
    "Politics": "BSS 0.67 — gradual information incorporation over market lifetime.",
    "Sports":   "BSS 0.48 — information arrives at game time, not gradually.",
    "Other":    "BSS varies — mix of miscellaneous market types.",
  };

  // Build toggle buttons
  const cats = ["All", ...Object.keys(categoryData.categories).filter(c => categoryData.categories[c].n_markets >= 30)];
  catEl.innerHTML = cats.map(c =>
    `<button class="cat-btn ${c === selectorActiveCat ? 'active' : ''}" data-cat="${c}">${c}</button>`
  ).join("");
  catEl.querySelectorAll(".cat-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      selectorActiveCat = btn.dataset.cat;
      selectorActiveMarket = null;
      renderCategorySelector();
    });
  });

  descEl.textContent = catDescs[selectorActiveCat] || "";

  // Render calibration chart for selected category
  renderSelectorChart();

  // Render market list
  renderSelectorMarketList();
}

function renderSelectorChart() {
  const el = document.getElementById("selector-chart");
  el.innerHTML = "";
  const w = el.clientWidth || 880, h = 380;

  // Get points for active category
  let points, color;
  if (selectorActiveCat === "All") {
    points = bucketsToPoints(calibrationData.buckets);
    color = "var(--accent)";
  } else {
    const info = categoryData.categories[selectorActiveCat];
    points = bucketsToPoints(info.buckets, 3);
    color = COLORS[selectorActiveCat] || "var(--accent)";
  }

  // Build as Observable Plot (no animation needed here, it's not scroll-driven)
  let overlayMark = null;
  if (selectorActiveMarket) {
    const m = selectorActiveMarket;
    overlayMark = Plot.dot([m], {
      x: m.final_yes_price,
      y: m.resolved_yes,
      r: 9,
      fill: m.resolved_yes === 1 ? "var(--green)" : "var(--red)",
      stroke: "var(--bg-card)",
      strokeWidth: 2,
      tip: true,
      title: () => `${m.question}\nFinal price: ${(m.final_yes_price*100).toFixed(1)}%\nResolved: ${m.resolved_yes ? "YES" : "NO"}`,
    });
  }

  const plot = Plot.plot({
    width: w, height: h,
    style: { background: "transparent", color: "var(--text-muted)", fontSize: "12px" },
    x: { label: "Predicted probability", domain: [0,1], ticks: [0,.25,.5,.75,1], tickFormat: ".0%" },
    y: { label: "Observed outcome rate", domain: [0,1], ticks: [0,.25,.5,.75,1], tickFormat: ".0%" },
    marks: [
      Plot.line([[0,0],[1,1]], { stroke: "var(--diagonal)", strokeWidth: 1, strokeDasharray: "6,4" }),
      Plot.line(points.sort((a,b) => a.predicted - b.predicted), {
        x: "predicted", y: "actual", stroke: color, strokeWidth: 2.5,
        strokeOpacity: 0.6, curve: "catmull-rom",
      }),
      Plot.dot(points, {
        x: "predicted", y: "actual",
        fill: color, r: d => 3 + 5 * Math.sqrt(d.n / (d3.max(points, p => p.n) || 1)),
        fillOpacity: 0.7, tip: true,
        title: d => `Predicted: ${(d.predicted*100).toFixed(1)}%\nActual: ${(d.actual*100).toFixed(1)}%\nn=${d.n}`,
      }),
      ...(overlayMark ? [overlayMark] : []),
    ],
  });
  el.appendChild(plot);
}

function renderSelectorMarketList() {
  const el = document.getElementById("selector-market-list");

  // Use hall_of_shame.markets + hidden_gems.markets as the browsable set
  // Filter by category if not "All"
  let markets = [...(hallOfShame.markets || []), ...(hiddenGems.markets || [])];
  if (selectorActiveCat !== "All") {
    markets = markets.filter(m => m.category === selectorActiveCat);
  }
  markets = markets.slice(0, 30); // cap list length

  el.innerHTML = markets.map((m, i) => {
    const isSelected = selectorActiveMarket && selectorActiveMarket.question === m.question;
    const isYes = m.resolved_yes === 1;
    const priceColor = (isYes && m.final_yes_price < 0.5) || (!isYes && m.final_yes_price > 0.5)
      ? "var(--red)" : "var(--green)";
    return `
      <div class="selector-market-row ${isSelected ? 'selected' : ''}" data-idx="${i}">
        <span>${m.question}</span>
        <span class="selector-market-outcome" style="color:${priceColor}">
          ${(m.final_yes_price*100).toFixed(0)}% → ${isYes ? "YES" : "NO"}
        </span>
      </div>
    `;
  }).join("");

  el.querySelectorAll(".selector-market-row").forEach((row, i) => {
    row.addEventListener("click", () => {
      selectorActiveMarket = selectorActiveMarket?.question === markets[i].question ? null : markets[i];
      renderCategorySelector();
    });
  });
}
```

**Init call** — add after `renderDynamicsChart()` at line 1161:

```js
renderCategorySelector();
```

---

## Change 4 — Section 2C: Animate dynamics lines on scroll entry

### What's wrong
`renderDynamicsChart()` (lines 1055–1102) renders all lines simultaneously with no animation. The toggle buttons exist but the chart has no entry animation.

### Fix: staggered line draw on first scroll entry using `stroke-dasharray` trick

The existing `Plot.plot()` call for dynamics can stay, but wrap it in a scroll-triggered reveal. Since Observable Plot doesn't expose individual path elements easily, **switch `renderDynamicsChart()` to D3** for the line drawing, keeping the same data from `buildDynamicsData()`.

Add a flag and an IntersectionObserver:

```js
let dynamicsAnimated = false;

function renderDynamicsChart() {
  const el = document.getElementById("dynamics-line-chart");
  el.innerHTML = "";
  const w = el.clientWidth || 880, h = 400;
  const margin = { top: 20, right: 100, bottom: 50, left: 54 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const allRows = buildDynamicsData();  // existing function, unchanged
  const filtered = allRows.filter(d => activeDynCats.has(d.category));

  const xScale = d3.scaleLinear().domain([0.1, 0.95]).range([0, iw]);
  const yScale = d3.scaleLinear()
    .domain([0, d3.max(filtered, d => d.bss) * 1.1 || 1]).range([ih, 0]);

  const svg = d3.select(el).append("svg").attr("width", w).attr("height", h);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  // Grid + axes (unchanged logic)
  g.append("g").call(d3.axisLeft(yScale).ticks(5).tickFormat(d3.format(".0%")))
    .call(ax => { ax.select(".domain").remove(); ax.selectAll("text").attr("fill","var(--text-dim)"); });
  g.append("g").attr("transform",`translate(0,${ih})`)
    .call(d3.axisBottom(xScale).tickValues([0.1,0.25,0.5,0.75,0.9,0.95]).tickFormat(d => (d*100)+"%"))
    .call(ax => { ax.select(".domain").remove(); ax.selectAll("text").attr("fill","var(--text-dim)"); });

  const categories = [...new Set(filtered.map(d => d.category))];
  const lineGen = d3.line().x(d => xScale(d.pct)).y(d => yScale(d.bss)).curve(d3.curveCatmullRom);

  // Draw each category line with staggered animation
  categories.forEach((cat, i) => {
    const catData = filtered.filter(d => d.category === cat).sort((a,b) => a.pct - b.pct);
    const color = COLORS[cat] || "#8b949e";
    const strokeW = cat === "All" ? 3 : 2;

    const path = g.append("path")
      .datum(catData)
      .attr("fill", "none")
      .attr("stroke", color)
      .attr("stroke-width", strokeW)
      .attr("d", lineGen);

    // Animate using stroke-dasharray trick
    const totalLength = path.node().getTotalLength();
    path.attr("stroke-dasharray", totalLength)
      .attr("stroke-dashoffset", dynamicsAnimated ? 0 : totalLength);

    if (!dynamicsAnimated) {
      path.transition()
        .delay(i * 150)          // 150ms stagger per category
        .duration(800)
        .attr("stroke-dashoffset", 0);
    }

    // End-of-line label
    const lastPt = catData[catData.length - 1];
    const gain = ((lastPt.bss - catData[0].bss) * 100).toFixed(0);
    g.append("text")
      .attr("x", xScale(lastPt.pct) + 8)
      .attr("y", yScale(lastPt.bss) + 4)
      .attr("fill", color).attr("font-size", "11px").attr("font-weight", 600)
      .text(cat)
      .attr("opacity", dynamicsAnimated ? 1 : 0)
      .transition().delay(i * 150 + 800).duration(300)
      .attr("opacity", 1);

    // "info arrives at game time" annotation for Sports
    if (cat === "Sports") {
      g.append("text")
        .attr("x", xScale(0.5))
        .attr("y", yScale(lastPt.bss) - 12)
        .attr("text-anchor", "middle")
        .attr("fill", color).attr("font-size", "10px").attr("opacity", 0)
        .text("info arrives at game time")
        .transition().delay(i * 150 + 1100).duration(400)
        .attr("opacity", 0.75);
    }

    // Dots
    g.selectAll(`.dot-${cat.replace(/\s/g,"")}`)
      .data(catData).enter().append("circle")
      .attr("cx", d => xScale(d.pct)).attr("cy", d => yScale(d.bss))
      .attr("r", 4).attr("fill", color).attr("stroke","var(--bg-card)").attr("stroke-width",1.5)
      .attr("opacity", 0)
      .transition().delay(i * 150 + 800).duration(300).attr("opacity", 1);
  });

  dynamicsAnimated = true;
}
```

**Reset `dynamicsAnimated = false`** when toggle buttons are clicked (in `renderDynamicsToggles()`, line 1105) so toggling a category re-draws with animation:

```js
// In the click handler inside renderDynamicsToggles():
btn.addEventListener("click", () => {
  const cat = btn.dataset.cat;
  if (activeDynCats.has(cat)) activeDynCats.delete(cat);
  else activeDynCats.add(cat);
  dynamicsAnimated = false;  // ← add this line
  renderDynamicsToggles();
  renderDynamicsChart();
});
```

**Trigger animation on scroll entry** using IntersectionObserver (add after `renderDynamicsChart()` init call):

```js
const dynamicsObserver = new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && !dynamicsAnimated) {
    renderDynamicsChart();
  }
}, { threshold: 0.3 });
dynamicsObserver.observe(document.getElementById("dynamics-line-chart"));
```

---

## Change 5 — Section 3: Add close date + animated surprise table

### What's wrong
`renderSurpriseCards()` (lines 1128–1154) renders `.market-card` divs with no date and no animation. The `hallOfShame` JSON has a `end_date` or `close_time` field on each market object — the format depends on your data pipeline but it will be either a Unix timestamp or ISO string.

### Add close date to card HTML

Inside `renderSurpriseCards()`, update the card template. The existing template is at lines 1135–1151. Add a formatted close date next to the volume line:

```js
// Add this helper above renderSurpriseCards():
function formatCloseDate(m) {
  // Try common field names from Polymarket data
  const ts = m.end_date || m.close_time || m.end_date_iso;
  if (!ts) return "";
  const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
```

In the card template, replace line 1148:

```js
// BEFORE:
`${formatVolume(m.volume)} volume &middot; ${(surprise * 100).toFixed(0)}pp miss`

// AFTER:
`${formatVolume(m.volume)} volume &middot; ${(surprise * 100).toFixed(0)}pp miss &middot; <span style="color:var(--text-dim)">${formatCloseDate(m)}</span>`
```

### Animate cards on scroll entry

Replace the static grid with a stagger-animated reveal. Add CSS:

```css
.market-card {
  /* existing styles unchanged, add: */
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.4s ease, transform 0.4s ease, border-color 0.3s;
}
.market-card.card-visible {
  opacity: 1;
  transform: translateY(0);
}
```

After `renderSurpriseCards()` populates `#surprise-cards`, trigger staggered reveal with IntersectionObserver:

```js
function observeSurpriseCards() {
  const cards = document.querySelectorAll("#surprise-cards .market-card");
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const i = [...cards].indexOf(entry.target);
        setTimeout(() => entry.target.classList.add("card-visible"), i * 60);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  cards.forEach(card => observer.observe(card));
}

// Call after renderSurpriseCards():
renderSurpriseCards();
observeSurpriseCards();
```

### Longshot dot-plot (optional addition)

This is a net-new chart that doesn't exist yet. If adding it, insert a `<div id="longshot-dotplot"></div>` before `#surprise-cards` (after line ~620 in the HTML) and add the following render function using `longshotData` and `longshotVolume` (already loaded at line 769):

```js
function renderLongshotDotplot() {
  const el = document.getElementById("longshot-dotplot");
  if (!el || !longshotData) return;
  // longshotData.markets is assumed to be an array of { predicted, actual_rate, volume }
  // Plot: x = predicted (0–0.15), y = jitter, dot size = volume tier
  const plot = Plot.plot({
    width: el.clientWidth || 880, height: 180,
    style: { background: "transparent", color: "var(--text-muted)", fontSize: "12px" },
    x: { label: "Predicted probability", domain: [0, 0.15], tickFormat: ".0%" },
    y: { axis: null },
    marks: [
      Plot.dot(longshotData.markets, Plot.dodgeY({
        x: "predicted",
        fill: d => d.occurred ? "var(--green)" : (d.volume_tier === "high" ? "var(--text-dim)" : "var(--border)"),
        r: d => d.volume_tier === "high" ? 5 : 3.5,
        fillOpacity: 0.8,
        tip: true,
        title: d => `${d.question || ""}\n${(d.predicted*100).toFixed(1)}% predicted\n${d.occurred ? "Occurred" : "Did not occur"}`,
      })),
    ],
  });
  el.appendChild(plot);
}
```

---

## Summary of all function-level changes

| Function | Action |
|---|---|
| `timelineSteps` (line 775) | Replace hardcoded data with Fed rate cut series |
| `renderTimeline()` (line 784) | Replace with `initTimelineChart()` + `updateTimeline(step)` |
| `makeCalibrationPlot()` (line 835) | Keep for category selector; add `initCalibrationChart()` + `updateCalibration(step)` |
| `renderCalibration()` (line 895) | Keep for category selector fallback; primary path now via `updateCalibration()` |
| Scroll step `cal-category` HTML (line ~490) | Remove from scrolly steps |
| New `#section-2b-selector` HTML | Add after `#scrolly-calibration` |
| `renderCategorySelector()` | Add new function |
| `renderSelectorChart()` | Add new function |
| `renderSelectorMarketList()` | Add new function |
| `renderDynamicsChart()` (line 1055) | Rewrite with D3 + stagger animation |
| `renderDynamicsToggles()` (line 1104) | Add `dynamicsAnimated = false` on click |
| `renderSurpriseCards()` (line 1128) | Add `formatCloseDate()` + close date in template |
| `observeSurpriseCards()` | Add new function |
| `renderLongshotDotplot()` | Add new function (optional) |
| Init block (line 1157) | Replace `renderTimeline()` with `initTimelineChart(); updateTimeline("tl-open")` |
| Init block (line 1158) | Replace `renderCalibration("cal-overall")` with `initCalibrationChart(); updateCalibration("cal-overall")` |

---

## Visual reference

The `viz-mockup.jsx` artifact shows all five proposed chart states interactively:
- **§1 Market Timeline** — 4 step buttons simulate scroll; shows opening dot → noisy middle with shading → event line + pulsing terminal dot → summary with gap annotation
- **§2A Calibration Steps** — 5 step buttons; dots tween position between steps, underconfidence band fades in on step 3, green fill on step 5
- **§2B Category Selector** — category toggle buttons update curve + BSS; market list overlays a dot on the calibration chart
- **§2C Dynamics Lines** — 3 reveal buttons simulate staggered line draw; Sports gets flat-line annotation
- **§3 Longshots** — dot-plot with volume sizing + overpricing bracket; surprise table with month/year column + animated background bars
