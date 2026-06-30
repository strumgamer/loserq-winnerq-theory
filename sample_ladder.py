#!/usr/bin/env python3
"""
sample_ladder.py — Échantillonnage aléatoire du ladder EUW pour la phase confirmatoire.

Pour chaque tier (Bronze → Diamond), tire aléatoirement des joueurs du classement,
vérifie qu'ils ont ≥35 ranked Solo/Duo games dans les 60 derniers jours,
et génère la liste des Riot IDs à collecter avec collect.py.

Usage :
    export RIOT_API_KEY="RGAPI-xxxx"
    python sample_ladder.py --per-tier 8 --out confirmatory_players.txt

    # Puis collecte batch (résumable si interrompue) :
    python sample_ladder.py --collect --in confirmatory_players.txt

Budget API estimé : ~5–10 appels par candidat examiné, ~50 appels par joueur validé.
Pour 30 joueurs (6 × 5 tiers) avec taux de rejet ~30% : ~2000 appels ≈ 40 min.
"""

import argparse
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from collect import riot_get, RateLimiter, Cache

# ─── Constantes ───────────────────────────────────────────────────────────────

QUEUE        = "RANKED_SOLO_5x5"
PLATFORM     = "euw1"
REGION       = "europe"
TIERS        = ["BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER"]
DIVISIONS    = ["I", "II", "III", "IV"]
MIN_RECENT   = 35    # games ranked dans les 60 derniers jours
LOOKBACK_D   = 60    # jours
LOOKBACK_TS  = int(time.time()) - LOOKBACK_D * 86400
GM_LP_CAP    = 1000  # Grandmaster : on exclut les joueurs > 1000 LP

# Joueurs pilotes — à exclure (Riot IDs normalisés)
PILOT_IDS = {
    "kristal_uwu1", "san_ejetz", "vikingspt_euw", "weedymary_euw",
    "seestern_7777", "tjelletmeister_euw", "cap1tancalzones_euw",
}

# ─── Helpers API ──────────────────────────────────────────────────────────────

def get_ladder_page(tier, division, page, api_key):
    url = (f"https://{PLATFORM}.api.riotgames.com"
           f"/lol/league/v4/entries/{QUEUE}/{tier}/{division}")
    return riot_get(url, api_key, params={"page": page}) or []


def get_apex_entries(tier, api_key, lp_cap=None):
    """Master / Grandmaster / Challenger — endpoint dédié, pas de pagination."""
    url = (f"https://{PLATFORM}.api.riotgames.com"
           f"/lol/league/v4/{tier.lower()}leagues/by-queue/{QUEUE}")
    data = riot_get(url, api_key) or {}
    entries = data.get("entries", [])
    if lp_cap is not None:
        entries = [e for e in entries if e.get("leaguePoints", 0) <= lp_cap]
    return entries


def get_riot_id_from_puuid(puuid, api_key):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
    data = riot_get(url, api_key)
    if data and data.get("gameName") and data.get("tagLine"):
        return f"{data['gameName']}#{data['tagLine']}"
    return None


def count_recent_ranked(puuid, api_key):
    """Nombre de games Ranked Solo/Duo dans les LOOKBACK_D derniers jours."""
    url = (f"https://{REGION}.api.riotgames.com"
           f"/lol/match/v5/matches/by-puuid/{puuid}/ids")
    data = riot_get(url, api_key, params={
        "queue": 420,
        "type": "ranked",
        "startTime": LOOKBACK_TS,
        "count": 100,
    }) or []
    return len(data)


# ─── Sampling ─────────────────────────────────────────────────────────────────

def sample_tier(tier, n_target, api_key, seen_puuids):
    """
    Retourne une liste de (riot_id, puuid, tier, division) pour un tier donné.
    Tire aléatoirement dans les pages du ladder jusqu'à obtenir n_target joueurs valides.
    """
    results = []

    # Collecte un pool de candidats
    pool = []
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        lp_cap = GM_LP_CAP if tier == "GRANDMASTER" else None
        entries = get_apex_entries(tier, api_key, lp_cap=lp_cap)
        for e in entries:
            e["_div"] = "-"
        pool.extend(entries)
    else:
        for div in DIVISIONS:
            for page in random.sample(range(1, 11), k=4):
                entries = get_ladder_page(tier, div, page, api_key)
                for e in entries:
                    e["_div"] = div
                pool.extend(entries)
    random.shuffle(pool)

    examined = 0
    for entry in pool:
        if len(results) >= n_target:
            break

        examined += 1
        # L'API 2024+ retourne le PUUID directement dans les entrées league
        puuid = entry.get("puuid")
        if not puuid or puuid in seen_puuids:
            continue

        # Récupère le Riot ID
        riot_id = get_riot_id_from_puuid(puuid, api_key)
        if not riot_id:
            continue

        # Exclusion pilotes
        name_norm = riot_id.split("#")[0].lower().replace(" ", "_")
        if name_norm in PILOT_IDS:
            print(f"    [skip pilote] {riot_id}")
            continue

        # Filtre activité récente
        n_recent = count_recent_ranked(puuid, api_key)
        if n_recent < MIN_RECENT:
            print(f"    [skip inactif] {riot_id} — {n_recent} games / {LOOKBACK_D}j")
            continue

        div = entry.get("_div", "?")
        lp  = entry.get("leaguePoints", 0)
        print(f"    ✓ {riot_id}  [{tier} {div} {lp}LP, {n_recent} games récentes]")
        results.append({
            "riot_id":  riot_id,
            "puuid":    puuid,
            "tier":     tier,
            "division": div,
            "lp":       lp,
        })
        seen_puuids.add(puuid)

    print(f"  → {len(results)}/{n_target} validés  (examiné {examined} candidats)")
    return results


