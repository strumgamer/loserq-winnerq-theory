import React, { useState, useRef, useCallback } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function useIsMobile(breakpoint = 640) {
  const [mobile, setMobile] = React.useState(() => window.innerWidth < breakpoint);
  React.useEffect(() => {
    const fn = () => setMobile(window.innerWidth < breakpoint);
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, [breakpoint]);
  return mobile;
}

const C = {
  target:  "#C89B0A",
  rig:     "#C4302A",
  fair:    "#1A8F89",
  carry:   "#7C5CE8",
  ink:     "#F6F4EF",
  paper:   "#FDFCFA",
  card:    "#FFFFFF",
  mute:    "#72706D",
  dim:     "#E0DBD3",
  text:    "#1A1917",
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
      background: "rgba(196,48,42,0.08)",
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

function getEpisodeForGame(gameIndex, episodeRanges) {
  return episodeRanges?.find(ep => gameIndex >= ep.start && gameIndex <= ep.end) || null;
}

function TimelineView({ timeline, episodeRanges }) {
  const [activeEpisode, setActiveEpisode] = useState(null);

  const handleClick = useCallback((gameIndex) => {
    const ep = getEpisodeForGame(gameIndex, episodeRanges);
    if (!ep) return;
    setActiveEpisode(prev =>
      prev && prev.start === ep.start && prev.end === ep.end ? null : ep
    );
  }, [episodeRanges]);

  if (!timeline || timeline.length === 0) return null;

  const episodeGames = activeEpisode
    ? timeline.filter(([idx]) => idx >= activeEpisode.start && idx <= activeEpisode.end)
    : [];

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
        textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
        Timeline des parties
      </div>

      <div style={{ display: "flex", gap: 2, flexWrap: "wrap", maxHeight: 80, overflowY: "auto" }}>
        {timeline.map(([idx, , , win]) => {
          const ep = getEpisodeForGame(idx, episodeRanges);
          const isActive = activeEpisode && ep && ep.start === activeEpisode.start && ep.end === activeEpisode.end;
          return (
            <div
              key={idx}
              onClick={() => handleClick(idx)}
              title={ep ? `Épisode ${ep.type?.toUpperCase() ?? "LQ"} — games ${ep.start}–${ep.end}` : `Game ${idx}`}
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: win ? C.fair : C.rig,
                border: ep
                  ? `2px solid ${isActive ? C.target : C.target + "99"}`
                  : "2px solid transparent",
                boxSizing: "border-box",
                cursor: ep ? "pointer" : "default",
                opacity: activeEpisode && !isActive && ep ? 0.45 : 1,
                transition: "opacity .1s, border-color .1s",
                flexShrink: 0,
              }}
            />
          );
        })}
      </div>

      {episodeRanges && episodeRanges.length > 0 && (
        <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10, color: C.mute, fontFamily: MONO }}>
          <span><span style={{ color: C.fair }}>■</span> victoire</span>
          <span><span style={{ color: C.rig }}>■</span> défaite</span>
          <span><span style={{ color: C.target }}>■</span> épisode LQ/WQ — cliquer pour détails</span>
        </div>
      )}

      {activeEpisode && episodeGames.length > 0 && (
        <div style={{
          marginTop: 14,
          background: C.paper,
          border: `1px solid ${C.target}55`,
          borderRadius: 10,
          overflow: "hidden",
        }}>
          <div style={{
            padding: "10px 14px",
            background: `${C.target}12`,
            borderBottom: `1px solid ${C.target}33`,
            fontSize: 11,
            fontWeight: 700,
            fontFamily: MONO,
            color: C.target,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
          }}>
            Épisode {activeEpisode.type?.toUpperCase() ?? "LQ"} — games {activeEpisode.start} à {activeEpisode.end}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 11,
              fontFamily: MONO,
            }}>
              <thead>
                <tr style={{ background: C.paper }}>
                  {["#", "Résultat", "Forme", "Équipe", "KDA", "Dmg"].map(h => (
                    <th key={h} style={{
                      padding: "6px 12px",
                      textAlign: h === "#" ? "center" : "right",
                      color: C.mute,
                      fontWeight: 600,
                      borderBottom: `1px solid ${C.dim}`,
                      whiteSpace: "nowrap",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {episodeGames.map(([idx, recent_wr, team_diff, win, kda, damage]) => (
                  <tr key={idx} style={{ borderBottom: `1px solid ${C.dim}` }}>
                    <td style={{ padding: "6px 12px", textAlign: "center", color: C.mute }}>{idx}</td>
                    <td style={{ padding: "6px 12px", textAlign: "right", color: win ? C.fair : C.rig, fontWeight: 700 }}>
                      {win ? "✓" : "✗"}
                    </td>
                    <td style={{ padding: "6px 12px", textAlign: "right", color: C.text }}>
                      {recent_wr != null ? (recent_wr * 100).toFixed(0) + "%" : "—"}
                    </td>
                    <td style={{ padding: "6px 12px", textAlign: "right",
                      color: team_diff != null && team_diff < -50 ? C.rig : team_diff != null && team_diff > 50 ? C.fair : C.text }}>
                      {team_diff != null ? (team_diff > 0 ? "+" : "") + team_diff.toFixed(0) : "—"}
                    </td>
                    <td style={{ padding: "6px 12px", textAlign: "right", color: C.text }}>
                      {kda != null ? kda.toFixed(1) : "—"}
                    </td>
                    <td style={{ padding: "6px 12px", textAlign: "right", color: C.text }}>
                      {damage != null ? Math.round(damage).toLocaleString("fr-FR") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function CarrySection({ slope_1v9, slope_teamdep, n_1v9, n_teamdep }) {
  if (slope_1v9 == null && slope_teamdep == null) return null;
  if ((n_1v9 == null || n_1v9 < 30) || (n_teamdep == null || n_teamdep < 30)) {
    return (
      <div style={{ marginTop: 20, padding: "10px 14px", background: "#F6F4EF",
        borderRadius: 8, fontSize: 11, color: "#72706D", fontFamily: "ui-monospace,Menlo,'SF Mono',monospace" }}>
        Carry stratification — sous-groupes insuffisants (n_1v9={n_1v9 ?? "—"}, n_teamdep={n_teamdep ?? "—"}, minimum 30 par groupe requis).
      </div>
    );
  }
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

const SERVER_MAP = {
  "euw1": { region: "europe",   platform: "euw1", label: "EUW — Europe Ouest" },
  "eun1": { region: "europe",   platform: "eun1", label: "EUNE — Europe Nord-Est" },
  "tr1":  { region: "europe",   platform: "tr1",  label: "TR — Turquie" },
  "ru":   { region: "europe",   platform: "ru",   label: "RU — Russie" },
  "na1":  { region: "americas", platform: "na1",  label: "NA — Amérique du Nord" },
  "br1":  { region: "americas", platform: "br1",  label: "BR — Brésil" },
  "la1":  { region: "americas", platform: "la1",  label: "LAN — Amérique Latine Nord" },
  "la2":  { region: "americas", platform: "la2",  label: "LAS — Amérique Latine Sud" },
  "kr":   { region: "asia",     platform: "kr",   label: "KR — Corée du Sud" },
  "jp1":  { region: "asia",     platform: "jp1",  label: "JP — Japon" },
};

export default function Analysis() {
  const [riotId,  setRiotId]  = useState("");
  const [server, setServer] = useState("euw1");
  const [count,   setCount]   = useState(100);
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);
  const abortRef = useRef(null);
  const [loadingStep, setLoadingStep] = useState(0);
  const stepTimerRef = useRef(null);


  const handleSubmit = async (e) => {
    e.preventDefault();
    const normalized = riotId.trim().replace(/\s*#\s*/g, '#');
    if (!normalized.includes("#")) {
      setError("Format invalide. Utilisez le format: Pseudo#TAG");
      return;
    }

    setLoading(true);
    setResult(null);
    setError(null);
    setLoadingStep(0);
    // Avance les étapes toutes les 35s pour simuler la progression
    let step = 0;
    stepTimerRef.current = setInterval(() => {
      step = Math.min(step + 1, 2);
      setLoadingStep(step);
    }, 35000);

    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000);

    try {
      const resp = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ riot_id: normalized, region: SERVER_MAP[server].region, platform: SERVER_MAP[server].platform, count }),
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
      clearInterval(stepTimerRef.current);
      setLoadingStep(0);
      abortRef.current = null;
    }
  };

  const isMobile = useIsMobile();

  const hasSignal = result && result.p_uni < 0.05 && result.slope < 0;

  return (
    <div style={{
      background: C.card,
      border: "1px solid rgba(0,0,0,0.06)",
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

      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", flexDirection: isMobile ? "column" : "row" }}>
        <div style={{ flex: "2 1 200px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>
            Riot ID (ex : Pseudo#EUW)
          </label>
          <input
            type="text"
            value={riotId}
            onChange={e => setRiotId(e.target.value)}
            placeholder="Ex : Pseudo#EUW"
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
          <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>
            Trouve ton Riot ID dans le client LoL → Profil → ton nom#tag
          </div>
        </div>

        <div>
          <label style={{ display: "block", fontSize: 11, color: C.mute, marginBottom: 4 }}>Serveur</label>
          <select value={server} onChange={e => setServer(e.target.value)} style={{
            padding: "8px 10px", borderRadius: 8, border: `1px solid ${C.dim}`,
            fontSize: 13, background: C.card, color: C.text, cursor: "pointer",
            minHeight: isMobile ? 40 : undefined,
          }}>
            {Object.entries(SERVER_MAP).map(([key, { label }]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        <div style={{ flex: "0 1 90px" }}>
          <label style={{ fontSize: 11, color: C.mute, display: "block", marginBottom: 5 }}>
            Nombre de games
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
            padding: "11px 26px",
            background: loading ? C.mute : C.target,
            color: C.ink,
            border: "none",
            borderRadius: 7,
            fontSize: 14,
            fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer",
            transition: "background .12s",
            alignSelf: "flex-end",
            whiteSpace: "nowrap",
          }}
        >
          {loading ? "Analyse en cours…" : "Analyser →"}
        </button>
      </form>

      {loading && (
        <div style={{ marginTop: 24, padding: "18px 20px", background: "#FDFCFA", border: `1px solid ${C.dim}`, borderRadius: 12 }}>
          {[
            { label: "Résolution du compte Riot…",   detail: "Vérification du Riot ID" },
            { label: "Récupération des parties…",     detail: `Téléchargement jusqu’à ${count} games` },
            { label: "Calcul des statistiques…",      detail: "Régression + test unilatéral" },
          ].map((s, i) => {
            const done    = i < loadingStep;
            const active  = i === loadingStep;
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "8px 0",
                opacity: done ? 0.45 : active ? 1 : 0.3,
                borderBottom: i < 2 ? `1px solid ${C.dim}` : "none",
              }}>
                <div style={{
                  width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: done ? C.fair + "22" : active ? C.target + "22" : C.dim + "44",
                  border: `1.5px solid ${done ? C.fair : active ? C.target : C.dim}`,
                }}>
                  {done
                    ? <span style={{ fontSize: 11, color: C.fair, fontWeight: 700 }}>✓</span>
                    : active
                    ? <span style={{
                        width: 8, height: 8, borderRadius: "50%",
                        background: C.target, display: "block",
                        animation: "spin 1s linear infinite",
                      }} />
                    : <span style={{ fontSize: 9, color: C.mute }}>{i + 1}</span>
                  }
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? C.text : C.mute }}>
                    {s.label}
                  </div>
                  {active && (
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1, fontFamily: MONO }}>
                      {s.detail}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div style={{ marginTop: 12, fontSize: 11, color: C.mute, fontFamily: MONO }}>
            ⏱ 2–5 min selon le cache Riot · Ne pas fermer la page
          </div>
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
            background: hasSignal ? "rgba(196,48,42,0.08)" : "rgba(26,143,137,0.08)",
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
            <div style={{
              marginTop: 12,
              paddingTop: 10,
              borderTop: `1px solid ${hasSignal ? C.rig + "22" : C.fair + "22"}`,
              fontSize: 13,
              color: C.text,
              lineHeight: 1.7,
            }}>
              {hasSignal && result.slope < -80
                ? <>Signal fort : sur {result.n} parties, ta forme récente était corrélée à un écart d'équipe défavorable. <b>Compatible avec la loser queue, mais non répliqué</b> — un drift de rang ou un biais de sélection temporelle peuvent aussi expliquer ce résultat. <span style={{ color: C.mute }}>Basé sur le rang visible, pas le MMR interne Riot.</span></>
                : hasSignal
                ? <>Signal faible : légère corrélation détectée entre ta forme et l'écart d'équipe. <b>Compatible avec H1, mais insuffisant pour conclure</b> — la variance naturelle sur {result.n} parties l'explique aussi. <span style={{ color: C.mute }}>Plus de parties = plus de puissance de test.</span></>
                : <>Pas de signal. Sur {result.n} parties, <b>ta forme récente ne prédit pas la force de tes équipes</b> — résultat compatible avec un matchmaking neutre sur cette période.</>
              }
            </div>
          </div>

          {result.timeline && result.timeline.length > 0 && (
            <TimelineView timeline={result.timeline} episodeRanges={result.episode_ranges} />
          )}

          {result.scatter && result.scatter.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
                textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
                Écart d'équipe selon ta forme récente
              </div>
              <div style={{ display: "flex", gap: 8, fontSize: 10, color: C.mute, fontFamily: MONO, marginBottom: 6 }}>
                <span><span style={{ color: C.fair }}>■</span> victoire</span>
                <span><span style={{ color: C.rig }}>■</span> défaite</span>
                <span style={{ marginLeft: 4, color: C.mute }}>· axe X = ta forme récente · axe Y = force de ton équipe vs l'adversaire</span>
              </div>
              <ScatterSVG scatter={result.scatter} slope={result.slope ?? 0} />
            </div>
          )}

          {result.timeline && result.timeline.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
                textTransform: "uppercase", color: C.mute, fontFamily: MONO, marginBottom: 8 }}>
                Force de ton équipe partie par partie
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 10, color: C.mute, fontFamily: MONO, marginBottom: 6 }}>
                <span><span style={{ color: C.fair }}>●</span> victoire</span>
                <span><span style={{ color: C.rig }}>●</span> défaite</span>
                <span><span style={{ color: C.target }}>─</span> forme récente</span>
              </div>
              <TimelineSVG timeline={result.timeline} />
            </div>
          )}

          <CarrySection slope_1v9={result.slope_1v9} slope_teamdep={result.slope_teamdep} n_1v9={result.n_1v9} n_teamdep={result.n_teamdep} />

          <div style={{
            marginTop: 20,
            padding: "10px 14px",
            background: C.paper,
            borderRadius: 8,
            fontSize: 11,
            color: C.mute,
            lineHeight: 1.65,
          }}>
            Ce test utilise le rang visible (pas le MMR interne de Riot).
            Un signal détecté est compatible avec la loser queue — mais ne prouve pas que Riot le fait intentionnellement.
          </div>
        </div>
      )}
    </div>
  );
}
