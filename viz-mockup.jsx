import { useState, useEffect, useRef } from "react";

const DARK = "#0f1117";
const CARD = "#181c27";
const BORDER = "#2a2f3f";
const TEXT = "#e2e8f0";
const MUTED = "#8892a4";
const ACCENT = "#6ee7b7";
const AMBER = "#fbbf24";
const BLUE = "#60a5fa";
const RED = "#f87171";
const PURPLE = "#a78bfa";

// ─── helpers ───────────────────────────────────────────────────────────────
function lerp(a, b, t) { return a + (b - a) * t; }

function SectionLabel({ n, title }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
      <span style={{ fontFamily: "monospace", fontSize: 11, color: MUTED, background: "#23293a", padding: "2px 8px", borderRadius: 4, letterSpacing: 1 }}>SECTION {n}</span>
      <span style={{ fontSize: 13, color: MUTED }}>{title}</span>
    </div>
  );
}

function StepNav({ steps, current, onStep }) {
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
      {steps.map((s, i) => (
        <button key={i} onClick={() => onStep(i)}
          style={{
            padding: "5px 13px", borderRadius: 20, border: `1px solid ${i === current ? ACCENT : BORDER}`,
            background: i === current ? ACCENT + "22" : "transparent",
            color: i === current ? ACCENT : MUTED, fontSize: 12, cursor: "pointer", transition: "all .2s"
          }}>
          {s}
        </button>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SECTION 1 — Market Timeline
// ══════════════════════════════════════════════════════════════════════════
const FED_DATA = [
  { t: 0,   p: 48, label: "Opens 48%" },
  { t: 0.08, p: 52 },
  { t: 0.16, p: 44 },
  { t: 0.24, p: 41 },
  { t: 0.31, p: 55, peak: true },
  { t: 0.40, p: 49 },
  { t: 0.48, p: 38 },
  { t: 0.55, p: 61, peak: true },
  { t: 0.63, p: 67 },
  { t: 0.70, p: 72 },
  { t: 0.77, p: 78 },
  { t: 0.83, p: 85, event: true, label: "CPI data drops" },
  { t: 0.90, p: 92 },
  { t: 0.96, p: 97 },
  { t: 1.00, p: 100, label: "Resolved YES" },
];

function Section1() {
  const [step, setStep] = useState(0);
  const W = 520, H = 280, PL = 48, PR = 20, PT = 20, PB = 40;
  const IW = W - PL - PR, IH = H - PT - PB;

  const xOf = d => PL + d.t * IW;
  const yOf = d => PT + (1 - d.p / 100) * IH;

  const steps = ["1. Opens", "2. Fluctuates", "3. Event", "4. Summary"];
  const visibleCount = [1, 10, 13, 15][step];
  const visible = FED_DATA.slice(0, visibleCount);

  const pathD = visible.length > 1
    ? visible.map((d, i) => `${i === 0 ? "M" : "L"}${xOf(d).toFixed(1)},${yOf(d).toFixed(1)}`).join(" ")
    : null;

  const openingP = FED_DATA[0].p;
  const openingY = yOf(FED_DATA[0]);
  const eventPoint = FED_DATA.find(d => d.event);
  const lastPoint = visible[visible.length - 1];

  return (
    <div>
      <SectionLabel n={1} title="Market Timeline — Fed Rate Cut 2024" />
      <StepNav steps={steps} current={step} onStep={setStep} />
      <svg width={W} height={H} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, display: "block" }}>
        {/* grid */}
        {[0, 25, 50, 75, 100].map(v => {
          const y = PT + (1 - v / 100) * IH;
          return <g key={v}>
            <line x1={PL} x2={PL + IW} y1={y} y2={y} stroke="#1e2535" strokeWidth={1} />
            <text x={PL - 6} y={y + 4} textAnchor="end" fill={MUTED} fontSize={10}>{v}%</text>
          </g>;
        })}
        {/* x axis */}
        <line x1={PL} x2={PL + IW} y1={PT + IH} y2={PT + IH} stroke={BORDER} strokeWidth={1} />
        {["Jan", "Apr", "Jul", "Oct", "Dec"].map((m, i) => {
          const x = PL + (i / 4) * IW;
          return <text key={m} x={x} y={PT + IH + 16} textAnchor="middle" fill={MUTED} fontSize={10}>{m}</text>;
        })}

        {/* opening horizontal ref line (step 4) */}
        {step === 3 && (
          <g>
            <line x1={PL} x2={PL + IW} y1={openingY} y2={openingY} stroke={AMBER} strokeWidth={1} strokeDasharray="4 3" opacity={0.7} />
            <text x={PL + 4} y={openingY - 5} fill={AMBER} fontSize={10}>opened {openingP}%</text>
            <text x={PL + IW - 4} y={yOf(FED_DATA[FED_DATA.length - 1]) - 8} textAnchor="end" fill={ACCENT} fontSize={10}>resolved YES ✓</text>
          </g>
        )}

        {/* middle noise shading (step 2+) */}
        {step >= 1 && (
          <rect x={PL} y={PT} width={IW * 0.75} height={IH} fill="#2a2f3f" opacity={0.25} />
        )}

        {/* event vertical line (step 3+) */}
        {step >= 2 && eventPoint && (
          <g>
            <line x1={xOf(eventPoint)} x2={xOf(eventPoint)} y1={PT} y2={PT + IH} stroke={AMBER} strokeWidth={1.5} strokeDasharray="5 3" />
            <text x={xOf(eventPoint) + 4} y={PT + 14} fill={AMBER} fontSize={10}>{eventPoint.label}</text>
          </g>
        )}

        {/* main line */}
        {pathD && (
          <path d={pathD} fill="none" stroke={ACCENT} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        )}

        {/* peak annotations (step 2+) */}
        {step >= 1 && visible.filter(d => d.peak).map((d, i) => (
          <circle key={i} cx={xOf(d)} cy={yOf(d)} r={4} fill={MUTED} stroke={CARD} strokeWidth={1.5} />
        ))}

        {/* opening dot (step 1+) */}
        {step >= 0 && (
          <g>
            <circle cx={xOf(FED_DATA[0])} cy={yOf(FED_DATA[0])} r={6} fill={ACCENT} stroke={CARD} strokeWidth={2} />
            <text x={xOf(FED_DATA[0]) + 10} y={yOf(FED_DATA[0]) + 4} fill={ACCENT} fontSize={11} fontWeight="600">48%</text>
          </g>
        )}

        {/* terminal dot (step 3+) */}
        {step >= 2 && (
          <g>
            <circle cx={xOf(lastPoint)} cy={yOf(lastPoint)} r={7} fill={ACCENT} stroke={CARD} strokeWidth={2} />
            {step >= 3 && <text x={xOf(lastPoint) - 6} y={yOf(lastPoint) - 12} fill={ACCENT} fontSize={10} textAnchor="middle">YES</text>}
          </g>
        )}

        {/* title */}
        <text x={PL} y={14} fill={TEXT} fontSize={11} fontWeight="600">Will the Fed cut rates in 2024?</text>
      </svg>
      <p style={{ fontSize: 12, color: MUTED, marginTop: 8 }}>
        {[
          "Step 1: Opening dot appears with price label. Nothing else visible yet.",
          "Step 2: Line animates forward through the noisy middle. Peaks get subtle dots. Shaded region marks uncertainty zone.",
          "Step 3: Vertical dashed line drops at the CPI data event. Line continues to resolution. Terminal dot pulses.",
          "Step 4: Full chart frozen. Horizontal dashed line at opening price shows the gap between 'opened at 48%' and 'resolved YES'.",
        ][step]}
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SECTION 2A — Calibration Chart stepped
// ══════════════════════════════════════════════════════════════════════════
function makeCalibCurve(slope, noise, offset = 0) {
  return [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map(x => {
    const ideal = x;
    const compressed = 50 + (x - 50) * slope;
    const actual = lerp(ideal, compressed, 0.6) + offset + (Math.random() - 0.5) * noise;
    return { x, y: Math.max(0, Math.min(100, actual)) };
  });
}

// deterministic curves
const CURVES = {
  overall:  [0,7,16,26,35,46,57,67,76,86,96].map((y,i)=>({x:i*10,y})),
  t10:      [0,10,19,27,34,44,52,61,70,80,93].map((y,i)=>({x:i*10,y})),
  t50:      [0,8,17,29,38,48,56,65,74,83,95].map((y,i)=>({x:i*10,y})),
  t90:      [0,7,16,27,36,47,58,68,77,88,97].map((y,i)=>({x:i*10,y})),
  final:    [0,6,15,26,36,47,58,69,78,89,98].map((y,i)=>({x:i*10,y})),
  crypto:   [0,5,14,25,36,48,60,71,81,91,99].map((y,i)=>({x:i*10,y})),
  sports:   [0,12,21,30,38,47,55,63,71,80,91].map((y,i)=>({x:i*10,y})),
  politics: [0,8,17,27,37,48,58,68,77,87,96].map((y,i)=>({x:i*10,y})),
};

const STEP_META = [
  { key: "overall",  color: ACCENT,  bss: "0.62", label: "Overall" },
  { key: "t10",      color: BLUE,    bss: "0.46", label: "10% elapsed" },
  { key: "t50",      color: AMBER,   bss: "0.58", label: "50% elapsed" },
  { key: "t90",      color: PURPLE,  bss: "0.68", label: "90% elapsed" },
  { key: "final",    color: ACCENT,  bss: "0.73", label: "Final prices" },
];

function Section2A() {
  const [step, setStep] = useState(0);
  const W = 520, H = 280, PL = 48, PR = 20, PT = 20, PB = 40;
  const IW = W - PL - PR, IH = H - PT - PB;

  const xOf = v => PL + (v / 100) * IW;
  const yOf = v => PT + (1 - v / 100) * IH;

  const stepNames = ["1. Overall", "2. Early (10%)", "3. Midlife (50%)", "4. Late (90%)", "5. Final"];
  const meta = STEP_META[step];
  const prevMeta = step > 0 ? STEP_META[step - 1] : null;

  function curvePath(key) {
    const pts = CURVES[key];
    return pts.map((d, i) => `${i === 0 ? "M" : "L"}${xOf(d.x).toFixed(1)},${yOf(d.y).toFixed(1)}`).join(" ");
  }

  // fill between curve and diagonal for final step
  function fillPath(key) {
    const pts = CURVES[key];
    const upper = pts.map((d, i) => `${i === 0 ? "M" : "L"}${xOf(d.x).toFixed(1)},${yOf(d.y).toFixed(1)}`).join(" ");
    const lower = [...pts].reverse().map((d, i) => `${i === 0 ? "M" : "L"}${xOf(d.x).toFixed(1)},${yOf(d.x).toFixed(1)}`).join(" ");
    return upper + " " + lower + " Z";
  }

  const showUnderconfidence = step === 2;
  const showFill = step === 4;

  return (
    <div>
      <SectionLabel n={2} title="Calibration Chart — Scroll Steps" />
      <StepNav steps={stepNames} current={step} onStep={setStep} />
      <svg width={W} height={H} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, display: "block" }}>
        {/* grid */}
        {[0,25,50,75,100].map(v => (
          <g key={v}>
            <line x1={PL} x2={PL+IW} y1={yOf(v)} y2={yOf(v)} stroke="#1e2535" strokeWidth={1}/>
            <text x={PL-6} y={yOf(v)+4} textAnchor="end" fill={MUTED} fontSize={10}>{v}%</text>
            <text x={xOf(v)} y={PT+IH+16} textAnchor="middle" fill={MUTED} fontSize={10}>{v}%</text>
          </g>
        ))}
        <line x1={PL} x2={PL+IW} y1={PT+IH} y2={PT+IH} stroke={BORDER}/>
        <line x1={PL} x2={PL} y1={PT} y2={PT+IH} stroke={BORDER}/>

        {/* diagonal */}
        <line x1={xOf(0)} y1={yOf(0)} x2={xOf(100)} y2={yOf(100)} stroke="#3a4155" strokeWidth={1.5} strokeDasharray="5 3"/>
        <text x={xOf(85)} y={yOf(88)} fill="#3a4155" fontSize={9} transform={`rotate(-42,${xOf(85)},${yOf(88)})`}>perfect calibration</text>

        {/* underconfidence band (step 2) */}
        {showUnderconfidence && (
          <g>
            <rect x={xOf(30)} y={PT} width={xOf(60)-xOf(30)} height={IH} fill={AMBER} opacity={0.08}/>
            <text x={xOf(45)} y={PT+20} textAnchor="middle" fill={AMBER} fontSize={10} opacity={0.8}>underconfidence zone</text>
          </g>
        )}

        {/* fill (step 4) */}
        {showFill && (
          <path d={fillPath("final")} fill={ACCENT} opacity={0.08}/>
        )}

        {/* previous curve (faded) */}
        {prevMeta && step < 4 && (
          <path d={curvePath(prevMeta.key)} fill="none" stroke={prevMeta.color} strokeWidth={1.5} opacity={0.2} strokeDasharray="4 3"/>
        )}

        {/* active curve */}
        <path d={curvePath(meta.key)} fill="none" stroke={meta.color} strokeWidth={2.5} strokeLinejoin="round"/>

        {/* dots on active curve */}
        {CURVES[meta.key].map((d, i) => (
          <circle key={i} cx={xOf(d.x)} cy={yOf(d.y)} r={3.5} fill={meta.color} stroke={CARD} strokeWidth={1.5}/>
        ))}

        {/* BSS badge */}
        <rect x={PL+IW-74} y={PT+6} width={70} height={26} rx={5} fill="#23293a" stroke={meta.color} strokeWidth={1} opacity={0.9}/>
        <text x={PL+IW-39} y={PT+17} textAnchor="middle" fill={MUTED} fontSize={9}>BSS</text>
        <text x={PL+IW-39} y={PT+27} textAnchor="middle" fill={meta.color} fontSize={11} fontWeight="700">{meta.bss}</text>

        {/* axis labels */}
        <text x={PL + IW/2} y={H-4} textAnchor="middle" fill={MUTED} fontSize={10}>Predicted Probability</text>
        <text x={10} y={PT+IH/2} textAnchor="middle" fill={MUTED} fontSize={10} transform={`rotate(-90,10,${PT+IH/2})`}>Actual Outcome Rate</text>
      </svg>
      <p style={{ fontSize: 12, color: MUTED, marginTop: 8 }}>
        {[
          "Step 1: Diagonal reference appears first, then the overall curve fades in with dots. BSS badge shows 0.62.",
          "Step 2: Previous curve ghosts to 20% opacity. Early (10%) curve animates in (blue). Still rough — information is sparse.",
          "Step 3: Midlife curve (amber) replaces early. Amber shaded band highlights 30–60% underconfidence zone.",
          "Step 4: 90% curve (purple) enters, hugs diagonal tightly. Dots would slide toward diagonal with a tween animation.",
          "Step 5: Final-price curve shown. Green fill between curve and diagonal. BSS 0.73 — best the crowd achieves.",
        ][step]}
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SECTION 2B — Category Selector
// ══════════════════════════════════════════════════════════════════════════
const MOCK_MARKETS = [
  { label: "Will Bitcoin hit $100k in 2024?", cat: "Crypto", finalP: 82, resolved: 1 },
  { label: "Will the Fed cut in Sept 2024?", cat: "Politics", finalP: 74, resolved: 1 },
  { label: "Will Lakers win 2024 NBA Finals?", cat: "Sports", finalP: 8, resolved: 0 },
  { label: "Will Ethereum ETF be approved?", cat: "Crypto", finalP: 91, resolved: 1 },
  { label: "Will UK hold early election?", cat: "Politics", finalP: 68, resolved: 1 },
];

function Section2B() {
  const [cat, setCat] = useState("All");
  const [selectedMarket, setSelectedMarket] = useState(null);
  const W = 520, H = 280, PL = 48, PR = 20, PT = 20, PB = 40;
  const IW = W - PL - PR, IH = H - PT - PB;
  const xOf = v => PL + (v / 100) * IW;
  const yOf = v => PT + (1 - v / 100) * IH;

  const cats = ["All", "Crypto", "Politics", "Sports"];
  const catColors = { All: ACCENT, Crypto: BLUE, Politics: PURPLE, Sports: AMBER };
  const catBSS = { All: "0.62", Crypto: "0.84", Politics: "0.67", Sports: "0.48" };
  const catDesc = {
    All: "All 806 markets — reasonable overall calibration.",
    Crypto: "Best-calibrated category — clear binary thresholds, quantitative outcomes.",
    Politics: "Mid-range — gradual information incorporation over market lifetime.",
    Sports: "Weakest — information arrives at game time, not gradually.",
  };

  const curveKey = cat === "All" ? "overall" : cat.toLowerCase();
  const color = catColors[cat];

  // sparkline for selected market
  function marketSparkline(m) {
    const pts = Array.from({ length: 8 }, (_, i) => {
      const t = i / 7;
      const noise = (Math.sin(i * 2.3) * 0.15 + Math.cos(i * 1.7) * 0.1);
      const trend = m.resolved ? lerp(50, m.finalP, t) : lerp(50, m.finalP, t);
      return { t, p: Math.max(2, Math.min(98, trend + noise * 30)) };
    });
    pts[pts.length - 1].p = m.finalP;
    return pts;
  }

  function curvePath(key) {
    const pts = CURVES[key] || CURVES.overall;
    return pts.map((d, i) => `${i === 0 ? "M" : "L"}${xOf(d.x).toFixed(1)},${yOf(d.y).toFixed(1)}`).join(" ");
  }

  const sm = selectedMarket !== null ? MOCK_MARKETS[selectedMarket] : null;
  const sparkPts = sm ? marketSparkline(sm) : [];

  return (
    <div>
      <SectionLabel n={2} title="Category Selector (interactive panel)" />
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {cats.map(c => (
          <button key={c} onClick={() => { setCat(c); setSelectedMarket(null); }}
            style={{
              padding: "5px 14px", borderRadius: 20, border: `1px solid ${c === cat ? catColors[c] : BORDER}`,
              background: c === cat ? catColors[c] + "22" : "transparent",
              color: c === cat ? catColors[c] : MUTED, fontSize: 12, cursor: "pointer"
            }}>{c}</button>
        ))}
      </div>

      <svg width={W} height={H} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, display: "block" }}>
        {[0,25,50,75,100].map(v => (
          <g key={v}>
            <line x1={PL} x2={PL+IW} y1={yOf(v)} y2={yOf(v)} stroke="#1e2535" strokeWidth={1}/>
            <text x={PL-6} y={yOf(v)+4} textAnchor="end" fill={MUTED} fontSize={10}>{v}%</text>
            <text x={xOf(v)} y={PT+IH+16} textAnchor="middle" fill={MUTED} fontSize={10}>{v}%</text>
          </g>
        ))}
        <line x1={PL} x2={PL+IW} y1={PT+IH} y2={PT+IH} stroke={BORDER}/>
        <line x1={PL} x2={PL} y1={PT} y2={PT+IH} stroke={BORDER}/>
        <line x1={xOf(0)} y1={yOf(0)} x2={xOf(100)} y2={yOf(100)} stroke="#3a4155" strokeWidth={1.5} strokeDasharray="5 3"/>

        <path d={curvePath(curveKey)} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round"/>
        {(CURVES[curveKey] || CURVES.overall).map((d,i) => (
          <circle key={i} cx={xOf(d.x)} cy={yOf(d.y)} r={3.5} fill={color} stroke={CARD} strokeWidth={1.5}/>
        ))}

        {/* sparkline overlay */}
        {sm && (() => {
          const path = sparkPts.map((d,i) => `${i===0?"M":"L"}${xOf(d.p).toFixed(1)},${(PT+IH-(d.t)*IH).toFixed(1)}`).join(" ");
          const dotX = xOf(sm.finalP), dotY = yOf(sm.resolved ? sm.finalP : 100 - sm.finalP + 10);
          return (
            <g>
              <path d={path} fill="none" stroke="#ffffff" strokeWidth={1} opacity={0.25} strokeDasharray="3 2"/>
              <circle cx={dotX} cy={yOf(sm.finalP)} r={7} fill={sm.resolved ? ACCENT : RED} stroke={CARD} strokeWidth={2} opacity={0.9}/>
              <text x={dotX+10} y={yOf(sm.finalP)+4} fill={TEXT} fontSize={10}>{sm.label.slice(0,22)}…</text>
            </g>
          );
        })()}

        <rect x={PL+IW-74} y={PT+6} width={70} height={26} rx={5} fill="#23293a" stroke={color} strokeWidth={1}/>
        <text x={PL+IW-39} y={PT+17} textAnchor="middle" fill={MUTED} fontSize={9}>BSS</text>
        <text x={PL+IW-39} y={PT+27} textAnchor="middle" fill={color} fontSize={11} fontWeight="700">{catBSS[cat]}</text>
      </svg>

      <p style={{ fontSize: 12, color: MUTED, marginTop: 6, marginBottom: 10 }}>{catDesc[cat]}</p>

      <div style={{ fontSize: 11, color: MUTED, marginBottom: 6 }}>↓ Select a specific market to overlay its final price on the calibration chart:</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {MOCK_MARKETS.filter(m => cat === "All" || m.cat === cat).map((m, i) => (
          <button key={i} onClick={() => setSelectedMarket(MOCK_MARKETS.indexOf(m))}
            style={{
              textAlign: "left", padding: "7px 12px", borderRadius: 8,
              border: `1px solid ${selectedMarket === MOCK_MARKETS.indexOf(m) ? color : BORDER}`,
              background: selectedMarket === MOCK_MARKETS.indexOf(m) ? color + "15" : "#1a1f2e",
              color: TEXT, fontSize: 12, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center"
            }}>
            <span>{m.label}</span>
            <span style={{ color: m.resolved ? ACCENT : RED, fontFamily: "monospace", fontSize: 11 }}>
              {m.finalP}% → {m.resolved ? "YES" : "NO"}
            </span>
          </button>
        ))}
      </div>
      <p style={{ fontSize: 12, color: MUTED, marginTop: 8 }}>
        Selecting a market overlays a gray sparkline of its price history and places a dot on the calibration chart where its final price landed — showing whether it was over/under-confident.
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SECTION 2C — Dynamics Trajectory (BSS over time, animated lines)
// ══════════════════════════════════════════════════════════════════════════
const DYNAMICS = {
  Politics: [0.37, 0.42, 0.49, 0.55, 0.61, 0.67],
  Crypto:   [0.55, 0.62, 0.70, 0.76, 0.81, 0.84],
  Sports:   [0.40, 0.41, 0.42, 0.44, 0.46, 0.48],
};
const DYN_COLORS = { Politics: PURPLE, Crypto: BLUE, Sports: AMBER };
const SNAPS = [10, 25, 40, 55, 70, 90];

function Section2C() {
  const [revealed, setRevealed] = useState(0);
  const W = 520, H = 240, PL = 48, PR = 80, PT = 20, PB = 40;
  const IW = W - PL - PR, IH = H - PT - PB;
  const xOf = i => PL + (i / (SNAPS.length - 1)) * IW;
  const yOf = v => PT + (1 - (v - 0.3) / 0.65) * IH;

  return (
    <div>
      <SectionLabel n="2b" title="Dynamics Trajectory — BSS over market lifetime" />
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {["Show Politics", "Add Crypto", "Add Sports"].map((s, i) => (
          <button key={i} onClick={() => setRevealed(i + 1)}
            style={{
              padding: "5px 13px", borderRadius: 20, border: `1px solid ${revealed > i ? ACCENT : BORDER}`,
              background: revealed > i ? ACCENT + "22" : "transparent",
              color: revealed > i ? ACCENT : MUTED, fontSize: 12, cursor: "pointer"
            }}>{s}</button>
        ))}
      </div>
      <svg width={W} height={H} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, display: "block" }}>
        {[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map(v => (
          <g key={v}>
            <line x1={PL} x2={PL+IW} y1={yOf(v)} y2={yOf(v)} stroke="#1e2535" strokeWidth={1}/>
            <text x={PL-6} y={yOf(v)+4} textAnchor="end" fill={MUTED} fontSize={10}>{v.toFixed(1)}</text>
          </g>
        ))}
        {SNAPS.map((s, i) => (
          <text key={s} x={xOf(i)} y={PT+IH+16} textAnchor="middle" fill={MUTED} fontSize={10}>{s}%</text>
        ))}
        <text x={PL+IW/2} y={H-4} textAnchor="middle" fill={MUTED} fontSize={10}>Market lifetime elapsed</text>
        <text x={12} y={PT+IH/2} textAnchor="middle" fill={MUTED} fontSize={10} transform={`rotate(-90,12,${PT+IH/2})`}>BSS</text>

        {Object.entries(DYNAMICS).map(([cat, vals], ci) => {
          if (ci >= revealed) return null;
          const color = DYN_COLORS[cat];
          const path = vals.map((v,i) => `${i===0?"M":"L"}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
          const last = vals[vals.length - 1];
          const gain = (last - vals[0]).toFixed(2);
          return (
            <g key={cat}>
              <path d={path} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round"/>
              {vals.map((v,i) => <circle key={i} cx={xOf(i)} cy={yOf(v)} r={3} fill={color} stroke={CARD} strokeWidth={1.5}/>)}
              <text x={xOf(vals.length-1)+8} y={yOf(last)+4} fill={color} fontSize={11} fontWeight="600">{cat}</text>
              <text x={xOf(vals.length-1)+8} y={yOf(last)+16} fill={color} fontSize={9} opacity={0.7}>+{gain}</text>
            </g>
          );
        })}

        {/* annotation for sports */}
        {revealed >= 3 && (
          <g>
            <line x1={xOf(2)} x2={xOf(4)} y1={yOf(0.41)} y2={yOf(0.41)} stroke={AMBER} strokeWidth={1} strokeDasharray="3 2" opacity={0.5}/>
            <text x={xOf(3)} y={yOf(0.38)} textAnchor="middle" fill={AMBER} fontSize={9} opacity={0.8}>info arrives at game time</text>
          </g>
        )}
      </svg>
      <p style={{ fontSize: 12, color: MUTED, marginTop: 8 }}>
        Each category line draws in sequentially (150ms stagger). Politics gains +0.30 BSS over its lifetime — labeled last because it draws last. Sports is nearly flat; annotation fades in after its line finishes.
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// SECTION 3 — Longshot dot-plot + surprise table
// ══════════════════════════════════════════════════════════════════════════
const LONGSHOTS = [
  { label: "Will Gaetz resign from Congress?", finalP: 3.4, actual: 1, vol: "low", month: "Nov 2024" },
  { label: "Will FTX customers be made whole?", finalP: 5.1, actual: 1, vol: "high", month: "Jun 2024" },
  { label: "Will Roe v Wade be reinstated?", finalP: 2.8, actual: 0, vol: "low", month: "Mar 2024" },
  { label: "Will Elon Musk buy Twitter?", finalP: 88, actual: 1, vol: "high", month: "Oct 2022" },
  { label: "Will Trump be indicted?", finalP: 91, actual: 1, vol: "high", month: "Apr 2023" },
  { label: "Will Nikki Haley win NH primary?", finalP: 12, actual: 0, vol: "low", month: "Jan 2024" },
];

const DOTS = Array.from({ length: 60 }, (_, i) => ({
  p: Math.random() * 14 + 0.5,
  jitter: Math.random() * 60 - 30,
  vol: Math.random() > 0.3 ? "low" : "high",
  occurred: Math.random() < 0.065,
}));

function Section3() {
  const [shown, setShown] = useState(false);
  const W = 520, H = 140, PL = 48, PR = 20, PT = 20, PB = 30;
  const IW = W - PL - PR, IH = H - PT - PB;
  const xOf = p => PL + (p / 15) * IW;
  const yOf = j => H / 2 + j * 0.5;

  return (
    <div>
      <SectionLabel n={3} title="Longshot Overpricing + Biggest Surprises" />

      <div style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 12, color: MUTED }}>Markets priced at ≤15%</span>
        <button onClick={() => setShown(true)}
          style={{ padding: "4px 12px", borderRadius: 16, border: `1px solid ${ACCENT}`, background: ACCENT+"22", color: ACCENT, fontSize: 11, cursor: "pointer" }}>
          Reveal dots ↓
        </button>
      </div>

      <svg width={W} height={H} style={{ background: CARD, borderRadius: 10, border: `1px solid ${BORDER}`, display: "block", marginBottom: 16 }}>
        {[0,5,10,15].map(v => (
          <g key={v}>
            <line x1={xOf(v)} x2={xOf(v)} y1={PT} y2={PT+IH+10} stroke="#1e2535" strokeWidth={1}/>
            <text x={xOf(v)} y={PT+IH+22} textAnchor="middle" fill={MUTED} fontSize={10}>{v}%</text>
          </g>
        ))}
        <line x1={PL} x2={PL+IW} y1={H/2} y2={H/2} stroke={BORDER}/>
        <text x={PL-6} y={H/2+4} textAnchor="end" fill={MUTED} fontSize={9}>jitter</text>

        {shown && DOTS.map((d, i) => (
          <circle key={i} cx={xOf(d.p)} cy={yOf(d.jitter)}
            r={d.vol === "high" ? 5 : 3.5}
            fill={d.occurred ? ACCENT : (d.vol === "high" ? "#374151" : "#1e2535")}
            stroke={d.occurred ? CARD : "none"}
            strokeWidth={1.5}
            opacity={d.vol === "high" ? 0.9 : 0.6}
          />
        ))}

        {/* bracket annotation */}
        {shown && (
          <g>
            <line x1={xOf(1.3)} x2={xOf(2.6)} y1={PT+4} y2={PT+4} stroke={AMBER} strokeWidth={1.5}/>
            <line x1={xOf(1.3)} x2={xOf(1.3)} y1={PT+4} y2={PT+14} stroke={AMBER} strokeWidth={1.5}/>
            <line x1={xOf(2.6)} x2={xOf(2.6)} y1={PT+4} y2={PT+14} stroke={AMBER} strokeWidth={1.5}/>
            <text x={xOf(1.95)} y={PT+2} textAnchor="middle" fill={AMBER} fontSize={9}>avg overpricing +1.3pp</text>
          </g>
        )}

        <text x={PL + IW/2} y={H-2} textAnchor="middle" fill={MUTED} fontSize={10}>Predicted Probability</text>
        <g>
          <circle cx={PL+8} cy={PT+10} r={4} fill={ACCENT}/>
          <text x={PL+15} y={PT+14} fill={MUTED} fontSize={9}>occurred</text>
          <circle cx={PL+65} cy={PT+10} r={4} fill="#374151"/>
          <text x={PL+72} y={PT+14} fill={MUTED} fontSize={9}>high vol</text>
          <circle cx={PL+115} cy={PT+10} r={3} fill="#1e2535" stroke={MUTED} strokeWidth={0.5}/>
          <text x={PL+122} y={PT+14} fill={MUTED} fontSize={9}>low vol</text>
        </g>
      </svg>

      {/* Surprise table */}
      <div style={{ fontSize: 11, color: MUTED, marginBottom: 8 }}>Biggest surprises — crowd's most confident mistakes:</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {LONGSHOTS.map((m, i) => {
          const isWrong = (m.finalP > 50 && m.actual === 0) || (m.finalP < 50 && m.actual === 1);
          const barColor = isWrong ? RED : ACCENT;
          const barW = m.finalP / 100;
          return (
            <div key={i} style={{
              background: "#1a1f2e", borderRadius: 7, padding: "8px 12px",
              border: `1px solid ${BORDER}`, position: "relative", overflow: "hidden"
            }}>
              <div style={{
                position: "absolute", left: 0, top: 0, bottom: 0,
                width: `${m.finalP}%`, background: barColor, opacity: 0.1
              }}/>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", position: "relative" }}>
                <span style={{ color: TEXT, fontSize: 12 }}>{m.label}</span>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0, marginLeft: 12 }}>
                  <span style={{ color: MUTED, fontSize: 10, fontFamily: "monospace" }}>{m.month}</span>
                  <span style={{ color: barColor, fontSize: 11, fontFamily: "monospace" }}>{m.finalP}% → {m.actual ? "YES" : "NO"}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p style={{ fontSize: 12, color: MUTED, marginTop: 8 }}>
        Dots enter from top on scroll with stagger. Green dots = longshots that occurred. Large dots = high volume (shows less overpricing). Table rows animate bar width from 0 on scroll entry. Month/year column added per your request.
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// MAIN
// ══════════════════════════════════════════════════════════════════════════
export default function App() {
  const [tab, setTab] = useState(0);
  const tabs = ["§1 Market Timeline", "§2A Calibration Steps", "§2B Category Selector", "§2C Dynamics Lines", "§3 Longshots"];
  const panels = [<Section1/>, <Section2A/>, <Section2B/>, <Section2C/>, <Section3/>];

  return (
    <div style={{ background: DARK, minHeight: "100vh", color: TEXT, fontFamily: "'Georgia', serif", padding: "24px 20px" }}>
      <div style={{ maxWidth: 600, margin: "0 auto" }}>
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontFamily: "monospace", fontSize: 10, color: MUTED, letterSpacing: 2 }}>VISUALIZATION MOCKUPS</span>
        </div>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px", color: TEXT }}>Polymarket — Proposed Chart Designs</h1>
        <p style={{ fontSize: 13, color: MUTED, margin: "0 0 24px" }}>Click each tab to see how the chart should look at each scroll step. Buttons simulate scroll triggers.</p>

        <div style={{ display: "flex", gap: 4, marginBottom: 24, flexWrap: "wrap" }}>
          {tabs.map((t, i) => (
            <button key={i} onClick={() => setTab(i)}
              style={{
                padding: "6px 14px", borderRadius: 8, border: `1px solid ${i === tab ? ACCENT : BORDER}`,
                background: i === tab ? ACCENT + "22" : "#1a1f2e",
                color: i === tab ? ACCENT : MUTED, fontSize: 12, cursor: "pointer", fontFamily: "monospace"
              }}>{t}</button>
          ))}
        </div>

        {panels[tab]}
      </div>
    </div>
  );
}