# ─── Collecte batch ───────────────────────────────────────────────────────────

def run_collect(riot_id, out_dir):
    """Lance collect.py pour un joueur. Retourne True si succès."""
    safe_name = riot_id.replace("#", "_").replace(" ", "_")
    out_path  = Path(out_dir) / f"{safe_name}.csv"

    if out_path.exists():
        print(f"  [skip] {riot_id} — déjà collecté ({out_path})")
        return True

    cmd = [
        sys.executable, "collect.py",
        "--riot-id", riot_id,
        "--region",   REGION,
        "--platform", PLATFORM,
        "--count",    "100",
        "--out",      str(out_path),
    ]
    print(f"\n→ Collecte : {riot_id}")
    result = subprocess.run(cmd)
    return result.returncode == 0


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-tier", type=int, default=6,
                    help="joueurs cibles par tier (défaut 6)")
    ap.add_argument("--out", default="confirmatory_players.txt",
                    help="fichier de sortie listing les joueurs sélectionnés")
    ap.add_argument("--collect", action="store_true",
                    help="lance collect.py sur chaque joueur listé dans --in")
    ap.add_argument("--in",  dest="infile", default="confirmatory_players.txt",
                    help="fichier d'entrée pour --collect")
    ap.add_argument("--batch-out", default="batch_out",
                    help="dossier de sortie des CSV par joueur")
    ap.add_argument("--seed", type=int, default=2026,
                    help="seed aléatoire pour reproductibilité (pre-registration)")
    args = ap.parse_args()

    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        print("ERREUR : export RIOT_API_KEY='RGAPI-xxxx'")
        sys.exit(1)

    # ── Mode collecte batch ──────────────────────────────────────────────────
    if args.collect:
        infile = Path(args.infile)
        if not infile.exists():
            print(f"ERREUR : {infile} introuvable. Lance d'abord sans --collect.")
            sys.exit(1)
        Path(args.batch_out).mkdir(exist_ok=True)
        lines = [l.strip() for l in infile.read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        players = []
        for line in lines:
            parts = line.split(",", 1)
            if len(parts) == 2:
                players.append((parts[0].strip(), parts[1].strip()))

        print(f"→ {len(players)} joueurs à collecter depuis {infile}")
        ok = err = 0
        for tier, riot_id in players:
            if run_collect(riot_id, args.batch_out):
                ok += 1
            else:
                err += 1
        print(f"\n✓ {ok} collectés, {err} erreurs")
        print(f"CSV dans {args.batch_out}/")
        return

    # ── Mode sampling ────────────────────────────────────────────────────────
    random.seed(args.seed)
    seen_puuids = set()
    all_players = []

    for tier in TIERS:
        print(f"\n{'='*50}")
        print(f"Sampling {tier} (cible : {args.per_tier} joueurs)")
        print(f"{'='*50}")
        players = sample_tier(tier, args.per_tier, api_key, seen_puuids)
        all_players.extend(players)
        if len(players) < args.per_tier:
            print(f"  ⚠ Seulement {len(players)}/{args.per_tier} validés pour {tier}")

    # Écriture du fichier de sortie
    outfile = Path(args.out)
    with outfile.open("w", encoding="utf-8") as f:
        f.write(f"# Confirmatory players — sampled {time.strftime('%Y-%m-%d')}\n")
        f.write(f"# Seed: {args.seed} | Per-tier: {args.per_tier}\n")
        f.write(f"# Total: {len(all_players)} joueurs\n")
        f.write(f"# Format: TIER,RIOT_ID\n#\n")
        f.write(f"# Joueurs pilotes exclus :\n")
        f.write(f"#   kristal_uwu1, SAN_eJetz, VikingsPT_EUW, WeedyMary_EUW\n")
        f.write(f"#   seestern_7777, TjelletMeister_EUW, cap1tancalzones_EUW\n\n")
        for p in all_players:
            f.write(f"{p['tier']},{p['riot_id']}\n")

    print(f"\n{'='*50}")
    print(f"✓ {len(all_players)} joueurs écrits dans {outfile}")
    print(f"\nÉtape suivante — collecte (résumable si interrompue) :")
    print(f"  python sample_ladder.py --collect --in {outfile} --batch-out batch_out/")
    print(f"\nPuis pipeline d'analyse :")
    print(f"  python meta_analysis.py batch_out/")


if __name__ == "__main__":
    main()
