#!/usr/bin/env python3
"""
collect.py — Collecteur de données Riot API pour l'analyse loser/winner queue.

Architecture façon OP.GG : on NE calcule rien en direct. On télécharge tes games
dans un fichier local (cache JSON + CSV), et l'analyse se fait séparément sur ce
fichier. L'API ne supporte pas les requêtes en masse ; il faut donc collecter
patiemment, avec cache et respect des rate limits.

Ce que ce script récupère, par game :
  - métadonnées (date, durée, queue)
  - pour TOI : KDA, vision, dégâts, CS, champion, rôle, résultat
  - pour les 9 AUTRES : rang actuel, et de quoi calculer leur win-rate et leur pool
  - l'écart de force entre ton équipe et l'équipe adverse (le coeur du test)

LIMITE FONDAMENTALE À GARDER EN TÊTE :
  L'API ne donne PAS le MMR (ni le tien ni celui des autres). Elle donne le rang
  (tier/division/LP). On utilise le rang comme PROXY du MMR. Toute conclusion porte
  donc sur ce proxy, pas sur le MMR réel interne de Riot. C'est exactement la même
  limite qu'OP.GG : eux non plus n'ont pas le vrai MMR.

Usage :
    export RIOT_API_KEY="RGAPI-xxxx"
    python collect.py --riot-id "TonPseudo#EUW" --region europe --platform euw1 --count 200

Régions (mass_region) : americas | asia | europe | sea
Plateformes : euw1 | euw1 | na1 | kr | br1 | etc.  (doit matcher ta région)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

from champion_data import get_carry_score

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITING
# Clé de dev Riot : ~20 req/s et 100 req / 2 min. On reste TRÈS en dessous.
# On gère aussi le code 429 (rate limited) avec le header Retry-After.
# ─────────────────────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, per_second=15, per_two_min=95):
        self.per_second = per_second
        self.per_two_min = per_two_min
        self.calls = []  # timestamps

    def wait(self):
        now = time.time()
        # purge > 120 s
        self.calls = [t for t in self.calls if now - t < 120]
        # fenêtre 2 min
        if len(self.calls) >= self.per_two_min:
            sleep = 120 - (now - self.calls[0]) + 0.5
            if sleep > 0:
                print(f"  [rate] pause fenêtre 2 min : {sleep:.0f}s")
                time.sleep(sleep)
        # fenêtre 1 s
        recent = [t for t in self.calls if now - t < 1.0]
        if len(recent) >= self.per_second:
            time.sleep(1.0)
        self.calls.append(time.time())


LIMITER = RateLimiter()


def riot_get(url, api_key, params=None, retries=3):
    """GET avec rate limiting, gestion 429 et 404."""
    headers = {"X-Riot-Token": api_key}
    for attempt in range(retries):
        LIMITER.wait()
        request_params = dict(params) if params else {}
        resp = requests.get(url, params=request_params, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            print(f"  [429] rate limited, pause {retry_after}s")
            time.sleep(retry_after + 1)
            continue
        if resp.status_code in (500, 502, 503, 504):
            print(f"  [{resp.status_code}] erreur serveur Riot, retry…")
            time.sleep(2 ** attempt)
            continue
        print(f"  [erreur] {resp.status_code} sur {url}: {resp.text[:200]}")
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CACHE — on ne re-télécharge jamais une game déjà récupérée
# ─────────────────────────────────────────────────────────────────────────────
class Cache:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / "matches").mkdir(parents=True, exist_ok=True)
        (self.root / "ranks").mkdir(parents=True, exist_ok=True)

    def match(self, mid):
        p = self.root / "matches" / f"{mid}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def save_match(self, mid, data):
        (self.root / "matches" / f"{mid}.json").write_text(json.dumps(data))

    def rank(self, puuid):
        p = self.root / "ranks" / f"{puuid}.json"
        # le rang change dans le temps ; on met un TTL court (1 jour) pour limiter le bruit
        if p.exists() and (time.time() - p.stat().st_mtime) < 86400:
            return json.loads(p.read_text())
        return None

    def save_rank(self, puuid, data):
        (self.root / "ranks" / f"{puuid}.json").write_text(json.dumps(data))


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────
def get_puuid(riot_id, mass_region, api_key):
    """Résout un Riot ID (GameName#TagLine) en PUUID via account-v1 (méthode 2024+)."""
    if "#" not in riot_id:
        print("ERREUR : le Riot ID doit être au format Pseudo#TAG (ex: Faker#KR1)")
        sys.exit(1)
    name, tag = riot_id.split("#", 1)
    url = f"https://{mass_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
    data = riot_get(url, api_key)
    if not data:
        print(f"ERREUR : Riot ID introuvable : {riot_id}")
        sys.exit(1)
    return data["puuid"]


def get_match_ids(puuid, mass_region, api_key, count, queue=420):
    """queue=420 = Ranked Solo/Duo. On pagine par paquets de 100 (max API)."""
    ids = []
    start = 0
    while len(ids) < count:
        batch = min(100, count - len(ids))
        url = f"https://{mass_region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        data = riot_get(url, api_key, params={"start": start, "count": batch,
                                              "queue": queue, "type": "ranked"})
        if not data:
            break
        ids.extend(data)
        if len(data) < batch:
            break  # plus de games disponibles
        start += batch
    return ids[:count]


