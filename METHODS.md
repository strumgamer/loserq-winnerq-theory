# METHODS — Loser Queue / Winner Queue Statistical Test

Pre-registered analysis plan. Parameters listed here must not be changed after data collection begins.

---

## 1. Primary Estimator and Argument of Symmetry

**Estimator**: FE OLS within-player, Newey-West HAC standard errors (lag=10), one-tailed α=0.05.

**Argument of symmetry**: The regression of `team_diff` (mean rank gap allies − enemies, excluding the target player) on `recent_wr_10` (win rate over the prior 10 games) is symmetric under the null: if matchmaking is honest, a player's current form contains no information about the relative strength of teammates versus opponents. A negative slope (worse teammates when in form) is the unique directional signature of targeted suppression. A positive slope would falsify the "loser queue" hypothesis in both directions. The test is therefore one-tailed (H1: slope < 0), which increases power by ~20% relative to two-tailed at identical α.

**Practical significance threshold (illustrative only, not a decision rule)**: slope ≤ −30 rank points per unit win rate, corresponding to approximately one full tier per 10-game streak at 80% win rate.

---

## 2. Secondary Analyses (pre-specified with direction)

Secondary analyses are exploratory and subject to Benjamini-Hochberg correction (q=0.05). They do not affect the primary conclusion.

| Analysis | H1 direction | Operationalization |
|---|---|---|
| Queue timing | Longer queue time when in form | `queue_time ~ recent_wr_10`, slope > 0 |
| Ladder comparison | Confirmatoire slopes < random sample | Mann-Whitney U, one-tailed |
| Champion pool | More off-pool allies when target is in form | `off_pool_rate ~ recent_wr_10`, slope > 0 |

Correction: BH applied to the three secondary p-values. Primary (symmetry) is not penalized.

---

## 3. Inclusion and Exclusion Criteria

**Minimum games**: N ≥ 20 ranked Solo/Duo per player. Players with fewer games are excluded entirely.

**Game-level exclusions**:
- Remake (duration < 300 s)
- AFK flag: duration < 800 s or `timePlayed` < 600 s for any participant
- Queue type ≠ RANKED_SOLO_5x5 (queue ID 420)

**Player-level exclusions**:
- Pilot accounts (see `sample_ladder.py::PILOT_IDS`)
- Fewer than 35 games in the past 60 days at time of sampling (inactive)
- Grandmaster with LP > 1000 at time of sampling (extreme outliers)

**Rank coverage**: a game contributes to `team_diff` only if ≥ 85% of teammates and opponents have a retrievable rank. Games below this threshold are retained for win-rate computation but excluded from the regression.

---

## 4. Stopping Rule

- Primary: collect until total valid games N = 3000 across all confirmatoire players, OR until 2026-12-31, whichever comes first.
- If recruitment stalls below 25 players before the deadline, stop on the deadline date.
- **No interim analyses as a stopping criterion**. Peeking at p-values during collection and stopping early on significance violates Type I control. The only valid mid-run check is verifying API errors or data quality issues.

---

## 5. Multiple Testing — Primary vs Secondary

| Analysis | Status | BH correction |
|---|---|---|
| `team_diff ~ recent_wr_10` (symmetry) | **Primary** | No — single pre-registered directional test |
| Queue timing | Secondary | Yes — BH across secondaries |
| Ladder comparison | Secondary | Yes |
| Champion pool | Secondary | Yes |

The wild cluster bootstrap-t (CGM) on the primary estimator is a robustness check only. The pre-registered decision is based on Newey-West OLS.

---

## 6. Measurement Limitations

**Temporal drift**: Player rank is retrieved at collection time, not at the time each historical game was played. For a player who climbed significantly, recent games will show an underestimated `team_diff`. This creates attenuation bias toward zero — a conservative bias for the null. It does not create false positives but reduces power.

**Rank proxy noise**: True MMR is not accessible via the public API. Rank (Iron IV = 0, Challenger ≈ 2800+) is a noisy proxy. Measurement error on the dependent variable does not bias the slope estimator but inflates SE. See `power_analysis.py::attenuation_bounds` and `sensitivity_table` for power estimates under noise ratios 0.20–0.70.

**Selection bias**: Confirmatoire players were sampled conditional on ≥ 35 games / 60 days. Highly active players may differ from the general population in ways that interact with the effect of interest. Inferences apply to this population segment.

---

## 7. Pre-registered Constants

```
alpha         = 0.05  (one-tailed)
min_games     = 20    (per player)
rank_coverage = 0.85  (game inclusion threshold)
nw_lag        = 10    (Newey-West max lag)
window_wr     = 10    (recent win rate window)
bootstrap_n   = 9999  (wild cluster bootstrap replications)
seed          = 2026
stopping_N    = 3000
stopping_date = 2026-12-31
```

These values must not be changed after data collection begins. Any deviation must be logged as a sensitivity analysis, not substituted for the primary result.
