# Pre-registration — Test loser queue EUW

> À déposer sur OSF (osf.io) ou AsPredicted (aspredicted.org) AVANT toute collecte
> des joueurs de la phase confirmatoire. La date de dépôt fait foi.

---

## 1. Hypothèse et test décisif

**H0** : β = 0 dans la régression `team_diff ~ recent_wr_10` (matchmaking honnête).

**H1** : β < 0 (loser queue ciblée — quand le joueur est en forme, ses alliés sont plus faibles).

`team_diff` = score rang moyen alliés − score rang moyen ennemis (joueur ciblé exclu).
`recent_wr_10` = win-rate des 10 dernières games (fenêtre glissante).
Proxy : rang public converti en score numérique (Iron IV = 0, Challenger ≈ 2800 LP). Ce test porte sur ce proxy, pas sur le MMR réel.

---

## 2. Estimateur principal (unique base de décision)

**Fixed-effects within-player OLS** avec correction Newey-West HAC (lag=10, plancher SE_NW ≥ SE_OLS).

Implémentation : `meta_analysis.py` → `within_center()` + `linregress_nw()` sur le pool centré.

**Règle de rejet de H0** : β < 0 ET p < 0.05 unilatéral sur cet estimateur.

---

## 3. Test de robustesse (secondaire, non décisionnel)

Sign test binomial unilatéral sur les pentes individuelles.
- p_true attendu sous H1 : Φ(r√(N−2)/√(1−r²)) ≈ 0.84 (r=0.10, N=100, nw_factor=1.0)
- Résultat sign test rapporté comme limite si divergent de l'estimateur principal.
- Le sign test ne peut PAS invalider un rejet de H0 par le FE OLS.

---

## 4. Données pilotes (exclus de l'analyse confirmatoire)

7 joueurs collectés en Juin 2026 ont servi uniquement à calibrer `nw_factor` et calculer la puissance.
Ils sont **exclus** de l'analyse confirmatoire. Noms de fichier pilotes :

```
kristal_uwu1, SAN_eJetz_シ_EUWw, VikingsPT_EUW, WeedyMary_EUW,
seestern_7777, TjelletMeister_EUW, cap1tancalzones_EUW
```

---

## 5. Critères d'inclusion des joueurs confirmatoires

- Serveur EUW, file Ranked Solo/Duo uniquement (queueId=420)
- ≥ 35 games ranked Solo/Duo dans les 60 derniers jours
- Recrutement via canaux non-thématiques ("analyse de performance ranked")
- Révélation de l'hypothèse loser queue uniquement après collecte complète

---

## 6. Critères d'exclusion des lignes

- `n_ally_ranked < 4` OU `n_enemy_ranked < 4` → ligne exclue de la régression
- Si couverture qualité < 85% pour un joueur → joueur exclu de l'analyse principale
- `recent_wr_10 = None` (moins de 10 games précédentes) → ligne exclue

---

## 7. Stratification de l'échantillon

Cible : 6 joueurs × 5 paliers = 30 joueurs.
Paliers : Bronze, Silver, Gold, Platinum, Diamond+.

La stratification sert uniquement à garantir la diversité de l'échantillon.
**Elle n'implique aucun test d'interaction palier × forme.** Ce test est déclaré exploratoire
et non confirmatoire. Le test confirmatoire unique est le FE OLS poolé.

---

## 8. Taille d'échantillon et puissance

Calibration empirique (7 joueurs pilotes) : nw_factor médian = 1.0 (plancher conservateur actif).

| Effet | n_total | Puissance FE OLS |
|---|---|---|
| r = 0.10 | 3 000 (30×100) | ~99% |
| r = 0.10 | 700 (7×100, pilotes seuls) | ~55% |
| r = 0.15 | 3 000 | ~100% |

Sign test (robustesse) : k=30, p_true=0.84 → puissance ≈ 99%.
Le plan est surdimensionné pour r=0.10 ; il garantit la détection de r ≥ 0.05.

---

## 9. Règle de décision finale

```
SI β_within < 0 ET p_within < 0.05 (unilatéral) :
    → H0 rejetée. Signal loser queue détecté au niveau du proxy rang.
SINON :
    → H0 conservée. Pas de signal détectable avec ce design.
    (Ne pas conclure à l'absence — atténuation par proxy rang possible.)
```

---

## 10. Limites déclarées

1. Proxy rang ≠ MMR réel → β atténoué vers 0 (measurement error in Y).
2. Drift temporel : rangs actuels sur games historiques.
3. Confond burst loser queue (K=3-7 games) : MMR drop naturel indiscernable.
4. Échantillon EUW uniquement — non généralisable à d'autres serveurs.
5. Carry score subjectif — classification pré-enregistrée, seuil 0.65.
