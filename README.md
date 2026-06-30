# loserq_winnerq_theory

**Statut** : ✓ H0 conservée — phase pilote (10 joueurs, 924 obs within-player)

Test statistique empirique de la théorie "loser/winner queue" dans League of Legends via la Riot API publique.

---

## Résumé

On teste si le matchmaking de Riot assigne des alliés systématiquement plus faibles quand un joueur est en forme (win-streak). Le test décisif est une régression `team_diff ~ recent_wr_10` avec fixed-effects intra-joueur et correction Newey-West HAC. La difficulté centrale est que l'API ne donne pas le MMR interne : `team_diff` est construit sur le rang public (proxy imparfait), ce qui atténue l'effet vers zéro même s'il existait. Sur les données pilotes (10 joueurs, 924 observations within-player), la pente est positive et non significative (slope=+30.5, p=0.76) : H0 conservée, mais la puissance actuelle (~55 %) est insuffisante pour conclure à l'absence d'effet.

---

## Hypothèses

**H0** : β = 0 dans `team_diff ~ recent_wr_10` — matchmaking indépendant de la forme récente.

**H1** : β < 0 — quand le joueur est en forme, ses alliés sont plus faibles que ses ennemis.

**Variables** :
- `team_diff` = score rang moyen alliés − score rang moyen ennemis (joueur ciblé exclu)
- `recent_wr_10` = win-rate des 10 dernières games (fenêtre glissante)

**Test décisif** : Fixed-effects within-player OLS, SE Newey-West HAC (lag=10). Rejet de H0 si β < 0 ET p < 0.05 unilatéral.

**Note proxy** : rang public ≠ MMR interne Riot. Toute conclusion porte sur ce proxy. Une atténuation vers 0 est attendue même sous H1 (measurement error in Y).

---

## Résultats actuels (phase pilote)

### FE OLS poolé within-player (estimateur pré-enregistré)

| Estimateur | n_obs | slope | p (unilatéral) | Verdict |
|---|---|---|---|---|
| FE OLS NW-HAC | 924 | +30.5 | 0.76 | ✓ H0 conservée |

### Résultats individuels (export anonymisé — `src/results/data.json`)

| Joueur (anonyme) | Palier | n | slope | r |
|---|---|---|---|---|
| Silver #2 | Silver | 100 | -56.7 | -0.050 |
| Silver #3 | Silver | 100 | +123.3 | +0.129 |
| Platinum #2 | Platinum | 63 | -144.0 | -0.191 |
| PLATINUM #1 | Platinum | 43 | -89.6 | -0.121 |
| IRON #1 | Iron | 100 | -62.0 | -0.048 |
| BRONZE #1 | Bronze | 80 | +73.9 | +0.065 |

Les slopes individuels ci-dessus sont les OLS bruts (sans NW-HAC). Pour les SE corrigées et p-values individuelles, lancer `python3 meta_analysis.py batch_out/*.csv`.

**Puissance** (nw_factor=1.0, α=0.05 unilatéral) :
- n=700 (7×100), r=0.10 → ~55 % (insuffisant pour conclure)
- n=3000 (30×100), r=0.10 → ~99 % (phase confirmatoire planifiée)

---

## Architecture

| Fichier | Rôle |
|---|---|
| `collect.py` | Collecte Riot API → `games.csv` (rate limiting, cache disque) |
| `analyze.py` | Tests statistiques individuels : runs test, autocorrélation, régression symétrie |
| `meta_analysis.py` | Méta-analyse multi-joueurs : FE OLS within-player, DerSimonian-Laird, sign test |
| `anonymize.py` | Suppression des PII, export `src/results/data.json` pour le frontend |
| `power_analysis.py` | Calcul de puissance OLS unilatéral + binomial sign test |
| `batch.py` | Collecte automatisée pour plusieurs joueurs |
| `champion_data.py` | Données champions (utilitaire) |
| `preregistration_template.md` | Plan d'analyse pré-enregistré (à déposer sur OSF) |
| `src/App.jsx` | Frontend React : simulateur + visualisations |
| `src/Analysis.jsx` | Composant d'analyse frontend |
| `api/server.py` | Backend FastAPI : proxy sécurisé Riot API |
| `api/requirements.txt` | Dépendances Python du backend |

---

## Installation

```bash
# Dépendances Python
pip install requests fastapi uvicorn
# Dépendances frontend
npm install
```

---

## Usage

```bash
# 1. Injecter la clé Riot (ne JAMAIS hardcoder)
read -rs -p "Clé Riot : " key && echo && export RIOT_API_KEY="$key"

# 2. Collecter les données d'un joueur
python3 collect.py --riot-id "Pseudo#EUW" --region europe --platform euw1 --count 200

# 3. Analyser
python3 analyze.py games.csv

# 4. Méta-analyse (plusieurs joueurs)
python3 anonymize.py && python3 meta_analysis.py batch_out/*.csv

# 5. Frontend (développement)
npm run dev

# 6. Backend (optionnel, pour l'analyse personnalisée)
uvicorn api.server:app --reload --port 8000
```

Si la collecte est interrompue, relancer la même commande — le cache (`riot_cache/`) évite de re-télécharger les games déjà récupérées.

---

## Limites connues

- **Proxy rang** : rang public ≠ MMR réel Riot — β atténué vers 0 (measurement error in Y)
- **Drift temporel** : rangs actuels sur des games historiques — biais de mesure non contrôlé
- **Confond burst** : un MMR drop naturel sur 3–7 games est indiscernable d'une loser queue
- **EUW uniquement** : résultats non généralisables à d'autres serveurs
- **Puissance actuelle ~55 %** : insuffisant pour conclure à l'absence d'effet (phase confirmatoire requise)

---

## Pre-registration

Le plan d'analyse complet est dans `preregistration_template.md`. Il doit être déposé sur [OSF](https://osf.io) ou [AsPredicted](https://aspredicted.org) **avant toute collecte confirmatoire**. La date de dépôt fait foi.

---

## Sécurité

- La clé Riot doit être injectée via variable d'environnement uniquement (`RIOT_API_KEY`)
- Ne jamais committer `riot_cache/`, `batch_out/`, `games.csv`, `.env`
- La clé de développement expire toutes les 24 h — regénérer sur [developer.riotgames.com](https://developer.riotgames.com)

---

## Licence

MIT — voir `LICENSE`.
