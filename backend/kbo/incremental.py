"""Recalcul incrémental de la couche Gold (support du DAG Airflow annuel).

Principe (cf. énoncé, « Chantier 4 ») : pour chaque entreprise déjà traitée
(`status=done` en StateDB), on compare ses dépôts connus (`filings`) avec ce que
NBB expose aujourd'hui ; on télécharge uniquement les exercices manquants, puis on
reconstruit le document Gold des seules entreprises modifiées. Les entreprises sans
nouveau dépôt ne sont pas retouchées — le DAG peut donc tourner chaque année sans
retraiter l'intégralité du dataset.

Ces fonctions sont utilisables telles quelles, avec ou sans Airflow :
    python -m kbo refresh [--limit N]
"""
from __future__ import annotations

import time

import requests

from . import db, gold, nbb, statedb, storage


def list_done(limit: int | None = None) -> list[dict]:
    """Entreprises déjà scrapées (status=done)."""
    cursor = db.state().find({"status": statedb.DONE})
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def detect_new_filings(session: requests.Session, enterprise: dict) -> list[dict]:
    """Dépôts exposés par NBB aujourd'hui mais absents de la StateDB de l'entreprise."""
    number = enterprise["_id"]
    known = {f.get("reference") for f in enterprise.get("filings", [])}
    current = [f for f in nbb.list_filings(session, number) if f["year"] >= nbb.MIN_YEAR]
    return [f for f in current if f["reference"] not in known]


def download_new(session: requests.Session, enterprise: dict, new_filings: list[dict],
                 delay: float = 0.5) -> int:
    """Télécharge et enregistre (StateDB + stockage) les nouveaux dépôts."""
    number = enterprise["_id"]
    count = 0
    for filing in new_filings:
        content = nbb.download_filing(session, filing["id"])
        if content is None:
            continue
        path = storage.store(number, filing["year"], filing["reference"], content)
        statedb.add_filing(number, filing["reference"], filing["year"], path)
        count += 1
        time.sleep(delay)
    return count


def recompute_gold(numbers: list[str]) -> int:
    """Reconstruit le document Gold des entreprises données (upsert)."""
    gold.ensure_indexes()
    rebuilt = 0
    for number in numbers:
        enterprise = db.state().find_one({"_id": number})
        if not enterprise:
            continue
        document = gold.build_document(enterprise)
        if document is None:
            continue
        db.gold().update_one(
            {"enterprise_number": number}, {"$set": document}, upsert=True
        )
        rebuilt += 1
    return rebuilt


def fetch_new_filings(limit: int | None = None, delay: float = 0.5) -> list[str]:
    """Étapes 1-3 du DAG : détecte et télécharge les nouveaux dépôts.

    Renvoie la liste des numéros d'entreprise ayant reçu au moins un nouveau dépôt.
    """
    session = requests.Session()
    updated: list[str] = []
    for enterprise in list_done(limit):
        number = enterprise["_id"]
        try:
            new_filings = detect_new_filings(session, enterprise)
        except nbb.RateLimited:
            print("  [429] rate limit — arrêt (reprise possible plus tard)")
            break
        if not new_filings:
            continue
        downloaded = download_new(session, enterprise, new_filings, delay)
        if downloaded:
            updated.append(number)
            print(f"  [MAJ] {number} : +{downloaded} nouveau(x) dépôt(s)")
    return updated


def refresh_all(limit: int | None = None, delay: float = 0.5) -> dict:
    """Passe complète : nouveaux dépôts (1-3) puis recalcul Gold ciblé (4-5)."""
    updated = fetch_new_filings(limit=limit, delay=delay)
    rebuilt = recompute_gold(updated)
    summary = {"updated_enterprises": len(updated), "gold_rebuilt": rebuilt}
    print(f"\nIncrémental : {len(updated)} entreprise(s) avec nouveaux dépôts, "
          f"{rebuilt} document(s) Gold recalculé(s).")
    return summary
