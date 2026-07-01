import React, { useState, useMemo } from "react";
import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import realData from "./results/data.json";
import Analysis from "./Analysis.jsx";
import logoSvg from "./logo.svg";

// ─────────────────────────────────────────────────────────────────────────────
// LOSER QUEUE — BANC D'ESSAI STATISTIQUE
// ─────────────────────────────────────────────────────────────────────────────

// Palette claire — accents sémantiques saturés
const C = {
  target:  "#C89B0A",              // or foncé — CTAs, moments clés
  rig:     "#C4302A",              // rouge vif — signal négatif
  fair:    "#1A8F89",              // sarcelle foncée — signal positif
  carry:   "#7C5CE8",              // violet saturé — H3
  ink:     "#F6F4EF",              // fond global crème
  paper:   "#FDFCFA",              // fond de sections near-white
  card:    "#FFFFFF",              // surface des cards blanc
  mute:    "#72706D",              // texte secondaire
  dim:     "#E0DBD3",              // ligne subtile / séparateur
  text:    "#1A1917",              // texte principal
  suspect: "rgba(200,155,10,0.10)",
};

const MONO = "ui-monospace,Menlo,'SF Mono',monospace";
const SANS = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";

function useIsMobile(bp = 640) {
  const [m, setM] = React.useState(() => window.innerWidth < bp);
  React.useEffect(() => {
    const fn = () => setM(window.innerWidth < bp);
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, [bp]);
  return m;
}

// ─────────────────────────────────────────────────────────────────────────────
// SIMULATION
// ─────────────────────────────────────────────────────────────────────────────

function rand(seed) {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

function winProb(diff) { return 1 / (1 + Math.pow(10, -diff / 400)); }

function linearRegression(points) {
  const n = points.length;
  if (n < 5) return { slope: 0, intercept: 0, r2: 0 };
  const mx = points.reduce((s, p) => s + p.x, 0) / n;
  const my = points.reduce((s, p) => s + p.y, 0) / n;
  const ssXY = points.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0);
  const ssXX = points.reduce((s, p) => s + (p.x - mx) ** 2, 0);
  const ssYY = points.reduce((s, p) => s + (p.y - my) ** 2, 0);
  const slope     = ssXX > 0 ? ssXY / ssXX : 0;
  const intercept = my - slope * mx;
  const r2        = ssXX > 0 && ssYY > 0 ? ssXY ** 2 / (ssXX * ssYY) : 0;
  return { slope, intercept, r2 };
}

function findEpisodeRanges(results, minRun = 3) {
  const ranges = [];
  let start = -1;
  for (let i = 0; i <= results.length; i++) {
    const sus = i < results.length && results[i].suspect;
    if (sus && start === -1) start = i;
    if (!sus && start !== -1) {
      if (i - start >= minRun) ranges.push({ start, end: i - 1, len: i - start });
      start = -1;
    }
  }
  return ranges;
}

function simulate({ engine, games, heroMMR, poolSpread, rigStrength, carryScore, seed }) {
  const results = [];
  let streak = 0, maxWin = 0, maxLoss = 0, s = seed;
  let suspectCount = 0, suspectRun = 0, episodes = 0;

  for (let g = 0; g < games; g++) {
    s += 1;
    const recent   = results.slice(-10);
    const recentWR = recent.length ? recent.filter(r => r.win).length / recent.length : 0.5;

    let allies = 0, enemies = 0;
    for (let i = 0; i < 4; i++) allies  += heroMMR + (rand(s * 31 + i) - 0.5) * 2 * poolSpread;
    for (let i = 0; i < 5; i++) enemies += heroMMR + (rand(s * 57 + i) - 0.5) * 2 * poolSpread;

    let allyAvg  = (allies + heroMMR) / 5;
    let enemyAvg = enemies / 5;

    if (engine === "rig") {
      const push           = (recentWR - 0.5) * 2;
      const autonomyFactor = 1 - carryScore * 0.6;
      const bias           = push * rigStrength * autonomyFactor;
      allyAvg  -= bias;
      enemyAvg += bias;
    }

    const diff    = allyAvg - enemyAvg;
    const p       = winProb(diff);
    const win     = rand(s * 99) < p;
    const suspect = diff < -poolSpread * 0.6 && recentWR > 0.55;

    if (suspect) { suspectRun++; suspectCount++; if (suspectRun === 3) episodes++; }
    else suspectRun = 0;

    if (win) { streak = streak > 0 ? streak + 1 : 1;  maxWin  = Math.max(maxWin, streak); }
    else     { streak = streak < 0 ? streak - 1 : -1; maxLoss = Math.max(maxLoss, -streak); }

    results.push({ g, win, diff, recentWR, suspect });
  }

  let wins = 0;
  const wr = results.map((r, i) => { if (r.win) wins++; return (wins / (i + 1)) * 100; });

  const scatterPoints = results.map(r => ({ x: r.recentWR, y: r.diff, win: r.win }));
  const reg = linearRegression(scatterPoints);

  const unfavGames = results.filter(r => r.diff < 0);
  const wrUnfav    = unfavGames.length
    ? unfavGames.filter(r => r.win).length / unfavGames.length * 100
    : null;

  return { results, wr, reg, scatterPoints, winRate: (wins / games) * 100,
           maxWin, maxLoss, suspectCount, episodes, wrUnfav };
}

function batchSimulate(params, runs) {
  const winRates = [], maxWins = [], maxLosses = [], slopes = [];
  for (let i = 0; i < runs; i++) {
    const r = simulate({ ...params, seed: params.seed + i * 1000 });
    winRates.push(r.winRate);
    maxWins.push(r.maxWin);
    maxLosses.push(r.maxLoss);
    slopes.push(r.reg.slope);
  }
  return { winRates, maxWins, maxLosses, slopes };
}

function histBins(values, min, max, bins) {
  const counts = new Array(bins).fill(0);
  const width  = (max - min) / bins;
  values.forEach(v => {
    let idx = Math.floor((v - min) / width);
    counts[Math.max(0, Math.min(bins - 1, idx))]++;
  });
  return counts.map((c, i) => ({ x0: min + i * width, x1: min + (i + 1) * width, count: c }));
}

function batchStats(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const n      = sorted.length;
  const mean   = values.reduce((a, b) => a + b, 0) / n;
  const std    = Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / n);
  return { mean, std, p10: sorted[Math.floor(n * 0.10)], p90: sorted[Math.floor(n * 0.90)] };
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS & PRIMITIVES
// ─────────────────────────────────────────────────────────────────────────────

// Surface de card — fond légèrement surélevé, bordure quasi-invisible
function Card({ children, style = {} }) {
  return (
    <div style={{
      background: C.card,
      border: `1px solid ${C.dim}`,
      borderRadius: 14,
      padding: "24px",
      marginTop: 16,
      boxShadow: "0 1px 4px rgba(0,0,0,0.06), 0 0 0 0.5px rgba(0,0,0,0.03)",
      fontFamily: SANS,
      ...style,
    }}>
      {children}
    </div>
  );
}

// Eyebrow — petite étiquette de section, discrète
function Eyebrow({ children, color }) {
  return (
    <div style={{
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: "0.1em",
      textTransform: "uppercase",
      color: color || C.mute,
      fontFamily: MONO,
      marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

// Stat — chiffre avec étiquette
function Stat({ label, value, sub, color }) {
  return (
    <div style={{ flex: 1, minWidth: 90 }}>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: MONO, color: color || C.text, lineHeight: 1 }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: C.mute, marginTop: 5 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: C.mute, opacity: 0.6, marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

// Divider horizontal
function Divider({ margin = "20px 0" }) {
  return <div style={{ borderTop: `1px solid ${C.dim}`, margin }} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// VISUALISATIONS
// ─────────────────────────────────────────────────────────────────────────────

function Histogram({ values, min, max, bins, color, unit = "", highlightNeg }) {
  const bars = useMemo(() => histBins(values, min, max, bins), [values, min, max, bins]);
  const peak = Math.max(1, ...bars.map(b => b.count));
  const mean = batchStats(values).mean;
  const W = 520, H = 100, PAD_TOP = 6;
  const bw = W / bins;
  const toX = v => ((v - min) / (max - min)) * W;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H + 22}`} style={{ display: "block" }}>
      {bars.map((b, i) => {
        const bh    = (b.count / peak) * (H - PAD_TOP);
        const isNeg = highlightNeg && b.x1 <= 0;
        return (
          <rect key={i}
            x={i * bw + 1} y={H - bh} width={bw - 2} height={bh}
            fill={isNeg ? C.rig : color} opacity={isNeg ? 0.7 : 0.65} rx={1} />
        );
      })}
      {/* Ligne de moyenne */}
      {(() => {
        const x = toX(mean);
        return (
          <>
            <line x1={x} y1={0} x2={x} y2={H} stroke={C.target} strokeWidth="1" strokeDasharray="4 3" strokeOpacity="0.7" />
            <text x={Math.min(W - 40, x + 4)} y={12}
              fill={C.target} fontSize="9" fontFamily={MONO} opacity="0.9">
              moy {mean.toFixed(1)}{unit}
            </text>
          </>
        );
      })()}
      {/* Axe bas */}
      {[min, (min + max) / 2, max].map((t, i) => (
        <text key={i}
          x={i === 0 ? 2 : i === 2 ? W - 2 : W / 2}
          y={H + 14}
          fill={C.mute} fontSize="9" fontFamily={MONO}
          textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>
          {Number.isInteger(t) ? t : t.toFixed(1)}{unit}
        </text>
      ))}
    </svg>
  );
}

function Sparkline({ data, episodeRanges, color, W = 520, H = 110 }) {
  const path = useMemo(() => {
    if (!data.length) return "";
    const mn = 30, mx = 70;
    return data.map((v, i) => {
      const x = (i / (data.length - 1)) * W;
      const y = H - ((Math.max(mn, Math.min(mx, v)) - mn) / (mx - mn)) * H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [data, W, H]);

  const mid  = H - ((50 - 30) / 40) * H;
  const toX  = i => (i / (data.length - 1)) * W;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {/* Épisodes suspects — teinte dorée très subtile */}
      {episodeRanges.map((ep, i) => (
        <rect key={i}
          x={toX(ep.start)} y={0}
          width={toX(ep.end) - toX(ep.start) + W / data.length}
          height={H}
          fill={C.suspect} />
      ))}
      {/* Ligne 50% */}
      <line x1={0} y1={mid} x2={W} y2={mid}
        stroke={C.dim} strokeDasharray="3 5" strokeWidth="1" />
      <text x={4} y={mid - 6} fill={C.mute} fontSize="9" fontFamily={MONO}>50%</text>
      {/* Courbe */}
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function StreakStrip({ results, episodeRanges }) {
  const episodeSet = useMemo(() => {
    const s = new Set();
    episodeRanges.forEach(ep => { for (let i = ep.start; i <= ep.end; i++) s.add(i); });
    return s;
  }, [episodeRanges]);

  const last   = results.slice(-80);
  const offset = results.length - last.length;

  return (
    <div style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
      {last.map((r, i) => {
        const idx  = offset + i;
        const inEp = episodeSet.has(idx);
        return (
          <div key={i}
            title={`G${r.g + 1} · ${r.win ? "W" : "L"}${inEp ? " · épisode" : r.suspect ? " · suspect" : ""}`}
            style={{
              width: 10, height: 10, borderRadius: 2,
              background: r.win ? C.fair : C.rig,
              opacity: 0.8,
              outline: inEp
                ? `1.5px solid ${C.target}`
                : r.suspect ? `1px solid ${C.target}44` : "none",
              outlineOffset: 1,
            }} />
        );
      })}
    </div>
  );
}

function EpisodeTimeline({ results, episodeRanges, W = 520 }) {
  const H = 20, n = results.length;
  if (!n) return null;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H + 18}`} style={{ display: "block" }}>
      {/* Fond neutre */}
      <rect x={0} y={2} width={W} height={H - 4} fill={C.dim} rx={2} />
      {/* Chaque game */}
      {results.map((r, i) => (
        <rect key={i}
          x={(i / n) * W} y={2} width={Math.max(1, W / n - 0.5)} height={H - 4}
          fill={r.win ? C.fair : C.rig}
          opacity={r.suspect ? 0.9 : 0.3} />
      ))}
      {/* Cadres épisodes */}
      {episodeRanges.map((ep, i) => {
        const x1 = (ep.start / n) * W;
        const x2 = ((ep.end + 1) / n) * W;
        return (
          <g key={i}>
            <rect x={x1} y={0} width={x2 - x1} height={H + 2}
              fill="none" stroke={C.target} strokeWidth="1.5" rx={2} />
            <text x={(x1 + x2) / 2} y={H + 15}
              fill={C.target} fontSize="9" fontFamily={MONO} textAnchor="middle">
              {ep.len}
            </text>
          </g>
        );
      })}
      <text x={2}     y={H + 15} fill={C.mute} fontSize="9" fontFamily={MONO}>1</text>
      <text x={W - 2} y={H + 15} fill={C.mute} fontSize="9" fontFamily={MONO} textAnchor="end">{n}</text>
    </svg>
  );
}

// Scatter épuré : pas de remplissage quadrant, axes fins, droite propre
function ScatterPlot({ scatterPoints, reg, poolSpread, showReg = true }) {
  const W = 520, H = 170;
  const PAD = { l: 44, r: 14, t: 28, b: 30 };
  const IW = W - PAD.l - PAD.r;
  const IH = H - PAD.t - PAD.b;

  const yRange = poolSpread * 2.4;
  const toSX = x => PAD.l + x * IW;
  const toSY = y => PAD.t + (1 - (y + yRange) / (2 * yRange)) * IH;

  const midY = toSY(0);
  const regX0 = toSX(0), regY0 = toSY(reg.intercept);
  const regX1 = toSX(1), regY1 = toSY(reg.slope + reg.intercept);

  const slopeColor = reg.slope < -80 ? C.rig : reg.slope < -30 ? C.target : C.fair;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {/* Axes */}
      <line x1={PAD.l} y1={midY} x2={W - PAD.r} y2={midY}
        stroke={C.dim} strokeWidth="1" />
      <line x1={toSX(0.5)} y1={PAD.t} x2={toSX(0.5)} y2={H - PAD.b}
        stroke={C.dim} strokeWidth="1" strokeDasharray="3 4" />

      {/* Labels d'axes */}
      <text x={PAD.l}           y={H - 6} fill={C.mute} fontSize="9" fontFamily={MONO}>0%</text>
      <text x={toSX(0.5) - 8}  y={H - 6} fill={C.mute} fontSize="9" fontFamily={MONO}>50%</text>
      <text x={W - PAD.r - 20} y={H - 6} fill={C.mute} fontSize="9" fontFamily={MONO}>100%</text>
      <text x={PAD.l - 4}      y={PAD.t + 4}    fill={C.mute} fontSize="9" fontFamily={MONO} textAnchor="end">+</text>
      <text x={PAD.l - 4}      y={H - PAD.b - 4} fill={C.mute} fontSize="9" fontFamily={MONO} textAnchor="end">−</text>

      {/* Titre axe X */}
      <text x={W / 2} y={H - 2} fill={C.mute} fontSize="9" fontFamily={MONO} textAnchor="middle">
        forme récente (10 dernières games)
      </text>

      {/* Points */}
      {scatterPoints.map((p, i) => (
        <circle key={i}
          cx={toSX(p.x)}
          cy={toSY(Math.max(-yRange, Math.min(yRange, p.y)))}
          r={2.2}
          fill={p.win ? C.fair : C.rig}
          opacity={0.4} />
      ))}

      {/* Droite de régression */}
      {showReg && <line x1={regX0} y1={regY0} x2={regX1} y2={regY1}
        stroke={slopeColor} strokeWidth="1.5" opacity="0.9" />}

      {/* Valeur de pente — seule annotation nécessaire */}
      {showReg && <text x={W - PAD.r - 2} y={PAD.t - 6}
        fill={slopeColor} fontSize="11" fontFamily={MONO}
        fontWeight="600" textAnchor="end">
        pente {reg.slope.toFixed(0)}
      </text>}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPOSANTS NARRATIFS
// ─────────────────────────────────────────────────────────────────────────────

// Encart insight — fond teinté, pas de bordure décorative
function Callout({ color, children }) {
  return (
    <div style={{
      background: color + "0F",
      borderRadius: 10,
      padding: "14px 18px",
      marginTop: 14,
      fontSize: 13,
      color: C.text,
      lineHeight: 1.65,
    }}>
      {children}
    </div>
  );
}

// En-tête de section numérotée — typographique, sans ornement
function Step({ n, title, sub }) {
  return (
    <div style={{ margin: "36px 0 14px" }}>
      <div style={{ fontSize: 10, fontFamily: MONO, color: C.mute, letterSpacing: "0.12em", marginBottom: 4 }}>
        {String(n).padStart(2, "0")}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: C.text, lineHeight: 1.2 }}>{title}</div>
      {sub && <div style={{ fontSize: 13, color: C.mute, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DONNÉES RÉELLES — composant principal
// ─────────────────────────────────────────────────────────────────────────────

// Scatter mini sans axes — adapté à l'affichage en grille compacte
function MiniScatter({ scatter, slope, poolSpread = 300, color }) {
  const W = 260, H = 130;
  const PAD = { l: 8, r: 8, t: 20, b: 8 };
  const IW = W - PAD.l - PAD.r;
  const IH = H - PAD.t - PAD.b;
  const yRange = poolSpread * 2.6;
  const toSX = x => PAD.l + x * IW;
  const toSY = y => PAD.t + (1 - (y + yRange) / (2 * yRange)) * IH;

  // Droite de régression
  const midY = toSY(0);
  let regLine = null;
  if (slope != null) {
    // intercept approché : la droite passe par le centroïde (~0.5, ~0)
    const intercept = -(slope * 0.5);
    regLine = {
      x0: toSX(0), y0: toSY(intercept),
      x1: toSX(1), y1: toSY(slope + intercept),
    };
  }

  const slopeColor = slope == null ? C.mute
    : slope < -80  ? C.rig
    : slope < -30  ? C.target
    : C.fair;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {/* Axe central */}
      <line x1={PAD.l} y1={midY} x2={W - PAD.r} y2={midY}
        stroke={C.dim} strokeWidth="1" />
      {/* Points */}
      {scatter.map(([x, y, w], i) => (
        <circle key={i}
          cx={toSX(x)}
          cy={toSY(Math.max(-yRange, Math.min(yRange, y)))}
          r={2} fill={w ? C.fair : C.rig} opacity={0.38} />
      ))}
      {/* Droite */}
      {regLine && (
        <line x1={regLine.x0} y1={regLine.y0} x2={regLine.x1} y2={regLine.y1}
          stroke={slopeColor} strokeWidth="1.5" opacity="0.85" />
      )}
      {/* Valeur pente */}
      <text x={W - PAD.r - 2} y={PAD.t - 4}
        fill={slopeColor} fontSize="10" fontFamily={MONO}
        fontWeight="600" textAnchor="end">
        {slope != null ? slope.toFixed(0) : "—"}
      </text>
    </svg>
  );
}

// Verdict textuel selon la pente
function verdict(slope) {
  if (slope == null)  return { label: "Insuffisant",  color: C.mute };
  if (slope < -100)   return { label: "Signal fort",  color: C.rig  };
  if (slope < -50)    return { label: "Signal modéré",color: C.target };
  if (slope < -20)    return { label: "Ambigu",       color: C.mute };
  return                     { label: "Honnête",      color: C.fair };
}

function SlopePill({ value, n }) {
  if (value == null || n == null || n < 8)
    return <span style={{ color: C.mute, fontFamily: MONO, fontSize: 11 }}>—</span>;
  const col = value < -80 ? C.rig : value < -30 ? C.target : value > 50 ? C.fair : C.mute;
  return (
    <span style={{ color: col, fontFamily: MONO, fontSize: 11, fontWeight: 600 }}>
      {value > 0 ? "+" : ""}{value.toFixed(0)}
      <span style={{ color: C.mute, fontWeight: 400 }}> ({n}g)</span>
    </span>
  );
}

function CarryBars({ slope_1v9, slope_teamdep }) {
  const maxAbs = 250;
  const bar = (val, label, color) => {
    if (val == null) return null;
    const pct = Math.min(Math.abs(val) / maxAbs * 100, 100);
    const neg  = val < 0;
    return (
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2, fontSize: 10, color: C.mute }}>
          <span>{label}</span>
          <span style={{ color, fontFamily: MONO, fontWeight: 600 }}>
            {val > 0 ? "+" : ""}{val.toFixed(0)}
          </span>
        </div>
        <div style={{ height: 4, background: C.dim, borderRadius: 2, overflow: "hidden" }}>
          <div style={{
            height: "100%", width: pct + "%",
            background: neg ? color : C.fair,
            borderRadius: 2,
            marginLeft: neg ? 0 : "auto",
          }} />
        </div>
      </div>
    );
  };
  return (
    <div>
      {bar(slope_1v9,    "1v9 carry",    C.rig)}
      {bar(slope_teamdep,"team-depend.", C.carry)}
    </div>
  );
}

function RealDataSection({ poolSpread = 300 }) {
  const mobile = useIsMobile();
  const { players, n_total, generated } = realData;
  const [view, setView] = useState("table"); // "table" | "scatter" | "carry"

  if (!players || players.length === 0) {
    return (
      <Card style={{ opacity: 0.5 }}>
        <Eyebrow>Données réelles — en attente</Eyebrow>
        <p style={{ fontSize: 13, color: C.mute, margin: 0, lineHeight: 1.55 }}>
          Le batch de collecte n'est pas encore terminé.
          Lance <code style={{ color: C.target, fontFamily: MONO }}>python3 anonymize.py</code>{" "}
          une fois le batch fini pour peupler cette section.
        </p>
      </Card>
    );
  }

  const slopes    = players.map(p => p.slope).filter(s => s != null);
  const intercepts = players.map(p => p.mean_team_diff).filter(v => v != null);
  const meanSlope  = slopes.length ? slopes.reduce((a, b) => a + b, 0) / slopes.length : null;
  const meanInter  = intercepts.length ? intercepts.reduce((a, b) => a + b, 0) / intercepts.length : null;
  const nSignal    = slopes.filter(s => s < -50).length;

  return (
    <Card>
      {/* ── Header ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Eyebrow>Données réelles · API Riot</Eyebrow>
          <div style={{ fontWeight: 700, fontSize: 17, margin: "2px 0 4px" }}>
            {n_total.toLocaleString()} games · {players.length} joueurs anonymisés
          </div>
          <div style={{ fontSize: 12, color: C.mute }}>
            Collecte du {generated} · Riot IDs remplacés par palier elo
          </div>
        </div>
        {/* KPIs */}
        <div style={{ display: "flex", gap: 20 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{
              fontSize: 28, fontWeight: 700, fontFamily: MONO,
              color: meanSlope != null && meanSlope < -50 ? C.rig : C.fair,
            }}>
              {meanSlope != null ? (meanSlope > 0 ? "+" : "") + meanSlope.toFixed(0) : "—"}
            </div>
            <div style={{ fontSize: 11, color: C.mute }}>pente moy.</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: MONO,
              color: meanInter != null && meanInter < -50 ? C.rig : C.mute }}>
              {meanInter != null ? (meanInter > 0 ? "+" : "") + meanInter.toFixed(0) : "—"}
            </div>
            <div style={{ fontSize: 11, color: C.mute }}>intercept moy.</div>
          </div>
        </div>
      </div>

      <Divider margin="18px 0 14px" />

      {/* ── Toggle vue ── */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {[["table", "Tableau"], ["scatter", "Scatter"], ["carry", "Carry vs Team-dep"]].map(([k, l]) => (
          <button key={k} onClick={() => setView(k)} style={{
            padding: "7px 14px",
            background: view === k ? C.paper : "transparent",
            color: view === k ? C.text : C.mute,
            border: `1px solid ${view === k ? C.dim : "transparent"}`,
            borderRadius: 7, fontSize: 12, fontWeight: 500,
            cursor: "pointer",
          }}>{l}</button>
        ))}
      </div>

      {/* ── Vue tableau ── */}
      {view === "table" && (
        <div>
          {/* Résultat agrégé pré-enregistré */}
          <div style={{
            marginBottom: 14, padding: "12px 16px",
            background: C.paper, borderRadius: 8,
            border: `1px solid ${C.dim}`,
          }}>
            <div style={{ fontSize: 11, color: C.mute, fontFamily: MONO, letterSpacing: "0.05em", marginBottom: 4 }}>
              RÉSULTAT AGRÉGÉ · estimateur pré-enregistré (27 joueurs · 2 561 obs)
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.fair, fontFamily: MONO }}>
              pente = −20,2 &nbsp;·&nbsp; SE = 21,5 &nbsp;·&nbsp; p = 0,17 &nbsp;→&nbsp; <span style={{ color: C.fair }}>H0 conservée</span>
            </div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 6, lineHeight: 1.6 }}>
              Les pentes individuelles ci-dessous varient largement par pur hasard — c'est précisément pourquoi seul le résultat agrégé compte.
              Une pente de −200 sur 100 games est attendue sous H0 (monde honnête). Le tableau illustre la variance que le simulateur prédit.
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.dim}` }}>
                  {[
                    { label: "Joueur",  align: "left"  },
                    { label: "Games",   align: "right" },
                    { label: "WR",      align: "right" },
                    { label: "Pente",   align: "right" },
                  ].map(({ label, align }) => (
                    <th key={label} style={{
                      padding: "6px 10px", textAlign: align,
                      fontWeight: 500, fontSize: 11, color: C.mute,
                      fontFamily: MONO, letterSpacing: "0.05em",
                    }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {players.map((p, i) => (
                    <tr key={p.id} style={{
                      borderBottom: `1px solid ${C.dim}`,
                      background: i % 2 === 0 ? "transparent" : "rgba(0,0,0,0.03)",
                    }}>
                      <td style={{ padding: "10px 10px", color: C.text, fontWeight: 500 }}>{p.id}</td>
                      <td style={{ padding: "10px 10px", color: C.mute, textAlign: "right", fontFamily: MONO }}>{p.n}</td>
                      <td style={{ padding: "10px 10px", textAlign: "right", fontFamily: MONO, color: C.text }}>{p.wr}%</td>
                      <td style={{ padding: "10px 10px", textAlign: "right", fontFamily: MONO,
                        color: C.mute, fontWeight: 600 }}>
                        {p.slope != null ? (p.slope > 0 ? "+" : "") + p.slope.toFixed(0) : "—"}
                      </td>
                    </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 12, fontSize: 11, color: C.mute, lineHeight: 1.6 }}>
            <b style={{ color: C.text }}>Pente</b> : corrélation OLS brute (sans correction HAC) entre la forme récente et l'écart d'équipe.
            Négatif = équipe plus faible quand le joueur est en forme. Positif = l'inverse.
            À ~100 games, l'intervalle de confiance à 95 % couvre typiquement ±200 pts — ces valeurs individuelles ne permettent pas de conclure.
            Colonnes avancées disponibles via l'onglet Scatter.
          </div>
        </div>
      )}

      {/* ── Vue scatter ── */}
      {view === "scatter" && (
        <div style={{
          display: "grid",
          gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fill, minmax(240px, 1fr))",
          gap: 12,
        }}>
          {players.map(p => {
            const v = verdict(p.slope);
            return (
              <div key={p.id} style={{
                background: C.paper,
                border: "1px solid rgba(0,0,0,0.05)",
                borderRadius: 10, padding: "14px",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{p.id}</div>
                    <div style={{ fontSize: 11, color: C.mute, fontFamily: MONO }}>{p.n} games</div>
                  </div>
                  <span style={{
                    fontSize: 10, color: v.color, fontWeight: 600,
                    background: v.color + "18", borderRadius: 4,
                    padding: "2px 7px", alignSelf: "flex-start",
                  }}>{v.label}</span>
                </div>
                <MiniScatter scatter={p.scatter} slope={p.slope} poolSpread={poolSpread} />
                <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: C.mute, fontFamily: MONO }}>
                  <span>ép. <b style={{ color: p.episodes > 3 ? C.rig : C.text }}>{p.episodes}</b></span>
                  <span>R² <b style={{ color: C.text }}>{p.r2 != null ? (p.r2 * 100).toFixed(1) + "%" : "—"}</b></span>
                  <span>biais <b style={{
                    color: p.mean_team_diff != null && p.mean_team_diff < -50 ? C.rig : C.mute,
                  }}>
                    {p.mean_team_diff != null ? (p.mean_team_diff > 0 ? "+" : "") + p.mean_team_diff.toFixed(0) : "—"}
                  </b></span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Vue carry-stratification ── */}
      {view === "carry" && (
        <div>
          <div style={{ marginBottom: 14, fontSize: 12, color: C.mute, lineHeight: 1.6 }}>
            Pente <code style={{ color: C.rig, fontFamily: MONO }}>team_diff ~ forme</code> séparée
            pour les champions <b style={{ color: C.text }}>1v9 carry</b> (carry_score ≥ 0.65)
            vs <b style={{ color: C.text }}>team-dependent</b> (&lt; 0.65).
            Selon la théorie challenge mode, la pente devrait être plus négative
            sur les champions team-dep (alliés faibles = défaite assurée).
          </div>
          <div style={{ display: "grid", gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {players.map(p => {
              const divergence = p.slope_1v9 != null && p.slope_teamdep != null
                ? p.slope_1v9 - p.slope_teamdep : null;
              const hasDivergence = divergence != null && Math.abs(divergence) > 80;
              return (
                <div key={p.id} style={{
                  background: C.paper,
                  border: `1px solid ${hasDivergence ? C.target + "44" : "rgba(0,0,0,0.05)"}`,
                  borderRadius: 10, padding: 16,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{p.id}</div>
                      <div style={{ fontSize: 11, color: C.mute }}>pente globale : <span style={{
                        fontFamily: MONO, color: p.slope < -50 ? C.rig : C.fair,
                        fontWeight: 600,
                      }}>{p.slope != null ? (p.slope > 0 ? "+" : "") + p.slope.toFixed(0) : "—"}</span></div>
                    </div>
                    {hasDivergence && (
                      <span style={{
                        fontSize: 10, color: C.target, fontWeight: 600,
                        background: C.target + "18", borderRadius: 4,
                        padding: "2px 7px", alignSelf: "flex-start",
                      }}>divergence</span>
                    )}
                  </div>
                  <CarryBars slope_1v9={p.slope_1v9} slope_teamdep={p.slope_teamdep} />
                  <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <div style={{ background: C.card, borderRadius: 6, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.mute, marginBottom: 3 }}>1v9 carry</div>
                      <SlopePill value={p.slope_1v9} n={p.n_1v9} />
                    </div>
                    <div style={{ background: C.card, borderRadius: 6, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.mute, marginBottom: 3 }}>team-dep</div>
                      <SlopePill value={p.slope_teamdep} n={p.n_teamdep} />
                    </div>
                  </div>
                  {divergence != null && (
                    <div style={{ marginTop: 8, fontSize: 11, color: C.mute }}>
                      Δ pente : <span style={{
                        fontFamily: MONO, fontWeight: 600,
                        color: Math.abs(divergence) > 80 ? C.target : C.mute,
                      }}>{divergence > 0 ? "+" : ""}{divergence.toFixed(0)} pts</span>
                      <span style={{ color: C.mute }}> (1v9 − team-dep)</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 14, padding: "12px 14px", background: C.card, borderRadius: 8, fontSize: 11, color: C.mute, lineHeight: 1.7 }}>
            <b style={{ color: C.text }}>Comment lire :</b> si le challenge mode cible les smurfs
            indépendamment de leur champion, les deux pentes devraient être similaires.
            Une <b style={{ color: C.target }}>divergence forte</b> (1v9 &gt;&gt; team-dep)
            suggère que l'équipe faible pénalise davantage les champions synergiques —
            cohérent avec la théorie, mais aussi avec la variance naturelle de petits échantillons.
            Seuil pré-enregistré : carry_score ≥ 0.65 (Katarina, Master Yi, Yone…).
          </div>
        </div>
      )}

      {/* ── Note méthodologique ── */}
      <div style={{ marginTop: 16, fontSize: 11, color: C.mute, lineHeight: 1.6 }}>
        Données anonymisées · Riot IDs, match IDs, timestamps supprimés.
        Colonnes : win, my_champ, my_role, carry_score, team_diff, recent_wr, rank_score.
      </div>
    </Card>
  );
}

// Section repliable — déclencheur discret, sans chrome lourd
function Collapsible({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 20 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        width: "100%", padding: "16px 20px",
        background: C.card,
        border: "1px solid rgba(0,0,0,0.06)",
        borderRadius: open ? "12px 12px 0 0" : 12,
        color: C.text, fontSize: 14, fontWeight: 600,
        cursor: "pointer",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        textAlign: "left",
      }}>
        <span>{title}</span>
        <span style={{
          color: C.mute, fontSize: 14,
          display: "inline-block",
          transform: open ? "rotate(180deg)" : "none",
          transition: "transform .18s",
        }}>▾</span>
      </button>
      {open && (
        <div style={{
          border: "1px solid rgba(0,0,0,0.06)", borderTop: "none",
          borderRadius: "0 0 12px 12px",
          padding: "8px 0 16px",
        }}>
          {children}
        </div>
      )}
    </div>
  );
}

// Slider — control sobre
function Slider({ label, value, min, max, step, onChange, hint, disabled, color }) {
  return (
    <div style={{ marginBottom: 20, opacity: disabled ? 0.35 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: C.text }}>{label}</span>
        <span style={{ fontSize: 13, color: C.mute, fontFamily: MONO }}>{value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: color || C.target, cursor: disabled ? "not-allowed" : "pointer" }} />
      {hint && <div style={{ fontSize: 11, color: C.mute, marginTop: 4, lineHeight: 1.4 }}>{hint}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTIONS NARRATIVES
// ─────────────────────────────────────────────────────────────────────────────

// Étape 1 — Les deux courbes côte à côte, même seed
function ParadoxSection({ seed, heroMMR, poolSpread, rigStrength, carryScore, games }) {
  const base    = { games, heroMMR, poolSpread, rigStrength, carryScore, seed };
  const rigSim  = useMemo(() => simulate({ ...base, engine: "rig" }),
    [seed, heroMMR, poolSpread, rigStrength, carryScore, games]);
  const fairSim = useMemo(() => simulate({ ...base, engine: "fair" }),
    [seed, heroMMR, poolSpread, rigStrength, carryScore, games]);

  return (
    <Card>
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
        {[["Simulation A", rigSim, C.rig], ["Simulation B", fairSim, C.fair]].map(([label, sim, color]) => (
          <div key={label} style={{ flex: 1, minWidth: 220 }}>
            <Eyebrow color={color}>{label}</Eyebrow>
            <Sparkline data={sim.wr} episodeRanges={[]} color={color} H={90} />
            <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 12, color: C.mute }}>
              <span>WR <b style={{ color: C.text, fontFamily: MONO }}>{sim.winRate.toFixed(1)}%</b></span>
              <span>Série L max <b style={{ color: C.text, fontFamily: MONO }}>{sim.maxLoss}</b></span>
              <span>Ép. <b style={{ color: C.text, fontFamily: MONO }}>{sim.episodes}</b></span>
            </div>
          </div>
        ))}
      </div>
      <Divider margin="16px 0 12px" />
      <div style={{ fontSize: 13, color: C.mute, textAlign: "center" }}>
        Même seed · même MMR ·{" "}
        <span style={{ color: C.text, fontWeight: 600 }}>Laquelle est truquée ?</span>
      </div>
    </Card>
  );
}

// Étape 3 — Scatter toujours visible pour les deux moteurs
function AlwaysOnScatterComparison({ heroMMR, poolSpread, rigStrength, carryScore, seed, games }) {
  const mobile  = useIsMobile();
  const base    = { games, heroMMR, poolSpread, rigStrength, carryScore, seed };
  const rigSim  = useMemo(() => simulate({ ...base, engine: "rig" }),
    [seed, heroMMR, poolSpread, rigStrength, carryScore, games]);
  const fairSim = useMemo(() => simulate({ ...base, engine: "fair" }),
    [seed, heroMMR, poolSpread, rigStrength, carryScore, games]);

  return (
    <Card>
      <Eyebrow>team_diff ~ recent_wr · même seed</Eyebrow>
      <p style={{ fontSize: 12, color: C.mute, margin: "0 0 18px", lineHeight: 1.55 }}>
        X = forme récente du joueur. Y = écart de force entre les deux équipes.
        La droite révèle si ces deux variables sont corrélées.
      </p>

      <div style={{ display: "flex", gap: 16, flexDirection: mobile ? "column" : "row" }}>
        {[["rig", rigSim, C.rig, "TRUQUÉ"], ["fair", fairSim, C.fair, "HONNÊTE"]].map(([key, sim, color, label]) => (
          <div key={key} style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <Eyebrow color={color}>{label}</Eyebrow>
              <span style={{
                fontSize: 26, fontWeight: 700, fontFamily: MONO,
                color: sim.reg.slope < -50 ? C.rig : C.fair,
                lineHeight: 1,
              }}>
                {sim.reg.slope.toFixed(0)}
              </span>
            </div>
            <ScatterPlot scatterPoints={sim.scatterPoints} reg={sim.reg} poolSpread={poolSpread} />
            <div style={{ fontSize: 11, color: C.mute, marginTop: 6 }}>
              R² = {(sim.reg.r2 * 100).toFixed(1)}% · {sim.episodes} épisode(s)
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPOSANTS INTERACTIFS
// ─────────────────────────────────────────────────────────────────────────────

function CarryComparison({ engine, heroMMR, poolSpread, rigStrength, seed, games }) {
  const pairs = useMemo(() => {
    const base = { engine, games, heroMMR, poolSpread, rigStrength, seed };
    return [
      { label: "Yuumi",      sub: "carry 0.05", cs: 0.05, color: C.rig   },
      { label: "Jinx",       sub: "carry 0.65", cs: 0.65, color: C.mute  },
      { label: "Tryndamere", sub: "carry 0.96", cs: 0.96, color: C.fair  },
    ].map(({ label, sub, cs, color }) => {
      const s    = simulate({ ...base, carryScore: cs });
      const unfav = s.results.filter(r => r.diff < 0);
      const wrU   = unfav.length ? (unfav.filter(r => r.win).length / unfav.length * 100) : 0;
      return { label, sub, cs, color, episodes: s.episodes, slope: s.reg.slope, wrUnfav: wrU };
    });
  }, [engine, heroMMR, poolSpread, rigStrength, seed, games]);

  return (
    <Card>
      <Eyebrow color={C.carry}>Hypothèse H3 — archétype et tankabilité du biais</Eyebrow>
      <p style={{ fontSize: 13, color: C.mute, lineHeight: 1.55, margin: "0 0 18px" }}>
        {engine === "rig"
          ? "Même seed, même biais — seul le carry score varie. Un champion autonome peut-il s'en sortir mieux ?"
          : "Passe en moteur truqué pour voir l'effet du carry score."}
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {pairs.map(({ label, sub, color, episodes, slope, wrUnfav }) => (
          <div key={label} style={{
            flex: 1, minWidth: 150,
            background: C.paper,
            border: "1px solid rgba(0,0,0,0.05)",
            borderRadius: 10, padding: "16px",
          }}>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 11, color: C.mute, fontFamily: MONO, marginBottom: 14 }}>{sub}</div>
            {[
              ["Épisodes",   episodes,              episodes > 3 ? C.rig : C.fair],
              ["Pente",      slope.toFixed(0),       slope < -60 ? C.rig : C.fair],
              ["WR déf.",    `${wrUnfav.toFixed(0)}%`, wrUnfav < 45 ? C.rig : C.fair],
            ].map(([l, v, c]) => (
              <div key={l} style={{
                display: "flex", justifyContent: "space-between",
                marginBottom: 6, alignItems: "baseline",
              }}>
                <span style={{ fontSize: 12, color: C.mute }}>{l}</span>
                <span style={{ fontSize: 14, fontWeight: 700, fontFamily: MONO, color: c }}>{v}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}


// Bandeau méthodologie — sobre, 3 colonnes
function MethodologyBanner() {
  return (
    <Card style={{ marginTop: 0 }}>
      <Eyebrow>Méthodologie — 3 niveaux</Eyebrow>
      <div style={{ display: "flex", gap: 0, flexWrap: "wrap" }}>
        {[
          { n: "01", title: "Simulation",       color: C.fair,   tool: "cette page",
            desc: "Deux moteurs, courbes indiscernables à l'œil. Le ressenti ne suffit pas." },
          { n: "02", title: "Collecte Riot API", color: C.target, tool: "collect.py",
            desc: "200+ games par joueur. Variables : team_diff, recent_wr, carry_score, smurf_diff." },
          { n: "03", title: "Test décisif",      color: C.rig,    tool: "analyze.py",
            desc: "Régression team_diff ~ recent_wr. Pente &lt; 0 significative = signature de biais." },
        ].map(({ n, title, color, desc, tool }) => (
          <div key={n} style={{ flex: 1, minWidth: 180, paddingRight: 20 }}>
            <div style={{ fontSize: 10, fontFamily: MONO, color: C.mute, letterSpacing: "0.1em", marginBottom: 6 }}>
              {n}
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{title}</div>
            <p style={{ fontSize: 12, color: C.mute, lineHeight: 1.5, margin: "0 0 6px" }}
              dangerouslySetInnerHTML={{ __html: desc }} />
            <code style={{ fontSize: 11, color, fontFamily: MONO }}>{tool}</code>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NAV
// ─────────────────────────────────────────────────────────────────────────────

function injectLogoKeyframes() {
  if (document.getElementById('logo-kf')) return;
  const s = document.createElement('style');
  s.id = 'logo-kf';
  s.textContent = `
    @keyframes logoZoomIn {
      from { transform: scale(0.12) rotate(-6deg); opacity: 0; }
      to   { transform: scale(1)    rotate(0deg);  opacity: 1; }
    }
    @keyframes logoZoomOut {
      from { transform: scale(1)    rotate(0deg);  opacity: 1; }
      to   { transform: scale(0.12) rotate(6deg);  opacity: 0; }
    }
    @media (prefers-reduced-motion: reduce) {
      @keyframes logoZoomIn {
        from { opacity: 0; }
        to   { opacity: 1; }
      }
      @keyframes logoZoomOut {
        from { opacity: 1; }
        to   { opacity: 0; }
      }
    }
  `;
  document.head.appendChild(s);
}

function LogoOverlay({ open, onClose }) {
  const [visible, setVisible] = React.useState(false);
  const [phase, setPhase] = React.useState('in');

  React.useEffect(() => {
    injectLogoKeyframes();
  }, []);

  React.useEffect(() => {
    if (open) {
      setVisible(true);
      setPhase('in');
    } else if (visible) {
      setPhase('out');
      const t = setTimeout(() => setVisible(false), 320);
      return () => clearTimeout(t);
    }
  }, [open]);

  if (!visible) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'transparent',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
        cursor: 'pointer',
      }}
    >
      <img
        src={logoSvg}
        alt="LQ/WQ logo agrandi"
        style={{
          width: 220, height: 220,
          animation: `${phase === 'in' ? 'logoZoomIn' : 'logoZoomOut'} 0.38s cubic-bezier(0.34,1.56,0.64,1) forwards`,
          pointerEvents: 'none',
          filter: 'drop-shadow(0 8px 32px rgba(26,25,23,0.18))',
        }}
      />
    </div>
  );
}

function NavBar() {
  const loc = useLocation();
  const navigate = useNavigate();
  const mobile = useIsMobile();
  const [logoOpen, setLogoOpen] = React.useState(false);
  const NAV = [
    { to: "/",           label: mobile ? "Théorie"    : "La Théorie"  },
    { to: "/simulateur", label: mobile ? "Simulateur" : "Simulateur"  },
    { to: "/resultats",  label: mobile ? "Résultats"  : "Résultats"   },
  ];
  return (
    <>
      <LogoOverlay open={logoOpen} onClose={() => setLogoOpen(false)} />
      <nav style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "rgba(246,244,239,0.92)",
        backdropFilter: "blur(14px)",
        borderBottom: `1px solid ${C.dim}`,
      }}>
        <div style={{
          maxWidth: 1060, margin: "0 auto",
          display: "flex", alignItems: "center", gap: 2,
          height: 50, padding: "0 20px",
        }}>
          <button
            onClick={(e) => { e.preventDefault(); setLogoOpen(o => !o); navigate("/"); }}
            style={{
              background: 'none', border: 'none', padding: 0,
              cursor: 'pointer', marginRight: mobile ? 6 : 14, flexShrink: 0,
              display: 'flex', alignItems: 'center',
            }}
            aria-label="Afficher le logo"
          >
            <img
              src={logoSvg}
              alt="LQ/WQ logo"
              style={{ height: mobile ? 26 : 32, width: mobile ? 26 : 32 }}
            />
          </button>
          {NAV.map(({ to, label }) => {
            const active = loc.pathname === to;
            return (
              <Link key={to} to={to} style={{
                padding: mobile ? "5px 9px" : "5px 13px", borderRadius: 7,
                fontSize: mobile ? 12 : 13, fontWeight: active ? 600 : 400,
                color: active ? C.text : C.mute,
                background: active ? C.card : "transparent",
                textDecoration: "none",
                border: `1px solid ${active ? C.dim : "transparent"}`,
                transition: "all .1s", whiteSpace: "nowrap",
              }}>{label}</Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MATCHMAKING SCENE — standalone (TheoriePage step 3)
// ─────────────────────────────────────────────────────────────────────────────

function usePrefersReducedMotion() {
  const [reduced, setReduced] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = e => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function mmRng(seed) {
  let s = (seed >>> 0) || 1;
  return () => { s = (Math.imul(1664525, s) + 1013904223) >>> 0; return s / 4294967296; };
}

function mmBuildState(engine, form, seed) {
  const rng = mmRng(seed);
  const base = 72;
  const noise = () => Math.round((rng() - 0.5) * 44);
  const players = [];
  for (let i = 0; i < 5; i++) {
    let lp = base + noise();
    if (engine === "rig" && form === "hot" && i > 0) lp -= 20;
    players.push({ lp: Math.max(15, Math.min(100, lp)), team: "blue", isYou: i === 0 });
  }
  for (let i = 0; i < 5; i++) {
    let lp = base + noise();
    if (engine === "rig" && form === "hot") lp += 20;
    players.push({ lp: Math.max(15, Math.min(100, lp)), team: "red", isYou: false });
  }
  const blue = players.filter(p => p.team === "blue");
  const red  = players.filter(p => p.team === "red");
  const gap  = Math.round(
    blue.reduce((s, p) => s + p.lp, 0) / blue.length -
    red.reduce((s, p) => s + p.lp, 0) / red.length
  );
  return { players, gap };
}

function PlayerDotMM({ lp, team, isYou, noMotion }) {
  const color = team === "blue" ? C.fair : C.rig;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
      <div style={{
        width: isYou ? 30 : 24, height: isYou ? 30 : 24,
        borderRadius: "50%", background: color,
        opacity: isYou ? 1 : 0.6,
        border: isYou ? `2px solid ${C.target}` : "none",
        boxShadow: isYou ? `0 0 0 3px ${C.target}33` : "none",
        transition: noMotion ? "none" : "all .4s cubic-bezier(.4,0,.2,1)",
      }} />
      <span style={{ fontSize: 9, fontFamily: MONO, color: isYou ? C.text : C.mute, fontWeight: isYou ? 700 : 400 }}>
        {lp}
      </span>
    </div>
  );
}

function GapBarMM({ gapLP, noMotion }) {
  const maxLP = 100;
  const clamped = Math.max(-maxLP, Math.min(maxLP, gapLP));
  const pct = (Math.abs(clamped) / maxLP) * 50;
  const toRight = clamped < 0;
  const color = toRight ? C.rig : C.fair;
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ position: "relative", height: 8, borderRadius: 4, background: C.dim, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 2, background: C.mute, opacity: .4, transform: "translateX(-50%)" }} />
        <div style={{
          position: "absolute", top: 0, bottom: 0,
          [toRight ? "left" : "right"]: "50%",
          width: `${pct}%`, background: color, borderRadius: 4,
          transition: noMotion ? "none" : "all .5s cubic-bezier(.4,0,.2,1)",
        }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, fontSize: 10, fontFamily: MONO, color: C.mute }}>
        <span style={{ color: C.fair }}>bleue</span>
        <span style={{ color: Math.abs(gapLP) > 4 ? color : C.mute, fontWeight: 600 }}>
          {Math.abs(gapLP) < 3 ? "équilibré" : `${Math.abs(gapLP)} LP`}
        </span>
        <span style={{ color: C.rig }}>rouge</span>
      </div>
    </div>
  );
}

function MatchmakingScene({ seed }) {
  const mobile    = useIsMobile();
  const noMotion  = usePrefersReducedMotion();
  const [engine, setEngine] = useState("fair");
  const [form,   setForm]   = useState("hot");

  const { players, gap } = useMemo(
    () => mmBuildState(engine, form, seed * 997 + 13),
    [engine, form, seed]
  );
  const blue = players.filter(p => p.team === "blue");
  const red  = players.filter(p => p.team === "red");

  return (
    <div style={{ background: C.paper, border: `1px solid ${C.dim}`, borderRadius: 12, padding: "22px 20px 18px", marginBottom: 8 }}>
      <div style={{ textAlign: "center", marginBottom: 16, fontSize: 10, letterSpacing: "0.1em",
        fontFamily: MONO, color: engine === "rig" ? C.rig : C.fair, textTransform: "uppercase" }}>
        Hypothèse · matchmaking {engine === "rig" ? "truqué" : "honnête"}
      </div>

      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: mobile ? 10 : 20, flexWrap: "nowrap" }}>
        <div style={{ display: "flex", gap: mobile ? 6 : 8, flexWrap: "wrap", justifyContent: "center", width: mobile ? 130 : 155 }}>
          {blue.map((p, i) => <PlayerDotMM key={i} {...p} noMotion={noMotion} />)}
        </div>
        <span style={{ fontSize: 10, fontFamily: MONO, color: C.mute, flexShrink: 0 }}>vs</span>
        <div style={{ display: "flex", gap: mobile ? 6 : 8, flexWrap: "wrap", justifyContent: "center", width: mobile ? 130 : 155 }}>
          {red.map((p, i) => <PlayerDotMM key={i} {...p} noMotion={noMotion} />)}
        </div>
      </div>

      <GapBarMM gapLP={gap} noMotion={noMotion} />

      <div style={{ display: "flex", gap: 6, marginTop: 18, flexWrap: "wrap" }}>
        {[["fair", "Honnête", C.fair], ["rig", "Truqué", C.rig]].map(([k, l, c]) => (
          <button key={k} onClick={() => setEngine(k)} style={{
            flex: 1, padding: "7px 10px", borderRadius: 7, fontSize: 12, fontWeight: 600,
            cursor: "pointer",
            background: engine === k ? c + "18" : "transparent",
            color: engine === k ? c : C.mute,
            border: `1px solid ${engine === k ? c + "55" : C.dim}`,
            transition: "all .12s",
          }}>{l}</button>
        ))}
      </div>

      {engine === "rig" && (
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          {[["hot", "En forme 🔥"], ["cold", "En défaite"]].map(([k, l]) => (
            <button key={k} onClick={() => setForm(k)} style={{
              flex: 1, padding: "5px 10px", borderRadius: 20, fontSize: 11,
              cursor: "pointer",
              background: form === k ? C.target + "18" : "transparent",
              color: form === k ? C.target : C.mute,
              border: `1px solid ${form === k ? C.target + "55" : C.dim}`,
              transition: "all .12s",
            }}>{l}</button>
          ))}
        </div>
      )}

      <p style={{ fontSize: 11, color: C.mute, margin: "12px 0 0", lineHeight: 1.6 }}>
        {engine === "fair"
          ? <>En matchmaking <b style={{ color: C.fair }}>honnête</b>, la barre oscille sans direction — la forme du joueur n'influence pas la composition des équipes.</>
          : form === "hot"
          ? <>En matchmaking <b style={{ color: C.rig }}>truqué</b> et joueur en forme, l'équipe bleue est désavantagée. C'est la signature que <code style={{ fontFamily: MONO, color: C.target }}>team_diff~recent_wr</code> détecte.</>
          : <>En matchmaking <b style={{ color: C.rig }}>truqué</b> et joueur en défaite, l'effet s'inverse — le biais est corrélé à la forme, pas au hasard.</>
        }
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE — THÉORIE (/)
// ─────────────────────────────────────────────────────────────────────────────

function TheoriePage() {
  const mobile = useIsMobile();
  const [seed, setSeed] = useState(7);
  const BASE = { heroMMR: 2400, poolSpread: 180, rigStrength: 220, carryScore: 0.65, games: 300 };

  return (
    <div style={{ padding: mobile ? "24px 16px" : "40px 20px" }}>
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>

        <div style={{ marginBottom: 36 }}>
          <div style={{ fontSize: 10, letterSpacing: "0.15em", color: C.mute, fontFamily: MONO, marginBottom: 10 }}>
            MATCHMAKING · BANC D'ESSAI STATISTIQUE
          </div>
          <h1 style={{ fontSize: mobile ? 22 : 32, fontWeight: 800, margin: "0 0 10px", lineHeight: 1.15, letterSpacing: "-0.5px", fontFamily: SANS }}>
            L'expérience décrite laisse-t-elle une trace détectable dans les données publiques ?
          </h1>
          <p style={{ color: C.mute, fontSize: 14, lineHeight: 1.65, maxWidth: 520, margin: 0 }}>
            Simule les deux moteurs, teste ton intuition, puis vois ce que les{" "}
            <Link to="/resultats" style={{ color: C.text, textDecoration: "underline", textDecorationColor: C.dim }}>
              vraies données
            </Link>{" "}
            disent. Le test ne peut pas prouver que la manipulation n'existe pas — il peut seulement
            montrer qu'elle ne laisse aucune trace détectable dans les données publiques.
          </p>
          <div style={{ marginTop: 20, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link to="/resultats" style={{
              padding: "10px 22px", background: C.target, color: C.ink,
              borderRadius: 7, fontSize: 13, fontWeight: 700, textDecoration: "none",
            }}>Voir les résultats →</Link>
            <Link to="/resultats" style={{
              padding: "10px 18px", background: "transparent", color: C.mute,
              borderRadius: 7, fontSize: 13, fontWeight: 500, textDecoration: "none",
              border: `1px solid ${C.dim}`,
            }}>Tester mon compte</Link>
          </div>
        </div>

        {/* 01 */}
        <Step n={1} title="Le paradoxe"
          sub="Un matchmaking honnête et un matchmaking truqué produisent des courbes de WR identiques à l'œil" />
        <ParadoxSection seed={seed} {...BASE} />
        <Callout color={C.fair}>
          Les deux win-rates convergent vers 50%, les séries de défaites ont la même longueur.{" "}
          <b>Impossible de dire laquelle est truquée</b> — c'est tout le piège.
          Le ressenti ne distingue pas les deux moteurs. Il faut un test différent.
        </Callout>
        <p style={{ fontSize: 12, color: C.mute, lineHeight: 1.6, marginTop: 8, fontStyle: "italic" }}>
          Ce que le simulateur montre déjà : les deux moteurs produisent la même expérience vécue.
          Pourquoi ? Parce que le hasard honnête produit des <em>séries distinctes</em>, pas de
          l'alternance — des paquets de victoires suivis de défaites. L'intuition inverse (« sans
          truquage ce serait plus dilué ») est la confusion la plus documentée en théorie des
          probabilités. Une alternance régulière serait elle-même suspecte. C'est pour ça que le
          test de symétrie regarde la composition des équipes — pas les résultats.
        </p>

        {/* 02 */}
        <Step n={2} title="Le test décisif"
          sub="Ce que les courbes cachent — le nuage de points révèle le signal" />
        <div style={{
          margin: "0 0 16px",
          padding: "14px 18px",
          background: C.paper,
          border: `1px solid ${C.dim}`,
          borderLeft: `3px solid ${C.target}`,
          borderRadius: "0 8px 8px 0",
          fontSize: 13, color: C.mute, lineHeight: 1.65,
        }}>
          <b style={{ color: C.text }}>Comment lire ce graphe :</b>{" "}
          si le jeu te truque, quand tu gagnes beaucoup (droite sur l'axe X),
          tes alliés devraient être plus faibles (valeur négative sur l'axe Y).
          Une droite qui penche vers le bas = signature d'un matchmaking truqué.
        </div>
        <AlwaysOnScatterComparison {...BASE} seed={seed} />
        <Callout color={C.rig}>
          <b>Moteur truqué :</b> pente nettement négative — quand le joueur est en forme,
          l'écart d'équipe se creuse systématiquement.{" "}
          <b>Moteur honnête :</b> pente ≈ 0, nuage plat. C'est ce test —{" "}
          <code style={{ color: C.target, fontFamily: MONO }}>team_diff ~ recent_wr</code>
          {" "}— appliqué sur les{" "}
          <Link to="/resultats" style={{ color: C.target }}>vraies données →</Link>
        </Callout>

        {/* 03 */}
        <Step n={3} title="La composition des équipes"
          sub="Hypothèses — voici à quoi ressemblerait la répartition selon chaque modèle" />
        <MatchmakingScene seed={seed} />

        <div style={{ marginTop: 24 }}>
          <button onClick={() => setSeed(s => s + 1)} style={{
            padding: "8px 16px", background: "transparent", color: C.mute,
            border: `1px solid ${C.dim}`, borderRadius: 7, fontSize: 12,
            cursor: "pointer", fontFamily: MONO,
          }}>⟳ Nouvelle seed #{seed + 1}</button>
        </div>

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE — SIMULATEUR (/simulateur)
// ─────────────────────────────────────────────────────────────────────────────

function SimulatorPage() {
  const mobile = useIsMobile();
  const [engine,      setEngine]      = useState("rig");
  const [heroMMR,     setHeroMMR]     = useState(2400);
  const [poolSpread,  setPoolSpread]  = useState(180);
  const [rigStrength, setRigStrength] = useState(220);
  const [carryScore,  setCarryScore]  = useState(0.65);
  const [seed,        setSeed]        = useState(7);
  const [runs,        setRuns]        = useState(200);
  const [batch,       setBatch]       = useState(null);
  const [batchEngine, setBatchEngine] = useState(null);
  const games = 300;

  const sim = useMemo(
    () => simulate({ engine, games, heroMMR, poolSpread, rigStrength, carryScore, seed }),
    [engine, games, heroMMR, poolSpread, rigStrength, carryScore, seed]
  );
  const episodeRanges = useMemo(() => findEpisodeRanges(sim.results), [sim.results]);
  const color = engine === "rig" ? C.rig : C.fair;

  const carryLabel =
    carryScore < 0.20 ? "Enchanteur pur (Yuumi, Sona)"
    : carryScore < 0.40 ? "Support engage (Leona, Braum)"
    : carryScore < 0.58 ? "Mage équilibré (Orianna, Viktor)"
    : carryScore < 0.75 ? "ADC / Carry mid (Jinx, Ahri)"
    : carryScore < 0.88 ? "Assassin (Zed, Akali, Riven)"
    : "Split pusher (Tryndamere, Fiora)";

  return (
    <div style={{ padding: mobile ? "24px 16px" : "40px 20px" }}>
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>

        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, letterSpacing: "0.15em", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
            SIMULATEUR INTERACTIF
          </div>
          <h2 style={{ fontSize: mobile ? 20 : 26, fontWeight: 800, margin: "0 0 8px", letterSpacing: "-0.3px" }}>
            Explorer les deux moteurs
          </h2>
          <p style={{ fontSize: 13, color: C.mute, lineHeight: 1.6, maxWidth: 520, margin: 0 }}>
            Bascule entre truqué et honnête pour visualiser les deux moteurs en temps réel.
          </p>
        </div>

        {/* Toggle moteur */}
        <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
          {[["rig", "Truqué", C.rig], ["fair", "Honnête", C.fair]].map(([k, l, c]) => (
            <button key={k} onClick={() => setEngine(k)} style={{
              flex: 1, padding: "11px 14px",
              background: engine === k ? c + "20" : "transparent",
              color: engine === k ? c : C.mute,
              border: `1px solid ${engine === k ? c + "60" : C.dim}`,
              borderRadius: 8, fontSize: 13, fontWeight: 600,
              cursor: "pointer", transition: "all .12s",
            }}>
              <span style={{
                display: "inline-block", width: 7, height: 7, borderRadius: "50%",
                background: c, marginRight: 7, verticalAlign: "middle",
                opacity: engine === k ? 1 : 0.35,
              }} />
              {l}
            </button>
          ))}
        </div>

        {/* Indicateurs */}
        <Card>
          <Eyebrow>Indicateurs · {games} games</Eyebrow>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <Stat label="Win-rate"        value={`${sim.winRate.toFixed(1)}%`} />
            <Stat label="Série L max"     value={sim.maxLoss} />
            <Stat label="Épisodes"        value={sim.episodes} color={sim.episodes > 3 ? C.rig : C.mute} />
            <Stat label="WR équipe faible"
              value={sim.wrUnfav != null ? `${sim.wrUnfav.toFixed(0)}%` : "—"}
              color={sim.wrUnfav < 45 ? C.rig : C.fair} />
            <Stat label="Pente reg."      value={sim.reg.slope.toFixed(0)}
              color={sim.reg.slope < -60 ? C.rig : sim.reg.slope < -25 ? C.target : C.fair} />
          </div>
        </Card>

        {/* Courbe WR + streak strip */}
        <Card>
          <Eyebrow>Win-rate cumulé{episodeRanges.length > 0 && ` · ${episodeRanges.length} épisode(s)`}</Eyebrow>
          {episodeRanges.length > 0 && (
            <p style={{ fontSize: 12, color: C.mute, margin: "0 0 10px", lineHeight: 1.5 }}>
              Zones ombrées : ≥3 games de suite où{" "}
              <span style={{ color: C.rig }}>l'équipe est anormalement faible</span>{" "}
              alors que <span style={{ color: C.fair }}>le joueur est en forme</span> (WR récent &gt; 55%)
            </p>
          )}
          <Sparkline data={sim.wr} episodeRanges={episodeRanges} color={color} />
          <Divider margin="14px 0 10px" />
          <div style={{ fontSize: 11, color: C.mute, marginBottom: 8, fontFamily: MONO }}>
            <span style={{ color: C.fair }}>■ victoire</span>{"  "}
            <span style={{ color: C.rig }}>■ défaite</span>
            {episodeRanges.length > 0 && <span style={{ color: C.target }}> · contour or = dans un épisode</span>}
          </div>
          <StreakStrip results={sim.results} episodeRanges={episodeRanges} />
        </Card>

        {/* Carry */}
        <CarryComparison engine={engine} heroMMR={heroMMR} poolSpread={poolSpread}
          rigStrength={rigStrength} seed={seed} games={games} />

        {/* Paramètres */}
        <Card>
          <Eyebrow>Paramètres</Eyebrow>
          <Slider label="MMR du héros" value={heroMMR} min={1000} max={3200} step={50}
            onChange={setHeroMMR} hint="Plus haut = pool plus rare = écarts naturellement plus larges." />
          <Slider label="Dispersion du pool" value={poolSpread} min={50} max={400} step={10}
            onChange={setPoolSpread} hint="Écart-type de niveau des 9 autres joueurs." />
          <Slider label="Force du biais" value={rigStrength} min={0} max={500} step={10}
            onChange={setRigStrength} disabled={engine !== "rig"}
            hint={engine === "rig" ? "Intensité du biais quand le joueur est en forme." : "Inactif en mode honnête."} />
          <Divider margin="8px 0 16px" />
          <Slider label={`Carry score — ${carryLabel}`}
            value={Math.round(carryScore * 100)} min={0} max={100} step={5}
            onChange={v => setCarryScore(v / 100)} color={C.carry}
            hint="0 = Yuumi → 100 = Tryndamere. Modifie l'impact du biais (H3)." />
          <button onClick={() => setSeed(s => s + 1)} style={{
            marginTop: 4, padding: "9px 16px", background: "transparent", color: C.mute,
            border: `1px solid ${C.dim}`, borderRadius: 7, fontSize: 12, cursor: "pointer", fontFamily: MONO,
          }}>⟳ Nouvelle seed #{seed + 1}</button>
        </Card>

        {/* Batch — mode avancé */}
        <Collapsible title="Distribution sur N simulations — mode avancé">
          <div style={{ padding: "0 24px" }}>
            <p style={{ fontSize: 12, color: C.mute, margin: "12px 0 16px", lineHeight: 1.5 }}>
              Lance N fois la simulation. Les <b style={{ color: C.text }}>pentes de régression</b> sont l'indicateur le plus décisif.
            </p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <button onClick={() => {
                setBatch(batchSimulate({ engine, games, heroMMR, poolSpread, rigStrength, carryScore, seed }, runs));
                setBatchEngine(engine);
              }} style={{
                padding: "10px 18px", background: color, color: C.ink,
                border: "none", borderRadius: 7, fontSize: 13, fontWeight: 700, cursor: "pointer",
              }}>▶ Lancer {runs} simulations</button>
              <div style={{ flex: 1, minWidth: 160 }}>
                <input type="range" min={20} max={1000} step={20} value={runs}
                  onChange={e => setRuns(Number(e.target.value))}
                  style={{ width: "100%", accentColor: C.target }} />
                <div style={{ fontSize: 11, color: C.mute, marginTop: 2, fontFamily: MONO }}>
                  {runs} runs · {(runs * games).toLocaleString()} parties
                </div>
              </div>
            </div>
            {batch && (
              <div style={{ marginTop: 18 }}>
                <div style={{ fontSize: 11, color: C.mute, marginBottom: 12, fontFamily: MONO }}>
                  {runs} runs ·{" "}
                  <span style={{ color: batchEngine === "rig" ? C.rig : C.fair }}>
                    moteur {batchEngine === "rig" ? "truqué" : "honnête"}
                  </span>{" · ligne pointillée = moyenne"}
                </div>
                {[
                  { label: "Win-rate final", values: batch.winRates, min: 35, max: 65, bins: 24, color: batchEngine === "rig" ? C.rig : C.fair, unit: "%" },
                  { label: "Pentes de régression — à gauche de 0 = signature d'un matchmaking truqué", values: batch.slopes, min: -400, max: 200, bins: 24, color: C.target, unit: "", highlightNeg: true },
                  { label: "Série de défaites max", values: batch.maxLosses, min: 0, max: 20, bins: 20, color: C.rig, unit: "" },
                ].map(({ label, ...props }) => (
                  <div key={label} style={{ marginBottom: 20 }}>
                    <div style={{ fontSize: 12, color: C.text, marginBottom: 4 }}>{label}</div>
                    <Histogram {...props} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </Collapsible>

        <p style={{ color: C.mute, fontSize: 12, lineHeight: 1.7, marginTop: 20 }}>
          Essaie : biais à 0 en mode honnête, MMR à 3000. Tu verras des séries de 7–8 défaites{" "}
          <em>sans aucun biais</em> — juste la variance naturelle d'un pool rare.
          Seule la <span style={{ color: C.text }}>pente de régression</span> distingue les deux hypothèses.
        </p>

        <div style={{
          marginTop: 32, padding: "20px 24px",
          background: C.card, border: `1px solid ${C.dim}`,
          borderRadius: 14, textAlign: "center",
          boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
        }}>
          <div style={{ fontSize: 14, color: C.mute, marginBottom: 12 }}>
            Prochaine étape — applique le test sur ton propre compte
          </div>
          <Link to="/resultats" style={{
            display: "inline-block",
            padding: "12px 28px", background: C.target, color: C.ink,
            borderRadius: 8, fontSize: 14, fontWeight: 700, textDecoration: "none",
          }}>Tester mon compte →</Link>
        </div>

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE — RÉSULTATS (/resultats)
// ─────────────────────────────────────────────────────────────────────────────

function ResultatsPage() {
  const mobile = useIsMobile();
  const { players, n_total } = realData;
  const n = players ? players.length : 0;
  const phase = n >= 10 ? "confirmatoire" : "pilote";

  return (
    <div style={{ padding: mobile ? "24px 16px" : "40px 20px" }}>
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, letterSpacing: "0.15em", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
            RÉSULTATS · API RIOT
          </div>
          <h2 style={{ fontSize: mobile ? 20 : 26, fontWeight: 800, margin: "0 0 8px", letterSpacing: "-0.3px" }}>
            Données réelles
          </h2>
          <p style={{ fontSize: 13, color: C.mute, lineHeight: 1.6, maxWidth: 560, margin: 0 }}>
            Le test <code style={{ color: C.target, fontFamily: MONO }}>team_diff ~ recent_wr</code>{" "}
            appliqué sur de vraies games via l'API Riot.{" "}
            <b style={{ color: C.text }}>{n} joueurs · {n_total?.toLocaleString("fr-FR")} games</b>
            {phase === "pilote"
              ? " · collecte confirmatoire en cours (cible : 48 joueurs)."
              : " · phase confirmatoire active."}
          </p>
        </div>

        {/* OSF — crédibilité avant les chiffres */}
        <div style={{
          marginBottom: 20,
          padding: "14px 18px",
          background: "rgba(200,155,10,0.06)",
          border: `1px solid rgba(200,155,10,0.25)`,
          borderLeft: `3px solid ${C.target}`,
          borderRadius: 10,
          fontSize: 13, color: C.mute, lineHeight: 1.65,
        }}>
          <b style={{ color: C.target }}>Pré-registration · osf.io/kdbxg</b>
          {" — "}Hypothèses et méthode déposées publiquement avant toute collecte
          (<b style={{ color: C.text }}>30 juin 2026, 15:09</b>).
          Garantit que les résultats ci-dessous ne sont pas fabriqués après coup.
        </div>

        {/* Données réelles — raison principale de la visite */}
        <RealDataSection />

        {/* Analyser mon compte — maintenant motivé par les données vues */}
        <div style={{ marginTop: 28, marginBottom: 8 }}>
          <div style={{ fontSize: 10, letterSpacing: "0.15em", color: C.mute, fontFamily: "monospace", marginBottom: 6 }}>
            ANALYSER MON COMPTE
          </div>
          <p style={{ fontSize: 13, color: C.mute, margin: "0 0 14px" }}>
            Entre ton Riot ID pour voir si ton matchmaking est neutre ou biaisé.
          </p>
        </div>
        <Analysis />

        {/* Limites structurelles */}
        <div style={{
          margin: "24px 0 16px",
          padding: "14px 18px",
          background: C.paper,
          border: `1px solid ${C.dim}`,
          borderLeft: `3px solid ${C.mute}`,
          borderRadius: "0 8px 8px 0",
          fontSize: 12, color: C.mute, lineHeight: 1.7,
        }}>
          <b style={{ color: C.text, display: "block", marginBottom: 6 }}>Limites de cette mesure</b>
          <div style={{ marginBottom: 4 }}>
            <b style={{ color: C.text }}>Drift temporel</b> — le rang utilisé est le rang actuel, appliqué à des games historiques.
            Un joueur dont le niveau a changé entre ses parties et aujourd'hui introduit un biais dans l'écart d'équipe calculé.
            L'effet peut être sous-estimé ou sur-estimé selon le sens du drift.
          </div>
          <div style={{ marginBottom: 4 }}>
            <b style={{ color: C.text }}>Biais de sélection</b> — le recrutement attire préférentiellement des joueurs qui croient à la loser queue.
            Le test de symétrie mesure la composition des équipes (pas la performance individuelle), ce qui le rend partiellement immunisé —
            mais une sur-représentation de joueurs en tilt reste possible.
          </div>
          <div>
            <b style={{ color: C.text }}>Frontière de détectabilité</b> — en dessous de 26,3 points de rang par unité de win-rate
            (noise_ratio = 0,50, N = 3 000), le test actuel ne peut pas conclure. Si la manipulation déclenchait
            sur le MMR interne plutôt que sur le win-rate observable, l'effet serait atténué d'un facteur λ = 0,800
            dans les données — une réduction irréductible. Détecter cet effet nécessiterait environ 1,6× plus de données ;
            dans la limite orthogonale (λ→0), une infinité — aucune étude externe ne pourrait conclure.
          </div>
        </div>

        {/* Méthodologie */}
        <div style={{ marginTop: 16, fontSize: 12, color: C.mute, textAlign: "center" }}>
          <a href="/" style={{ color: C.mute, textDecoration: "underline" }}>← Comment fonctionne le test statistique ?</a>
        </div>

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// APP
// ─────────────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <div style={{ minHeight: "100vh", background: C.ink, color: C.text, fontFamily: SANS }}>
      <NavBar />
      <Routes>
        <Route path="/"           element={<TheoriePage />} />
        <Route path="/simulateur" element={<SimulatorPage />} />
        <Route path="/resultats"  element={<ResultatsPage />} />
        <Route path="*"           element={<TheoriePage />} />
      </Routes>
    </div>
  );
}
