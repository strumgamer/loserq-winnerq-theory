#!/usr/bin/env python3
"""
batch.py — Analyse comparative loser/winner queue sur N joueurs échantillonnés
           automatiquement par palier Elo.

Usage :
    # Auto-sample 10 joueurs répartis sur tous les paliers EUW :
    python3 batch.py --auto --platform euw1 --region europe --count 100

    # Ou fournir une liste de Riot IDs manuellement :
    python3 batch.py --riot-ids "Player1#TAG,Player2#TAG" --platform euw1 --region europe --count 100

    # Changer le nombre de joueurs par palier (défaut 1) :
    python3 batch.py --auto --per-tier 2 --platform euw1 --region europe --count 100

Durée estimée : ~10-20 min par joueur (100 games, clé de dev).
"""

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from math import sqrt
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter partagé pour le sampling (appels légers, on reste conservatif)
# ─────────────────────────────────────────────────────────────────────────────
_calls = []

def _rate_wait():
    global _calls
    now = time.time()
    _calls = [t for t in _calls if now - t < 120]
    if len(_calls) >= 90:
        sleep = 120 - (now - _calls[0]) + 1
        print(f"  [rate] pause {sleep:.0f}s")
        time.sleep(sleep)
    recent = [t for t in _calls if now - t < 1]
    if len(recent) >= 18:
        time.sleep(1)
    _calls.append(time.time())


