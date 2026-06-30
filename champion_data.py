"""
champion_data.py — Score d'autonomie individuelle (carry_score) par champion.

Échelle 0.0 → 1.0 :
  0.0  = zéro agency, multiplicateur pur de ses alliés (Yuumi)
  0.5  = équilibre team/solo
  1.0  = win condition entièrement indépendante (split pusher extrême)

Logique :
  - Score BAS  → loser queue très difficile à "tanker" (dépend des alliés)
  - Score HAUT → loser queue plus absorbable via skill individuel

Source : archétypes de rôle + potentiel 1v9 en meta standard.
Champions absents → fallback par rôle dans get_carry_score().
"""

CARRY_SCORES: dict[str, float] = {

    # ── ENCHANTERS purs (0.05 – 0.25) ───────────────────────────────────────
    "Yuumi":        0.05,
    "Soraka":       0.10,
    "Janna":        0.15,
    "Lulu":         0.18,
    "Sona":         0.20,
    "Nami":         0.22,
    "Seraphine":    0.22,
    "Renata Glasc": 0.22,
    "Karma":        0.30,   # peut mid mais orientée buff/peel
    "Taric":        0.15,
    "Zilean":       0.25,

    # ── SUPPORTS utility / engage (0.25 – 0.45) ──────────────────────────────
    "Braum":        0.25,
    "Alistar":      0.30,
    "Leona":        0.30,
    "Nautilus":     0.32,
    "Rakan":        0.32,
    "Maokai":       0.35,
    "Amumu":        0.35,
    "Galio":        0.40,
    "Morgana":      0.42,
    "Lux":          0.50,   # dépend du rôle, mid = plus carry
    "Zyra":         0.45,
    "Brand":        0.50,
    "Xerath":       0.50,
    "Vel'Koz":      0.50,
    "Blitzcrank":   0.38,
    "Thresh":       0.42,
    "Pyke":         0.65,   # support assassin, carry potentiel

    # ── TANKS engage top/jgl (0.30 – 0.55) ──────────────────────────────────
    "Malphite":     0.38,
    "Ornn":         0.35,
    "Jarvan IV":    0.42,
    "Zac":          0.38,
    "Sejuani":      0.38,
    "Rammus":       0.40,
    "Nunu & Willump": 0.40,
    "Nunu":         0.40,
    "Cho'Gath":     0.50,
    "Sion":         0.45,
    "Malzahar":     0.52,
    "Volibear":     0.50,
    "Mundo":        0.55,   # peut tenir une lane seul
    "Garen":        0.65,
    "Poppy":        0.48,
    "Kennen":       0.55,

    # ── MAGES mid/top (0.50 – 0.70) ──────────────────────────────────────────
    "Orianna":      0.50,
    "Azir":         0.52,
    "Anivia":       0.52,
    "Viktor":       0.58,
    "Syndra":       0.60,
    "Twisted Fate": 0.62,
    "Zoe":          0.60,
    "Cassiopeia":   0.65,
    "Ahri":         0.65,
    "Annie":        0.55,
    "Veigar":       0.58,
    "Lissandra":    0.55,
    "Neeko":        0.52,
    "Ziggs":        0.55,
    "Heimerdinger": 0.60,
    "Swain":        0.60,
    "Ryze":         0.55,
    "Taliyah":      0.58,
    "Aurelion Sol": 0.65,
    "Hwei":         0.55,
    "Vex":          0.58,
    "Leblanc":      0.72,
    "LeBlanc":      0.72,

    # ── ASSASSINS (0.72 – 0.90) ──────────────────────────────────────────────
    "Zed":          0.85,
    "Talon":        0.85,
    "Shaco":        0.85,
    "Katarina":     0.80,
    "Akali":        0.80,
    "Qiyana":       0.80,
    "Rengar":       0.80,
    "Kha'Zix":      0.80,
    "Khazix":       0.80,
    "Fizz":         0.75,
    "Diana":        0.72,
    "Ekko":         0.75,
    "Evelynn":      0.78,
    "Nocturne":     0.72,
    "Naafiri":      0.78,

    # ── FIGHTERS / BRUISERS top (0.60 – 0.85) ────────────────────────────────
    "Darius":       0.75,
    "Irelia":       0.78,
    "Riven":        0.80,
    "Yasuo":        0.78,
    "Yone":         0.78,
    "Pantheon":     0.70,
    "Renekton":     0.72,
    "Wukong":       0.68,
    "Xin Zhao":     0.70,
    "Hecarim":      0.72,
    "Olaf":         0.72,
    "Sett":         0.70,
    "Mordekaiser":  0.75,
    "Sylas":        0.72,
    "Urgot":        0.70,
    "Gwen":         0.75,
    "Illaoi":       0.75,
    "Aatrox":       0.72,
    "Grasp":        0.65,
    "K'Sante":      0.60,
    "Warwick":      0.70,
    "Vi":           0.65,
    "Xin Zhao":     0.70,
    "Lee Sin":      0.72,
    "Graves":       0.75,
    "Kindred":      0.68,

    # ── SPLIT PUSHERS (0.85 – 0.98) ──────────────────────────────────────────
    "Tryndamere":   0.96,
    "Fiora":        0.95,
    "Yorick":       0.95,
    "Master Yi":    0.92,
    "Jax":          0.90,
    "Camille":      0.90,
    "Nasus":        0.85,
    "Trynd":        0.96,
    "Singed":       0.85,
    "Teemo":        0.78,

    # ── ADC (0.60 – 0.82) ────────────────────────────────────────────────────
    "Jinx":         0.65,
    "Caitlyn":      0.65,
    "Jhin":         0.60,
    "Ashe":         0.60,
    "Miss Fortune": 0.62,
    "Sivir":        0.60,
    "Senna":        0.55,
    "Samira":       0.78,
    "Draven":       0.78,
    "Vayne":        0.82,
    "Tristana":     0.75,
    "Twitch":       0.75,
    "Kalista":      0.62,
    "Ezreal":       0.68,
    "Lucian":       0.72,
    "Kai'Sa":       0.72,
    "Kaisa":        0.72,
    "Xayah":        0.62,
    "Aphelios":     0.65,
    "Nilah":        0.68,
    "Zeri":         0.70,
    "Smolder":      0.62,
    "Yunara":       0.78,   # ADC mobile self-suffisant (type Vayne/Tristana)
    "Corki":        0.65,
    "Varus":        0.62,
    "Kog'Maw":      0.55,   # dépend du peel
    "KogMaw":       0.55,

    # ── MAGES/CARRIES hybrides (0.58 – 0.72) ─────────────────────────────────
    "Jayce":        0.70,
    "Vladimir":     0.72,
    "Rumble":       0.65,
    "Gangplank":    0.75,
    "Twisted Fate": 0.62,
    "Akshan":       0.72,
    "Elise":        0.68,
    "Nidalee":      0.70,
    "Lillia":       0.65,
    "Briar":        0.72,
    "Viego":        0.75,
    "Kayn":         0.72,
    "Fiddlesticks":  0.60,
    "Karthus":      0.65,
    "Bel'Veth":     0.75,
    "Belveth":      0.75,
    "Ivern":        0.35,   # full utility jungle
}

# Fallbacks par rôle si le champion n'est pas dans le dict
ROLE_FALLBACK: dict[str, float] = {
    "TOP":     0.68,
    "JUNGLE":  0.68,
    "MIDDLE":  0.63,
    "BOTTOM":  0.65,
    "UTILITY": 0.35,
    "":        0.55,
}


def get_carry_score(champion_name: str, role: str = "") -> float:
    """Retourne le carry_score d'un champion (fallback par rôle si inconnu)."""
    if champion_name in CARRY_SCORES:
        return CARRY_SCORES[champion_name]
    # Quelques normalisations de noms courants
    normalized = champion_name.replace(" ", "").replace("'", "").lower()
    for k, v in CARRY_SCORES.items():
        if k.replace(" ", "").replace("'", "").lower() == normalized:
            return v
    return ROLE_FALLBACK.get(role, 0.55)
