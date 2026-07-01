"""Ciblage du secteur hôtelier (PART 2).

On filtre la couche Bronze (enterprise_finale) pour extraire les entreprises
hôtelières éligibles au scraping NBB, puis on les charge en StateDB (pending).

Critères :
    Status = AC (actif)
    TypeOfEnterprise = 2 (personne morale privée)
    activité MAIN dont le NaceCode est dans la liste hôtellerie
    JuridicalForm hors formes juridiques publiques exclues
"""
from __future__ import annotations

from tqdm import tqdm

from . import config, db, statedb


def _query() -> dict:
    return {
        "Status": "AC",
        "TypeOfEnterprise": "2",
        "JuridicalForm": {"$nin": list(config.EXCLUDED_JURIDICAL_FORMS)},
        "activities": {
            "$elemMatch": {
                "Classification": "MAIN",
                "NaceCode": {"$in": list(config.HOTEL_NACE_CODES)},
            }
        },
    }


def _matched_hotel_codes(doc: dict) -> list[str]:
    matched = {
        activity.get("NaceCode")
        for activity in doc.get("activities", [])
        if activity.get("Classification") == "MAIN"
        and activity.get("NaceCode") in config.HOTEL_NACE_CODES
    }
    return sorted(code for code in matched if code)


def _name(doc: dict) -> str | None:
    for denomination in doc.get("denominations", []):
        if denomination.get("TypeOfDenomination") == "001" and denomination.get("Denomination"):
            return denomination["Denomination"]
    for denomination in doc.get("denominations", []):
        if denomination.get("Denomination"):
            return denomination["Denomination"]
    return None


def target(limit: int | None = None) -> int:
    """Extrait les entreprises hôtelières du Bronze et les charge en StateDB."""
    statedb.ensure_indexes()
    coll = db.bronze()
    query = _query()

    total = coll.count_documents(query)
    print(f"Entreprises hôtelières éligibles : {total:,}")

    cursor = coll.find(query)
    if limit:
        cursor = cursor.limit(limit)

    loaded = 0
    for doc in tqdm(cursor, total=(limit or total), desc="  StateDB", unit=" ent"):
        statedb.upsert_target(doc["_id"], _name(doc), _matched_hotel_codes(doc))
        loaded += 1

    print(f"Chargées en StateDB (pending) : {loaded:,}")
    return loaded
