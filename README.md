# loserq_winnerq_theory

**Statut** : ✓ H0 conservée — phase confirmatoire intermédiaire (27 joueurs, 2 561 obs within-player — analyse ; 22 joueurs, 2 055 games — visualisation site)

Test statistique empirique de la théorie "loser/winner queue" dans League of Legends via la Riot API publique.

---

## Résumé

On teste si **l'expérience que les joueurs décrivent comme "loser queue" laisse une trace détectable** dans les données publiques Riot. Le test décisif est une régression `team_diff ~ recent_wr_10` avec fixed-effects intra-joueur et correction Newey-West HAC. La difficulté centrale est que l'API ne donne pas le MMR interne : `team_diff` est construit sur le rang public (proxy imparfait), ce qui atténue l'effet vers zéro même s'il existait. Sur les données confirmatoires intermédiaires (27 joueurs, 2 561 observations within-player), la pente est négative et non significative (slope=−20.2, SE=21.5, p=0.17) : H0 conservée. La puissance actuelle est ~100 % pour r=0.10 — le résultat est informatif. Les estimateurs secondaires (FE p=0.070, RE p=0.075) s'approchent du seuil dans la direction H1 sans l'atteindre.

**Espace des hypothèses** : trois mondes sont compatibles avec les données disponibles. (1) Matchmaking honnête : β ≈ 0, aucune signature détectable. (2) Manipulation grossière : β < 0 significatif sur le proxy rang — détectable par ce test. (3) Manipulation fine : opère via MMR interne et données privées Riot, structurellement indétectable depuis l'extérieur — aucune donnée publique ne peut ni la prouver ni la réfuter. Ce projet peut écarter ou confirmer le monde 2. Il ne peut pas trancher sur le monde 3.

---

## Hypothèses

**Question** : l'expérience vécue par les joueurs laisse-t-elle une trace détectable dans les données publiques ?

**H0** : β = 0 dans `team_diff ~ recent_wr_10` — matchmaking indépendant de la forme récente.

**H1** : β < 0 — quand le joueur est en forme, ses alliés sont plus faibles que ses ennemis.

**Variables** :
- `team_diff` = score rang moyen alliés − score rang moyen ennemis (joueur ciblé exclu)
- `recent_wr_10` = win-rate des 10 dernières games (fenêtre glissante)

**Test décisif** : Fixed-effects within-player OLS, SE Newey-West HAC (lag=10). Rejet de H0 si β < 0 ET p < 0.05 unilatéral.

**Note proxy** : rang public ≠ MMR interne Riot. Toute conclusion porte sur ce proxy. Une atténuation vers 0 est attendue même sous H1 (measurement error in Y).

**Pré-spécification des deux issues** :

- Si H0 rejetée (β < 0, p < 0.05) : données compatibles avec le monde 2 sur le proxy rang. La vraie amplitude peut être plus grande (atténuation par le bruit du proxy).
- Si H0 conservée (N ≥ 3 000, puissance > 80 %) : monde 2 absent des données publiques. Le monde 3 reste non testable — ce n'est pas un échec, c'est la conclusion.

---

## Résultats actuels (phase confirmatoire — intermédiaire)

### FE OLS poolé within-player (estimateur pré-enregistré)

| Estimateur | n_obs | n_joueurs | slope | SE_NW | p (unilatéral) | Verdict |
|---|---|---|---|---|---|---|
| FE OLS NW-HAC | 2 561 | 27 | −20.2 | 21.5 | 0.17 | ✓ H0 conservée |

Puissance actuelle (r=0.10, N=2561) ≈ 100 % — le résultat est informatif.
Secondaires non-décisionnels : FE β=−28.8 p=0.070 ; RE β=−34.4 p=0.075 (BH-correction à appliquer).

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

## Remerciements

L'ensemble des choix méthodologiques, statistiques et interprétatifs est sous la responsabilité de l'auteur. Ce projet a été développé avec l'assistance d'un modèle de langage (Claude, Anthropic) pour la mise en œuvre technique et la relecture critique.

---

## Licence

MIT — voir `LICENSE`.
