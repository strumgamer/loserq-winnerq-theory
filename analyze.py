#!/usr/bin/env python3
"""
analyze.py — Le test qui tranche (ou non) la théorie loser/winner queue.

On part du CSV produit par collect.py. L'idée centrale, déjà rencontrée :
un matchmaking honnête par MMR et une "loser queue" produisent TOUS LES DEUX
un retour vers 50% et des streaks. Pour les séparer, il ne faut PAS regarder
"est-ce que je perds après avoir gagné" (les deux le prédisent), mais chercher
une prédiction où ils DIVERGENT.

LE TEST DE SYMÉTRIE (le seul vraiment décisif ici)
--------------------------------------------------
Un matchmaking honnête traite les deux équipes de façon identique : il n'existe
pas de "joueur cible". L'écart de force attendu entre ton équipe et l'équipe
adverse est donc ~0 EN MOYENNE, quelle que soit ta série en cours.

Une loser queue, elle, VISE un joueur : quand tu es en forme (winstreak), elle
devrait t'attribuer une équipe plus faible que l'adverse. Donc :

  H0 (honnête) : team_diff ne dépend PAS de ta forme récente (pente ≈ 0).
  H1 (rigged)  : team_diff DÉCROÎT quand ta forme récente monte (pente < 0).

On régresse team_diff sur recent_wr_10. Une pente significativement négative
est la signature d'un ciblage. Une pente nulle est cohérente avec un système
honnête. C'est falsifiable, et ça n'utilise PAS le résultat de la game comme
prédicteur — on évite ainsi la circularité (gagner → MMR monte → adversaires
plus durs, qui contaminerait toute analyse basée sur les résultats).

Tests secondaires : runs test (les streaks sont-elles au-delà du hasard),
auto-corrélation des résultats, et distribution de team_diff.

LIMITE RAPPELÉE : team_diff est bâti sur le RANG (proxy), pas le MMR réel.
Une pente nulle ne prouve pas l'absence absolue de loser queue ; elle montre
qu'au niveau du proxy disponible, rien ne distingue tes données d'un système
honnête. Pour aller plus loin il faudrait les données internes de Riot.

Usage :
    python analyze.py games.csv
"""

import csv
import sys
import statistics
from math import sqrt, isfinite

from champion_data import get_carry_score


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES SMURF
# ─────────────────────────────────────────────────────────────────────────────
# Écart de rang estimé entre le vrai MMR d'un smurf et son rang visible.
# Un Diamond III (~2300) jouant en Bronze III (~300) dévie team_diff de
# (2300 - 300) / 4 ≈ 500 pts en valeur absolue. On estime une correction
# modérée : le smurf "moyen" est 2 tiers au-dessus de son rang apparent.
SMURF_RANK_GAP = 800   # correction en pts de rang par smurf non détecté
# Taux de faux négatifs estimé de la détection binaire actuelle :
# is_smurf() ne capte que les profils Gold/Platine peu joués.
# Un smurf Diamond qui a simplement joué >60 games passe sous le radar.
SMURF_FNR = 0.60       # 60 % des vrais smurfs ne sont PAS flaggés


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            def num(k):
                v = r.get(k, "")
                if v in ("", "None", None):
                    return None
                try:
                    return float(v)
                except ValueError:
                    return v
            row = {k: num(k) for k in r}
            # Rétro-compatibilité : calcule carry_score si absent du CSV
            if row.get("my_carry_score") is None:
                champ = r.get("my_champ", "")
                role  = r.get("my_role", "")
                row["my_carry_score"] = get_carry_score(champ, role)
            rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Régression linéaire simple avec test de significativité de la pente