def api_get(url, api_key, params=None):
    _rate_wait()
    headers = {"X-Riot-Token": api_key}
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=15)
    except requests.RequestException as e:
        print(f"  [réseau] {e}")
        return None
    if r.status_code == 200:
        return r.json()
    if r.status_code == 429:
        wait = int(r.headers.get("Retry-After", "10"))
        print(f"  [429] pause {wait}s")
        time.sleep(wait + 1)
        return api_get(url, api_key, params)
    if r.status_code == 404:
        return None
    print(f"  [erreur {r.status_code}] {url}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Sampling : on tire aléatoirement des joueurs depuis les endpoints league-v4
# ─────────────────────────────────────────────────────────────────────────────

# (tier, division, label affiché)
ELO_BRACKETS = [
    ("IRON",      "IV",  "IRON"),
    ("BRONZE",    "IV",  "BRONZE"),
    ("SILVER",    "IV",  "SILVER"),
    ("GOLD",      "IV",  "GOLD"),
    ("PLATINUM",  "IV",  "PLATINUM"),
    ("EMERALD",   "IV",  "EMERALD"),
    ("DIAMOND",   "IV",  "DIAMOND"),
]


def sample_puuids(api_key, platform, tier, division, n):
    """Tire n puuids au hasard dans un palier/division (API 2024+ : puuid direct)."""
    puuids = []
    for page in random.sample(range(1, 10), min(n * 3, 9)):
        url = (f"https://{platform}.api.riotgames.com"
               f"/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}")
        data = api_get(url, api_key, params={"page": page})
        if data:
            puuids.extend(e["puuid"] for e in data if e.get("puuid"))
        if len(puuids) >= n * 5:
            break
    if not puuids:
        return []
    return random.sample(puuids, min(n, len(puuids)))


def sample_master_puuids(api_key, platform, n):
    """Tire n puuids depuis la Master league."""
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5"
    data = api_get(url, api_key)
    if not data or "entries" not in data:
        return []
    entries = [e for e in data["entries"] if e.get("puuid")]
    return [e["puuid"] for e in random.sample(entries, min(n, len(entries)))]


def puuid_to_riot_id(api_key, mass_region, puuid):
    """puuid → gameName#tagLine (account-v1)."""
    url = f"https://{mass_region}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
    a = api_get(url, api_key)
    if not a:
        return None
    return f"{a['gameName']}#{a['tagLine']}"


def auto_sample(api_key, platform, mass_region, per_tier):
    """Renvoie une liste de (riot_id, elo_label)."""
    players = []
    for tier, division, label in ELO_BRACKETS:
        print(f"  Sampling {per_tier}× {label}…")
        puuids = sample_puuids(api_key, platform, tier, division, per_tier * 3)
        added = 0
        for puuid in puuids:
            if added >= per_tier:
                break
            riot_id = puuid_to_riot_id(api_key, mass_region, puuid)
            if riot_id:
                players.append((riot_id, label, 0))
                print(f"    ✓ {riot_id}")
                added += 1
    # Master (1 joueur)
    print("  Sampling 1× MASTER…")
    puuids = sample_master_puuids(api_key, platform, 5)
    for puuid in puuids:
        riot_id = puuid_to_riot_id(api_key, mass_region, puuid)
        if riot_id:
            players.append((riot_id, "MASTER+", 0))
            print(f"    ✓ {riot_id}")
            break
    return players


# ─────────────────────────────────────────────────────────────────────────────
# Collecte : on appelle collect.py en sous-processus pour chaque joueur
# ─────────────────────────────────────────────────────────────────────────────

def collect_player(riot_id, platform, region, count, out_csv, cache_dir):
    env = os.environ.copy()
    cmd = [
        sys.executable, "collect.py",
        "--riot-id", riot_id,
        "--platform", platform,
        "--region", region,
        "--count", str(count),
        "--out", out_csv,
        "--cache", cache_dir,
    ]
    print(f"\n  → Collecte : {riot_id}  ({count} games)…")
    result = subprocess.run(cmd, env=env, capture_output=False)
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Analyse légère : statistiques clés extraites du CSV sans relancer analyze.py
# ─────────────────────────────────────────────────────────────────────────────

def _mean_std(vals):
    if not vals:
        return None, None
    m = sum(vals) / len(vals)
    v = sum((x - m) ** 2 for x in vals) / len(vals)
    return m, sqrt(v) if v > 0 else 0.0


def quick_stats(csv_path):
    """Renvoie un dict de métriques clés pour un joueur."""
    rows = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                def num(k):
                    v = r.get(k, "")
                    if v in ("", "None", None):
                        return None
                    try:
                        return float(v)
                    except ValueError:
                        return None
                rows.append({k: num(k) for k in r})
    except FileNotFoundError:
        return None

    rows = [r for r in rows if r.get("game_index") is not None]
    rows.sort(key=lambda r: r["game_index"])
    n = len(rows)
    if n == 0:
        return None

    wins = [int(r["win"]) for r in rows]
    wr = sum(wins) / n

    # team_diff stats
    td_vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
    td_mean, td_std = _mean_std(td_vals)

    # Smurf
    smurf_diffs = [r.get("smurf_diff") or 0 for r in rows if r.get("smurf_diff") is not None]
    avg_smurf_diff = sum(smurf_diffs) / len(smurf_diffs) if smurf_diffs else None
    smurf_rates = [r.get("smurf_rate") for r in rows if r.get("smurf_rate") is not None]
    avg_smurf_rate = sum(smurf_rates) / len(smurf_rates) if smurf_rates else None

    # Détection d'épisodes (reprise de la logique de analyze.py)
    hc_vals = []
    for r in rows:
        my = r.get("my_rank_score")
        ally = r.get("avg_ally_score")
        if my is not None and ally is not None:
            r["_hc"] = my - ally
            hc_vals.append(r["_hc"])
        else:
            r["_hc"] = None

    td_m, td_s = _mean_std(td_vals)
    hc_m, hc_s = _mean_std(hc_vals)

    # Paramètres de détection
    Z_TEAM, Z_INDIV, MIN_RUN = -1.5, 1.2, 3

    for r in rows:
        td = r.get("team_diff")
        r["_zt"] = (td - td_m) / td_s if (td is not None and td_s) else None
        hc = r.get("_hc")
        r["_zi"] = (hc - hc_m) / hc_s if (hc is not None and hc_s) else None
        ft = r["_zt"] is not None and r["_zt"] < Z_TEAM
        fi = r["_zi"] is not None and r["_zi"] > Z_INDIV
        r["_sus"] = int(ft) + int(fi)

    episodes, run = 0, []
    for r in rows:
        if r["_sus"] >= 1:
            run.append(r)
        else:
            if len(run) >= MIN_RUN:
                episodes += 1
            run = []
    if len(run) >= MIN_RUN:
        episodes += 1

    # ── Carry score : sensibilité au team_diff par archétype ─────────────────
    CARRY_THRESH = 0.55
    def wr_delta(group):
        """Δ WR entre games avec team_diff ≥ 0 et team_diff < 0."""
        up   = [r for r in group if r.get("team_diff") is not None and r["team_diff"] >= 0]
        down = [r for r in group if r.get("team_diff") is not None and r["team_diff"] <  0]
        if not up or not down:
            return None
        return round(
            (sum(int(r["win"]) for r in up)   / len(up) -
             sum(int(r["win"]) for r in down) / len(down)) * 100, 1
        )

    lo = [r for r in rows if (r.get("my_carry_score") or 0.55) < CARRY_THRESH]
    hi = [r for r in rows if (r.get("my_carry_score") or 0.55) >= CARRY_THRESH]
    carry_delta_lo = wr_delta(lo)  # sensibilité champions dépendants
    carry_delta_hi = wr_delta(hi)  # sensibilité champions autonomes

    return {
        "n": n,
        "wr": round(wr * 100, 1),
        "td_mean": round(td_mean, 1) if td_mean is not None else None,
        "td_std": round(td_std, 1) if td_std is not None else None,
        "episodes": episodes,
        "avg_smurf_diff": round(avg_smurf_diff, 2) if avg_smurf_diff is not None else None,
        "avg_smurf_rate": round(avg_smurf_rate, 3) if avg_smurf_rate is not None else None,
        "carry_delta_lo": carry_delta_lo,   # Δ WR champions dépendants (pp)
        "carry_delta_hi": carry_delta_hi,   # Δ WR champions autonomes  (pp)
        "n_lo_games": len(lo),
        "n_hi_games": len(hi),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto",      action="store_true", help="Auto-sampler des joueurs par elo")
    ap.add_argument("--riot-ids",  default="",  help="Liste de Riot IDs séparés par des virgules")
    ap.add_argument("--per-tier",  type=int, default=1, help="Joueurs par palier (auto uniquement)")
    ap.add_argument("--region",    required=True, help="Région mass : europe|americas|asia|sea")
    ap.add_argument("--platform",  required=True, help="Plateforme : euw1|na1|kr|…")
    ap.add_argument("--count",     type=int, default=100, help="Games par joueur (défaut 100)")
    ap.add_argument("--out-dir",   default="batch_out", help="Dossier de sortie")
    ap.add_argument("--cache",     default="riot_cache", help="Cache partagé")
    args = ap.parse_args()

    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        print("ERREUR : exporte ta clé : export RIOT_API_KEY='RGAPI-xxxx'")
        sys.exit(1)

    Path(args.out_dir).mkdir(exist_ok=True)

    # ── Collecte de la liste des joueurs ─────────────────────────────────────
    players = []  # liste de (riot_id, elo_label)

    if args.auto:
        print("\n=== Sampling automatique par elo ===")
        sampled = auto_sample(api_key, args.platform, args.region, args.per_tier)
        players = [(rid, label) for rid, label, _ in sampled]
    elif args.riot_ids:
        for rid in args.riot_ids.split(","):
            rid = rid.strip()
            if rid:
                players.append((rid, "MANUEL"))
    else:
        print("ERREUR : utilise --auto ou --riot-ids")
        sys.exit(1)

    if not players:
        print("Aucun joueur à analyser.")
        sys.exit(1)

    print(f"\n{len(players)} joueurs à analyser ({args.count} games chacun)")

    # ── Collecte des games ───────────────────────────────────────────────────
    results = []
    for i, (riot_id, elo_label) in enumerate(players, 1):
        safe_name = riot_id.replace("#", "_").replace(" ", "_")
        out_csv   = f"{args.out_dir}/{safe_name}.csv"
        cache_dir = f"{args.cache}/{safe_name}"

        print(f"\n[{i}/{len(players)}] {riot_id}  ({elo_label})")
        ok = collect_player(riot_id, args.platform, args.region, args.count, out_csv, cache_dir)
        if not ok:
            print(f"  ✗ Collecte échouée pour {riot_id}")
            results.append({"riot_id": riot_id, "elo": elo_label, "error": True})
            continue

        stats = quick_stats(out_csv)
        if stats is None:
            print(f"  ✗ CSV vide pour {riot_id}")
            results.append({"riot_id": riot_id, "elo": elo_label, "error": True})
            continue

        stats["riot_id"] = riot_id
        stats["elo"]     = elo_label
        stats["error"]   = False
        results.append(stats)
        lo = stats.get("carry_delta_lo")
        hi = stats.get("carry_delta_hi")
        carry_info = f"  ΔWR dép={lo:+.1f}pp / auto={hi:+.1f}pp" if lo is not None and hi is not None else ""
        print(f"  ✓ {stats['n']} games  WR={stats['wr']}%  "
              f"épisodes={stats['episodes']}  smurf_diff={stats['avg_smurf_diff']}{carry_info}")

    # ── Tableau comparatif ───────────────────────────────────────────────────
    ok_results = [r for r in results if not r.get("error")]
    if not ok_results:
        print("\nAucun résultat disponible.")
        return

    print(f"\n\n{'='*100}")
    print("  TABLEAU COMPARATIF PAR ELO")
    print(f"{'='*100}")
    hdr = (f"{'Riot ID':<26} {'Elo':<10} {'N':>5} {'WR':>6} {'Ep':>4} "
           f"{'td_std':>7} {'Smurf↑':>7} "
           f"{'ΔWR dép':>9} {'ΔWR auto':>9}  Interprétation")
    print(hdr)
    print("─" * 100)
    for r in results:
        if r.get("error"):
            print(f"  {r['riot_id']:<24} {r['elo']:<10}  ERREUR")
            continue
        lo = r.get("carry_delta_lo")
        hi = r.get("carry_delta_hi")
        lo_s = f"{lo:+.1f}pp" if lo is not None else "   n/a"
        hi_s = f"{hi:+.1f}pp" if hi is not None else "   n/a"
        if lo is not None and hi is not None:
            diff = lo - hi
            interp = ("dép >> auto (+loser Q dure)" if diff > 10
                      else "dép ≈ auto (neutre)"     if abs(diff) <= 5
                      else "auto >> dép (?)")
        else:
            interp = ""
        print(
            f"  {r['riot_id']:<24} {r['elo']:<10} "
            f"{r['n']:>5} {r['wr']:>5.1f}% {r['episodes']:>3} "
            f"{r['td_std'] or 0:>7.0f} "
            f"{r['avg_smurf_diff'] or 0:>+7.2f} "
            f"{lo_s:>9} {hi_s:>9}  {interp}"
        )

    # ── Agrégation par elo ───────────────────────────────────────────────────
    from collections import defaultdict
    by_elo = defaultdict(list)
    for r in ok_results:
        by_elo[r["elo"]].append(r)

    print(f"\n{'─'*100}")
    print("  MOYENNES PAR PALIER")
    print(f"{'─'*100}")
    print(f"  {'Palier':<12} {'Joueurs':>7} {'Avg WR':>7} {'Ep/j':>6} {'td_std':>7} {'Smurf↑':>7} {'ΔWR dép':>9} {'ΔWR auto':>9}  Note")
    elo_order = [l for _, _, l in ELO_BRACKETS] + ["MASTER+", "MANUEL"]
    for label in elo_order:
        grp = by_elo.get(label, [])
        if not grp:
            continue
        avg_wr  = sum(r["wr"]          for r in grp) / len(grp)
        avg_ep  = sum(r["episodes"]    for r in grp) / len(grp)
        std_td  = sum(r["td_std"] or 0 for r in grp) / len(grp)
        avg_sm  = sum(r["avg_smurf_diff"] or 0 for r in grp) / len(grp)
        lo_vals = [r["carry_delta_lo"] for r in grp if r.get("carry_delta_lo") is not None]
        hi_vals = [r["carry_delta_hi"] for r in grp if r.get("carry_delta_hi") is not None]
        lo_s = f"{sum(lo_vals)/len(lo_vals):+.1f}pp" if lo_vals else "  n/a"
        hi_s = f"{sum(hi_vals)/len(hi_vals):+.1f}pp" if hi_vals else "  n/a"
        note = ""
        if lo_vals and hi_vals:
            avg_lo = sum(lo_vals) / len(lo_vals)
            avg_hi = sum(hi_vals) / len(hi_vals)
            if avg_lo - avg_hi > 10:
                note = "loser Q dure sur champ. dépendants"
            elif abs(avg_lo - avg_hi) <= 5:
                note = "archétypes équivalents"
        print(f"  {label:<12} {len(grp):>7} {avg_wr:>6.1f}% {avg_ep:>6.2f} "
              f"{std_td:>7.0f} {avg_sm:>+7.2f} {lo_s:>9} {hi_s:>9}  {note}")

    # ── Export CSV de synthèse ────────────────────────────────────────────────
    summary_path = f"{args.out_dir}/comparison.csv"
    fields = ["riot_id", "elo", "n", "wr", "episodes", "td_mean", "td_std",
              "avg_smurf_diff", "avg_smurf_rate",
              "carry_delta_lo", "carry_delta_hi", "n_lo_games", "n_hi_games", "error"]
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    print(f"\n✓ Synthèse exportée dans {summary_path}")
    print(f"✓ CSVs individuels dans {args.out_dir}/")
    print("\nPour analyser un joueur en détail :")
    print(f"  python3 analyze.py {args.out_dir}/<riot_id>.csv")


if __name__ == "__main__":
    main()
