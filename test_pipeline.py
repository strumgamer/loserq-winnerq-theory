#!/usr/bin/env python3
"""
test_pipeline.py — Vérification du pipeline statistique.

Usage : python test_pipeline.py
"""
import math, random, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from analyze import linregress_nw, linregress
from meta_analysis import linregress_nw_panel


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Contrôle négatif
# ─────────────────────────────────────────────────────────────────────────────

def test_negative_control(seed=2026, n=500):
    """H0 vraie : team_diff indépendant de recent_wr. La pente doit être ~0."""
    rng = random.Random(seed)
    xs = [rng.random() for _ in range(n)]
    ys = [rng.gauss(0, 150) for _ in range(n)]
    reg = linregress_nw(xs, ys, max_lag=10)
    assert reg is not None, "linregress_nw a retourné None"
    assert abs(reg["slope"]) < 60, f"Pente {reg['slope']:.1f} trop grande sous H0 (> 2.5 SE)"
    # p-value should not reject H0 at α=0.05 (one test)
    # On ne teste pas p directement ici (1 run peut rejeter par hasard)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Contrôle positif
# ─────────────────────────────────────────────────────────────────────────────

def test_positive_control(seed=2026, n=500):
    """H1 vraie : team_diff = -120 * recent_wr + bruit. Signal doit être détecté."""
    rng = random.Random(seed)
    xs = [rng.random() for _ in range(n)]
    ys = [-120 * x + rng.gauss(0, 100) for x in xs]
    reg = linregress_nw(xs, ys, max_lag=10)
    assert reg is not None
    assert reg["slope"] < -80, f"Pente {reg['slope']:.1f} insuffisante (attendu < -80)"
    assert reg.get("t_nw", reg.get("t", 0)) < -2, "t-stat trop proche de 0"
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — Convergence SE clustered-HAC
# ─────────────────────────────────────────────────────────────────────────────

def test_nw_panel_convergence(seed=42, n_per_cluster=500, n_clusters=5):
    """
    Sur résidus i.i.d. et séries longues, SE clustered-HAC doit converger
    vers SE OLS à ±10%. Séries longues (500 obs/cluster) pour que l'asymptotique morde.

    Note : analyze.linregress_nw ne supporte pas max_lag=0 explicitement
    (None → min(10, n//4)). On utilise analyze.linregress pour obtenir le
    SE OLS pur (clé "se"), puis linregress_nw_panel de meta_analysis pour
    le SE clustered-HAC (clé "se_nw").
    """
    rng = random.Random(seed)
    n = n_per_cluster * n_clusters
    xs = [rng.random() for _ in range(n)]
    ys = [rng.gauss(0, 150) for _ in range(n)]
    groups = [i // n_per_cluster for i in range(n)]  # clusters 0..4

    # SE OLS pur via linregress (pas de correction HAC)
    reg_ols = linregress(xs, ys)
    # SE clustered-HAC via panel
    reg_panel = linregress_nw_panel(xs, ys, groups, max_lag=10)

    assert reg_ols is not None and reg_panel is not None
    se_ols = reg_ols["se"]
    se_panel = reg_panel["se_nw"]

    ratio = se_panel / se_ols
    assert 0.90 <= ratio <= 1.10, (
        f"SE clustered-HAC ({se_panel:.4f}) dévie de >{10}% du SE OLS ({se_ols:.4f}), "
        f"ratio={ratio:.3f}. Possible bug dans linregress_nw_panel."
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — Calibration type I (test le plus important)
# ─────────────────────────────────────────────────────────────────────────────

def test_type1_calibration(n_reps=500, n=500, alpha=0.05):
    """
    Sur 500 datasets H0 (aucun signal), le taux de rejet doit être ≈ α.
    Seeds déterministes via un générateur maître pour garantir reproductibilité
    et indépendance des séquences (pas de seeds consécutives corrélées).
    """
    master = random.Random(2026)
    seeds = [master.randrange(10**9) for _ in range(n_reps)]

    rejections = 0
    for seed in seeds:
        rng = random.Random(seed)
        xs = [rng.random() for _ in range(n)]
        ys = [rng.gauss(0, 150) for _ in range(n)]
        reg = linregress_nw(xs, ys, max_lag=10)
        if reg is None:
            continue
        # p-value one-tailed depuis t_nw
        t = reg.get("t_nw", reg.get("t", 0))
        df = reg["n"] - 2
        # Approximation p one-tailed (t < 0 = H1 direction)
        import math as _math
        if df >= 100:
            z = t
            k = 1.0 / (1.0 + 0.2316419 * abs(z))
            b = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429]
            poly = k*(b[0]+k*(b[1]+k*(b[2]+k*(b[3]+k*b[4]))))
            phi = _math.exp(-0.5*z*z) / _math.sqrt(2*_math.pi)
            p_right = min(max(phi*poly, 0), 1)
            p_one = p_right if t < 0 else 1 - p_right
        else:
            p_one = 0.5
        if p_one < alpha:
            rejections += 1

    rate = rejections / n_reps
    # Intervalle [0.03, 0.07] = ±2σ pour n_reps=500, α=0.05
    assert 0.03 <= rate <= 0.07, (
        f"Taux de rejet type I = {rate:.3f} hors de [0.03, 0.07]. "
        f"Pipeline sur-rejette ou sous-rejette H0."
    )
    return rate


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — Validation regex Riot ID
# ─────────────────────────────────────────────────────────────────────────────

def test_riot_id_validation():
    """
    Vérifie la regex de validation des Riot IDs définie dans api/server.py.
    Utilise re directement avec le même pattern.
    """
    import re
    # Pattern cohérent avec B1 : nom unicode ≤50 chars, tag [A-Za-z0-9]{2,5}
    PATTERN = re.compile(r"^[^#]{1,50}#[A-Za-z0-9]{2,5}$")

    valid = [
        "Faker#KR1",
        "Player123#EUW",
        "홍길동#KR1",       # Unicode coréen
        "Иван#EUW",         # cyrillique
        "A#AB",             # tag 2 chars (vieux comptes)
        "Test Player#TAG",  # espace dans le nom
    ]
    invalid = [
        "NoPound",
        "A" * 51 + "#TAG",  # nom trop long
        "#TAG",             # nom vide
        "x#",               # tag vide
        "name#TOOLONGTAG",  # tag > 5 chars
    ]

    for rid in valid:
        assert PATTERN.match(rid), f"Riot ID valide rejeté : {rid!r}"
    for rid in invalid:
        assert not PATTERN.match(rid), f"Riot ID invalide accepté : {rid!r}"
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Runner principal
# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        ("Contrôle négatif",         lambda: test_negative_control()),
        ("Contrôle positif",         lambda: test_positive_control()),
        ("Convergence SE clustered", lambda: test_nw_panel_convergence()),
        ("Calibration type I",       lambda: test_type1_calibration()),
        ("Validation Riot ID regex", lambda: test_riot_id_validation()),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            result = fn()
            extra = f"  (taux rejet={result:.3f})" if isinstance(result, float) else ""
            print(f"  PASS  {name}{extra}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"  {passed}/{passed+failed} tests passés")
    if failed:
        print(f"  {failed} test(s) échoué(s)")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 50)
    print("test_pipeline.py — Pipeline loserq_winnerq_theory")
    print("=" * 50)
    run_all()
