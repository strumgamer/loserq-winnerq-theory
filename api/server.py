# cd /home/obiwan/Bureau/loserq_winnerq_theory
# export RIOT_API_KEY="RGAPI-xxxx"
# uvicorn api.server:app --reload --port 8000

import os
import sys
import json
import hashlib
import datetime
import secrets
import time

# Allow imports from project root (collect.py, analyze.py, anonymize.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from math import sqrt

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import re as _re

from collect import (
    Cache,
    get_puuid,
    get_match_ids,
    get_match,
    extract_row,
    riot_get,
)
from analyze import linregress_nw
from anonymize import find_episodes, wr_unfav, slope_by_carry, mean_team_diff

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="LoserQ / WinnerQ API", version="1.0.0")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Submissions — éphémère sur Render (perdu au redéploiement), persistant en local.
# Télécharger via GET /api/submissions?token=... avant tout déploiement.
_SUBMISSIONS_FILE = os.path.join(_PROJECT_ROOT, "submissions.json")
_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

MAX_COUNT = 200

_RIOT_ID_RE = _re.compile(r"^[^#]{1,50}#[A-Za-z0-9]{2,5}$")

# Vérification d'identité par changement d'icône de profil
# In-memory, éphémère (perdu au redémarrage Render) — TTL court, acceptable
_icon_challenges: dict = {}  # puuid → {original_icon_id, riot_id, expires_at}
_verified_tokens: dict  = {}  # token → {riot_id_lower, expires_at}


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    riot_id: str
    region: str = "europe"
    platform: str = "euw1"
    count: int = Field(default=100, ge=1, le=MAX_COUNT)

    @field_validator("riot_id")
    @classmethod
    def validate_riot_id(cls, v: str) -> str:
        normalized = v.strip()
        if "#" in normalized:
            parts = normalized.split("#", 1)
            normalized = parts[0].rstrip() + "#" + parts[1].lstrip()
        if not _RIOT_ID_RE.match(normalized):
            raise ValueError("Format invalide")
        return normalized


def _normalize_riot_id(v: str) -> str:
    normalized = v.strip()
    if "#" in normalized:
        parts = normalized.split("#", 1)
        normalized = parts[0].rstrip() + "#" + parts[1].lstrip()
    if not _RIOT_ID_RE.match(normalized):
        raise ValueError("Format invalide")
    return normalized


class ContributeRequest(BaseModel):
    riot_id: str
    region: str = "europe"
    platform: str = "euw1"
    consent: bool
    prior_belief: str = "unsure"
    verification_token: str

    @field_validator("riot_id")
    @classmethod
    def validate_riot_id_contrib(cls, v: str) -> str:
        return _normalize_riot_id(v)

    @field_validator("prior_belief")
    @classmethod
    def validate_belief(cls, v: str) -> str:
        if v not in ("yes", "no", "unsure"):
            raise ValueError("prior_belief doit être yes/no/unsure")
        return v

    @field_validator("verification_token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        if not v or len(v) < 8:
            raise ValueError("Token de vérification invalide")
        return v


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


@app.post("/api/contribute")
@limiter.limit("5/hour")
def contribute(req: ContributeRequest, request: Request):
    if not req.consent:
        raise HTTPException(status_code=400, detail="Consentement requis")

    # Valider le token de vérification par icône
    token_data = _verified_tokens.get(req.verification_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Vérification d'identité requise — vérifie ton compte via l'icône")
    if time.time() > token_data["expires_at"]:
        _verified_tokens.pop(req.verification_token, None)
        raise HTTPException(status_code=401, detail="Session expirée — relance la vérification")
    if token_data["riot_id_lower"] != req.riot_id.lower():
        raise HTTPException(status_code=401, detail="Token invalide pour ce Riot ID")
    # Consommer le token (usage unique)
    _verified_tokens.pop(req.verification_token, None)

    submissions = []
    if os.path.exists(_SUBMISSIONS_FILE):
        try:
            with open(_SUBMISSIONS_FILE) as f:
                submissions = json.load(f)
        except (json.JSONDecodeError, IOError):
            submissions = []

    existing_ids = {s["riot_id"].lower() for s in submissions}
    if req.riot_id.lower() in existing_ids:
        return {"status": "already_submitted"}

    submissions.append({
        "riot_id":      req.riot_id,
        "region":       req.region,
        "platform":     req.platform,
        "prior_belief": req.prior_belief,
        "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "ip_hash":      _hash_ip(get_remote_address(request)),
    })

    with open(_SUBMISSIONS_FILE, "w") as f:
        json.dump(submissions, f, ensure_ascii=False, indent=2)

    return {"status": "ok"}


@app.get("/api/submissions")
def get_submissions(token: str = ""):
    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not os.path.exists(_SUBMISSIONS_FILE):
        return {"count": 0, "submissions": []}

    with open(_SUBMISSIONS_FILE) as f:
        data = json.load(f)

    return {"count": len(data), "submissions": data}


@app.get("/api/verify/challenge")
@limiter.limit("10/hour")
def verify_challenge(request: Request, riot_id: str, platform: str = "euw1", region: str = "europe"):
    """Étape 1 : enregistre l'icône actuelle du joueur comme baseline de vérification."""
    if not _re.fullmatch(_RIOT_ID_RE, riot_id):
        raise HTTPException(status_code=422, detail="Riot ID invalide")
    api_key = _api_key()

    name, tag = riot_id.split("#", 1)
    account = riot_get(
        f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}",
        api_key,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Joueur introuvable — vérifie ton Riot ID et ton serveur")

    puuid = account["puuid"]
    summoner = riot_get(
        f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}",
        api_key,
    )
    if not summoner:
        raise HTTPException(status_code=404, detail="Données invocateur introuvables")

    _icon_challenges[puuid] = {
        "original_icon_id": summoner["profileIconId"],
        "riot_id":          riot_id,
        "expires_at":       time.time() + 900,  # 15 min
    }
    return {"status": "challenge_created"}


@app.get("/api/verify/check")
@limiter.limit("30/hour")
def verify_check(request: Request, riot_id: str, platform: str = "euw1", region: str = "europe"):
    """Étape 2 : vérifie que l'icône a changé → génère un token de soumission."""
    if not _re.fullmatch(_RIOT_ID_RE, riot_id):
        raise HTTPException(status_code=422, detail="Riot ID invalide")
    api_key = _api_key()

    name, tag = riot_id.split("#", 1)
    account = riot_get(
        f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}",
        api_key,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    puuid = account["puuid"]
    challenge = _icon_challenges.get(puuid)
    if not challenge or time.time() > challenge["expires_at"]:
        _icon_challenges.pop(puuid, None)
        raise HTTPException(status_code=410, detail="Challenge expiré — relance la vérification depuis le début")

    summoner = riot_get(
        f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}",
        api_key,
    )
    if not summoner:
        raise HTTPException(status_code=404, detail="Données invocateur introuvables")

    if summoner["profileIconId"] == challenge["original_icon_id"]:
        return {"verified": False, "message": "Icône inchangée. Si tu viens de changer ton icône, attends 30 secondes et réessaie — l'API Riot peut mettre quelques instants à se mettre à jour."}

    # Vérifié : générer un token usage unique (30 min pour compléter le formulaire)
    token = secrets.token_urlsafe(16)
    _verified_tokens[token] = {
        "riot_id_lower": riot_id.lower(),
        "expires_at":    time.time() + 1800,
    }
    _icon_challenges.pop(puuid, None)
    return {"verified": True, "token": token}


