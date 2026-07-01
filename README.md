# Le matchmaking de LoL est-il biaisé ? — Test statistique de la théorie de la "loser queue"

**Statut** : phase pilote recollectée (juillet 2026) — phase confirmatoire en préparation.

Un test statistique empirique : si le matchmaker de League of Legends ciblait individuellement les joueurs en forme, cela laisserait une signature détectable dans les données publiques Riot. Ce projet cherche cette signature, ou son absence.

---

## Résumé

On teste l'hypothèse centrale de la théorie de la "loser queue" : un matchmaker biaisé assignerait des alliés plus faibles à un joueur en winstreak. Le **test décisif** est une régression `team_diff ~ recent_wr_10` avec effets fixes intra-joueur et correction Newey-West HAC.

La difficulté fondamentale : l'API Riot ne donne pas le MMR interne. `team_diff` est construit sur le rang public (proxy imparfait), ce qui atténue l'effet vers zéro même s'il existait.

**Trois mondes sont compatibles avec les données disponibles :**

1. **Matchmaking honnête** : β ≈ 0, aucune signature détectable.
2. **Biais grossier** : β < 0 significatif sur le proxy rang — détectable par ce test.
3. **Biais fin** : opère via MMR interne et données privées Riot — structurellement indétectable depuis l'extérieur. Aucune donnée publique ne peut ni le prouver ni le réfuter.

Ce projet peut écarter ou confirmer le monde 2. Il ne peut pas trancher sur le monde 3.

---

## Hypothèse testée

**H0** : β = 0 dans `team_diff ~ recent_wr_10` — matchmaking indépendant de la forme récente.

**H1** : β < 0 — quand le joueur est en forme, ses alliés sont systématiquement plus faibles que ses ennemis.

**Test primaire** : FE OLS within-player, SE Newey-West HAC (lag=10). Rejet de H0 si β < 0 ET p < 0.05 unilatéral.

**Variables** :

| Variable | Définition |
| --- | --- |
| `team_diff` | Score rang moyen alliés − score rang moyen ennemis (joueur ciblé exclu) |
| `recent_wr_10` | Win-rate des 10 dernières games (fenêtre glissante) |
| `prior_belief` | Croyance déclarée du joueur (yes/no/unsure) — mesure le biais de sélection |
| `ally_rank_dispersion` | Écart-type des rangs alliés — dispersion intra-équipe |

**Note proxy** : rang public ≠ MMR interne Riot. Toute conclusion porte sur ce proxy. Une atténuation vers 0 est attendue même sous H1.

---

## Résultats pilotes

| Estimateur | n_obs | n_joueurs | slope | SE_NW | p (unilatéral) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| FE OLS NW-HAC | 2 561 | 27 | −25.4 | 21.5 | 0.119 | H0 |

Bootstrap CGM de robustesse : p = 0.145 (9 999 itérations, 27 clusters).

Corpus produit par commit `[HASH_COMMIT]`, juillet 2026 — pipeline `collect.py` v2 (colonnes `ally_rank_dispersion`, `lol_patch` ajoutées).

