import React, { useState, useMemo } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// SIMULATEUR — "RIGGED QUEUE" vs MATCHMAKING PAR MMR
// Démonstration : deux moteurs d'appariement produisent des courbes
// quasi identiques à l'œil. C'est tout le piège de l'argument "j'ai vu 500 games".
// ─────────────────────────────────────────────────────────────────────────────

const TARGET = "#E8C547";      // or — la cible
const RIG = "#D6453D";          // rouge — moteur truqué
const FAIR = "#3FA7A0";         // sarcelle — moteur honnête
const INK = "#0E0E12";
const PAPER = "#16161D";
const MUTE = "#6E6E7E";
const LINE = "#2A2A36";

// Génère un MMR "vrai" autour d'une cible, borné.
function rand(seed) {
  // PRNG déterministe (mulberry32) pour des runs reproductibles
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

// Probabilité de victoire logistique selon l'écart de MMR d'équipe.
function winProb(diff) {
  return 1 / (1 + Math.pow(10, -diff / 400));
}

function simulate({ engine, games, heroMMR, poolSpread, rigStrength, seed }) {
  const results = [];
  let streak = 0;
  let maxWin = 0;
  let maxLoss = 0;
  let s = seed;

  for (let g = 0; g < games; g++) {
    s += 1;
    // forme récente : -1 (perd beaucoup) .. +1 (gagne beaucoup)
    const recent = results.slice(-10);
    const recentWR = recent.length
      ? recent.filter((r) => r.win).length / recent.length
      : 0.5;

    // 9 autres joueurs tirés autour du MMR du héros
    let allies = 0;
    let enemies = 0;
    for (let i = 0; i < 4; i++) {
      allies += heroMMR + (rand(s * 31 + i) - 0.5) * 2 * poolSpread;
    }
    for (let i = 0; i < 5; i++) {
      enemies += heroMMR + (rand(s * 57 + i) - 0.5) * 2 * poolSpread;
    }
    let allyAvg = (allies + heroMMR) / 5;
    let enemyAvg = enemies / 5;

    if (engine === "rig") {
      // Moteur TRUQUÉ : on pousse le joueur vers 50%.
      // S'il gagne trop → on affaiblit ses alliés / renforce les ennemis.
      const push = (recentWR - 0.5) * 2; // >0 = en forme → on sabote
      const bias = push * rigStrength;
      allyAvg -= bias;
      enemyAvg += bias;
    }
    // Moteur HONNÊTE ("fair") : on ne touche à rien. Le retour vers 50%
    // émerge tout seul de l'appariement par MMR au fil de la montée.

    const diff = allyAvg - enemyAvg;
    const p = winProb(diff);
    const win = rand(s * 99) < p;

    if (win) {
      streak = streak > 0 ? streak + 1 : 1;
      maxWin = Math.max(maxWin, streak);
    } else {
      streak = streak < 0 ? streak - 1 : -1;
      maxLoss = Math.max(maxLoss, -streak);
    }

    results.push({ g, win, diff });
  }

  let wins = 0;
  const wr = results.map((r, i) => {
    if (r.win) wins++;
    return (wins / (i + 1)) * 100;
  });

  return {
    results,
    wr,
    winRate: (wins / games) * 100,
    maxWin,
    maxLoss,
  };
}

// Lance N simulations d'affilée et agrège les distributions.
function batchSimulate(params, runs) {
  const winRates = [];
  const maxWins = [];
  const maxLosses = [];
  for (let i = 0; i < runs; i++) {
    const r = simulate({ ...params, seed: params.seed + i * 1000 });
    winRates.push(r.winRate);
    maxWins.push(r.maxWin);
    maxLosses.push(r.maxLoss);
  }
  return { winRates, maxWins, maxLosses };
}

// Range les valeurs en bacs pour l'histogramme.
function histogram(values, min, max, bins) {
  const counts = new Array(bins).fill(0);
  const width = (max - min) / bins;
  values.forEach((v) => {
    let idx = Math.floor((v - min) / width);
    idx = Math.max(0, Math.min(bins - 1, idx));
    counts[idx]++;
  });
  return counts.map((c, i) => ({
    x0: min + i * width,
    x1: min + (i + 1) * width,
    count: c,
  }));
}

function Histogram({ values, min, max, bins, color, unit }) {
  const bars = useMemo(() => histogram(values, min, max, bins), [values, min, max, bins]);
  const peak = Math.max(1, ...bars.map((b) => b.count));
  const mean = values.reduce((a, b) => a + b, 0) / (values.length || 1);
  const w = 520, h = 130;
  const bw = w / bins;
  const meanX = ((mean - min) / (max - min)) * w;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h + 22}`} style={{ display: "block" }}>
        {bars.map((b, i) => {
          const bh = (b.count / peak) * h;
          return (
            <rect
              key={i}
              x={i * bw + 1}
              y={h - bh}
              width={bw - 2}
              height={bh}
              fill={color}
              opacity={0.8}
              rx={1.5}
            />
          );
        })}
        <line x1={meanX} y1={0} x2={meanX} y2={h} stroke={TARGET} strokeWidth="1.5" strokeDasharray="3 3" />
        <text x={Math.min(w - 60, meanX + 4)} y={12} fill={TARGET} fontSize="11" fontFamily="ui-monospace,monospace">
          moy {mean.toFixed(1)}{unit}
        </text>
        {[min, (min + max) / 2, max].map((t, i) => (
          <text
            key={i}
            x={i === 0 ? 2 : i === 2 ? w - 2 : w / 2}
            y={h + 16}
            fill={MUTE}
            fontSize="11"
            fontFamily="ui-monospace,monospace"
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
          >
            {t.toFixed(0)}{unit}
          </text>
        ))}
      </svg>
    </div>
  );
}

function Sparkline({ data, color, w = 520, h = 120 }) {
  const path = useMemo(() => {
    if (!data.length) return "";
    const min = 30, max = 70; // on zoome autour de 50%
    return data
      .map((v, i) => {
        const x = (i / (data.length - 1)) * w;
        const y = h - ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [data, w, h]);

  const mid = h - ((50 - 30) / 40) * h;

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <line x1="0" y1={mid} x2={w} y2={mid} stroke={LINE} strokeDasharray="3 4" />
      <text x="4" y={mid - 6} fill={MUTE} fontSize="11" fontFamily="ui-monospace,monospace">
        50%
      </text>
      <path d={path} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function StreakStrip({ results }) {
  const last = results.slice(-60);
  return (
    <div style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
      {last.map((r, i) => (
        <div
          key={i}
          title={`Game ${r.g + 1} · ${r.win ? "W" : "L"}`}
          style={{
            width: 12,
            height: 12,
            borderRadius: 2,
            background: r.win ? FAIR : RIG,
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MODE DOUBLE AVEUGLE
// Le simulateur choisit secrètement un moteur, te montre 50 games sans dire
// lequel, et te demande de deviner. Le score tenu sur plusieurs manches montre
// que tu plafonnes autour de 50% de bonnes réponses — soit le pur hasard.
// ─────────────────────────────────────────────────────────────────────────────
function BlindTest({ heroMMR, poolSpread, rigStrength }) {
  const [round, setRound] = useState(null); // { engine, sim } — engine caché
  const [guess, setGuess] = useState(null); // "rig" | "fair" pendant la révélation
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [revealed, setRevealed] = useState(false);

  const deal = () => {
    // moteur secret, seed aléatoire à chaque manche
    const engine = Math.random() < 0.5 ? "rig" : "fair";
    const seed = Math.floor(Math.random() * 1e9);
    const sim = simulate({ engine, games: 50, heroMMR, poolSpread, rigStrength, seed });
    setRound({ engine, sim });
    setGuess(null);
    setRevealed(false);
  };

  const submit = (g) => {
    if (!round || revealed) return;
    const correct = g === round.engine;
    setGuess(g);
    setRevealed(true);
    setScore((s) => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }));
  };

  const pct = score.total ? Math.round((score.correct / score.total) * 100) : 0;

  return (
    <div
      style={{
        background: PAPER,
        border: `1px solid ${TARGET}`,
        borderRadius: 12,
        padding: "20px 22px",
        marginTop: 16,
      }}
    >
      <div style={{ fontSize: 12, letterSpacing: 2, color: TARGET, fontFamily: "ui-monospace,monospace" }}>
        ÉPREUVE — DOUBLE AVEUGLE
      </div>
      <h2 style={{ fontSize: 22, margin: "6px 0 4px" }}>Devine le moteur</h2>
      <p style={{ color: MUTE, fontSize: 14, lineHeight: 1.5, maxWidth: 560 }}>
        Le simulateur tire en secret un moteur — truqué ou honnête — et joue 50 games.
        Regarde la bande de résultats, puis tranche. Le score se tient en bas : si tu n'arrives
        pas à dépasser 50% de bonnes réponses sur plusieurs manches, c'est que les deux mondes
        sont, vu de l'intérieur, indiscernables.
      </p>

      {!round && (
        <button
          onClick={deal}
          style={{
            marginTop: 14,
            padding: "12px 20px",
            background: TARGET,
            color: INK,
            border: "none",
            borderRadius: 8,
            fontSize: 15,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Distribuer une manche
        </button>
      )}

      {round && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, color: MUTE, marginBottom: 10 }}>
            50 games · <span style={{ color: FAIR }}>vert = win</span> ·{" "}
            <span style={{ color: RIG }}>rouge = loss</span> · moteur caché
          </div>
          <StreakStrip results={round.sim.results} />

          <div style={{ display: "flex", gap: 18, marginTop: 14, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, color: MUTE }}>
              Win-rate de la manche :{" "}
              <b style={{ color: "#EDEDF2", fontFamily: "ui-monospace,monospace" }}>
                {round.sim.winRate.toFixed(0)}%
              </b>
            </span>
            <span style={{ fontSize: 13, color: MUTE }}>
              Plus longue série W :{" "}
              <b style={{ color: "#EDEDF2", fontFamily: "ui-monospace,monospace" }}>{round.sim.maxWin}</b>
            </span>
            <span style={{ fontSize: 13, color: MUTE }}>
              Plus longue série L :{" "}
              <b style={{ color: "#EDEDF2", fontFamily: "ui-monospace,monospace" }}>{round.sim.maxLoss}</b>
            </span>
          </div>

          {!revealed && (
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button
                onClick={() => submit("rig")}
                style={{
                  flex: 1,
                  padding: "12px 14px",
                  background: "transparent",
                  color: RIG,
                  border: `1px solid ${RIG}`,
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                C'était truqué
              </button>
              <button
                onClick={() => submit("fair")}
                style={{
                  flex: 1,
                  padding: "12px 14px",
                  background: "transparent",
                  color: FAIR,
                  border: `1px solid ${FAIR}`,
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                C'était honnête
              </button>
            </div>
          )}

          {revealed && (
            <div style={{ marginTop: 16 }}>
              <div
                style={{
                  padding: "14px 16px",
                  borderRadius: 8,
                  background: guess === round.engine ? "rgba(63,167,160,.12)" : "rgba(214,69,61,.12)",
                  border: `1px solid ${guess === round.engine ? FAIR : RIG}`,
                  fontSize: 14,
                }}
              >
                <b style={{ color: guess === round.engine ? FAIR : RIG }}>
                  {guess === round.engine ? "Bonne réponse" : "Raté"}
                </b>{" "}
                — le moteur était{" "}
                <b style={{ color: round.engine === "rig" ? RIG : FAIR }}>
                  {round.engine === "rig" ? "truqué" : "honnête"}
                </b>
                . Tu as répondu « {guess === "rig" ? "truqué" : "honnête"} ».
              </div>
              <button
                onClick={deal}
                style={{
                  marginTop: 12,
                  padding: "11px 18px",
                  background: TARGET,
                  color: INK,
                  border: "none",
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                Manche suivante
              </button>
            </div>
          )}

          <div
            style={{
              marginTop: 18,
              paddingTop: 16,
              borderTop: `1px solid ${LINE}`,
              display: "flex",
              alignItems: "baseline",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: 28, fontWeight: 700, fontFamily: "ui-monospace,monospace", color: "#EDEDF2" }}>
              {score.correct}/{score.total}
            </span>
            <span style={{ fontSize: 14, color: MUTE }}>bonnes réponses</span>
            <span style={{ fontSize: 14, color: pct > 65 ? TARGET : MUTE, marginLeft: "auto", fontFamily: "ui-monospace,monospace" }}>
              {pct}% · le hasard pur vise 50%
            </span>
          </div>
          {score.total >= 6 && (
            <p style={{ fontSize: 12, color: MUTE, lineHeight: 1.6, marginTop: 12 }}>
              Après plusieurs manches, ton taux de réussite reste collé autour de 50% — exactement ce
              qu'on obtiendrait à pile ou face. C'est la démonstration la plus nette : même en{" "}
              <i>sachant</i> que l'un des moteurs triche, l'expérience de jeu seule ne permet pas de
              dire lequel. Donc « j'ai senti que c'était truqué » n'est pas une donnée qui sépare les
              deux hypothèses.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [engine, setEngine] = useState("rig");
  const [heroMMR, setHeroMMR] = useState(2400);
  const [poolSpread, setPoolSpread] = useState(180);
  const [rigStrength, setRigStrength] = useState(220);
  const [games] = useState(300);
  const [seed, setSeed] = useState(7);

  const [runs, setRuns] = useState(200);
  const [batch, setBatch] = useState(null);
  const [batchEngine, setBatchEngine] = useState(null);

  const sim = useMemo(
    () => simulate({ engine, games, heroMMR, poolSpread, rigStrength, seed }),
    [engine, games, heroMMR, poolSpread, rigStrength, seed]
  );

  const color = engine === "rig" ? RIG : FAIR;

  const runBatch = () => {
    const res = batchSimulate({ engine, games, heroMMR, poolSpread, rigStrength, seed }, runs);
    setBatch(res);
    setBatchEngine(engine);
  };

  const Stat = ({ label, value, sub }) => (
    <div style={{ flex: 1, minWidth: 120 }}>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "ui-monospace,monospace", color: "#EDEDF2" }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: MUTE, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: MUTE, opacity: 0.7 }}>{sub}</div>}
    </div>
  );

  return (
    <div
      style={{
        minHeight: "100vh",
        background: INK,
        color: "#EDEDF2",
        fontFamily: "ui-sans-serif,system-ui,sans-serif",
        padding: "32px 20px",
      }}
    >
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div style={{ fontSize: 12, letterSpacing: 3, color: TARGET, fontFamily: "ui-monospace,monospace" }}>
          MATCHMAKING — BANC D'ESSAI
        </div>
        <h1 style={{ fontSize: 34, margin: "8px 0 4px", lineHeight: 1.1 }}>
          Loser queue vs. retour vers 50%
        </h1>
        <p style={{ color: MUTE, fontSize: 15, maxWidth: 560, lineHeight: 1.5 }}>
          Bascule entre un moteur qui <b style={{ color: RIG }}>truque délibérément</b> tes games et un
          moteur honnête qui se contente d'apparier par niveau. Regarde la courbe de win-rate et les streaks.
          Le point de la démo : à l'œil, tu ne peux pas les distinguer.
        </p>

        {/* TOGGLE */}
        <div style={{ display: "flex", gap: 8, margin: "20px 0 24px" }}>
          {[
            ["rig", "Moteur truqué (loser queue)", RIG],
            ["fair", "Moteur honnête (MMR seul)", FAIR],
          ].map(([key, label, c]) => (
            <button
              key={key}
              onClick={() => setEngine(key)}
              style={{
                flex: 1,
                padding: "12px 14px",
                background: engine === key ? c : "transparent",
                color: engine === key ? INK : "#EDEDF2",
                border: `1px solid ${engine === key ? c : LINE}`,
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all .15s",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* STATS */}
        <div
          style={{
            display: "flex",
            gap: 16,
            background: PAPER,
            border: `1px solid ${LINE}`,
            borderRadius: 12,
            padding: "20px 22px",
            flexWrap: "wrap",
          }}
        >
          <Stat label="Win-rate final" value={`${sim.winRate.toFixed(1)}%`} sub={`sur ${games} games`} />
          <Stat label="Plus longue série de victoires" value={sim.maxWin} sub="d'affilée" />
          <Stat label="Plus longue série de défaites" value={sim.maxLoss} sub="d'affilée" />
        </div>

        {/* CURVE */}
        <div
          style={{
            background: PAPER,
            border: `1px solid ${LINE}`,
            borderRadius: 12,
            padding: "20px 22px",
            marginTop: 16,
          }}
        >
          <div style={{ fontSize: 13, color: MUTE, marginBottom: 12 }}>
            Win-rate cumulé — converge vers 50% dans les <i>deux</i> cas
          </div>
          <Sparkline data={sim.wr} color={color} />
          <div style={{ fontSize: 13, color: MUTE, margin: "18px 0 10px" }}>
            60 dernières games · <span style={{ color: FAIR }}>vert = win</span> ·{" "}
            <span style={{ color: RIG }}>rouge = loss</span>
          </div>
          <StreakStrip results={sim.results} />
        </div>

        {/* BATCH */}
        <div
          style={{
            background: PAPER,
            border: `1px solid ${LINE}`,
            borderRadius: 12,
            padding: "20px 22px",
            marginTop: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <button
              onClick={runBatch}
              style={{
                padding: "11px 18px",
                background: color,
                color: INK,
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              ▶ Lancer {runs} simulations en un clic
            </button>
            <div style={{ flex: 1, minWidth: 180 }}>
              <input
                type="range"
                min={20}
                max={1000}
                step={20}
                value={runs}
                onChange={(e) => setRuns(Number(e.target.value))}
                style={{ width: "100%", accentColor: TARGET }}
              />
              <div style={{ fontSize: 11, color: MUTE, marginTop: 2 }}>
                {runs} runs × {games} games = {(runs * games).toLocaleString()} parties simulées
              </div>
            </div>
          </div>

          {batch && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 13, color: MUTE, marginBottom: 4 }}>
                Distribution sur {runs} runs ·{" "}
                <span style={{ color: batchEngine === "rig" ? RIG : FAIR }}>
                  {batchEngine === "rig" ? "moteur truqué" : "moteur honnête"}
                </span>
              </div>

              <div style={{ fontSize: 12, color: "#EDEDF2", margin: "14px 0 4px" }}>
                Win-rate final par run (%)
              </div>
              <Histogram values={batch.winRates} min={35} max={65} bins={24}
                color={batchEngine === "rig" ? RIG : FAIR} unit="%" />

              <div style={{ fontSize: 12, color: "#EDEDF2", margin: "14px 0 4px" }}>
                Plus longue série de victoires par run
              </div>
              <Histogram values={batch.maxWins} min={0} max={20} bins={20}
                color={FAIR} unit="" />

              <div style={{ fontSize: 12, color: "#EDEDF2", margin: "14px 0 4px" }}>
                Plus longue série de défaites par run
              </div>
              <Histogram values={batch.maxLosses} min={0} max={20} bins={20}
                color={RIG} unit="" />

              <p style={{ fontSize: 12, color: MUTE, lineHeight: 1.6, marginTop: 14 }}>
                Lance le batch sur un moteur, note où tombent les pics, puis rebascule sur l'autre moteur
                et relance. Les deux distributions se superposent presque entièrement : même win-rate
                moyen (~50%), mêmes longueurs de streaks. C'est ça, l'argument central — l'expérience
                vécue ne sépare pas les deux hypothèses.
              </p>
            </div>
          )}
        </div>

        {/* DOUBLE AVEUGLE */}
        <BlindTest heroMMR={heroMMR} poolSpread={poolSpread} rigStrength={rigStrength} />

        {/* CONTROLS */}
        <div
          style={{
            background: PAPER,
            border: `1px solid ${LINE}`,
            borderRadius: 12,
            padding: "20px 22px",
            marginTop: 16,
          }}
        >
          <Slider label="MMR du héros" value={heroMMR} min={1000} max={3200} step={50}
            onChange={setHeroMMR} hint="Plus haut = pool plus rare = écarts plus larges (réel)." />
          <Slider label="Dispersion du pool" value={poolSpread} min={50} max={400} step={10}
            onChange={setPoolSpread} hint="Écart de niveau des 9 autres joueurs." />
          <Slider
            label="Force du truquage"
            value={rigStrength}
            min={0}
            max={500}
            step={10}
            onChange={setRigStrength}
            disabled={engine !== "rig"}
            hint={engine === "rig" ? "Intensité du sabotage quand tu es en forme." : "Inactif sur le moteur honnête."}
          />
          <button
            onClick={() => setSeed((s) => s + 1)}
            style={{
              marginTop: 8,
              padding: "10px 16px",
              background: "transparent",
              color: TARGET,
              border: `1px solid ${TARGET}`,
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "ui-monospace,monospace",
            }}
          >
            ⟳ Relancer (seed #{seed})
          </button>
        </div>

        <p style={{ color: MUTE, fontSize: 13, lineHeight: 1.6, marginTop: 22 }}>
          <b style={{ color: "#EDEDF2" }}>À tester :</b> mets le truquage à 0 sur le moteur honnête,
          monte le MMR du héros à 3000, et relance plusieurs fois. Tu verras des streaks de 6–8 et des
          games très déséquilibrées <i>sans aucun sabotage</i> — juste à cause de la rareté du pool en
          haut elo et du hasard. C'est exactement ce qu'on observe en jeu, et c'est pourquoi
          « j'ai regardé 500 games » ne tranche pas la question.
        </p>
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, hint, disabled }) {
  return (
    <div style={{ marginBottom: 18, opacity: disabled ? 0.4 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: "#EDEDF2" }}>{label}</span>
        <span style={{ fontSize: 13, color: MUTE, fontFamily: "ui-monospace,monospace" }}>{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: TARGET, cursor: disabled ? "not-allowed" : "pointer" }}
      />
      {hint && <div style={{ fontSize: 11, color: MUTE, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}
