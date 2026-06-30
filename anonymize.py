"""
anonymize.py — Post-traitement batch_out/ → src/results/data.json

Supprime toutes les données personnellement identifiables (PII) :
  - riot_id  →  remplacé par "{Elo} #N" (ex. "Diamond #1")
  - match_id, game_start  →  supprimés (permettent la cross-référence op.gg)
  - kills/deaths/assists/kda/vision/damage/cs  →  supprimés (fingerprint de style)

Conserve les colonnes analytiques uniquement :
  win, my_champ, my_role, my_carry_score, team_diff, recent_wr_10,
  my_rank_score, n_ally_ranked, n_enemy_ranked, game_index, smurf_diff, smurf_rate

Usage :
  python3 anonymize.py [--batch-dir batch_out] [--out src/results/data.json]
"""

import argparse, csv, json, os, glob, re
from math import sqrt
from datetime import date

CARRY_THRESHOLD = 0.65  # pré-enregistré : seuil carry_1v9 vs team-dependent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

ELO_ORDER = ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master+"]

# Seuils identiques à collect.py TIER_BASE (Iron=0, Bronze=400…)
_ELO_THRESHOLDS = [
    (2800, "Master+"), (2400, "Diamond"), (2000, "Emerald"),
    (1600, "Platinum"), (1200, "Gold"), (800, "Silver"),
    (400, "Bronze"), (0, "Iron"),
]

def score_to_elo(score):
    """Infère le palier depuis un rank_score ou avg_ally_score moyen."""
    if score is None or score <= 0:
        return "Unknown"
    for threshold, label in _ELO_THRESHOLDS:
        if score >= threshold:
            return label
    return "Unknown"

# Colonnes à conserver dans les données par game (tout le reste est supprimé)
KEEP_COLS = {
    "win", "my_champ", "my_role", "my_carry_score",
    "team_diff", "recent_wr_10", "my_rank_score",
    "n_ally_ranked", "n_enemy_ranked", "game_index",
    "smurf_diff", "smurf_rate",
}