def get_match(mid, mass_region, api_key, cache):
    cached = cache.match(mid)
    if cached:
        return cached
    url = f"https://{mass_region}.api.riotgames.com/lol/match/v5/matches/{mid}"
    data = riot_get(url, api_key)
    if data:
        cache.save_match(mid, data)
    return data


def get_rank(puuid, platform, api_key, cache):
    """league-v4 par PUUID : tier, division, LP, wins, losses pour chaque file."""
    cached = cache.rank(puuid)
    if cached is not None:
        return cached
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    data = riot_get(url, api_key) or []
    cache.save_rank(puuid, data)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION RANG → SCORE NUMÉRIQUE (proxy de force, PAS le MMR réel)
# ─────────────────────────────────────────────────────────────────────────────
TIER_BASE = {
    "IRON": 0, "BRONZE": 400, "SILVER": 800, "GOLD": 1200, "PLATINUM": 1600,
    "EMERALD": 2000, "DIAMOND": 2400, "MASTER": 2800, "GRANDMASTER": 2800,
    "CHALLENGER": 2800,
}
DIV = {"IV": 0, "III": 100, "II": 200, "I": 300}


def rank_to_score(entries):
    """Transforme la liste d'entrées ranked en un score unique pour le Solo/Duo.
    Master+ : pas de division, on ajoute les LP directement (peut dépasser 2800)."""
    for e in entries:
        if e.get("queueType") == "RANKED_SOLO_5x5":
            base = TIER_BASE.get(e["tier"], None)
            if base is None:
                return None
            if e["tier"] in ("MASTER", "GRANDMASTER", "CHALLENGER"):
                return base + e.get("leaguePoints", 0)
            return base + DIV.get(e["rank"], 0) + e.get("leaguePoints", 0)
    return None  # unranked


def winrate(entries):
    for e in entries:
        if e.get("queueType") == "RANKED_SOLO_5x5":
            w, l = e.get("wins", 0), e.get("losses", 0)
            return round(w / (w + l), 3) if (w + l) else None
    return None


def total_games_ranked(entries):
    for e in entries:
        if e.get("queueType") == "RANKED_SOLO_5x5":
            return e.get("wins", 0) + e.get("losses", 0)
    return None


# Plage LP et seuil de games pour détection smurf.
# Un joueur entre SMURF_LP_MIN et SMURF_LP_MAX avec < SMURF_GAMES_MAX games
# a une efficacité LP anormalement haute → suspect.
SMURF_LP_MIN    = 1200   # Gold IV
SMURF_LP_MAX    = 1700   # Platine I ~
SMURF_GAMES_MAX = 60


