import React, { useState, useRef } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const C = {
  target:  "#E8C547",
  rig:     "#D6453D",
  fair:    "#3FA7A0",
  carry:   "#A78BFA",
  ink:     "#08080E",
  paper:   "#10101A",
  card:    "#14141E",
  mute:    "#4E4E68",
  dim:     "#2A2A3C",
  text:    "#E2E2EE",
};

const MONO = "ui-monospace,Menlo,'SF Mono',monospace";
const SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";

function Spinner() {
  return (
    <span style={{
      display: "inline-block",
      width: 18, height: 18,
      border: `2px solid ${C.dim}`,
      borderTopColor: C.target,
      borderRadius: "50%",
      animation: "spin 0.75s linear infinite",
      verticalAlign: "middle",
      marginRight: 10,
    }} />
  );
}

function ErrorBox({ message }) {
  return (
    <div style={{
      background: "rgba(214,69,61,0.08)",
      border: `1px solid ${C.rig}44`,
      borderRadius: 10,
      padding: "14px 18px",
      color: C.rig,
      fontSize: 13,
      lineHeight: 1.6,
      fontFamily: MONO,
    }}>
      {message}
    </div>
  );
}

function ScatterSVG({ scatter, slope }) {
  const W = 300, H = 200;
  const PAD = { l: 30, r: 14, t: 20, b: 28 };
  const IW = W - PAD.l - PAD.r;
  const IH = H - PAD.t - PAD.b;

  const ys = scatter.map(([, y]) => y);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, 0);
  const yRange = Math.max(Math.abs(yMin), Math.abs(yMax), 50) * 1.15;

  const toSX = x => PAD.l + x * IW;
  const toSY = y => PAD.t + (1 - (y + yRange) / (2 * yRange)) * IH;

  const midY = toSY(0);
  const intercept = -(slope * 0.5);
  const regX0 = toSX(0), regY0 = toSY(intercept);
  const regX1 = toSX(1), regY1 = toSY(slope + intercept);
  const slopeColor = slope < -80 ? C.rig : slope < -30 ? C.target : C.fair;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      <line x1={PAD.l} y1={midY} x2={W - PAD.r} y2={midY} stroke={C.dim} strokeWidth="1" />
      <line x1={toSX(0.5)} y1={PAD.t} x2={toSX(0.5)} y2={H - PAD.b}
        stroke={C.dim} strokeWidth="1" strokeDasharray="3 4" />

      <text x={PAD.l}         y={H - 6} fill={C.mute} fontSize="8" fontFamily={MONO}>0%</text>
      <text x={toSX(0.5) - 6} y={H - 6} fill={C.mute} fontSize="8" fontFamily={MONO}>50%</text>
      <text x={W - PAD.r - 18} y={H - 6} fill={C.mute} fontSize="8" fontFamily={MONO}>100%</text>
      <text x={PAD.l - 3} y={PAD.t + 4}       fill={C.mute} fontSize="8" fontFamily={MONO} textAnchor="end">+</text>
      <text x={PAD.l - 3} y={H - PAD.b - 3}   fill={C.mute} fontSize="8" fontFamily={MONO} textAnchor="end">−</text>

      {scatter.map(([x, y, w], i) => (
        <circle key={i}
          cx={toSX(x)}
          cy={toSY(Math.max(-yRange, Math.min(yRange, y)))}
          r={2.2}
          fill={w ? C.fair : C.rig}
          opacity={0.42} />
      ))}

      <line x1={regX0} y1={regY0} x2={regX1} y2={regY1}
        stroke={slopeColor} strokeWidth="1.5" opacity="0.9" />

      <text x={W - PAD.r - 2} y={PAD.t - 4}
        fill={slopeColor} fontSize="10" fontFamily={MONO}
        fontWeight="600" textAnchor="end">
        pente {slope != null ? slope.toFixed(0) : "—"}
      </text>
    </svg>
  );
}

