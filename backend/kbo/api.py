"""API FastAPI : expose les couches Silver et Gold au frontend.

Endpoints
    GET /api/health                      sonde MongoDB
    GET /api/search?q=&limit=            recherche entreprise (nom ou numéro BCE)
    GET /api/enterprise/{number}         fiche : infos Silver + ratios Gold
    GET /api/enterprise/{number}/directors  dirigeants (kbopub, persistés après scrape)

Le SSE des statuts notaire (via Tor) est laissé de côté : l'énoncé autorise à
l'ignorer, et le scraping Tor n'apporte rien de plus au reste du pipeline.

Lancement :
    uvicorn kbo.api:app --reload --port 8000
"""
from __future__ import annotations

import re

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db

app = FastAPI(title="KBO Hôtellerie — API", version="1.0")

# Le frontend Vite tourne sur un autre port en dev : on autorise les origines locales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_BCE_CHARS = re.compile(r"[0-9.]")


def _normalize_bce(raw: str) -> str:
    """Formate un numéro en 0000.000.000 (format des _id Silver/Gold)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:  # certains numéros sont saisis sans le 0 initial
        digits = "0" + digits
    if len(digits) == 10:
        return f"{digits[:4]}.{digits[4:7]}.{digits[7:]}"
    return raw


def _looks_like_bce(q: str) -> bool:
    """Vrai si la requête est majoritairement composée de chiffres (numéro BCE)."""
    return len(q) >= 8 and all(_BCE_CHARS.match(c) for c in q)


def _city(address: dict | None) -> str | None:
    if not address:
        return None
    return address.get("MunicipalityFR") or address.get("MunicipalityNL")


def _search_hit(silver_doc: dict, gold_numbers: set[str]) -> dict:
    number = silver_doc["_id"]
    return {
        "enterprise_number": number,
        "name": silver_doc.get("name"),
        "juridical_form": silver_doc.get("JuridicalFormLabel"),
        "status": silver_doc.get("StatusLabel"),
        "city": _city(silver_doc.get("address")),
        "has_financials": number in gold_numbers,
    }


# --- Endpoints -------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    db.ping()
    return {"status": "ok"}


@app.get("/api/search")
def search(q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=50)) -> dict:
    """Recherche par numéro BCE (préfixe) ou par nom (index texte)."""
    projection = {
        "name": 1, "JuridicalFormLabel": 1, "StatusLabel": 1, "address": 1,
    }
    if _looks_like_bce(q):
        prefix = _normalize_bce(q)
        cursor = db.silver().find(
            {"_id": {"$regex": f"^{re.escape(prefix)}"}}, projection
        ).limit(limit)
        results = list(cursor)
    else:
        cursor = db.silver().find(
            {"$text": {"$search": q}},
            {**projection, "score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        results = list(cursor)

    numbers = [doc["_id"] for doc in results]
    gold_numbers = {
        d["enterprise_number"]
        for d in db.gold().find({"enterprise_number": {"$in": numbers}}, {"enterprise_number": 1})
    }
    return {"query": q, "count": len(results), "results": [_search_hit(d, gold_numbers) for d in results]}


@app.get("/api/enterprise/{number}")
def enterprise(number: str) -> dict:
    """Fiche entreprise : identité + activités (Silver) et exercices/ratios (Gold)."""
    number = _normalize_bce(number)
    silver_doc = db.silver().find_one({"_id": number})
    if silver_doc is None:
        raise HTTPException(status_code=404, detail=f"Entreprise {number} introuvable")
    silver_doc.pop("_id", None)

    gold_doc = db.gold().find_one({"enterprise_number": number}, {"_id": 0})
    return {
        "enterprise_number": number,
        "silver": silver_doc,
        "gold": gold_doc,  # None si pas de comptes annuels
    }


@app.get("/api/enterprise/{number}/directors")
def enterprise_directors(number: str) -> dict:
    """Dirigeants (fonctions) via kbopub. Scrapé une fois puis persisté en base."""
    from . import directors as directors_module
    number = _normalize_bce(number)
    try:
        return directors_module.get_or_scrape(number)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"kbopub injoignable : {exc}") from exc