def is_smurf(rank_score, n_games):
    if rank_score is None or n_games is None or n_games == 0:
        return False
    in_range   = SMURF_LP_MIN <= rank_score <= SMURF_LP_MAX
    few_games  = n_games < SMURF_GAMES_MAX
    efficiency = rank_score / n_games          # LP par game
    return in_range and few_games and efficiency > 20


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION D'UNE GAME → UNE LIGNE CSV
# ─────────────────────────────────────────────────────────────────────────────
# Position API → clé CSV
LANE_POSITIONS = [
    ("TOP",     "lane_diff_TOP"),
    ("JUNGLE",  "lane_diff_JGL"),
    ("MIDDLE",  "lane_diff_MID"),
    ("BOTTOM",  "lane_diff_BOT"),
    ("UTILITY", "lane_diff_SUP"),
]


def extract_row(match, my_puuid, platform, api_key, cache, champ_pool):
    info = match["info"]
    if info.get("queueId") != 420:
        return None  # on ne garde que le ranked solo
    parts = info["participants"]

    me = next((p for p in parts if p["puuid"] == my_puuid), None)
    if not me:
        return None

    my_team_id = me["teamId"]
    allies  = [p for p in parts if p["teamId"] == my_team_id and p["puuid"] != my_puuid]
    enemies = [p for p in parts if p["teamId"] != my_team_id]

    # Récupère rang + winrate + total games pour tous les autres joueurs en une seule passe
    def enrich(players):
        for p in players:
            entries      = get_rank(p["puuid"], platform, api_key, cache)
            p["_score"]  = rank_to_score(entries)
            p["_wr"]     = winrate(entries)
            p["_ngames"] = total_games_ranked(entries)
            p["_smurf"]  = is_smurf(p["_score"], p["_ngames"])
            champ_pool.setdefault(p["puuid"], {})
            champ_pool[p["puuid"]][p["championName"]] = \
                champ_pool[p["puuid"]].get(p["championName"], 0) + 1

    enrich(allies)
    enrich(enemies)

    my_entries = get_rank(my_puuid, platform, api_key, cache)
    my_score   = rank_to_score(my_entries)

    # ── Moyennes d'équipe ────────────────────────────────────────────────────
    ally_scores  = [p["_score"] for p in allies  if p["_score"] is not None]
    enemy_scores = [p["_score"] for p in enemies if p["_score"] is not None]
    ally_wrs     = [p["_wr"]    for p in allies  if p["_wr"]    is not None]
    enemy_wrs    = [p["_wr"]    for p in enemies if p["_wr"]    is not None]

    avg_ally  = sum(ally_scores)  / len(ally_scores)  if ally_scores  else None
    avg_enemy = sum(enemy_scores) / len(enemy_scores) if enemy_scores else None
    team_diff = (avg_ally - avg_enemy) if (avg_ally is not None and avg_enemy is not None) else None

    # ── Deltas par duel de lane ──────────────────────────────────────────────
    def player_at(players, pos):
        for p in players:
            if p.get("teamPosition") == pos:
                return p
        return None

    lane_diffs = {}
    n_lanes_matched = 0
    for api_pos, col in LANE_POSITIONS:
        a = player_at(allies,  api_pos)
        e = player_at(enemies, api_pos)
        a_s = a["_score"] if a else None
        e_s = e["_score"] if e else None
        if a_s is not None and e_s is not None:
            lane_diffs[col] = round(a_s - e_s, 1)
            n_lanes_matched += 1
        else:
            lane_diffs[col] = None

    # Duel spécifique du joueur ciblé vs son adversaire direct
    my_pos = me.get("teamPosition", "")
    my_lane_diff = None
    if my_pos and my_score is not None:
        opp = player_at(enemies, my_pos)
        if opp and opp["_score"] is not None:
            my_lane_diff = round(my_score - opp["_score"], 1)

    return {
        "match_id":   match["metadata"]["matchId"],
        "game_start": info.get("gameStartTimestamp", info.get("gameCreation")),
        "duration_s": info.get("gameDuration"),
        "win":        int(me["win"]),
        # toi
        "my_champ":  me["championName"],
        "my_role":   my_pos,
        "my_kills":  me["kills"], "my_deaths": me["deaths"], "my_assists": me["assists"],
        "my_kda":    round((me["kills"] + me["assists"]) / max(1, me["deaths"]), 2),
        "my_vision": me.get("visionScore", 0),
        "my_damage": me.get("totalDamageDealtToChampions", 0),
        "my_cs":     me.get("totalMinionsKilled", 0) + me.get("neutralMinionsKilled", 0),
        "my_rank_score":   my_score,
        "my_carry_score":  get_carry_score(me["championName"], my_pos),
        # équipes — moyennes globales
        "avg_ally_score":    round(avg_ally,  1) if avg_ally  is not None else None,
        "avg_enemy_score":   round(avg_enemy, 1) if avg_enemy is not None else None,
        "team_diff":         round(team_diff, 1) if team_diff is not None else None,
        "avg_ally_winrate":  round(sum(ally_wrs)  / len(ally_wrs),  3) if ally_wrs  else None,
        "avg_enemy_winrate": round(sum(enemy_wrs) / len(enemy_wrs), 3) if enemy_wrs else None,
        "n_ally_ranked":     len(ally_scores),
        "n_enemy_ranked":    len(enemy_scores),
        # duels de lane (allié - ennemi, négatif = allié plus faible)
        **lane_diffs,
        "my_lane_diff":    my_lane_diff,
        "n_lanes_matched": n_lanes_matched,
        # détection smurf
        "n_smurf_allies":  sum(1 for p in allies  if p["_smurf"]),
        "n_smurf_enemies": sum(1 for p in enemies if p["_smurf"]),
        "smurf_diff":      sum(1 for p in enemies if p["_smurf"]) - sum(1 for p in allies if p["_smurf"]),
        "smurf_rate":      round(
            (sum(1 for p in allies + enemies if p["_smurf"])) /
            max(1, sum(1 for p in allies + enemies if p["_score"] is not None)), 3
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--riot-id", required=True, help="Pseudo#TAG (ex: Faker#KR1)")
    ap.add_argument("--region", required=True, help="mass region: americas|asia|europe|sea")
    ap.add_argument("--platform", required=True, help="platform: euw1|na1|kr|br1|…")
    ap.add_argument("--count", type=int, default=100, help="nombre de games à récupérer")
    ap.add_argument("--cache", default="riot_cache", help="dossier de cache")
    ap.add_argument("--out", default="games.csv", help="CSV de sortie")
    args = ap.parse_args()

    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        print("ERREUR : exporte ta clé : export RIOT_API_KEY='RGAPI-xxxx'")
        sys.exit(1)

    cache = Cache(args.cache)

    print(f"→ Résolution du Riot ID {args.riot_id}…")
    puuid = get_puuid(args.riot_id, args.region, api_key)
    print(f"  PUUID : {puuid[:24]}…")

    print(f"→ Récupération de {args.count} match IDs (ranked solo)…")
    match_ids = get_match_ids(puuid, args.region, api_key, args.count)
    print(f"  {len(match_ids)} games trouvées.")

    import csv
    champ_pool = {}
    rows = []
    for i, mid in enumerate(match_ids, 1):
        print(f"  [{i}/{len(match_ids)}] {mid}")
        match = get_match(mid, args.region, api_key, cache)
        if not match:
            continue
        row = extract_row(match, puuid, args.platform, api_key, cache, champ_pool)
        if row:
            rows.append(row)

    if not rows:
        print("Aucune game ranked solo exploitable. Vérifie le Riot ID / la file.")
        return

    # tri chronologique (le plus ancien d'abord) — indispensable pour les streaks
    rows.sort(key=lambda r: r["game_start"])
    # ajoute l'index séquentiel et la forme récente (win-rate des 10 dernières)
    for idx, r in enumerate(rows):
        r["game_index"] = idx
        window = rows[max(0, idx - 10):idx]
        r["recent_wr_10"] = round(sum(w["win"] for w in window) / len(window), 3) if window else None

    fields = list(rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✓ {len(rows)} games écrites dans {args.out}")
    print(f"✓ cache dans {args.cache}/ (relancer ne re-télécharge pas)")
    print(f"\nLance maintenant :  python analyze.py {args.out}")


if __name__ == "__main__":
    main()
