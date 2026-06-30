# loserq_winnerq_theory

Test statistique de la théorie "loser/winner queue" dans League of Legends via la Riot API.

## Vue d'ensemble

Le projet teste si le matchmaking de Riot cible des joueurs individuels en leur assignant des équipes plus faibles quand ils sont en forme (winstreak). Le test décisif : régresser `team_diff` (écart de force entre les deux équipes, hors le joueur ciblé) sur `recent_wr_10` (win-rate des 10 dernières games). Une pente négative significative = signature d'un ciblage.

**Limite fondamentale** : l'API ne donne pas le MMR réel. `team_diff` est construit sur le rang (proxy). Toute conclusion porte sur ce proxy.

## Fichiers

- `collect.py` — collecte les données Riot API → `games.csv`
- `sample_ladder.py` — **phase confirmatoire** : échantillonne le ladder EUW par tier (Bronze→Grandmaster ≤1000 LP), filtre les joueurs actifs (≥35 games / 60 jours), exclut les pilotes, génère `confirmatory_players.txt`
- `batch.py` — pipeline complet auto-sample + collecte + stats rapides par joueur
- `analyze.py` — teste les trois hypothèses sur le CSV produit
- `meta_analysis.py` — DerSimonian-Laird, FE OLS within-player, sign test
- `anonymize.py` — suppression PII + export `src/results/data.json`
- `champion_data.py` — table carry_score par champion (0=enchanteur, 1=split pusher), utilisé par collect.py et analyze.py
- `power_analysis.py` — calcul de puissance OLS one-tailed + sign test binomial
- `api/server.py` — backend FastAPI déployé sur Render (POST /api/analyze, GET /health)
- `plan.docx` — document de conception du projet
- `App.jsx` — composant frontend (visualisation, contexte à préciser)

## Setup

```bash
pip install requests
```

## Clé API Riot

**Obtention** : connecte-toi sur [developer.riotgames.com](https://developer.riotgames.com), section "Development API Key" → "Regenerate API Key". Format : `RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

**Injection dans l'environnement** (ne jamais hardcoder ni committer) :

```bash
# Linux/macOS — utiliser read -rs pour ne pas stocker la clé dans ~/.bash_history
read -rs -p "Clé Riot : " key && echo
export RIOT_API_KEY="$key"
```

```powershell
# Windows PowerShell
$env:RIOT_API_KEY = Read-Host -Prompt "Clé Riot" -AsSecureString | ConvertFrom-SecureString -AsPlainText
```

**Limites de la clé de dev** :

- Expire toutes les 24h (le compteur repart à zéro à chaque regénération)
- 20 req/s et 100 req/2min au niveau application
- Des rate limits *method-level* s'appliquent aussi par endpoint (plus bas) — le script gère les 429 avec `Retry-After`

**Clé Personal** (sans expiry, même rate limits) : Register Product → Personal Project. Délai d'approbation : 3 semaines minimum en pratique.

**Clé Production** (rate limits augmentés) : requiert un prototype public fonctionnel. Un projet perso sera refusé.

## Usage

```bash
# Collecte (premier run : 20–45 min pour 200 games)
export RIOT_API_KEY="RGAPI-xxxx"
python collect.py --riot-id "Pseudo#EUW" --region europe --platform euw1 --count 200

# Analyse
python analyze.py games.csv
```

Si le run est interrompu, relancer la même commande — le cache (`riot_cache/`) évite de re-télécharger les games déjà récupérées.

## Sécurité — points critiques

**Header, pas query param.** Le script passe actuellement la clé via `params["api_key"]`, ce qui l'expose dans les URLs loggées par Riot, les proxies et urllib3. La méthode correcte est le header `X-Riot-Token` :

```python
headers = {"X-Riot-Token": api_key}
resp = requests.get(url, params=params or {}, headers=headers, timeout=20)
```

**Ne jamais committer** : `riot_cache/`, `games.csv`, `.env`. Ajouter à `.gitignore`.

**Expiry mid-run** : si la clé expire pendant une collecte, `get_rank()` cache `[]` (joueur "unranked") silencieusement. En cas de doute, supprimer `riot_cache/ranks/` avant de relancer.

## Architecture collect.py

- `RateLimiter` — fenêtres glissantes 1s et 120s ; gère les 429 avec `Retry-After`
- `Cache` — cache disque par match ID et par PUUID avec TTL 24h sur les rangs
- `rank_to_score()` — conversion rang → score numérique (Iron IV = 0, Challenger ≈ 2800+LP)
- `extract_row()` — par game : stats du joueur ciblé + `team_diff` (écart moyen ally vs enemy)

Budget API typique pour 200 games : ~800 appels (cold cache : ~1800 appels).

## Tests statistiques (analyze.py)

1. **Runs test** — les séries sont-elles au-delà du hasard ? (indicatif seulement)
2. **Auto-corrélation** — gagner prédit-il le résultat suivant ? (non décisif : les deux modèles le prédisent)
3. **Test de symétrie** — `team_diff ~ recent_wr_10` [DÉCISIF]
   - H0 (honnête) : pente ≈ 0
   - H1 (rigged) : pente < 0 significative
   - Note : H1 est directionnelle → un test unilatéral (α=0.05 unilatéral) serait plus puissant (~+20% de puissance pour N=200, r=0.15)

## Biais connus

- Les rangs sont actuels, les games sont historiques → drift temporel des joueurs
- Joueurs unranked exclus de `team_diff` (`n_ally_ranked` / `n_enemy_ranked` renseignent la couverture)
- `champ_pool` est construit mais non exporté dans le CSV — à implémenter si analyse du champion pool souhaitée
