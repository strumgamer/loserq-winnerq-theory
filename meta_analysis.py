#!/usr/bin/env python3
"""
meta_analysis.py — Méta-analyse loser queue sur plusieurs joueurs.

Intègre les quatre corrections issues de l'analyse PhD :
  1. Newey-West SE  — corrige l'autocorrélation de la fenêtre glissante (×~3 sur SE)
  2. Within-centering — nécessaire pour pooler des joueurs de paliers hétérogènes
  3. Test du signe  — conclusion utilisable même sans sig. individuelle
  4. DerSimonian-Laird — hétérogénéité entre joueurs

Usage :
  python3 meta_analysis.py batch_out/joueur1.csv batch_out/joueur2.csv ...
  python3 meta_analysis.py batch_out/*.csv
"""

import csv
import sys
import os
import math
from math import sqrt, comb


# ─────────────────────────────────────────────────────────────────────────────
# RÉGRESSION OLS + NEWEY-WEST HAC
# ─────────────────────────────────────────────────────────────────────────────

def _erf(x):
    sign = 1 if x >= 0 else -1
    x = abs(x)
    a1, a2, a3, a4, a5, p = (0.254829592, -0.284496736, 1.421413741,
                              -1.453152027,  1.061405429, 0.3275911)
    t = 1 / (1 + p * x)
    y = 1 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t * math.exp(-x*x)
    return sign * y


def p_one_sided(t_stat):
    """p-value unilatérale H1 : β < 0."""
    z = abs(t_stat)
    phi = 0.5 * (1 + _erf(z / sqrt(2)))
    return 1 - phi if t_stat < 0 else phi


