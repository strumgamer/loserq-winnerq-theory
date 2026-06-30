# cd /home/obiwan/Bureau/loserq_winnerq_theory
# export RIOT_API_KEY="RGAPI-xxxx"
# uvicorn api.server:app --reload --port 8000

import os
import sys

# Allow imports from project root (collect.py, analyze.py, anonymize.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from math import sqrt

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from collect import (
    Cache,
    get_puuid,
    get_match_ids,
    get_match,
    extract_row,
)
from analyze import linregress_nw
from anonymize import find_episodes, wr_unfav, slope_by_carry, mean_team_diff

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="LoserQ / WinnerQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://theoryofleagueoflegends.fr",
        "https://www.theoryofleagueoflegends.fr",
        "https://theoryofleagueoflegends.com",
        "https://www.theoryofleagueoflegends.com",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache partagé entre les requêtes — chemin relatif à la racine du projet
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "riot_cache")
_cache = Cache(_CACHE_DIR)

MAX_COUNT = 200


# ─────────────────────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    riot_id: str
    region: str = "europe"
    platform: str = "euw1"
    count: int = Field(default=100, ge=1, le=MAX_COUNT)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _t_to_p_one_sided(t: float, df: int) -> float:
    """
    p-value unilatérale gauche (H1 : pente < 0) via approximation de Hill (1970).
    Précision suffisante pour df > 5.
    """
    if df <= 0:
        return 0.5
    # Approximation normale pour grands df
    if df >= 100:
        # Approximation via la fonction de répartition normale
        x = t
        # Abramowitz & Stegun 26.2.17
        b = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429]
        p_coef = 0.2316419
        k = 1.0 / (1.0 + p_coef * abs(x))
        poly = k * (b[0] + k * (b[1] + k * (b[2] + k * (b[3] + k * b[4]))))
        phi = (1.0 / sqrt(2 * 3.141592653589793)) * (2.718281828459045 ** (-0.5 * x * x))
        p_right = phi * poly
        p_right = max(0.0, min(1.0, p_right))
        # p unilatérale gauche
        return p_right if t < 0 else 1.0 - p_right
    # Pour df modérés : approximation normale corrigée pour Student
    correction = (1.0 + t * t / df) ** (-0.5)
    z_adj = t * correction
    # Re-utilise l'approx normale sur z_adj
    b_list = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429]
    p_coef2 = 0.2316419
    k = 1.0 / (1.0 + p_coef2 * abs(z_adj))
    poly = k * (b_list[0] + k * (b_list[1] + k * (b_list[2] + k * (b_list[3] + k * b_list[4]))))
    phi = (1.0 / sqrt(2 * 3.141592653589793)) * (2.718281828459045 ** (-0.5 * z_adj * z_adj))
    p_right = phi * poly
    p_right = max(0.0, min(1.0, p_right))
    return p_right if t < 0 else 1.0 - p_right


