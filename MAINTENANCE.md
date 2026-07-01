# Politique de maintenance — loserq_winnerq_theory

Ce site est **en maintenance**, pas en développement actif. Il ne sera mis à jour que si l'une des conditions ci-dessous est remplie. Pour tout le reste : v2, plus tard.

---

## Raisons qui déclenchent une mise à jour

**1. La phase confirmatoire aboutit**
Quand N ≥ 3 000 obs within-player (ou date butoir 2026-12-31) : mettre à jour le résultat agrégé affiché, régénérer `data.json`, republier. C'est le seul raffinement planifié.

**2. L'API Riot casse la collecte**
Si Riot modifie ses endpoints ou si un patch majeur rend les données non comparables : corriger `collect.py` ou ajouter un avertissement dans le site. Le résultat affiché date alors d'avant le changement.

**3. Une erreur méthodologique est signalée**
Si un contributeur ou un critique identifie un bug réel (statistique, logique, ou présentation qui induit en erreur) : corriger, versionner, noter la correction dans le README.

---

## Ce qui n'est pas une raison

- Une nouvelle variable ou hypothèse exploratoire → liste v2
- Un raffinement de la frontière de détectabilité → liste v2
- Une amélioration esthétique → liste v2
- Un test secondaire supplémentaire → liste v2

---

## Comment contribuer

Les contributions bienvenues : nouvelles données (CSV via `batch.py`), signalements d'erreurs, traductions. Ouvrir une issue sur GitHub avec le contexte.

Les contributions hors périmètre de la v1 seront étiquetées `v2` et intégrées si une masse critique se constitue.