function TimelineSVG({ timeline }) {
  const W = 500, H = 150;
  const PAD = { l: 36, r: 36, t: 16, b: 24 };
  const IW = W - PAD.l - PAD.r;
  const IH = H - PAD.t - PAD.b;

  const n = timeline.length;
  if (n === 0) return null;

  const diffs = timeline.map(([, , d]) => d).filter(d => d != null);
  const wrs   = timeline.map(([, w])   => w).filter(w => w != null);

  const yMin  = Math.min(...diffs, 0);
  const yMax  = Math.max(...diffs, 0);
  const yRange = Math.max(Math.abs(yMin), Math.abs(yMax), 50) * 1.2;

  const toX  = idx => PAD.l + (idx / Math.max(n - 1, 1)) * IW;
  const toYL = y   => PAD.t + (1 - (y + yRange) / (2 * yRange)) * IH;

  const wrMin = Math.min(...wrs, 0);
  const wrMax = Math.max(...wrs, 1);
  const toYR  = w => PAD.t + (1 - (w - wrMin) / Math.max(wrMax - wrMin, 0.01)) * IH;

  const midY = toYL(0);

  const wrPath = timeline
    .filter(([, w]) => w != null)
    .map(([idx, w]) => `${toX(idx).toFixed(1)},${toYR(w).toFixed(1)}`)
    .join(" L ");
  const wrPathD = wrPath ? "M " + wrPath : null;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      <line x1={PAD.l} y1={midY} x2={W - PAD.r} y2={midY} stroke={C.dim} strokeWidth="1" />

      {timeline.map(([idx, , d, w]) => {
        if (d == null) return null;
        return (
          <circle key={idx}
            cx={toX(idx)}
            cy={toYL(Math.max(-yRange, Math.min(yRange, d)))}
            r={2.5}
            fill={w ? C.fair : C.rig}
            opacity={0.6} />
        );
      })}

      {wrPathD && (
        <path d={wrPathD} fill="none" stroke={C.target} strokeWidth="1.2" opacity="0.7" />
      )}

      <text x={PAD.l} y={H - 5}       fill={C.mute} fontSize="8" fontFamily={MONO}>0</text>
      <text x={W - PAD.r} y={H - 5}   fill={C.mute} fontSize="8" fontFamily={MONO} textAnchor="end">{n - 1}</text>
      <text x={PAD.l - 3} y={PAD.t + 4} fill={C.mute} fontSize="8" fontFamily={MONO} textAnchor="end">+</text>
      <text x={PAD.l - 3} y={H - PAD.b - 2} fill={C.mute} fontSize="8" fontFamily={MONO} textAnchor="end">−</text>

      {wrPathD && (
        <text x={W - PAD.r + 2} y={PAD.t + 8} fill={C.target} fontSize="8" fontFamily={MONO}>WR</text>
      )}
    </svg>
  );
}

function CarrySection({ slope_1v9, slope_teamdep }) {
  if (slope_1v9 == null && slope_teamdep == null) return null;
  const maxAbs = 250;
  const bar = (val, label, color) => {
    if (val == null) return null;
    const pct = Math.min(Math.abs(val) / maxAbs * 100, 100);
    const neg  = val < 0;
    return (
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3, fontSize: 11, color: C.mute }}>
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
          }} />
        </div>
      </div>
    );
  };
  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase",
        color: C.mute, fontFamily: MONO, marginBottom: 10 }}>
        Carry stratification
      </div>
      {bar(slope_1v9,    "1v9 carry",    C.rig)}
      {bar(slope_teamdep,"team-dep.",     C.carry)}
    </div>
  );
}