def _api_key() -> str:
    key = os.environ.get("RIOT_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="RIOT_API_KEY not configured")
    return key


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    key_configured = bool(os.environ.get("RIOT_API_KEY", ""))
    return {"status": "ok", "key_configured": key_configured}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    api_key = _api_key()

    count = min(req.count, MAX_COUNT)

    # ── 1. Résolution PUUID ──────────────────────────────────────────────────
    try:
        # get_puuid appelle sys.exit() si introuvable — on le court-circuite
        # en vérifiant le format puis en appelant riot_get directement
        from collect import riot_get
        if "#" not in req.riot_id:
            raise HTTPException(
                status_code=400,
                detail="riot_id doit être au format Pseudo#TAG (ex: Faker#KR1)",
            )
        name, tag = req.riot_id.split("#", 1)
        url = (
            f"https://{req.region}.api.riotgames.com"
            f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
        )
        account_data = riot_get(url, api_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Riot API: {exc}") from exc

    if not account_data:
        raise HTTPException(
            status_code=404, detail=f"Joueur introuvable: {req.riot_id}"
        )
    puuid = account_data["puuid"]

    # ── 2. Match IDs ─────────────────────────────────────────────────────────
    try:
        match_ids = get_match_ids(puuid, req.region, api_key, count)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Riot API: {exc}") from exc

    if not match_ids:
        raise HTTPException(
            status_code=404, detail="Aucune game ranked Solo/Duo trouvée"
        )

    # ── 3. Extraction des rows ───────────────────────────────────────────────
    champ_pool: dict = {}
    raw_rows = []
    try:
        for mid in match_ids:
            match = get_match(mid, req.region, api_key, _cache)
            if not match:
                continue
            row = extract_row(match, puuid, req.platform, api_key, _cache, champ_pool)
            if row:
                raw_rows.append(row)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Riot API: {exc}") from exc

    if not raw_rows:
        raise HTTPException(
            status_code=404, detail="Aucune game ranked Solo/Duo trouvée"
        )

    # ── 4. Tri chronologique + recent_wr_10 ──────────────────────────────────
    raw_rows.sort(key=lambda r: r["game_start"])
    for idx, r in enumerate(raw_rows):
        r["game_index"] = idx
        window = raw_rows[max(0, idx - 10):idx]
        r["recent_wr_10"] = (
            round(sum(w["win"] for w in window) / len(window), 3)
            if window
            else None
        )

    # ── 5. Filtrage pour la régression ───────────────────────────────────────
    valid_rows = [
        r for r in raw_rows
        if r.get("recent_wr_10") is not None and r.get("team_diff") is not None
    ]

    # ── 6. Statistiques ──────────────────────────────────────────────────────
    recent_wrs = [r["recent_wr_10"] for r in valid_rows]
    team_diffs = [r["team_diff"] for r in valid_rows]

    reg = linregress_nw(recent_wrs, team_diffs) if len(valid_rows) >= 3 else None

    if reg is not None:
        slope_val  = round(reg["slope"], 2)
        r_val      = round(reg["r"], 4)
        r2_val     = round(reg["r"] ** 2, 6)
        se_nw_val  = round(reg.get("se_nw", reg["se"]), 2)
        t_nw       = reg.get("t_nw", reg["t"])
        df         = reg["n"] - 2
        p_uni      = round(_t_to_p_one_sided(t_nw, df), 4)
    else:
        slope_val = r_val = r2_val = se_nw_val = p_uni = None

    episodes   = find_episodes(valid_rows)
    wu         = wr_unfav(valid_rows)
    carry      = slope_by_carry(valid_rows)
    mtd        = mean_team_diff(valid_rows)

    n_total = len(raw_rows)
    wins    = [r["win"] for r in raw_rows]
    wr_pct  = round(sum(wins) / n_total * 100, 1) if n_total else None

    # ── 7. Scatter & timeline ─────────────────────────────────────────────────
    scatter = [
        [round(r["recent_wr_10"], 3), round(r["team_diff"], 1), r["win"]]
        for r in raw_rows
        if r.get("recent_wr_10") is not None and r.get("team_diff") is not None
    ]

    timeline = [
        [
            r["game_index"],
            round(r["recent_wr_10"], 3) if r.get("recent_wr_10") is not None else None,
            round(r["team_diff"], 1) if r.get("team_diff") is not None else None,
            r["win"],
        ]
        for r in raw_rows
    ]

    # ── 8. Réponse ───────────────────────────────────────────────────────────
    return {
        "id":            req.riot_id,
        "n":             n_total,
        "wr":            wr_pct,
        "slope":         slope_val,
        "r2":            r2_val,
        "r":             r_val,
        "p_uni":         p_uni,
        "se_nw":         se_nw_val,
        "episodes":      episodes,
        "wr_unfav":      wu,
        "mean_team_diff": mtd,
        "slope_1v9":     carry["slope_1v9"],
        "n_1v9":         carry["n_1v9"],
        "slope_teamdep": carry["slope_teamdep"],
        "n_teamdep":     carry["n_teamdep"],
        "scatter":       scatter,
        "timeline":      timeline,
    }