# ─────────────────────────────────────────────────────────────────────────────
def linregress(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    sse = sum(e ** 2 for e in resid)
    if n <= 2:
        return None
    se_slope = sqrt((sse / (n - 2)) / sxx) if sxx else float("inf")
    t = slope / se_slope if se_slope else 0.0
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / sqrt(sxx * syy) if sxx and syy else 0.0
    return {"slope": slope, "intercept": intercept, "se": se_slope,
            "t": t, "r": r, "n": n}


def linregress_nw(xs, ys, max_lag=None):
    """
    OLS + Newey-West HAC standard errors (Bartlett kernel).

    Contexte : recent_wr_10 est une fenêtre glissante de 10 games.
    L'autocorrélation d'ordre 1 est ρ₁ ≈ 0.9 → N effectif ≈ N/10.
    Les SE de linregress() classique sont ~√10 ≈ 3× trop petites,
    donc les p-values sont ~3× trop optimistes.

    max_lag : longueur de la fenêtre (None → 10, adapté à recent_wr_10).
    Retourne le même dict que linregress() + 'se_nw', 't_nw', 'n_eff'.
    """
    n = len(xs)
    if max_lag is None:
        max_lag = min(10, n // 4)
    base = linregress(xs, ys)
    if base is None or n < max_lag + 5:
        return base

    mx    = sum(xs) / n
    sxx   = sum((x - mx) ** 2 for x in xs)
    resid = [y - (base["slope"] * x + base["intercept"]) for x, y in zip(xs, ys)]

    # Scores ψ_t = (x_t - x̄) · ε_t
    scores = [(xs[t] - mx) * resid[t] for t in range(n)]

    # Variance long-run (Bartlett)
    S = sum(s ** 2 for s in scores) / n
    for lag in range(1, max_lag + 1):
        w = 1.0 - lag / (max_lag + 1)           # poids Bartlett
        gamma = sum(scores[t] * scores[t - lag]
                    for t in range(lag, n)) / n
        S += 2.0 * w * gamma

    # Plancher conservateur : SE_NW ≥ SE_OLS.
    # Quand les scores ont une autocorrélation négative (S < S0), NW donnerait
    # SE_NW < SE_OLS — pathologique à N≈100 (biais fini-échantillon). Sous H0
    # (résidus iid), SE_OLS est déjà valide ; on garde NW uniquement comme
    # correction positive (erreurs positivement autocorrélées → tests trop libéraux).
    S0         = sum(s ** 2 for s in scores) / n
    se_nw_raw  = sqrt(max(S, 0.0) / (sxx / n)) / sqrt(n) if sxx else float("inf")
    se_nw      = max(se_nw_raw, base["se"])  # conservateur : jamais < SE_OLS
    t_nw       = base["slope"] / se_nw if se_nw > 0 else 0.0

    # N effectif approximatif (jamais > n)
    n_eff  = int(n * S0 / max(S, S0)) if S > 0 else n

    return {**base, "se_nw": se_nw, "t_nw": t_nw, "n_eff": n_eff}


def estimate_rank_at_time(rows, lp_per_win=20, lp_per_loss=20):
    """
    Corrige my_rank_score pour chaque game : rang estimé AU MOMENT de la game.

    Principe : backpropagation depuis rank_current (snapshot API).
        rank_at_game_i = rank_current - Σ LP_delta(games j > i)

    Ajoute 'rank_score_estimated' et 'handicap_corrected' à chaque row.
    team_diff n'est PAS modifié : le drift temporel est symétrique intra-lobby
    (alliés et ennemis ont le même drift → s'annule dans la différence).
    """
    if not rows:
        return rows
    rank_current = next(
        (r["my_rank_score"] for r in reversed(rows)
         if r.get("my_rank_score") is not None), None)

    if rank_current is None:
        for r in rows:
            r["rank_score_estimated"] = None
            r["handicap_corrected"]   = None
        return rows

    # Cumul des LP gagnés/perdus APRÈS chaque game
    n = len(rows)
    running = 0.0
    cumul   = [0.0] * n
    for idx in range(n - 1, -1, -1):
        cumul[idx] = running
        win = rows[idx].get("win")
        if win == 1 or win == 1.0:
            running += lp_per_win
        else:
            running -= lp_per_loss

    for idx, r in enumerate(rows):
        est  = rank_current - cumul[idx]
        ally = r.get("avg_ally_score")
        r["rank_score_estimated"] = round(est, 1)
        r["handicap_corrected"]   = round(est - ally, 1) if ally is not None else None

    return rows


def carry_1v9(row, threshold=0.65):
    """Classifie le champion joué : 1 si carry solitaire, 0 si team-dependent."""
    cs = row.get("my_carry_score")
    if cs is None:
        return None
    return int(float(cs) >= threshold)


def test_intercept(rows):
    """
    Teste si E[team_diff] = 0. H1 challenge mode : E[team_diff] < 0 en permanence.
    Retourne dict avec mean, std, se, t, n.
    """
    vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
    n = len(vals)
    if n < 10:
        return None
    mu  = sum(vals) / n
    std = sqrt(sum((v - mu)**2 for v in vals) / (n - 1))
    se  = std / sqrt(n)
    t   = mu / se if se > 0 else 0.0
    return {"mean": round(mu, 1), "std": round(std, 1), "se": round(se, 1),
            "t": round(t, 3), "n": n}


# ─────────────────────────────────────────────────────────────────────────────
# RÉGRESSION MULTIPLE — OLS pur numpy-free
#
# Résout le système normal X'X β = X'y via élimination de Gauss-Jordan.
# Retourne les coefficients + erreurs standard + statistiques t pour chaque
# prédicteur. Design matrix X est passé en liste-de-lignes (chaque ligne = une
# observation, AVEC la colonne constante en première position si intercept=True).
# ─────────────────────────────────────────────────────────────────────────────
def _matmul(A, B):
    """Produit matriciel A (n×m) · B (m×p) → (n×p), représentés en listes."""
    n, m, p = len(A), len(A[0]), len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def _transpose(A):
    return [[A[i][j] for i in range(len(A))] for j in range(len(A[0]))]


def _gauss_jordan_inv(M):
    """Inverse d'une matrice carrée par élimination de Gauss-Jordan avec pivot partiel."""
    n = len(M)
    # Augmentation [M | I]
    aug = [list(M[i]) + [float(i == j) for j in range(n)] for i in range(n)]
    for col in range(n):
        # Pivot partiel
        max_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[max_row] = aug[max_row], aug[col]
        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            raise ValueError("Matrice singulière — colonnes colinéaires ?")
        aug[col] = [v / pivot for v in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [aug[row][k] - factor * aug[col][k] for k in range(2 * n)]
    return [row[n:] for row in aug]


def multilinregress(X_rows, ys, intercept=True):
    """
    Régression MCO multiple.

    Paramètres
    ----------
    X_rows   : list[list[float]]  — N lignes, chacune = [x1, x2, …]
    ys       : list[float]        — N observations
    intercept: bool               — ajoute une colonne de 1 en première position

    Retourne un dict avec :
      'coefs'     : list[(name_if_given, coef, se, t, p_approx)]
                    dans l'ordre [intercept?, x1, x2, …]
      'r2'        : R² ajusté
      'n'         : N
      'k'         : nb de paramètres (intercept compris)
      'residuals' : résidus
      'sse'       : somme des carrés des résidus
    """
    n = len(ys)
    if n < 3:
        return None

    # Construction de la design matrix
    if intercept:
        X = [[1.0] + list(row) for row in X_rows]
    else:
        X = [list(row) for row in X_rows]
    k = len(X[0])

    if n <= k:
        return None

    Xt = _transpose(X)
    XtX = _matmul(Xt, X)
    Xty_col = [[y] for y in ys]
    Xty = _matmul(Xt, Xty_col)           # k×1

    try:
        XtX_inv = _gauss_jordan_inv(XtX)
    except ValueError:
        return None

    # β = (X'X)^{-1} X'y
    beta_col = _matmul(XtX_inv, Xty)     # k×1
    beta = [b[0] for b in beta_col]

    # Résidus et MSE
    y_hat = [sum(X[i][j] * beta[j] for j in range(k)) for i in range(n)]
    resid = [ys[i] - y_hat[i] for i in range(n)]
    sse = sum(e ** 2 for e in resid)
    mse = sse / (n - k)

    # Erreurs standard et statistiques t
    se_list = [sqrt(max(0, XtX_inv[j][j] * mse)) for j in range(k)]
    t_list  = [beta[j] / se_list[j] if se_list[j] > 0 else 0.0 for j in range(k)]
    p_list  = [t_to_p_approx(t_list[j], n - k) for j in range(k)]

    # R² et R² ajusté
    y_mean = sum(ys) / n
    sst = sum((y - y_mean) ** 2 for y in ys)
    r2     = 1.0 - sse / sst if sst > 0 else 0.0
    r2_adj = 1.0 - (1 - r2) * (n - 1) / (n - k) if n > k else 0.0

    coefs = []
    labels = (["intercept"] + [f"x{i+1}" for i in range(k - 1)]) if intercept \
             else [f"x{i+1}" for i in range(k)]
    for j in range(k):
        coefs.append((labels[j], beta[j], se_list[j], t_list[j], p_list[j]))

    return {"coefs": coefs, "r2": r2, "r2_adj": r2_adj,
            "n": n, "k": k, "residuals": resid, "sse": sse}


# ─────────────────────────────────────────────────────────────────────────────
# SCORE SMURF CONTINU [0, 1]
#
# Heuristique par game, construite sur les variables disponibles dans le CSV.
# On ne dispose pas du profil individuel de chaque joueur — on raisonne sur
# les DÉSÉQUILIBRES observés qui sont des empreintes des smurfs non détectés.
# ─────────────────────────────────────────────────────────────────────────────
LANE_DIFF_COLS = ["lane_diff_TOP", "lane_diff_JGL", "lane_diff_MID",
                  "lane_diff_BOT", "lane_diff_SUP"]


def smurf_prob_score(row,
                     lane_extreme_threshold=350,
                     team_gap_threshold=200,
                     win_despite_deficit=-150):
    """
    Estime la probabilité composite qu'il y ait au moins un smurf non détecté
    dans la game, depuis les signaux indirects disponibles. Retourne un score
    ∈ [0, 1] — c'est une heuristique, pas une probabilité calibrée.

    Signaux utilisés
    ----------------
    S1 — Lane dominée de façon extrême (≥ lane_extreme_threshold pts)
         Un duel lane_diff_X très négatif (allié très faible sur sa lane)
         peut indiquer un smurf ennemi sur cette lane.
         Symétriquement, très positif → smurf allié ou handicap ennemi.
         On prend l'amplitude max indépendamment du signe.

    S2 — team_diff très négatif MAIS victoire
         Si l'équipe semble faible (team_diff << 0) mais gagne, c'est
         cohérent avec des alliés sous-cotés (smurfs alliés).

    S3 — Écart entre my_rank_score et avg_ally_score
         Un joueur nettement au-dessus de ses alliés → composition anormale,
         souvent signe que certains alliés sont des smurfs (sous-cotés réels).

    S4 — smurf_diff non nul (détection binaire déjà disponible)
         Si is_smurf() a déjà flaggé quelqu'un, on monte le prior.

    Chaque signal contribue [0, 1] ; le score composite est leur max pondéré
    pour éviter la saturation artificielle sur des signaux colinéaires.
    """
    signals = []

    # S1 : extrêmes de lane
    lane_extremes = []
    for col in LANE_DIFF_COLS:
        v = row.get(col)
        if v is not None:
            lane_extremes.append(abs(v))
    if lane_extremes:
        max_extreme = max(lane_extremes)
        # Sigmoïde centrée sur le seuil : 0 sous le seuil, monte progressivement
        s1 = max(0.0, min(1.0, (max_extreme - lane_extreme_threshold) / lane_extreme_threshold))
        signals.append(("lane_extreme", s1, 0.40))

    # S2 : team_diff négatif + victoire (alliés sous-cotés)
    td = row.get("team_diff")
    win = row.get("win")
    if td is not None and win is not None:
        if int(win) == 1 and td < win_despite_deficit:
            # Plus le déficit est grand et la victoire surprenante, plus le score monte
            s2 = max(0.0, min(1.0, (abs(td) - abs(win_despite_deficit)) / 300))
            signals.append(("surprise_win", s2, 0.35))
        elif int(win) == 0 and td > abs(win_despite_deficit):
            # Défaite alors qu'on avait l'équipe forte → smurfs ennemis probables
            s2_inv = max(0.0, min(1.0, (td - abs(win_despite_deficit)) / 300))
            signals.append(("surprise_loss", s2_inv, 0.30))

    # S3 : écart my_rank_score vs avg_ally
    my_score = row.get("my_rank_score")
    avg_ally = row.get("avg_ally_score")
    if my_score is not None and avg_ally is not None:
        gap = my_score - avg_ally
        if abs(gap) > team_gap_threshold:
            s3 = max(0.0, min(1.0, (abs(gap) - team_gap_threshold) / team_gap_threshold))
            signals.append(("rank_gap", s3, 0.25))

    # S4 : détection binaire existante
    smurf_diff = row.get("smurf_diff")
    n_smurf_allies = row.get("n_smurf_allies", 0) or 0
    n_smurf_enemies = row.get("n_smurf_enemies", 0) or 0
    total_flagged = (n_smurf_allies or 0) + (n_smurf_enemies or 0)
    if total_flagged > 0:
        # Chaque smurf détecté ajoute ~0.4 de base (FNR = 60 % → signal partiel)
        s4 = min(1.0, total_flagged * 0.40)
        signals.append(("binary_flag", s4, 1.00))  # poids fort : détection directe

    if not signals:
        return 0.0

    # Score composite : moyenne pondérée des signaux actifs
    total_weight = sum(w for _, _, w in signals)
    composite = sum(s * w for _, s, w in signals) / total_weight

    # Présence d'un smurf détecté = plancher minimum
    if total_flagged > 0:
        composite = max(composite, 0.35)

    return round(composite, 3)


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION DE team_diff POUR LES SMURFS
#
# Approche conservative : on ne corrige que les smurfs DÉTECTÉS (is_smurf flag)
# pour éviter de créer plus de biais qu'on n'en supprime. La correction impute
# un MMR "réel" au smurf : on remplace son rank_score visible par une estimation
# de son vrai niveau.
# ─────────────────────────────────────────────────────────────────────────────
def smurf_adjusted_team_diff(row, rank_gap_per_smurf=SMURF_RANK_GAP):
    """
    Corrige team_diff en tenant compte des smurfs DÉTECTÉS.

    Logique de correction :
    -----------------------
    Un smurf allié "détecté" fait baisser avg_ally_score de ~rank_gap_per_smurf/4
    (il y a 4 alliés). Le vrai avg_ally serait plus élevé → on ajoute la correction.

    Un smurf ennemi détecté fait baisser avg_enemy_score → le vrai avg_enemy est
    plus élevé → team_diff est surestimé, on soustrait.

    Formule :
      correction_ally   = n_smurf_allies  * rank_gap_per_smurf / 4
      correction_enemy  = n_smurf_enemies * rank_gap_per_smurf / 5
      team_diff_corr    = team_diff + correction_ally - correction_enemy

    Note : rank_gap_per_smurf = MMR_réel_estimé - rang_visible.
    On utilise SMURF_RANK_GAP = 800 pts par défaut (profil typique : Gold visible,
    Diamond réel → ~800 pts d'écart). C'est une borne basse conservative.

    Retourne None si team_diff n'est pas disponible.
    """
    td = row.get("team_diff")
    if td is None:
        return None

    n_smurf_allies  = int(row.get("n_smurf_allies",  0) or 0)
    n_smurf_enemies = int(row.get("n_smurf_enemies", 0) or 0)

    # Impact sur les moyennes d'équipe (on divise par le nb de joueurs de l'équipe)
    # allies = 4 joueurs (joueur ciblé exclu), enemies = 5
    correction_ally  = n_smurf_allies  * rank_gap_per_smurf / 4.0
    correction_enemy = n_smurf_enemies * rank_gap_per_smurf / 5.0

    return round(td + correction_ally - correction_enemy, 1)


def smurf_bias_magnitude(rows):
    """
    Estime la magnitude du biais smurf sur team_diff (en pts de rang) :
      - biais moyen absolu (E[|correction|])
      - biais net directionnel (E[correction]) — non nul si smurfs asymétriques
      - corrélation entre smurf_diff et recent_wr_10 (teste si le biais est
        corrélé à la variable d'intérêt → biais systématique, pas que du bruit)
    """
    corrections = []
    corr_pairs  = []   # (recent_wr_10, smurf_diff)

    for r in rows:
        td = r.get("team_diff")
        td_adj = smurf_adjusted_team_diff(r)
        if td is not None and td_adj is not None:
            corrections.append(td_adj - td)

        wr10 = r.get("recent_wr_10")
        sd   = r.get("smurf_diff")
        if wr10 is not None and sd is not None:
            corr_pairs.append((wr10, float(sd)))

    if not corrections:
        return {}

    n = len(corrections)
    mean_bias  = sum(corrections) / n
    mean_abs   = sum(abs(c) for c in corrections) / n

    result = {
        "n_games_with_smurfs": sum(1 for c in corrections if c != 0),
        "mean_bias_net":  round(mean_bias,  1),   # biais directionnel moyen
        "mean_bias_abs":  round(mean_abs,   1),   # magnitude absolue moyenne
    }

    # Corrélation smurf_diff ~ recent_wr_10
    if len(corr_pairs) >= 5:
        reg = linregress([p[0] for p in corr_pairs], [p[1] for p in corr_pairs])
        if reg:
            result["smurf_diff_vs_wr10_r"]     = round(reg["r"], 3)
            result["smurf_diff_vs_wr10_slope"]  = round(reg["slope"], 2)
            result["smurf_diff_vs_wr10_t"]      = round(reg["t"], 2)
            result["smurf_diff_vs_wr10_p"]      = round(
                t_to_p_approx(reg["t"], reg["n"] - 2), 4)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# RÉGRESSION MULTIPLE : team_diff ~ recent_wr_10 + smurf_diff
#
# Test de robustesse : si le coefficient de recent_wr_10 reste significatif
# après contrôle de smurf_diff, le signal loser queue est robuste aux smurfs.
# ─────────────────────────────────────────────────────────────────────────────
def regression_with_smurf_control(rows, use_adjusted_td=False):
    """
    Régression multiple OLS :
      team_diff ~ 1 + recent_wr_10 + smurf_diff

    Optionnellement, utilise team_diff corrigé (smurf_adjusted_team_diff).

    Paramètres
    ----------
    rows            : liste de dicts (chaque ligne du CSV)
    use_adjusted_td : si True, corrige team_diff avant la régression

    Retourne le résultat de multilinregress() avec labels nommés, ou None.

    Interprétation des coefficients
    --------------------------------
    intercept      : team_diff prédit quand forme = 0 et smurf_diff = 0
    β_recent_wr_10 : variation de team_diff pour +1 de win-rate (échelle 0→1)
                     Si négatif et significatif → signal loser queue robuste
                     aux smurfs (après contrôle de leur déséquilibre)
    β_smurf_diff   : variation de team_diff par unité de smurf_diff
                     (smurf_diff = n_smurf_ennemis - n_smurf_alliés)
                     Attendu POSITIF : plus de smurfs ennemis → avg_enemy_score
                     sous-estimé → team_diff artificiellement élevé
                     → β > 0 confirme que les smurfs détectés biaisent bien
                     team_diff dans la direction attendue
    """
    triples = []
    for r in rows:
        wr10 = r.get("recent_wr_10")
        sd   = r.get("smurf_diff")
        td   = smurf_adjusted_team_diff(r) if use_adjusted_td else r.get("team_diff")
        if wr10 is not None and sd is not None and td is not None:
            triples.append((float(wr10), float(sd), float(td)))

    if len(triples) < 10:
        return None

    X_rows = [[t[0], t[1]] for t in triples]
    ys     = [t[2] for t in triples]

    result = multilinregress(X_rows, ys, intercept=True)
    if result is None:
        return None

    # Renomme les labels génériques
    labels = ["intercept", "recent_wr_10", "smurf_diff"]
    result["coefs"] = [
        (labels[j], *result["coefs"][j][1:])
        for j in range(len(result["coefs"]))
    ]
    return result


def t_to_p_approx(t, df):
    """Approximation grossière de la p-value bilatérale (sans scipy).
    Pour |t|>~2 avec df>30 c'est proche de la vraie valeur. Indicatif."""
    t = abs(t)
    # approximation normale (df grand)
    # p ≈ 2 * (1 - Phi(t)) ; Phi via erf approx
    import math
    z = t
    # erf via Abramowitz-Stegun 7.1.26
    def erf(x):
        sign = 1 if x >= 0 else -1
        x = abs(x)
        a1, a2, a3, a4, a5, p = (0.254829592, -0.284496736, 1.421413741,
                                 -1.453152027, 1.061405429, 0.3275911)
        tt = 1 / (1 + p * x)
        y = 1 - (((((a5 * tt + a4) * tt) + a3) * tt + a2) * tt + a1) * tt * math.exp(-x * x)
        return sign * y
    phi = 0.5 * (1 + erf(z / sqrt(2)))
    return 2 * (1 - phi)


# ─────────────────────────────────────────────────────────────────────────────
# Runs test : les séries observées sont-elles compatibles avec le hasard ?
# ─────────────────────────────────────────────────────────────────────────────
def runs_test(wins):
    n1 = sum(wins)
    n2 = len(wins) - n1
    if n1 == 0 or n2 == 0:
        return None
    runs = 1 + sum(1 for i in range(1, len(wins)) if wins[i] != wins[i - 1])
    exp = 1 + (2 * n1 * n2) / (n1 + n2)
    var = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    if var <= 0:
        return None
    z = (runs - exp) / sqrt(var)
    return {"runs": runs, "expected": exp, "z": z}


def longest_streaks(wins):
    maxw = maxl = cw = cl = 0
    for w in wins:
        if w:
            cw += 1; cl = 0
        else:
            cl += 1; cw = 0
        maxw = max(maxw, cw); maxl = max(maxl, cl)
    return maxw, maxl


# ─────────────────────────────────────────────────────────────────────────────
# Détection d'épisodes suspects
#
# Une loser queue n'est pas un phénomène sur 200 games : c'est une fenêtre
# courte où DEUX signaux sont anormaux simultanément :
#
#   Score global   = team_diff très négatif (tes alliés sont anormalement
#                    faibles par rapport à l'adversaire)
#   Score individuel = handicap très positif (ton rang est anormalement
#                    plus élevé que celui de tes coéquipiers — tu as été
#                    placé avec une équipe dégradée)
#
# On z-score les deux métriques sur l'ensemble des games, puis on classe
# chaque game sur une échelle de suspicion 0-2 (un point par signal
# anormal). Une game "suspecte" = au moins 1 signal déclenché.
# Un épisode = ≥ MIN_RUN games suspectes consécutives.
# ─────────────────────────────────────────────────────────────────────────────
def _mean_std(vals):
    if not vals:
        return 0.0, 1.0
    m = sum(vals) / len(vals)
    v = sum((x - m) ** 2 for x in vals) / len(vals)
    return m, sqrt(v) if v > 0 else 1.0


LANE_COLS = ["lane_diff_TOP", "lane_diff_JGL", "lane_diff_MID", "lane_diff_BOT", "lane_diff_SUP"]
LANE_LABELS = {"lane_diff_TOP": "TOP", "lane_diff_JGL": "JGL",
               "lane_diff_MID": "MID", "lane_diff_BOT": "BOT", "lane_diff_SUP": "SUP"}


def detect_episodes(rows, z_thresh_team=-1.5, z_thresh_indiv=1.2,
                    z_thresh_lane=-1.5, min_suspect_lanes=2, min_run=3):
    """
    Retourne (rows_annotés, épisodes).

    Signaux par game :
      z_team        : z-score de team_diff (global)
      z_indiv       : z-score de (my_rank_score - avg_ally_score)
      n_weak_lanes  : nombre de lanes avec z_lane < z_thresh_lane
      suspicion     : 0-3 (un point par signal déclenché)
    """
    # ── Signal 1 : team_diff global ─────────────────────────────────────────
    td_vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
    td_mean, td_std = _mean_std(td_vals)

    # ── Signal 2 : handicap individuel (joueur vs alliés) ───────────────────
    hc_vals = []
    for r in rows:
        my = r.get("my_rank_score")
        ally = r.get("avg_ally_score")
        if my is not None and ally is not None:
            r["_handicap"] = my - ally
            hc_vals.append(r["_handicap"])
        else:
            r["_handicap"] = None
    hc_mean, hc_std = _mean_std(hc_vals)

    # ── Signal 3 : déséquilibres par lane ───────────────────────────────────
    # z-score indépendant par lane (chaque lane a sa propre distribution)
    lane_stats = {}
    for col in LANE_COLS:
        vals = [r[col] for r in rows if r.get(col) is not None]
        lane_stats[col] = _mean_std(vals)

    # ── Annotation par game ──────────────────────────────────────────────────
    for r in rows:
        td = r.get("team_diff")
        r["z_team"] = (td - td_mean) / td_std if td is not None else None

        hc = r.get("_handicap")
        r["z_indiv"] = (hc - hc_mean) / hc_std if hc is not None else None

        weak_lanes = []
        for col in LANE_COLS:
            v = r.get(col)
            if v is not None:
                m, s = lane_stats[col]
                z = (v - m) / s
                if z < z_thresh_lane:
                    weak_lanes.append(LANE_LABELS[col])
        r["weak_lanes"]    = weak_lanes
        r["n_weak_lanes"]  = len(weak_lanes)

        flag_team  = r["z_team"]  is not None and r["z_team"]  < z_thresh_team
        flag_indiv = r["z_indiv"] is not None and r["z_indiv"] > z_thresh_indiv
        flag_lanes = r["n_weak_lanes"] >= min_suspect_lanes
        # Smurf signal : plus de smurfs côté ennemi qu'allié
        flag_smurf = (r.get("smurf_diff") is not None and r.get("smurf_diff", 0) > 0)
        r["suspicion"] = int(flag_team) + int(flag_indiv) + int(flag_lanes) + int(flag_smurf)

    # ── Détection d'épisodes ─────────────────────────────────────────────────
    episodes, run = [], []
    for r in rows:
        if r["suspicion"] >= 1:
            run.append(r)
        else:
            if len(run) >= min_run:
                episodes.append(list(run))
            run = []
    if len(run) >= min_run:
        episodes.append(list(run))

    return rows, episodes, (td_mean, td_std), (hc_mean, hc_std)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage : python analyze.py games.csv")
        sys.exit(1)
    rows = load(sys.argv[1])
    rows = [r for r in rows if r.get("game_index") is not None]
    rows.sort(key=lambda r: r["game_index"])
    n = len(rows)
    print(f"\n{'='*64}")
    print(f"  ANALYSE — {n} games")
    print(f"{'='*64}")

    wins = [int(r["win"]) for r in rows]
    wr = sum(wins) / n
    maxw, maxl = longest_streaks(wins)
    print(f"\nWin-rate global        : {wr*100:.1f}%")
    print(f"Plus longue série W    : {maxw}")
    print(f"Plus longue série L    : {maxl}")

    # ── 1. RUNS TEST ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("1. RUNS TEST — les streaks sont-elles au-delà du hasard ?")
    print(f"{'─'*64}")
    rt = runs_test(wins)
    if rt:
        print(f"  runs observés : {rt['runs']}  | attendus : {rt['expected']:.1f}")
        print(f"  z = {rt['z']:.2f}")
        if abs(rt["z"]) < 1.96:
            print("  → Compatible avec le hasard. Les séries que tu vis sont")
            print("    exactement ce qu'une pièce truquée à ton win-rate produit.")
        else:
            print("  → Écart significatif à l'indépendance. À creuser, mais note")
            print("    qu'un matchmaking honnête par MMR PEUT aussi en produire")
            print("    (ta forme change ton MMR, donc tes adversaires).")

    # ── 2. AUTO-CORRÉLATION ─────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("2. AUTO-CORRÉLATION — gagner prédit-il le résultat suivant ?")
    print(f"{'─'*64}")
    if n > 3:
        x = wins[:-1]
        y = wins[1:]
        reg = linregress([float(v) for v in x], [float(v) for v in y])
        if reg:
            p = t_to_p_approx(reg["t"], reg["n"] - 2)
            print(f"  corrélation r = {reg['r']:+.3f}  (p≈{p:.3f})")
            print("  Rappel : une corrélation NÉGATIVE (gagner → perdre ensuite)")
            print("  est prédite À LA FOIS par la loser queue ET par le simple")
            print("  retour vers 50%. Ce test seul ne tranche donc rien — il est")
            print("  ici pour mémoire. Le test décisif est le n°3.")

    # ── Correction temporelle du rang (handicap individuel, pas team_diff) ───
    rows = estimate_rank_at_time(rows)

    # ── 3. TEST DE SYMÉTRIE (DÉCISIF) ───────────────────────────────────────
    print(f"\n{'─'*64}")
    print("3. TEST DE SYMÉTRIE — team_diff dépend-il de ta forme ? [DÉCISIF]")
    print(f"{'─'*64}")
    pairs = [(r["recent_wr_10"], r["team_diff"]) for r in rows
             if r.get("recent_wr_10") is not None and r.get("team_diff") is not None]
    if len(pairs) < 10:
        print("  Pas assez de games avec rangs complets des deux équipes.")
        print("  Collecte davantage de games (--count plus élevé).")
    else:
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        mean_diff = sum(ys) / len(ys)
        reg    = linregress(xs, ys)
        reg_nw = linregress_nw(xs, ys, max_lag=10)
        print(f"  n = {len(pairs)} games  |  n_effectif (NW) ≈ {reg_nw['n_eff'] if reg_nw else '?'}")
        print(f"  team_diff moyen : {mean_diff:+.1f} pts de rang")
        print(f"    (≈0 attendu sous matchmaking honnête : équipes symétriques)")
        if reg and reg_nw:
            p_ols = t_to_p_approx(reg["t"],    reg["n"] - 2)
            p_nw  = t_to_p_approx(reg_nw["t_nw"], reg_nw["n"] - 2)
            print(f"\n  Régression team_diff ~ forme_récente :")
            print(f"    pente  = {reg['slope']:+.1f} pts / unité de WR récent")
            print(f"    OLS    : SE={reg['se']:.1f}   t={reg['t']:+.2f}   p≈{p_ols:.3f}")
            print(f"    NW-HAC : SE={reg_nw['se_nw']:.1f}   t={reg_nw['t_nw']:+.2f}   p≈{p_nw:.3f}  ← à utiliser")
            print(f"    (NW corrige l'autocorrélation de la fenêtre glissante de 10 games)")
            print()
            sig_nw = reg_nw["slope"] < 0 and p_nw < 0.05
            if sig_nw:
                print("  ⚠ PENTE NÉGATIVE SIGNIFICATIVE (même après correction NW).")
                print("    Quand tu es en forme, tes équipes deviennent plus faibles")
                print("    relativement à l'adverse — signature d'un ciblage.")
                print("    Vérifie la taille d'effet et le test 3c (pred_win_prob).")
            elif reg["slope"] < 0 and p_ols < 0.05 and p_nw >= 0.05:
                print("  ⚠ ATTENTION — FAUX POSITIF PROBABLE.")
                print("    La pente semble significative en OLS (p<0.05) mais ne l'est")
                print("    plus après correction Newey-West (autocorrélation de la fenêtre")
                print("    glissante de 10 games). Le résultat OLS seul est non fiable.")
            else:
                print("  ✓ Pas de pente négative significative (NW p≥0.05).")
                print("    Données cohérentes avec un matchmaking honnête au niveau du rang.")
                print("    Une pente nulle ne prouve pas l'absence de loser queue :")
                print("    le proxy (rang) peut masquer un effet MMR réel plus fin.")

    # ── 3c. PROBABILITÉ DE VICTOIRE PRÉDITE (test alternatif) ──────────────
    print(f"\n{'─'*64}")
    print("3c. PRED_WIN_PROB ~ forme récente [test alternatif à team_diff]")
    print(f"{'─'*64}")
    print("  Formule ELO : P = 1 / (1 + 10^(-(avg_ally - avg_enemy) / 400))")
    print("  Joueurs sans rang → imputés au rang du joueur ciblé (imputation conservatrice)")
    print()

    def pred_win_prob(row, k=400):
        """
        Probabilité ELO-like de gagner depuis avg_ally_score et avg_enemy_score.

        Les scores non-rankés sont imputés au rang du joueur ciblé :
        hypothèse de matchmaking (adversaires censés être au même niveau).
        Retourne None si couverture < 2 rankés de chaque côté.
        """
        ally  = row.get("avg_ally_score")
        enemy = row.get("avg_enemy_score")
        my    = row.get("my_rank_score")

        if ally is None or enemy is None:
            return None

        n_ally_ranked  = int(row.get("n_ally_ranked",  0) or 0)
        n_enemy_ranked = int(row.get("n_enemy_ranked", 0) or 0)

        # Couverture minimale : au moins 2 rankés de chaque côté
        if n_ally_ranked < 2 or n_enemy_ranked < 2:
            return None

        n_ally_missing  = 4 - n_ally_ranked   # alliés hors joueur ciblé
        n_enemy_missing = 5 - n_enemy_ranked

        if my is not None and (n_ally_missing > 0 or n_enemy_missing > 0):
            # Reconstruction des moyennes ajustées par imputation
            ally_sum  = ally  * n_ally_ranked  + my * n_ally_missing
            enemy_sum = enemy * n_enemy_ranked + my * n_enemy_missing
            avg_ally_adj  = ally_sum  / 4
            avg_enemy_adj = enemy_sum / 5
        else:
            avg_ally_adj  = ally
            avg_enemy_adj = enemy

        diff = avg_ally_adj - avg_enemy_adj
        return 1.0 / (1.0 + 10.0 ** (-diff / k))

    prob_pairs = []
    for r in rows:
        p = pred_win_prob(r)
        wr10 = r.get("recent_wr_10")
        if p is not None and wr10 is not None:
            # Pondération par la couverture : (n_ally_ranked + n_enemy_ranked) / 9
            n_a = int(r.get("n_ally_ranked", 0) or 0)
            n_e = int(r.get("n_enemy_ranked", 0) or 0)
            coverage = (n_a + n_e) / 9.0
            prob_pairs.append((wr10, p, coverage))

    if len(prob_pairs) < 10:
        print("  Pas assez de games avec couverture ≥ 2 rankés par équipe.")
    else:
        xs_p = [t[0] for t in prob_pairs]
        ys_p = [t[1] for t in prob_pairs]
        mean_prob = sum(ys_p) / len(ys_p)

        reg_p = linregress(xs_p, ys_p)
        p_val_p = t_to_p_approx(reg_p["t"], reg_p["n"] - 2) if reg_p else None

        print(f"  n = {len(prob_pairs)} games exploitables")
        print(f"  pred_win_prob moyenne : {mean_prob:.3f}  (attendu ≈ 0.500 sous H0)")
        print(f"  [note : < 0.500 = tes alliés sont statistiquement plus faibles en moyenne]")

        if reg_p:
            # p-value unilatérale (H1 directionnelle : pente < 0)
            p_bilateral = p_val_p
            p_unilateral = p_bilateral / 2.0  # valide seulement si t < 0
            if reg_p["t"] >= 0:
                p_unilateral = 1.0 - p_bilateral / 2.0  # pente positive → non dans le sens H1

            print(f"\n  Régression pred_win_prob ~ forme_récente (K=400) :")
            print(f"    pente     = {reg_p['slope']:+.4f}   (t={reg_p['t']:+.2f})")
            print(f"    p bilatéral ≈ {p_bilateral:.4f}   p unilatéral (H1: β<0) ≈ {p_unilateral:.4f}")
            print(f"    r         = {reg_p['r']:+.3f}")
            print()

            # Interprétation de la taille d'effet
            amp = max(xs_p) - min(xs_p)
            effet = abs(reg_p["slope"]) * amp * 100  # en points de pourcentage
            print(f"  Amplitude de forme observée : {amp:.2f}  (winrate de {min(xs_p):.0%} à {max(xs_p):.0%})")
            print(f"  Taille d'effet : {effet:.1f}pp de pred_win_prob sur cette amplitude")

            if reg_p["slope"] < 0 and p_unilateral < 0.05:
                print()
                print("  PENTE NEGATIVE SIGNIFICATIVE (test unilatéral α=0.05).")
                print("  Quand tu es en forme, la probabilité prédite de gagner DIMINUE.")
                print("  Signature cohérente avec une loser queue ciblant ce joueur.")
                print("  Rappel : pred_win_prob est un PROXY (rang ≠ MMR interne Riot).")
            elif reg_p["slope"] < 0 and p_unilateral < 0.10:
                print()
                print("  Tendance négative (p < 0.10 unilatéral), non significative à 0.05.")
                print("  Signal faible. Augmenter le nombre de games (objectif : N ≥ 300).")
            else:
                print()
                print("  Pas de pente négative significative.")
                print("  La probabilité prédite de gagner ne diminue pas quand tu es en forme.")
                print("  Cohérent avec un matchmaking honnête au niveau du rang observable.")

        # Sensibilité à K : re-tester avec K=200 et K=800
        print()
        print("  Robustesse à K (sensibilité au paramètre d'échelle) :")
        for k_test in (200, 400, 800):
            pairs_k = []
            for r in rows:
                p_k = pred_win_prob(r, k=k_test)
                wr10 = r.get("recent_wr_10")
                if p_k is not None and wr10 is not None:
                    pairs_k.append((wr10, p_k))
            if len(pairs_k) < 10:
                continue
            reg_k = linregress([t[0] for t in pairs_k], [t[1] for t in pairs_k])
            if reg_k:
                pk_p = t_to_p_approx(reg_k["t"], reg_k["n"] - 2)
                pk_uni = pk_p / 2.0 if reg_k["t"] < 0 else 1.0 - pk_p / 2.0
                print(f"    K={k_test:>4} : pente={reg_k['slope']:+.4f}  t={reg_k['t']:+.2f}  "
                      f"p_uni={pk_uni:.4f}")
        print("  (Si la conclusion change selon K, le signal n'est pas robuste.)")

    # ── 3b. CARRY SCORE — impact de l'archétype sur la tankabilité ──────────
    print(f"\n{'─'*64}")
    print("3b. CARRY SCORE — loser queue tankable selon le champion ?")
    print(f"{'─'*64}")
    print("  (0.0 = enchanteur pur, 1.0 = split pusher extrême)\n")

    # Séparer les games en deux groupes : carry_score bas vs élevé
    CARRY_THRESHOLD = 0.55
    lo_rows = [r for r in rows
               if r.get("my_carry_score") is not None
               and r["my_carry_score"] < CARRY_THRESHOLD
               and r.get("team_diff") is not None]
    hi_rows = [r for r in rows
               if r.get("my_carry_score") is not None
               and r["my_carry_score"] >= CARRY_THRESHOLD
               and r.get("team_diff") is not None]

    def group_stats(grp, label):
        if len(grp) < 5:
            print(f"  {label:<28} : pas assez de games ({len(grp)})")
            return
        wr_g    = sum(int(r["win"]) for r in grp) / len(grp)
        avg_cs  = sum(r["my_carry_score"] for r in grp) / len(grp)
        td_vals = [r["team_diff"] for r in grp]
        td_mean_g = sum(td_vals) / len(td_vals)
        # win rate selon que team_diff est positif ou négatif
        wr_up   = [r for r in grp if r["team_diff"] >= 0]
        wr_down = [r for r in grp if r["team_diff"] <  0]
        wr_up_v   = sum(int(r["win"]) for r in wr_up)   / len(wr_up)   if wr_up   else None
        wr_down_v = sum(int(r["win"]) for r in wr_down) / len(wr_down) if wr_down else None
        print(f"  {label:<28} : {len(grp):>4} games  carry={avg_cs:.2f}  WR={wr_g*100:.1f}%")
        if wr_up_v   is not None:
            print(f"    ↑ équipe favorable   ({len(wr_up):>3} games) → WR {wr_up_v*100:.1f}%")
        if wr_down_v is not None:
            print(f"    ↓ équipe défavorable ({len(wr_down):>3} games) → WR {wr_down_v*100:.1f}%")
        if wr_up_v is not None and wr_down_v is not None:
            delta = (wr_up_v - wr_down_v) * 100
            print(f"    Δ WR (favorable→défavorable) : {delta:+.1f}pp")
        print()

    group_stats(lo_rows, "Champions dépendants (< 0.55)")
    group_stats(hi_rows, "Champions autonomes  (≥ 0.55)")

    if lo_rows and hi_rows:
        lo_delta = None; hi_delta = None
        lo_up   = [r for r in lo_rows if r["team_diff"] >= 0]
        lo_down = [r for r in lo_rows if r["team_diff"] <  0]
        hi_up   = [r for r in hi_rows if r["team_diff"] >= 0]
        hi_down = [r for r in hi_rows if r["team_diff"] <  0]
        if lo_up and lo_down:
            lo_delta = (sum(int(r["win"]) for r in lo_up)   / len(lo_up) -
                        sum(int(r["win"]) for r in lo_down) / len(lo_down)) * 100
        if hi_up and hi_down:
            hi_delta = (sum(int(r["win"]) for r in hi_up)   / len(hi_up) -
                        sum(int(r["win"]) for r in hi_down) / len(hi_down)) * 100
        if lo_delta is not None and hi_delta is not None:
            print(f"  → Sensibilité au team_diff :")
            print(f"    Champions dépendants : {lo_delta:+.1f}pp  (grande sensibilité = loser queue plus dure)")
            print(f"    Champions autonomes  : {hi_delta:+.1f}pp")
            if lo_delta > hi_delta + 5:
                print("  ✓ Les champions dépendants souffrent davantage d'une équipe faible.")
                print("    Cohérent avec l'hypothèse : la loser queue est moins tankable")
                print("    sur les enchanters/supports que sur les carry solo.")
            elif abs(lo_delta - hi_delta) <= 5:
                print("  ≈ Pas de différence notable entre les deux archétypes.")
                print("    L'équipe faible pénalise tout le monde de façon similaire.")

    # ── 3d. ANALYSE SMURF — biais sur team_diff et contrôle statistique ────────
    print(f"\n{'─'*64}")
    print("3d. ANALYSE SMURF — biais sur team_diff et contrôle statistique")
    print(f"{'─'*64}")

    # Score smurf continu par game
    for r in rows:
        r["smurf_prob"] = smurf_prob_score(r)

    smurf_probs = [r["smurf_prob"] for r in rows]
    high_smurf_games = sum(1 for p in smurf_probs if p > 0.4)
    mean_smurf_prob  = sum(smurf_probs) / len(smurf_probs) if smurf_probs else 0

    n_ally_flags  = sum(int(r.get("n_smurf_allies",  0) or 0) for r in rows)
    n_enemy_flags = sum(int(r.get("n_smurf_enemies", 0) or 0) for r in rows)
    print(f"\n  Smurfs détectés (flag binaire is_smurf) :")
    print(f"    alliés  : {n_ally_flags}  sur {n} games")
    print(f"    ennemis : {n_enemy_flags}  sur {n} games")
    if n_ally_flags + n_enemy_flags > 0:
        ratio = n_enemy_flags / max(1, n_ally_flags + n_enemy_flags)
        print(f"    ratio ennemis/(total) = {ratio:.2f}  "
              f"(0.5 = équilibré, >0.5 = plus ennemis → biais team_diff artificiel)")

    print(f"\n  Score smurf continu (heuristique multi-signaux) :")
    print(f"    moyenne : {mean_smurf_prob:.3f}   (0 = aucun signal, 1 = très suspect)")
    print(f"    games > 0.4 : {high_smurf_games}/{n}  ({high_smurf_games/n*100:.1f}%)")

    # Magnitude du biais
    bias = smurf_bias_magnitude(rows)
    if bias:
        print(f"\n  Magnitude du biais smurf sur team_diff :")
        print(f"    biais net directionnel : {bias['mean_bias_net']:+.1f} pts de rang")
        print(f"    biais absolu moyen     : {bias['mean_bias_abs']:+.1f} pts de rang")
        print(f"    games avec smurfs détectés : {bias['n_games_with_smurfs']}/{n}")
        if "smurf_diff_vs_wr10_r" in bias:
            r_sd = bias["smurf_diff_vs_wr10_r"]
            sl_sd = bias["smurf_diff_vs_wr10_slope"]
            t_sd = bias["smurf_diff_vs_wr10_t"]
            p_sd = bias["smurf_diff_vs_wr10_p"]
            print(f"\n  Corrélation smurf_diff ~ recent_wr_10 :")
            print(f"    r = {r_sd:+.3f}   pente = {sl_sd:+.2f}   t = {t_sd:+.2f}   p ≈ {p_sd:.4f}")
            if abs(r_sd) < 0.10 or p_sd > 0.10:
                print("    → smurf_diff NOT corrélé à la forme récente.")
                print("      Le biais smurf est du BRUIT SYMÉTRIQUE : il gonfle la variance")
                print("      de team_diff mais ne crée PAS de faux signal loser queue.")
                print("      La régression principale (test 3) est peu affectée.")
            else:
                sign = "+" if r_sd > 0 else "-"
                print(f"    → smurf_diff CORRÉLÉ à la forme ({sign}). BIAIS ASYMÉTRIQUE :")
                if r_sd > 0:
                    print("      Quand tu es en forme, il y a plus de smurfs ENNEMIS détectés.")
                    print("      Ceci GONFLE team_diff (ennemi sous-coté → diff artificielle).")
                    print("      Le signal loser queue serait ATTÉNUÉ après correction.")
                else:
                    print("      Quand tu es en forme, il y a plus de smurfs ALLIÉS détectés.")
                    print("      Ceci BAISSE team_diff (allié sous-coté → diff négative fausse).")
                    print("      Le signal loser queue serait AMPLIFIÉ après correction.")

    # Régression multiple : team_diff ~ recent_wr_10 + smurf_diff (non corrigé)
    print(f"\n{'─'*48}")
    print("  Régression multiple : team_diff ~ recent_wr_10 + smurf_diff")
    print(f"{'─'*48}")
    print("  (Si β_recent_wr_10 reste négatif et significatif → signal loser")
    print("   queue robuste aux smurfs. β_smurf_diff > 0 attendu.)\n")

    for label, use_adj in [("Non corrigé (team_diff brut)", False),
                            ("Corrigé    (team_diff ajusté)", True)]:
        res = regression_with_smurf_control(rows, use_adjusted_td=use_adj)
        if res is None:
            print(f"  [{label}] : pas assez de données smurf (smurf_diff = None partout ?).")
            print("  Vérifier que collect.py produit bien n_smurf_allies / n_smurf_enemies.")
            continue

        print(f"  [{label}]")
        print(f"  n = {res['n']}   R² = {res['r2']:.3f}   R²adj = {res['r2_adj']:.3f}")
        print(f"  {'Variable':<18} {'Coef':>9} {'SE':>8} {'t':>7} {'p(bilatéral)':>14}")
        print(f"  {'─'*18} {'─'*9} {'─'*8} {'─'*7} {'─'*14}")
        for (vname, coef, se, t_stat, p_val) in res["coefs"]:
            stars = ""
            if p_val < 0.001: stars = "***"
            elif p_val < 0.01:  stars = "**"
            elif p_val < 0.05:  stars = "*"
            elif p_val < 0.10:  stars = "."
            print(f"  {vname:<18} {coef:>9.2f} {se:>8.2f} {t_stat:>7.2f} {p_val:>14.4f} {stars}")

        # Interprétation ciblée
        coef_wr  = next((c for c in res["coefs"] if c[0] == "recent_wr_10"), None)
        coef_sd  = next((c for c in res["coefs"] if c[0] == "smurf_diff"),   None)
        if coef_wr:
            _, b, _, t_wr, p_wr = coef_wr
            p_uni = p_wr / 2.0 if t_wr < 0 else 1.0 - p_wr / 2.0
            print(f"\n  recent_wr_10 : pente = {b:+.2f}   p unilatéral (H1: β<0) ≈ {p_uni:.4f}")
            if b < 0 and p_uni < 0.05:
                print("  => SIGNAL LOSER QUEUE ROBUSTE après contrôle smurf (p<0.05 unilatéral).")
            elif b < 0 and p_uni < 0.10:
                print("  => Tendance négative après contrôle smurf (p<0.10). Signal faible.")
            else:
                print("  => Pas de signal loser queue après contrôle smurf.")
        if coef_sd:
            _, b_sd, _, _, p_sd2 = coef_sd
            print(f"  smurf_diff   : pente = {b_sd:+.2f}   (attendu > 0 si smurfs biaisent team_diff)")
            if b_sd > 0:
                print("  => Confirmé : plus de smurfs ennemis → team_diff artificiellement positif.")
            else:
                print("  => Inattendu : plus de smurfs ennemis → team_diff négatif ?")
                print("     Possible si is_smurf() est trop conservateur (faux négatifs).")
        print()

    # Conclusion smurf
    print(f"  CONCLUSION SMURF")
    print(f"  ─────────────────────────────────────────────────────────")
    print(f"  1. Biais smurf absolue (~{SMURF_RANK_GAP} pts/smurf sur équipe de 4-5) :")
    print(f"     chaque smurf non détecté dévie team_diff de {SMURF_RANK_GAP//4}–{SMURF_RANK_GAP//4+40} pts")
    print(f"     (pour une équipe de 4-5 joueurs). Avec un taux de faux négatifs")
    print(f"     estimé à ~60 %, la plupart des smurfs ne sont pas capturés.")
    print(f"  2. Conditions d'invalidation de nos conclusions :")
    print(f"     Le biais invalide le test seulement si smurf_diff est CORRÉLÉ")
    print(f"     à recent_wr_10. Sinon, c'est un bruit qui réduit la puissance")
    print(f"     statistique mais ne crée ni ne masque de faux signal loser queue.")
    print(f"  3. Après contrôle de smurf_diff, si le signal loser queue disparaît,")
    print(f"     il était vraisemblablement artefactuel. S'il persiste, il est robuste.")

    # ── 3e. CHALLENGE MODE SMURF — intercept + carry-stratification ──────────
    print(f"\n{'─'*64}")
    print("3e. CHALLENGE MODE SMURF — intercept + carry-stratification")
    print(f"{'─'*64}")
    print("  Si un challenge mode cible les smurfs, team_diff est négatif en")
    print("  PERMANENCE (constante additive), indépendamment de la forme.")
    print("  Notre test pente (section 3) est aveugle à ce signal.")
    print()

    # ── Test de l'intercept (team_diff moyen) ─────────────────────────────────
    ic = test_intercept(rows)
    if ic:
        p_ic = t_to_p_approx(ic["t"], ic["n"] - 1)
        print(f"  Intercept — team_diff moyen : {ic['mean']:+.1f} pts  "
              f"(SE={ic['se']:.1f}, t={ic['t']:+.3f}, p≈{p_ic:.3f})")
        if ic["mean"] < -50 and p_ic < 0.05:
            print("  ⚠ INTERCEPT NÉGATIF SIGNIFICATIF — biais structurel détecté.")
            print("    Causes possibles : challenge mode smurf OU drift temporel du proxy rang.")
        else:
            print("  ✓ Intercept non significatif (|mean| < 50 ou p ≥ 0.05).")

    # ── Stratification carry_1v9 vs team-dependent ────────────────────────────
    print()
    print("  Stratification carry_1v9 (seuil my_carry_score ≥ 0.65) :")
    carry_rows   = [r for r in rows if carry_1v9(r) == 1]
    teamdep_rows = [r for r in rows if carry_1v9(r) == 0]
    print(f"    Champions 1v9      : {len(carry_rows)} games")
    print(f"    Champions team-dep : {len(teamdep_rows)} games")

    for label, subset in [("1v9", carry_rows), ("team-dep", teamdep_rows)]:
        pairs_c = [(r["recent_wr_10"], r["team_diff"]) for r in subset
                   if r.get("recent_wr_10") is not None and r.get("team_diff") is not None]
        if len(pairs_c) < 10:
            print(f"    [{label}] trop peu de données ({len(pairs_c)} games)")
            continue
        xs_c = [p[0] for p in pairs_c]
        ys_c = [p[1] for p in pairs_c]
        reg_c = linregress(xs_c, ys_c)
        ic_c  = test_intercept(subset)
        if reg_c and ic_c:
            p_c = t_to_p_approx(reg_c["t"], reg_c["n"] - 2)
            print(f"    [{label:8s}]  n={reg_c['n']:3d}  "
                  f"pente={reg_c['slope']:+.1f} (p≈{p_c:.3f})  "
                  f"intercept={ic_c['mean']:+.1f}")

    # ── Régression challenge mode : smurf_proxy × carry_1v9 ───────────────────
    print()
    print("  Régression H1 challenge mode :")
    print("    team_diff ~ intercept + smurf_proxy + carry_1v9 + smurf×carry")
    print("    H1 décisive : β(smurf×carry) < 0 significatif")
    print("    Seuils pré-enregistrés : smurf_score ≥ 0.40, carry_score ≥ 0.65")
    cm_rows, ys_cm = [], []
    for r in rows:
        td = r.get("team_diff")
        cs = r.get("my_carry_score")
        if td is None or cs is None:
            continue
        smurf_b = int(smurf_prob_score(r) >= 0.40)
        carry_b = int(float(cs) >= 0.65)
        cm_rows.append([smurf_b, carry_b, smurf_b * carry_b])
        ys_cm.append(td)

    if len(ys_cm) >= 20:
        cm_result = multilinregress(cm_rows, ys_cm, intercept=True)
        if cm_result:
            labels_cm = ["intercept", "smurf_proxy", "carry_1v9", "smurf×carry"]
            print(f"  N={cm_result['n']}  R²_adj={cm_result['r2_adj']:.4f}")
            for coef_tuple, name in zip(cm_result["coefs"], labels_cm):
                _, coef, se_c, t_val, p_val = coef_tuple
                star = "***" if abs(t_val) > 3.3 else "**" if abs(t_val) > 2.6 \
                       else "*" if abs(t_val) > 1.96 else "  "
                print(f"    {name:<18} β={coef:+8.1f}  SE={se_c:6.1f}  "
                      f"t={t_val:+6.2f}  p≈{p_val:.3f}  {star}")
            _, b4, _, t4, _ = cm_result["coefs"][3]
            if t4 < -1.96:
                print("  ⚠ H1 confirmée : smurf×carry_1v9 < 0 significatif")
            else:
                print("  ✓ H0 non rejetée : pas de signature challenge mode")
    else:
        print("  (données insuffisantes pour le test challenge mode)")

    # ── 4. DÉTECTION D'ÉPISODES SUSPECTS ────────────────────────────────────
    print(f"\n{'─'*64}")
    print("4. DÉTECTION D'ÉPISODES — fenêtres de loser queue locales")
    print(f"{'─'*64}")
    print("  Seuils : z_team_diff < -1.5  (équipe anormalement faible)")
    print("           z_handicap  >  1.2  (joueur nettement au-dessus de ses alliés)")
    print("  Épisode = ≥ 3 games suspectes consécutives (≥ 1 signal déclenché)\n")

    rows, episodes, (td_mean, td_std), (hc_mean, hc_std) = detect_episodes(rows)

    # Résumé par game (ligne de timeline)
    has_lanes = any(r.get("lane_diff_TOP") is not None for r in rows)
    if has_lanes:
        print(f"  {'#':>4}  {'Résultat':<9} {'Champion':<14} {'carry':>5} {'team_diff':>9} {'z_team':>7} {'z_indiv':>7} {'lanes⚠':>7}  signal")
        print(f"  {'─'*4}  {'─'*9} {'─'*14} {'─'*5} {'─'*9} {'─'*7} {'─'*7} {'─'*7}  {'─'*6}")
    else:
        print(f"  {'#':>4}  {'Résultat':<9} {'Champion':<14} {'carry':>5} {'team_diff':>9} {'z_team':>7} {'z_indiv':>7}  signal")
        print(f"  {'─'*4}  {'─'*9} {'─'*14} {'─'*5} {'─'*9} {'─'*7} {'─'*7}  {'─'*6}")
    for r in rows:
        idx    = int(r["game_index"]) + 1
        win_s  = "VICTOIRE" if int(r["win"]) else "DÉFAITE "
        champ  = str(r.get("my_champ") or "?")[:14]
        cs     = r.get("my_carry_score")
        cs_s   = f"{cs:.2f}" if cs is not None else "  ?"
        td_s   = f"{r['team_diff']:+.0f}" if r.get("team_diff") is not None else "  n/a"
        zt_s   = f"{r['z_team']:+.2f}"    if r.get("z_team")   is not None else "  n/a"
        zi_s   = f"{r['z_indiv']:+.2f}"   if r.get("z_indiv")  is not None else "  n/a"
        sus    = r.get("suspicion", 0)
        flag_s = ("!!!" if sus >= 3 else "!!" if sus == 2 else "! " if sus == 1 else "  ")
        if has_lanes:
            wl = ",".join(r.get("weak_lanes", [])) or "-"
            print(f"  {idx:>4}  {win_s:<9} {champ:<14} {cs_s:>5} {td_s:>9} {zt_s:>7} {zi_s:>7} {wl:>7}  {flag_s}")
        else:
            print(f"  {idx:>4}  {win_s:<9} {champ:<14} {cs_s:>5} {td_s:>9} {zt_s:>7} {zi_s:>7}  {flag_s}")

    # Épisodes détectés
    print()
    if not episodes:
        print("  → Aucun épisode suspect détecté sur l'ensemble des games.")
    else:
        print(f"  → {len(episodes)} épisode(s) détecté(s) :\n")
        for i, ep in enumerate(episodes, 1):
            g_start   = int(ep[0]["game_index"]) + 1
            g_end     = int(ep[-1]["game_index"]) + 1
            n_ep      = len(ep)
            n_wins    = sum(int(r["win"]) for r in ep)
            wr_ep     = n_wins / n_ep
            td_vals_ep = [r["team_diff"] for r in ep if r.get("team_diff") is not None]
            avg_td    = sum(td_vals_ep) / len(td_vals_ep) if td_vals_ep else None
            max_sus   = sum(1 for r in ep if r.get("suspicion", 0) >= 2)
            all_weak  = []
            for r in ep:
                all_weak.extend(r.get("weak_lanes", []))
            lane_counts = {l: all_weak.count(l) for l in set(all_weak)}
            top_lanes   = sorted(lane_counts, key=lambda l: -lane_counts[l])

            print(f"  ┌─ Épisode {i}  (games {g_start}→{g_end}, {n_ep} games)")
            if avg_td is not None:
                print(f"  │  team_diff moyen    : {avg_td:+.1f} pts  "
                      f"(référence : {td_mean:+.1f} ± {td_std:.1f})")
            print(f"  │  Win-rate épisode   : {wr_ep*100:.0f}%  ({n_wins}V / {n_ep-n_wins}D)")
            print(f"  │  ≥2 signaux cumulés : {max_sus}/{n_ep} games")
            if top_lanes:
                lanes_str = "  ".join(f"{l}×{lane_counts[l]}" for l in top_lanes)
                print(f"  │  Lanes suspectes    : {lanes_str}")
            # Smurf stats sur l'épisode
            smurf_diff_vals = [r.get("smurf_diff", 0) or 0 for r in ep]
            avg_smurf_diff  = sum(smurf_diff_vals) / len(smurf_diff_vals)
            smurf_games     = sum(1 for v in smurf_diff_vals if v > 0)
            if any(r.get("smurf_diff") is not None for r in ep):
                print(f"  │  Smurfs ennemis>alliés : {smurf_games}/{n_ep} games  "
                      f"(diff moy = {avg_smurf_diff:+.1f})")
            level = "⚠⚠ Forte suspicion" if max_sus >= 2 else "⚠ Suspicion modérée" if max_sus >= 1 else "Faible"
            print(f"  └─ {level}")
            print()

    # ── 5. RÉSUMÉ HONNÊTE ───────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("CE QUE CETTE ANALYSE PEUT ET NE PEUT PAS DIRE")
    print(f"{'─'*64}")
    print("  PEUT : dire si, au niveau du rang public, tes équipes sont biaisées")
    print("         en fonction de ta forme (test 3). C'est le seul test qui")
    print("         sépare réellement les deux hypothèses.")
    print("  NE PEUT PAS : accéder au MMR réel interne, ni prouver une absence")
    print("         totale de manipulation. team_diff est un proxy.")
    print("  PIÈGE évité : on n'a PAS utilisé 'je perds après avoir gagné' comme")
    print("         preuve — les deux modèles le prédisent, ça ne tranche rien.")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