def _num(v):
    if v in ("", "None", None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def linear_regression(xs, ys):
    """Régression linéaire simple. Renvoie (slope, intercept, r2) ou (None,None,None)."""
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 10:
        return None, None, None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    ssXY = sum((p[0] - mx) * (p[1] - my) for p in pts)
    ssXX = sum((p[0] - mx) ** 2 for p in pts)
    ssYY = sum((p[1] - my) ** 2 for p in pts)
    if ssXX == 0:
        return 0.0, my, 0.0
    slope = ssXY / ssXX
    intercept = my - slope * mx
    r2 = ssXY ** 2 / (ssXX * ssYY) if ssYY > 0 else 0.0
    return round(slope, 2), round(intercept, 2), round(r2, 4)


def find_episodes(rows, min_run=3):
    """Compte les épisodes suspects (≥ min_run games consécutives suspectes)."""
    td_vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
    if len(td_vals) < 5:
        return 0
    td_m = sum(td_vals) / len(td_vals)
    td_s = sqrt(sum((v - td_m) ** 2 for v in td_vals) / len(td_vals)) or 1
    Z_TEAM = -1.5
    episodes, run = 0, 0
    for r in rows:
        td = r.get("team_diff")
        zt = (td - td_m) / td_s if td is not None else None
        if zt is not None and zt < Z_TEAM:
            run += 1
        else:
            if run >= min_run:
                episodes += 1
            run = 0
    if run >= min_run:
        episodes += 1
    return episodes


def wr_unfav(rows):
    """WR moyen quand team_diff < 0."""
    unfav = [r for r in rows if r.get("team_diff") is not None and r["team_diff"] < 0]
    if not unfav:
        return None
    return round(sum(int(r["win"]) for r in unfav) / len(unfav) * 100, 1)


def slope_by_carry(rows, threshold=CARRY_THRESHOLD):
    """Pentes séparées pour champions 1v9 vs team-dependent."""
    carry_rows   = [r for r in rows
                    if r.get("my_carry_score") is not None
                    and float(r["my_carry_score"]) >= threshold]
    teamdep_rows = [r for r in rows
                    if r.get("my_carry_score") is not None
                    and float(r["my_carry_score"]) < threshold]

    def _slope(subset):
        pts = [(r["recent_wr_10"], r["team_diff"]) for r in subset
               if r.get("recent_wr_10") is not None and r.get("team_diff") is not None]
        if len(pts) < 8:
            return None, len(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        s, _, _ = linear_regression(xs, ys)
        return s, len(pts)

    s1, n1 = _slope(carry_rows)
    s2, n2 = _slope(teamdep_rows)
    return {
        "slope_1v9":     s1,
        "n_1v9":         n1,
        "slope_teamdep": s2,
        "n_teamdep":     n2,
    }


def mean_team_diff(rows):
    """Intercept — team_diff moyen (≠ 0 → biais structurel)."""
    vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def safe_name(riot_id):
    """Même transformation que batch.py pour trouver le fichier CSV."""
    return re.sub(r"[^\w\-.]", "_", riot_id).strip("_")


# ─────────────────────────────────────────────────────────────────────────────
# Chargement
# ─────────────────────────────────────────────────────────────────────────────

def load_comparison(batch_dir):
    """Lit comparison.csv → dict {safe_riot_id: {elo, riot_id, ...}}."""
    path = os.path.join(batch_dir, "comparison.csv")
    if not os.path.exists(path):
        return {}
    mapping = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("error") == "True":
                continue
            rid = row.get("riot_id", "")
            mapping[safe_name(rid)] = row
    return mapping


def load_player_csv(csv_path):
    """Charge un CSV individuel, ne garde que les colonnes analytiques."""
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            clean = {}
            for col in KEEP_COLS:
                clean[col] = _num(r.get(col, ""))
            # win en int, my_champ/my_role en str
            clean["win"]     = int(clean["win"]) if clean["win"] is not None else None
            clean["my_champ"] = r.get("my_champ", "")
            clean["my_role"]  = r.get("my_role", "")
            if clean.get("game_index") is not None and clean.get("win") is not None:
                rows.append(clean)
    rows.sort(key=lambda r: r["game_index"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Construction du JSON
# ─────────────────────────────────────────────────────────────────────────────

def infer_elo_from_csv(csv_path):
    """Fallback : inférence depuis avg_ally_score/my_rank_score bruts du CSV."""
    scores = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for col in ("avg_ally_score", "my_rank_score"):
                v = _num(r.get(col, ""))
                if v is not None and v > 0:
                    scores.append(v)
                    break
    if not scores:
        return "Unknown"
    return score_to_elo(sum(scores) / len(scores))


QUALITY_MIN_RANKED = 4  # n_ally_ranked ≥ 4 AND n_enemy_ranked ≥ 4 (pre-registered)


def quality_rows(rows):
    """Lignes avec couverture rang suffisante pour team_diff fiable."""
    return [r for r in rows
            if r.get("n_ally_ranked")  is not None and r["n_ally_ranked"]  >= QUALITY_MIN_RANKED
            and r.get("n_enemy_ranked") is not None and r["n_enemy_ranked"] >= QUALITY_MIN_RANKED]


def process_player(csv_path, elo_label_hint, anon_id_hint):
    rows = load_player_csv(csv_path)
    elo_label = elo_label_hint
    anon_id   = anon_id_hint

    if len(rows) < 20:
        print(f"  ✗ {anon_id} — seulement {len(rows)} games, ignoré")
        return None

    # Filtre qualité pre-registered : n_ally_ranked ≥ 4 AND n_enemy_ranked ≥ 4
    # NB : appliqué aux régressions uniquement ; recent_wr_10 et wins utilisent toutes les lignes
    q_rows = quality_rows(rows)
    coverage = len(q_rows) / len(rows) if rows else 0
    if coverage < 0.85:
        print(f"  ✗ {anon_id} — couverture rang {coverage:.0%} < 85%, exclu de l'analyse principale")
        return None

    recent_wrs = [r["recent_wr_10"] for r in q_rows]
    team_diffs = [r["team_diff"]    for r in q_rows]
    wins       = [r["win"]          for r in rows]   # WR sur toutes les games

    slope, intercept, r2 = linear_regression(recent_wrs, team_diffs)
    episodes = find_episodes(q_rows)
    wu = wr_unfav(q_rows)
    carry_stats = slope_by_carry(q_rows)
    mtd = mean_team_diff(q_rows)
    n  = len(rows)
    n_quality = len(q_rows)
    wr = round(sum(w for w in wins if w is not None) / n * 100, 1)

    # Scatter : [recent_wr, team_diff, win] — uniquement les games avec les deux valeurs
    scatter = [
        [round(rw, 3), round(td, 1), w]
        for rw, td, w in zip(recent_wrs, team_diffs, wins)
        if rw is not None and td is not None and w is not None
    ]

    print(f"  ✓ {anon_id:<18}  {n:>3} games  ({n_quality} quality)  elo={elo_label}  "
          f"slope={slope if slope is not None else '?'}  épisodes={episodes}")

    return {
        "id":        anon_id,
        "elo":       elo_label,
        "n":         n,
        "wr":        wr,
        "slope":     slope,
        "intercept": intercept,
        "r2":        r2,
        "episodes":  episodes,
        "wr_unfav":      wu,
        "mean_team_diff": mtd,
        "slope_1v9":      carry_stats["slope_1v9"],
        "n_1v9":          carry_stats["n_1v9"],
        "slope_teamdep":  carry_stats["slope_teamdep"],
        "n_teamdep":      carry_stats["n_teamdep"],
        "scatter":        scatter,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Anonymise batch_out/ → src/results/data.json")
    ap.add_argument("--batch-dir", default="batch_out")
    ap.add_argument("--out",       default="src/results/data.json")
    args = ap.parse_args()

    print(f"Lecture de {args.batch_dir}/")
    comparison = load_comparison(args.batch_dir)

    # Fichiers CSV individuels (tous sauf comparison.csv)
    csvs = sorted(glob.glob(os.path.join(args.batch_dir, "*.csv")))
    csvs = [p for p in csvs if os.path.basename(p) != "comparison.csv"]

    # Passe 1 : déterminer l'elo de chaque fichier
    file_elos = {}
    for csv_path in csvs:
        base     = os.path.splitext(os.path.basename(csv_path))[0]
        comp_row = comparison.get(base)
        if comp_row and comp_row.get("elo", "Unknown") != "Unknown":
            file_elos[csv_path] = comp_row["elo"]
        else:
            # Fallback : inférer depuis avg_ally_score / my_rank_score
            try:
                file_elos[csv_path] = infer_elo_from_csv(csv_path)
            except Exception:
                file_elos[csv_path] = "Unknown"

    # Passe 2 : traitement avec numérotation par elo
    elo_counters = {}
    players = []

    for csv_path in csvs:
        elo_label = file_elos[csv_path]
        elo_counters[elo_label] = elo_counters.get(elo_label, 0) + 1
        anon_id = f"{elo_label} #{elo_counters[elo_label]}"

        result = process_player(csv_path, elo_label, anon_id)
        if result:
            players.append(result)

    # Trier par elo
    def elo_rank(p):
        try:
            return ELO_ORDER.index(p["elo"])
        except ValueError:
            return 99

    players.sort(key=elo_rank)

    n_total = sum(p["n"] for p in players)

    output = {
        "generated": str(date.today()),
        "n_total":   n_total,
        "players":   players,
        "elo_order": ELO_ORDER,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✓ {len(players)} joueurs · {n_total} games → {args.out}")
    if players:
        slopes = [p["slope"] for p in players if p["slope"] is not None]
        if slopes:
            mean_s = sum(slopes) / len(slopes)
            print(f"  Pente moyenne : {mean_s:.1f}")
            neg = sum(1 for s in slopes if s < -50)
            print(f"  Pentes < -50  : {neg}/{len(slopes)}")


if __name__ == "__main__":
    main()