export default function Analysis() {
  const [riotId,  setRiotId]  = useState("");
  const [region,  setRegion]  = useState("europe");
  const [platform, setPlatform] = useState("euw1");
  const [count,   setCount]   = useState(100);
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);
  const abortRef = useRef(null);

  const platformByRegion = {
    europe:   ["euw1", "eun1", "tr1", "ru"],
    americas: ["na1", "br1", "la1", "la2"],
    asia:     ["kr", "jp1"],
  };

  const handleRegionChange = (r) => {
    setRegion(r);
    const platforms = platformByRegion[r];
    if (platforms && !platforms.includes(platform)) {
      setPlatform(platforms[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!riotId.includes("#")) {
      setError("Format invalide. Utilisez le format: Pseudo#TAG");
      return;
    }

    setLoading(true);
    setResult(null);
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000);

    try {
      const resp = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ riot_id: riotId, region, platform, count }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (resp.status === 404) {
        setError("Joueur introuvable. Vérifiez le Riot ID (format: Pseudo#TAG).");
        return;
      }
      if (resp.status === 429) {
        setError("Rate limit API Riot. Réessayez dans quelques secondes.");
        return;
      }
      if (!resp.ok) {
        const body = await resp.text().catch(() => "");
        setError(`Erreur serveur (${resp.status})${body ? ": " + body : ""}.`);
        return;
      }

      const data = await resp.json();
      setResult(data);
    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        setError("Délai dépassé (>10 min). Réessayez ou réduisez le nombre de games.");
      } else if (err.message && (err.message.includes("fetch") || err.message.includes("Failed"))) {
        setError("Backend non disponible. Lancez : cd api && uvicorn server:app --reload");
      } else {
        setError(`Erreur inattendue : ${err.message}`);
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const hasSignal = result && result.p_uni < 0.05 && result.slope < 0;

  const platforms = platformByRegion[region] || ["euw1"];

  return (
    <div style={{
      background: C.card,
      border: "1px solid rgba(255,255,255,0.05)",
      borderRadius: 14,
      padding: "28px 28px 24px",
      marginBottom: 32,
      fontFamily: SANS,
    }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
        textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 10 }}>
        Analyse personnelle · API Riot
      </div>
      <div style={{ fontWeight: 700, fontSize: 18, color: C.text, marginBottom: 6 }}>
        Mon analyse
      </div>
      <p style={{ fontSize: 13, color: C.mute, margin: "0 0 20px", lineHeight: 1.6 }}>
        Teste la théorie sur ton propre compte. Le backend collecte tes games et calcule
        la régression <code style={{ color: C.target, fontFamily: MONO }}>team_diff ~ recent_wr</code>.
      </p>

      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div style={{ flex: "2 1 200px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>
            Riot ID (ex : Pseudo#EUW)
          </label>
          <input
            type="text"
            value={riotId}
            onChange={e => setRiotId(e.target.value)}
            placeholder="Pseudo#TAG"
            required
            disabled={loading}
            style={{
              width: "100%",
              background: C.paper,
              border: `1px solid ${C.dim}`,
              borderRadius: 7,
              padding: "9px 12px",
              color: C.text,
              fontSize: 13,
              fontFamily: MONO,
              outline: "none",
              boxSizing: "border-box",
              opacity: loading ? 0.5 : 1,
            }}
          />
        </div>

        <div style={{ flex: "1 1 120px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>Région</label>
          <select
            value={region}
            onChange={e => handleRegionChange(e.target.value)}
            disabled={loading}
            style={{
              width: "100%",
              background: C.paper,
              border: `1px solid ${C.dim}`,
              borderRadius: 7,
              padding: "9px 10px",
              color: C.text,
              fontSize: 13,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.5 : 1,
            }}
          >
            <option value="europe">europe</option>
            <option value="americas">americas</option>
            <option value="asia">asia</option>
          </select>
        </div>

        <div style={{ flex: "1 1 100px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>Serveur</label>
          <select
            value={platform}
            onChange={e => setPlatform(e.target.value)}
            disabled={loading}
            style={{
              width: "100%",
              background: C.paper,
              border: `1px solid ${C.dim}`,
              borderRadius: 7,
              padding: "9px 10px",
              color: C.text,
              fontSize: 13,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.5 : 1,
            }}
          >
            {platforms.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div style={{ flex: "0 1 90px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>
            Games (<span style={{ fontFamily: MONO }}>count</span>)
          </label>
          <input
            type="number"
            value={count}
            onChange={e => setCount(Math.max(20, Math.min(500, Number(e.target.value))))}
            min={20} max={500}
            disabled={loading}
            style={{
              width: "100%",
              background: C.paper,
              border: `1px solid ${C.dim}`,
              borderRadius: 7,
              padding: "9px 10px",
              color: C.text,
              fontSize: 13,
              fontFamily: MONO,
              boxSizing: "border-box",
              opacity: loading ? 0.5 : 1,
            }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "10px 20px",
            background: loading ? C.mute : C.target,
            color: C.ink,
            border: "none",
            borderRadius: 7,
            fontSize: 13,
            fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer",
            transition: "background .12s",
            alignSelf: "flex-end",
            whiteSpace: "nowrap",
          }}
        >
          {loading ? "..." : "Analyser"}
        </button>
      </form>

      {loading && (
        <div style={{ marginTop: 20, display: "flex", alignItems: "center", color: C.mute, fontSize: 13 }}>
          <Spinner />
          Analyse en cours... (~2–5 min selon le cache)
        </div>
      )}

      {error && !loading && (
        <div style={{ marginTop: 18 }}>
          <ErrorBox message={error} />
        </div>
      )}

      {result && !loading && (
        <div style={{ marginTop: 24 }}>
          <div style={{ borderTop: `1px solid ${C.dim}`, marginBottom: 20 }} />

          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "baseline", marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: C.text }}>{result.id}</div>
              <div style={{ fontSize: 12, color: C.mute, fontFamily: MONO, marginTop: 2 }}>
                {result.n} games · WR{" "}
                <span style={{ color: C.text, fontWeight: 600 }}>{result.wr?.toFixed(1)}%</span>
              </div>
            </div>
          </div>

          <div style={{
            background: hasSignal ? "rgba(214,69,61,0.08)" : "rgba(63,167,160,0.08)",
            border: `1px solid ${hasSignal ? C.rig + "44" : C.fair + "44"}`,
            borderRadius: 10,
            padding: "14px 18px",
            marginBottom: 20,
          }}>
            <div style={{
              fontSize: 15, fontWeight: 700,
              color: hasSignal ? C.rig : C.fair,
              marginBottom: 6,
            }}>
              {hasSignal ? "⚠ Signal détecté" : "✓ Pas de signal"}
            </div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 13, color: C.mute, fontFamily: MONO }}>
              <span>
                pente{" "}
                <b style={{ color: result.slope < -80 ? C.rig : result.slope < -30 ? C.target : C.fair }}>
                  {result.slope != null ? result.slope.toFixed(0) : "—"}
                </b>
              </span>
              <span>
                p{" "}
                <b style={{ color: result.p_uni < 0.05 ? C.rig : C.mute }}>
                  {result.p_uni != null ? result.p_uni.toFixed(3) : "—"}
                </b>
              </span>
              <span>
                r{" "}
                <b style={{ color: C.text }}>
                  {result.r != null ? result.r.toFixed(3) : "—"}
                </b>
              </span>
            </div>
          </div>

          {result.scatter && result.scatter.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
                textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
                Scatter · team_diff ~ recent_wr_10
              </div>
              <div style={{ display: "flex", gap: 8, fontSize: 10, color: C.mute, fontFamily: MONO, marginBottom: 6 }}>
                <span><span style={{ color: C.fair }}>■</span> victoire</span>
                <span><span style={{ color: C.rig }}>■</span> défaite</span>
              </div>
              <ScatterSVG scatter={result.scatter} slope={result.slope ?? 0} />
            </div>
          )}

          {result.timeline && result.timeline.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
                textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
                Timeline · team_diff par game
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 10, color: C.mute, fontFamily: MONO, marginBottom: 6 }}>
                <span><span style={{ color: C.fair }}>●</span> victoire (team_diff)</span>
                <span><span style={{ color: C.rig }}>●</span> défaite (team_diff)</span>
                <span><span style={{ color: C.target }}>─</span> recent_wr_10</span>
              </div>
              <TimelineSVG timeline={result.timeline} />
            </div>
          )}

          <CarrySection slope_1v9={result.slope_1v9} slope_teamdep={result.slope_teamdep} />

          <div style={{
            marginTop: 20,
            padding: "10px 14px",
            background: C.paper,
            borderRadius: 8,
            fontSize: 11,
            color: C.mute,
            lineHeight: 1.65,
          }}>
            Ce test porte sur le rang public (proxy MMR). Ce n'est pas le MMR interne réel de Riot.
            Une pente négative significative est compatible avec H1 mais pas conclusive.
          </div>
        </div>
      )}
    </div>
  );
}