def linregress_nw(xs, ys, max_lag=10):
    """OLS + Newey-West HAC (Bartlett kernel, max_lag=10 pour fenêtre de 10)."""
    n = len(xs)
    if n < max_lag + 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx)**2 for x in xs)
    sxy = sum((x - mx)*(y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    slope     = sxy / sxx
    intercept = my - slope * mx
    resid     = [y - (slope*x + intercept) for x, y in zip(xs, ys)]

    # Scores de moment
    scores = [(xs[t] - mx) * resid[t] for t in range(n)]

    # Long-run variance (Bartlett kernel)
    S  = sum(s**2 for s in scores) / n
    S0 = S
    for lag in range(1, max_lag + 1):
        w     = 1.0 - lag / (max_lag + 1)
        gamma = sum(scores[t] * scores[t - lag] for t in range(lag, n)) / n
        S    += 2.0 * w * gamma

    # Plancher conservateur SE_NW ≥ SE_OLS (pathologie fini-échantillon à N≈100)
    se_ols    = sqrt((sum(e**2 for e in resid) / (n-2)) / sxx) if n > 2 else float("inf")
    se_nw_raw = sqrt(max(S, 0.0) / (sxx / n)) / sqrt(n) if sxx else float("inf")
    se_nw     = max(se_nw_raw, se_ols)
    t_nw      = slope / se_nw if se_nw > 0 else 0.0
    n_eff     = int(n * S0 / max(S, S0)) if S > 0 else n

    syy = sum((y - my)**2 for y in ys)
    r   = sxy / sqrt(sxx * syy) if sxx and syy else 0.0

    return {
        "slope": slope, "intercept": intercept,
        "se_ols": se_ols, "se_nw": se_nw, "t_nw": t_nw,
        "r": r, "n": n, "n_eff": n_eff,
        "p_uni": p_one_sided(t_nw),
    }


def linregress_nw_panel(xs, ys, groups, max_lag=10):
    """OLS avec SE Newey-West clustered par groupe (panel HAC).
    Les gammas de lag k sont calculés uniquement entre observations
    du même groupe — corrige le biais de concaténation inter-joueurs.
    """
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx < 1e-12:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    scores = [(xs[t] - mx) * resid[t] for t in range(n)]

    # Gamma_0
    gamma0 = sum(s * s for s in scores) / n

    # Gammas de lag k : uniquement intra-groupe
    gammas = [gamma0]
    for lag in range(1, max_lag + 1):
        gk = sum(
            scores[t] * scores[t - lag]
            for t in range(lag, n)
            if groups[t] == groups[t - lag]
        ) / n
        gammas.append(gk)

    # Bartlett kernel
    S = gammas[0]
    for lag in range(1, max_lag + 1):
        w = 1.0 - lag / (max_lag + 1)
        S += 2.0 * w * gammas[lag]

    se_nw_raw = (S / (sxx / n) ** 2 / n) ** 0.5
    se_ols = (sum(r * r for r in resid) / (n - 2) / sxx) ** 0.5
    se_nw = max(se_nw_raw, se_ols)
    t_nw = slope / se_nw if se_nw > 0 else 0.0
    syy = sum((y - my) ** 2 for y in ys)
    r_val = sxy / (sxx * syy) ** 0.5 if sxx > 0 and syy > 0 else 0.0
    return {
        "slope": slope, "intercept": intercept,
        "r": r_val, "se": se_ols, "se_nw": se_nw,
        "t_nw": t_nw, "n": n,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MÉTA-ANALYSE
# ─────────────────────────────────────────────────────────────────────────────

def meta_fixed_effects(betas, ses):
    """Fixed-effects (inverse variance)."""
    w  = [1/s**2 for s in ses]
    W  = sum(w)
    bf = sum(wi*bi for wi, bi in zip(w, betas)) / W
    sf = 1 / sqrt(W)
    return bf, sf, bf / sf


def meta_dersimonian_laird(betas, ses):
    """Random-effects DerSimonian-Laird."""
    k  = len(betas)
    w  = [1/s**2 for s in ses]
    W  = sum(w)
    bf = sum(wi*bi for wi, bi in zip(w, betas)) / W
    Q  = sum(wi*(bi - bf)**2 for wi, bi in zip(w, betas))
    C  = W - sum(wi**2 for wi in w) / W
    t2 = max(0.0, (Q - (k - 1)) / C)
    wr = [1 / (s**2 + t2) for s in ses]
    Wr = sum(wr)
    br = sum(wi*bi for wi, bi in zip(wr, betas)) / Wr
    sr = 1 / sqrt(Wr)
    I2 = max(0.0, (Q - (k - 1)) / Q) if Q > 0 else 0.0
    return br, sr, br / sr, t2, Q, I2


def sign_test(betas):
    """Test binomial unilatéral : H0 P(β<0)=0.5 vs H1 P(β<0)>0.5."""
    k     = len(betas)
    n_neg = sum(1 for b in betas if b < 0)
    p     = sum(comb(k, i) * (0.5**k) for i in range(n_neg, k + 1))
    return n_neg, k, p


# ─────────────────────────────────────────────────────────────────────────────
# WILD CLUSTER BOOTSTRAP-t (Cameron-Gelbach-Miller)
# ─────────────────────────────────────────────────────────────────────────────

def wild_cluster_bootstrap_t(xs_w, ys_w, gs_w, beta_obs, se_obs,
                              n_boot=9999, seed=2026, max_lag=10):
    """
    Wild cluster bootstrap-t (Cameron-Gelbach-Miller).
    Bootstrap restreint sous H0 (pente=0) avec statistique-t.

    Paramètres
    ----------
    xs_w, ys_w, gs_w : données demeaned within-player
    beta_obs : slope observée (FE poolé)
    se_obs   : SE clustered-HAC observé (de linregress_nw_panel)
    n_boot   : nombre d'itérations
    seed     : seed Rademacher

    Retourne
    --------
    dict avec p_boot (one-tailed H1: pente < 0), n_boot, n_clusters
    """
    import random as _rng

    n = len(xs_w)
    clusters = sorted(set(gs_w))
    n_clusters = len(clusters)

    if n_clusters < 10:
        print(f"  ⚠ Bootstrap peu fiable : {n_clusters} clusters "
              f"(2^{n_clusters} = {2**n_clusters} configurations seulement)")

    # t observée
    t_obs = beta_obs / se_obs if se_obs > 0 else 0.0

    # Résidus restreints sous H0 (pente = 0)
    # H0 : y_demeaned ~ mean(y_demeaned) + epsilon
    mean_y = sum(ys_w) / n
    e_r = [y - mean_y for y in ys_w]  # résidus restreints

    # Précalcul : x demeaned (x est fixe entre itérations)
    mean_x = sum(xs_w) / n
    x_dm = [x - mean_x for x in xs_w]
    sxx = sum(xi * xi for xi in x_dm)
    if sxx < 1e-12:
        return {"p_boot": None, "n_boot": n_boot, "n_clusters": n_clusters}

    # Map cluster → indices
    cluster_idx = {c: [] for c in clusters}
    for i, g in enumerate(gs_w):
        cluster_idx[g].append(i)

    rng = _rng.Random(seed)
    t_boots = []

    for _ in range(n_boot):
        # Tirer v_i ∈ {-1, +1} par cluster (Rademacher)
        signs = {c: (1 if rng.random() > 0.5 else -1) for c in clusters}

        # Construire y_b = mean_y + e_r * signe du cluster
        y_b = [mean_y + e_r[i] * signs[gs_w[i]] for i in range(n)]

        # slope_b via formule fermée O(n) (x fixe, seul y change)
        mean_yb = sum(y_b) / n
        slope_b = sum(x_dm[i] * (y_b[i] - mean_yb) for i in range(n)) / sxx

        # ⚠ se_b doit être clustered-HAC (même estimateur que se_obs)
        reg_b = linregress_nw_panel(xs_w, y_b, gs_w, max_lag=max_lag)
        if reg_b is None or reg_b["se_nw"] <= 0:
            continue
        se_b = reg_b["se_nw"]

        t_b = slope_b / se_b
        t_boots.append(t_b)

    if not t_boots:
        return {"p_boot": None, "n_boot": 0, "n_clusters": n_clusters}

    # p-value one-tailed H1: pente < 0
    p_boot = sum(1 for t in t_boots if t <= t_obs) / len(t_boots)

    return {
        "p_boot": round(p_boot, 4),
        "n_boot": len(t_boots),
        "n_clusters": n_clusters,
        "t_obs": round(t_obs, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# WITHIN-CENTERING (pooling inter-joueurs valide)
# ─────────────────────────────────────────────────────────────────────────────

def within_center(data_by_player):
    """
    Centrage intra-joueur avant pooling.

    Élimine les effets fixes (niveau MMR, palier) pour ne retenir
    que la variation INTRA-joueur : quand CE joueur est plus en forme
    que son habituel, ses équipes sont-elles plus faibles que d'habitude ?

    Retourne un triplet (xs, ys, group_ids) où group_ids est une liste
    parallèle identifiant le joueur de chaque observation — nécessaire
    pour l'estimateur clustered-HAC (panel NW).
    """
    xs_out = []
    ys_out = []
    group_ids = []
    for pid, pairs in data_by_player.items():
        if len(pairs) < 15:
            continue
        mx = sum(p[0] for p in pairs) / len(pairs)
        my = sum(p[1] for p in pairs) / len(pairs)
        for x, y in pairs:
            xs_out.append(x - mx)
            ys_out.append(y - my)
            group_ids.append(pid)
    return xs_out, ys_out, group_ids


# ─────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DES DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

def load_player(path):
    """Renvoie la liste de (recent_wr_10, team_diff) pour un CSV joueur."""
    pairs = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            wr = r.get("recent_wr_10", "")
            td = r.get("team_diff", "")
            if wr not in ("", "None") and td not in ("", "None"):
                try:
                    pairs.append((float(wr), float(td)))
                except ValueError:
                    pass
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    files = sys.argv[1:]
    if not files:
        print("Usage : python3 meta_analysis.py fichier1.csv fichier2.csv ...")
        sys.exit(1)

    SEP = "─" * 68
    print(f"\n{SEP}")
    print("MÉTA-ANALYSE LOSER QUEUE — plusieurs joueurs")
    print(f"{SEP}")
    print("(SE Newey-West, lag=10 — corrige l'autocorrélation fenêtre glissante)")
    print()

    results       = []
    data_by_player = {}

    for fpath in files:
        pairs = load_player(fpath)
        pid   = os.path.splitext(os.path.basename(fpath))[0]
        data_by_player[pid] = pairs

        if len(pairs) < 20:
            print(f"  [{pid}]  {len(pairs)} games — insuffisant, ignoré")
            continue

        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        reg = linregress_nw(xs, ys, max_lag=10)
        if reg is None:
            continue

        sig = "⚠" if reg["p_uni"] < 0.05 else " "
        print(f"  {sig} [{pid}]")
        print(f"      n={reg['n']}  n_eff≈{reg['n_eff']}  "
              f"slope={reg['slope']:+.1f}  SE_NW={reg['se_nw']:.1f}  "
              f"t={reg['t_nw']:+.2f}  p_uni={reg['p_uni']:.4f}  r={reg['r']:+.3f}")
        results.append((pid, reg))

    if len(results) < 2:
        print("\nPas assez de joueurs pour une méta-analyse (minimum 2).")
        return

    betas = [r[1]["slope"]  for r in results]
    ses   = [r[1]["se_nw"]  for r in results]

    # ══ ESTIMATEUR PRINCIPAL (pre-registered) ═══════════════════════════════
    print(f"\n{SEP}")
    print("ESTIMATEUR PRINCIPAL : FE OLS WITHIN-PLAYER (centrage intra-joueur)")
    print("(élimine les effets fixes MMR inter-joueurs — pre-registered)")
    print(f"{SEP}")
    xs_w, ys_w, gs_w = within_center(data_by_player)
    reg_w = None
    if len(xs_w) >= 30:
        reg_w = linregress_nw_panel(xs_w, ys_w, gs_w, max_lag=10)
        if reg_w:
            pw = p_one_sided(reg_w["t_nw"])
            sig = "⚠  H0 REJETÉE" if (pw < 0.05 and reg_w["slope"] < 0) else "✓  H0 conservée"
            print(f"  {sig}")
            print(f"  n_total={reg_w['n']}  "
                  f"slope={reg_w['slope']:+.1f}  SE_NW={reg_w['se_nw']:.1f}  "
                  f"t={reg_w['t_nw']:+.2f}  p_uni={pw:.4f}")
            print(f"  [SE calculées avec clustered-HAC panel NW — gammas intra-joueur uniquement]")
    else:
        print(f"  Données insuffisantes pour within-centering ({len(xs_w)} paires).")

    # ── Wild cluster bootstrap (robustness check) ─────────────────────────
    if reg_w is not None and xs_w:
        import time as _time
        t0 = _time.time()
        boot = wild_cluster_bootstrap_t(
            xs_w, ys_w, gs_w,
            beta_obs=reg_w["slope"],
            se_obs=reg_w["se_nw"],
            n_boot=9999,
            seed=2026,
        )
        elapsed = _time.time() - t0
        if boot["p_boot"] is not None:
            print(f"\n  [Bootstrap CGM — robustness check]")
            print(f"  n_boot={boot['n_boot']}, n_clusters={boot['n_clusters']}, "
                  f"t_obs={boot['t_obs']:.4f}")
            print(f"  p_bootstrap (one-tailed) = {boot['p_boot']:.4f}  "
                  f"[temps: {elapsed:.1f}s]")
            if elapsed > 120:
                print(f"  ⚠ Lent ({elapsed:.0f}s) — réduire n_boot à 1999 si nécessaire "
                      f"(pré-enregistrer la valeur choisie)")
        else:
            print("  [Bootstrap CGM : échec de calcul]")

    # ══ TESTS DE ROBUSTESSE (secondaires) ════════════════════════════════════
    print(f"\n{SEP}")
    print("ROBUSTESSE (tests secondaires — non décisionnels)")
    print(f"{SEP}")

    # ── Fixed-effects ────────────────────────────────────────────────────────
    bf, sf, zf = meta_fixed_effects(betas, ses)
    pf = p_one_sided(zf)
    print(f"\nFixed-effects   : β={bf:+.1f}  SE={sf:.1f}  z={zf:+.2f}  p_uni={pf:.4f}")

    # ── Random-effects DL ────────────────────────────────────────────────────
    br, sr, zr, t2, Q, I2 = meta_dersimonian_laird(betas, ses)
    pr = p_one_sided(zr)
    print(f"Random-effects  : β={br:+.1f}  SE={sr:.1f}  z={zr:+.2f}  p_uni={pr:.4f}")
    print(f"Hétérogénéité   : Q={Q:.1f}  I²={I2*100:.0f}%  τ²={t2:.1f}")

    # ── Test du signe ────────────────────────────────────────────────────────
    n_neg, k, p_sign = sign_test(betas)
    print(f"Test du signe   : {n_neg}/{k} pentes négatives  p_binom={p_sign:.4f}")

    # ── Conclusion ────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("CONCLUSION")
    print(f"{SEP}")
    # Décision basée UNIQUEMENT sur l'estimateur within (pre-registered)
    if len(xs_w) >= 30 and reg_w:
        pw_final = p_one_sided(reg_w["t_nw"])
        if pw_final < 0.05 and reg_w["slope"] < 0:
            print("⚠  Signal loser queue détecté (within-player β<0, p<0.05).")
            if p_sign < 0.05:
                print("   ✓ Sign test confirme (robustesse).")
            else:
                print(f"   ~ Sign test non-sig. ({n_neg}/{k} négatifs) — limite à noter.")
        else:
            print("✓  Pas de signal loser queue (within-player p≥0.05 ou β≥0).")
            print("   (Rappel : puissance ~95% pour r=0.10 avec n_total≥3000.)")
    else:
        print("  Données insuffisantes pour conclure.")

    print(f"\n   Puissance FE OLS (nw_factor=1.0, α=0.05 uni) :")
    print(f"     n_total=700  r=0.10 → ≈ 55%  |  r=0.15 → ≈ 86%")
    print(f"     n_total=3000 r=0.10 → ≈ 99%  |  r=0.15 → ≈ 100%")


if __name__ == "__main__":
    main()