@app.post("/api/analyze")
@limiter.limit("2/minute")
def analyze(req: AnalyzeRequest, request: Request):
    api_key = _api_key()

    # Normalisation défensive : supprime les espaces autour du '#'
    riot_id_clean = req.riot_id.strip()
    if "#" in riot_id_clean:
        parts = riot_id_clean.split("#", 1)
        riot_id_clean = parts[0].rstrip() + "#" + parts[1].lstrip()

    count = min(req.count, MAX_COUNT)

    # ── 1. Résolution PUUID ──────────────────────────────────────────────────
    try:
        if "#" not in riot_id_clean:
            raise HTTPException(
                status_code=400,
                detail="riot_id doit être au format Pseudo#TAG (ex: Faker#KR1)",
            )
        name, tag = riot_id_clean.split("#", 1)
        url = (
            f"https://{req.region}.api.riotgames.com"
            f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
        )
        account_data = riot_get(url, api_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Erreur lors de la récupération des données") from exc

    if not account_data:
        raise HTTPException(
            status_code=404, detail=f"Joueur introuvable: {riot_id_clean}"
        )
    puuid = account_data["puuid"]

    # ── 2. Match IDs ─────────────────────────────────────────────────────────
    try:
        match_ids = get_match_ids(puuid, req.region, api_key, count)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Erreur lors de la récupération des données") from exc

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
        raise HTTPException(status_code=502, detail="Erreur lors de la récupération des données") from exc

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

    def _episode_ranges(rows, min_run=3):
        """Retourne les plages de games suspectes (team trop faible)."""
        td_vals = [r["team_diff"] for r in rows if r.get("team_diff") is not None]
        if len(td_vals) < 5:
            return []
        td_m = sum(td_vals) / len(td_vals)
        td_s = (sum((v - td_m)**2 for v in td_vals) / len(td_vals))**0.5 or 1
        Z_TEAM = -1.5
        ranges, run_start, run = [], None, 0
        for r in rows:
            td = r.get("team_diff")
            zt = (td - td_m) / td_s if td is not None else None
            if zt is not None and zt < Z_TEAM:
                if run == 0:
                    run_start = r["game_index"]
                run += 1
            else:
                if run >= min_run:
                    ranges.append({"start": run_start, "end": rows[rows.index(r)-1]["game_index"], "type": "lq"})
                run = 0
        if run >= min_run:
            ranges.append({"start": run_start, "end": rows[-1]["game_index"], "type": "lq"})
        return ranges

    episode_ranges = _episode_ranges(valid_rows)

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
            r.get("my_kda", 0),
            r.get("my_damage", 0),
            r.get("my_vision", 0),
            1 if r.get("team_diff") is not None and r.get("recent_wr_10") is not None else 0,
        ]
        for r in raw_rows
    ]

    # ── 8. Réponse ───────────────────────────────────────────────────────────
    return {
        "id":            riot_id_clean,
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
        "episode_ranges": episode_ranges,
    }