Pré-enregistrement : [Loser Queue EUW — Statistical Test of Targeted Matchmaking](https://osf.io/kdbxg/) · Déposé le 2026-06-30 · Amendement `prior_belief` déposé le 2026-07-01.

---

## Limites

- **Proxy rang** : rang public ≠ MMR réel Riot — β atténué vers 0 (measurement error in Y)
- **Drift temporel** : rangs actuels sur des games historiques — biais de mesure non contrôlé
- **Confond burst** : un MMR drop naturel sur 3–7 games est indiscernable d'un biais de matchmaking
- **EUW uniquement** : résultats non généralisables à d'autres serveurs sans collecte dédiée
- **Biais de sélection** : les joueurs qui contribuent volontairement ne sont pas un échantillon aléatoire — la variable `prior_belief` mesure et documente ce biais

---

## Phase confirmatoire

Cible : 600 joueurs échantillonnés aléatoirement par palier (Bronze → Grandmaster), 60 000 games. Puissance ≈ 99 % pour r=0.10 (α=0.05 unilatéral).

Échantillonnage via `sample_ladder.py` (filtre : ≥35 games ranked / 60 jours). Corpus dans `batch_out_confirmatory/`, distinct du corpus pilote.

**Règle d'arrêt pré-spécifiée** : collecte jusqu'à N=3 000 observations ou 31/12/2026 (premier atteint). Aucune analyse intermédiaire comme critère d'arrêt.

---

## Contribuer

Tu joues à LoL sur EUW, NA, EUNE ou autre ? Tu peux ajouter tes games au corpus.

→ [theoryofleagueoflegends.fr/contribuer](https://theoryofleagueoflegends.fr/contribuer)

Le résultat peut être zéro — c'est une réponse valide. L'objectif est de mesurer, pas de confirmer une croyance.

---

## Architecture

| Fichier | Rôle |
| --- | --- |
| `collect.py` | Collecte Riot API → CSV par joueur (rate limiting, cache disque) |
| `analyze.py` | Tests statistiques individuels : runs test, autocorrélation, régression symétrie |
| `meta_analysis.py` | Méta-analyse : FE OLS within-player, DerSimonian-Laird, sign test |
| `anonymize.py` | Suppression PII, export `src/results/data.json` pour le frontend |
| `power_analysis.py` | Calcul de puissance OLS unilatéral + sign test binomial |
| `batch.py` | Collecte automatisée pour plusieurs joueurs (checkpoint, `--from-submissions`) |
| `sample_ladder.py` | Échantillonnage aléatoire du ladder EUW par palier (phase confirmatoire) |
| `champion_data.py` | Table carry_score par champion |
| `api/server.py` | Backend FastAPI : `/api/analyze`, `/api/contribute`, `/api/submissions` |
| `src/App.jsx` | Frontend React : simulateur, visualisations, page Contribuer |
| `METHODS.md` | Protocole d'analyse détaillé (hypothèses, analyses secondaires, critères d'exclusion) |
| `docs/plan_initial_juin2026.docx` | Plan initial du projet (archive — superseded by OSF + METHODS.md) |

---

## Installation

```bash
# Python
pip install requests

# Frontend
npm install
```

## Usage

```bash
# Clé Riot (ne jamais hardcoder ni committer)
read -rs -p "Clé Riot : " key && echo && export RIOT_API_KEY="$key"

# Collecter les données d'un joueur
python3 collect.py --riot-id "Pseudo#EUW" --region europe --platform euw1 --count 200

# Analyser un joueur
python3 analyze.py games.csv

# Méta-analyse multi-joueurs
python3 meta_analysis.py batch_out/*.csv

# Anonymiser et exporter pour le frontend
python3 anonymize.py

# Phase confirmatoire — échantillonner le ladder
python3 sample_ladder.py --per-tier 75 --out confirmatory_players.txt

# Frontend (développement)
npm run dev
```

Le cache (`riot_cache/`) protège les games déjà téléchargées — relancer la même commande reprend là où ça s'est arrêté.

---

## Sécurité

- Clé Riot via variable d'environnement uniquement (`X-Riot-Token` header, jamais en query param)
- Ne jamais committer : `riot_cache/`, `batch_out/`, `batch_out_confirmatory/`, `games.csv`, `.env`, `submissions.json`
- Clé de développement : expire toutes les 24h — regénérer sur [developer.riotgames.com](https://developer.riotgames.com)

---

## Remerciements

Tous les choix méthodologiques, statistiques et interprétatifs sont sous la responsabilité de l'auteur. Ce projet a été développé avec l'assistance d'un modèle de langage (Claude, Anthropic) pour la mise en œuvre technique et la relecture critique.

---

## Licence

MIT — voir `LICENSE`.
