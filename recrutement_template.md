# Template de recrutement — phase confirmatoire

> Usage : copier le texte de la section correspondante, adapter le pseudo,
> envoyer en DM ou poster dans le canal choisi.
> NE PAS mentionner "loser queue", "winner queue" ni "matchmaking biaisé"
> avant que le joueur ait terminé sa collecte (biais de confirmation).

---

## Version courte (Discord DM / Reddit DM)

> **Objet** : participation à une étude ranked EUW

Salut !

Je fais une étude statistique sur les performances ranked à EUW et je
cherche des joueurs actifs pour y participer.

**Ce que ça implique** :
- Autoriser l'analyse anonyme de tes ~100 dernières games ranked Solo/Duo
- 0 installation de ta part — tu me donnes juste ton Riot ID (Pseudo#EUW)
- ~5 min de ton temps au total

**Critères** :
- Serveur EUW, file Ranked Solo/Duo uniquement
- ≥ 35 games ranked dans les 60 derniers jours
- N'importe quel palier (Bronze → Diamond+)

Les données sont anonymisées avant toute publication (pas de Riot ID,
pas de match IDs). Tu reçois un résumé de tes stats à la fin.

Intéressé(e) ? Réponds ici avec ton Riot ID ou dis-moi si tu as des questions.

---

## Version longue (post Reddit r/leagueoflegends ou serveur Discord)

> **Titre** : [EUW] Recherche joueurs pour étude statistique ranked — 0 install, 5 min

**Contexte** :
Je mène une étude statistique sur les dynamiques d'équipe en ranked
Solo/Duo EUW. Le but est de mesurer si la qualité des équipes assignées
corrèle avec la forme récente d'un joueur, en utilisant les rangs publics
comme proxy.

Ce n'est pas une étude qualitative — tout est quantitatif et anonymisé.

**Ce que tu gardes** :
- Ton compte en sécurité totale (0 accès à ton compte, juste l'API publique)
- Tes données anonymisées (Riot ID supprimé, match IDs supprimés)
- Un résumé personnalisé de tes statistiques

**Ce que j'ai besoin** :
- Ton Riot ID (format : Pseudo#EUW)
- Que tu aies joué ≥ 35 games ranked Solo/Duo dans les 60 derniers jours
- N'importe quel palier

**Paliers recherchés** (stratification pour la représentativité) :
- [ ] Bronze (besoin de ~6 joueurs)
- [ ] Silver (besoin de ~6 joueurs)
- [ ] Gold (besoin de ~6 joueurs)
- [ ] Platinum (besoin de ~6 joueurs)
- [ ] Diamond+ (besoin de ~6 joueurs)

Résultats publiés sur GitHub une fois l'étude terminée (sous MIT).
Commentez ci-dessous ou envoyez un DM avec votre Riot ID.

---

## Instructions post-collecte (à envoyer après avoir récupéré les données)

> Envoyer une fois la collecte terminée.

Merci d'avoir participé ! Voici un résumé de tes statistiques :

**Riot ID** : [anonymisé]
**Games analysées** : N
**Win rate** : X%
**Pente team_diff ~ forme récente** : Y (p = Z)

*(Explication en bas de message)*

---

**C'est quoi "team_diff ~ forme récente" ?**

On a mesuré si tes équipes étaient statistiquement plus fortes ou plus
faibles selon ta forme récente (win rate des 10 dernières games).

- **Pente ≈ 0** : pas de lien détectable → conforme à un matchmaking aléatoire
- **Pente très négative et significative** (p < 0.05) : quand tu es en forme,
  tes alliés seraient en moyenne moins bien classés — ce serait un signal
  compatible avec la théorie "loser queue"

Sur notre échantillon pilote (10 joueurs, 924 games), la pente poolée
est de +30.5 (p = 0.76) — pas de signal détecté. L'étude continue
avec 30 joueurs pour augmenter la puissance statistique.

Résultats complets : [lien GitHub quand disponible]

---

## Notes de recrutement

- Viser 6 joueurs par palier (Bronze / Silver / Gold / Platinum / Diamond+)
- Canaux non-thématiques : serveurs de jeu généraux, r/leagueoflegends, Discord EUW
- Éviter : r/loserqueue, serveurs Discord axés "elo hell" (biais de sélection fort)
- Si un joueur mentionne la loser queue avant la collecte → noter dans un champ
  `recruited_blind: false` pour analyse de sensibilité (pas d'exclusion automatique)
- Joueurs pilotes déjà exclus (ne pas re-recruter) :
  kristal_uwu1, SAN_eJetz, VikingsPT_EUW, WeedyMary_EUW,
  seestern_7777, TjelletMeister_EUW, cap1tancalzones_EUW
