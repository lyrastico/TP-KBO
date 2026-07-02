"""StateDB : suivi du scraping NBB (collection state_nbb).

Statuts :
    pending      pas encore scrapé, à traiter
    in_progress  scraping en cours (ne pas retoucher)
    done         scrapé avec succès (dépôts en Bronze)

Chaque entreprise garde la liste des dépôts déjà téléchargés (`filings`) pour
permettre une reprise propre après un 429 sans tout relancer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ASCENDING

from . import db

PENDING = "pending"
IN_PROGRESS = "in_progress"
DONE = "done"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_indexes() -> None:
    db.state().create_index([("status", ASCENDING)])


def upsert_target(enterprise_number: str, name: str | None, nace_codes: list[str]) -> None:
    """Ajoute une entreprise cible en `pending` sans écraser un état déjà avancé."""
    db.state().update_one(
        {"_id": enterprise_number},
        {
            "$setOnInsert": {
                "enterprise_number": enterprise_number,
                "status": PENDING,
                "filings": [],
                "filings_count": 0,
                "created_at": _now(),
            },
            "$set": {"name": name, "nace": nace_codes, "updated_at": _now()},
        },
        upsert=True,
    )


def iter_pending(limit: int | None = None):
    cursor = db.state().find({"status": PENDING})
    if limit:
        cursor = cursor.limit(limit)
    return cursor


def mark_in_progress(enterprise_number: str) -> None:
    db.state().update_one(
        {"_id": enterprise_number},
        {"$set": {"status": IN_PROGRESS, "updated_at": _now()}},
    )


def mark_done(enterprise_number: str, filings_count: int) -> None:
    db.state().update_one(
        {"_id": enterprise_number},
        {"$set": {"status": DONE, "filings_count": filings_count, "updated_at": _now()}},
    )


def mark_pending(enterprise_number: str) -> None:
    """Remet en pending (ex. après un 429) pour reprise ultérieure."""
    db.state().update_one(
        {"_id": enterprise_number},
        {"$set": {"status": PENDING, "updated_at": _now()}},
    )


def is_filing_downloaded(enterprise_number: str, reference: str) -> bool:
    doc = db.state().find_one(
        {"_id": enterprise_number, "filings.reference": reference},
        {"_id": 1},
    )
    return doc is not None


def add_filing(enterprise_number: str, reference: str, year: int, path: str) -> None:
    """Enregistre un dépôt téléchargé (idempotent grâce à $addToSet sur la référence)."""
    if is_filing_downloaded(enterprise_number, reference):
        return
    db.state().update_one(
        {"_id": enterprise_number},
        {
            "$push": {"filings": {
                "reference": reference,
                "year": year,
                "path": path,
                "downloaded_at": _now(),
            }},
            "$set": {"updated_at": _now()},
        },
    )


def stats() -> dict[str, int]:
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    return {row["_id"]: row["n"] for row in db.state().aggregate(pipeline)}
