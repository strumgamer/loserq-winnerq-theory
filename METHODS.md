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
| Internal dispersion (**exploratory**) | Higher ally rank spread when in form (joueur pivot) | `ally_rank_dispersion ~ recent_wr_10`, slope > 0 |

Correction: BH applied to the three confirmatory secondary p-values. Primary (symmetry) is not penalized.

**Note on Internal dispersion**: this analysis was specified on 2026-07-01, after observing pilot results (FE secondary p ≈ 0.07 in the initial pilot, approaching 0.05). It is therefore **exploratory**, not confirmatory, and will be reported as such. It will only become confirmatory if tested on data collected after this specification date.

---

## 2b. Prior Belief Analysis (OSF amendment 2026-07-01)

**Variable**: `prior_belief` ∈ {yes, no, unsure} — collected at form submission for volunteer players only (not available for the random ladder sample).

**Hypothesis**: Players who believe matchmaking is biased (`prior_belief = yes`) will not show a systematically stronger negative slope than those who do not. This tests whether the belief predicts future data rather than merely being correlated with past perception.

**Analysis**: Interaction term `team_diff ~ recent_wr_10 × prior_belief` within the volunteer sub-corpus. Direction pre-specified: a stronger negative slope for `yes` players would indicate belief-consistent data; its absence would suggest belief is independent of the measurable signal.

**Strictly correlational**: cannot establish causal direction. The association between `prior_belief` and slope may reflect: (a) belief formed from genuine signal, (b) belief coloring perception and game selection, or (c) shared confound. This analysis documents association only.

**Scope**: Volunteer sub-corpus only. Not applicable to the random ladder sample. N depends on form recruitment; insufficient power if N < 50 volunteers.

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

## 7. Pilot Phase Results (informational — not part of pre-registration)

Collected July 2026 from 27 pilot accounts (volunteer recruitment). Pilot and confirmatory data are kept in separate directories (`batch_out/` vs `batch_out_confirmatory/`) and analysed separately.

| Estimator | n_obs | n_players | slope | SE | p (one-tailed) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| FE OLS NW-HAC | 2 561 | 27 | −25.4 | 21.5 | 0.119 | H0 |
| CGM bootstrap | — | 27 | — | — | 0.145 | H0 |

Secondary FE: β = −32.7, SE = 19.5, p = 0.046. Per protocol, this secondary estimator is non-decisional. It justifies the confirmatory phase but does not constitute evidence of an effect.

Source commit: `607f5b1`

---

## 8. Pre-registered Constants

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

---

## 8. Hypothesis Space — Three Worlds

**World 1 — Honest matchmaking**: β ≈ 0. Honest random matchmaking produces clustered streaks (runs), not alternation — this is a mathematical property of random sequences. The intuition that "honest matching would produce diluted, interleaved results" is statistically incorrect. Runs of wins and losses are expected; smooth alternation would itself be suspicious.

**World 2 — Coarse manipulation (primary test target)**: β < 0, statistically significant on the rank proxy. Detectable at r ≥ 0.10, N = 3 000.

**World 2b — Engagement manipulation (EOMM)**: Deferred. Testable via a session-proxy reconstructed from game timestamps (inter-game gap, position-in-session), but the proxy is too noisy to be a priority in this phase. Not "out of reach" — explicitly deferred.

**World 3 — Fine manipulation**: The observed slope is attenuated: β_obs = λ × β_true, λ = 1/(1+noise_ratio²), N-independent. The cost to detect World 3 effects grows as 1/λ²; in the fully orthogonal limit (λ→0), data_cost→∞ — no finite N suffices. There is NO N-independent floor in β_true for partial correlation (λ > 0); the structural argument is about data cost diverging, not a floor.

Assumption: World 3 acts on the component of MMR orthogonal to public rank (worst case). With Corr(rank, MMR) = r, λ_eff = λ × r². This is an assumption, not a fact.

**Scope of this study**: Rules World 2 in or out. Cannot address World 3. A null result means World 2 is absent from the public data; World 3 remains outside the reach of any external investigation. This is the conclusion, not a failure.

**Detectability** (see `power_analysis.py::detectability_frontier`, nr=0.50, N=3 000):

- MDE proxy: 26.3 rank pts/unit win-rate (study limit, N-dependent).
- λ = 0.800 (N-independent): attenuation factor on β_true.
- data_cost = 1.6× (N-independent): factor by which N must increase to detect the same β_true through the proxy. When λ→0: data_cost→∞.

---

## 9. Pre-specification of Both Outcomes

**If H0 is rejected** (β < 0, p < 0.05, FE OLS NW-HAC, N ≥ 3 000):

- Data are compatible with World 2 on the rank proxy.
- Caveat: true effect may be larger due to measurement error on Y (rank ≠ MMR).
- Caveat: β < 0 does not constitute proof of intentional manipulation.

**If H0 is retained** (β ≈ 0, p > 0.05, N ≥ 3 000, power ≥ 80 % for r = 0.10):

- World 2 is absent from the public data at the detectable effect size.
- The subjective experience of losing streaks is indistinguishable from honest matchmaking on these data. This is an informative result, not an absence of result.
- World 3 remains a non-disprovable hypothesis. Explicit statement required: "We cannot exclude that Riot uses internal signals invisible to the public API."
- Do not state that matchmaking is honest. State: "No detectable signature of coarse manipulation was found."
