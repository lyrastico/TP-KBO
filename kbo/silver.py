"""Couche Silver : enterprise_finale (Bronze) -> enterprise_silver (nettoyé).

Le Bronze reste intact. Chaque document Silver applique :
  1. Normalisation des dates DD-MM-YYYY -> YYYY-MM-DD
  2. Déduplication des activités (même NaceCode exact + même Classification)
  3. Adresse unique : on ne garde que le siège (TypeOfAddress = REGO)
  4. Dénomination principale (TypeOfDenomination = 001) placée en premier
  5. Décodage des codes -> labels FR (via code.csv), codes originaux conservés
"""
from __future__ import annotations

import re

from tqdm import tqdm

from . import codes, config, db

_DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
_MAIN_DENOMINATION = "001"
_REGO = "REGO"


def normalize_date(value: str | None) -> str | None:
    """DD-MM-YYYY -> YYYY-MM-DD. Valeur inchangée si le format ne correspond pas."""
    if not value:
        return value
    match = _DATE_RE.match(value.strip())
    if not match:
        return value
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _dedupe_activities(activities: list[dict]) -> list[dict]:
    """Déduplique sur (NaceCode, Classification). En cas de doublon, on conserve
    la version NACE la plus récente pour un libellé plus riche."""
    best_by_key: dict[tuple[str | None, str | None], dict] = {}
    order: list[tuple[str | None, str | None]] = []
    for activity in activities:
        key = (activity.get("NaceCode"), activity.get("Classification"))
        if key not in best_by_key:
            best_by_key[key] = activity
            order.append(key)
        else:
            current_version = best_by_key[key].get("NaceVersion") or "0"
            new_version = activity.get("NaceVersion") or "0"
            if new_version.isdigit() and current_version.isdigit() and int(new_version) > int(current_version):
                best_by_key[key] = activity
    # MAIN d'abord, puis tri par code pour un ordre stable.
    deduped = [best_by_key[key] for key in order]
    deduped.sort(key=lambda activity: (activity.get("Classification") != "MAIN", activity.get("NaceCode") or ""))
    return deduped


def _decorate_activities(activities: list[dict]) -> list[dict]:
    decorated = []
    for activity in _dedupe_activities(activities):
        activity = dict(activity)
        activity["NaceLabel"] = codes.nace_label(activity.get("NaceVersion"), activity.get("NaceCode"))
        decorated.append(activity)
    return decorated


def _order_denominations(denominations: list[dict]) -> list[dict]:
    """Nom officiel (001) en premier, labels ajoutés."""
    ordered = []
    for denomination in denominations:
        denomination = dict(denomination)
        denomination["TypeOfDenominationLabel"] = codes.label(
            "TypeOfDenomination", denomination.get("TypeOfDenomination"))
        ordered.append(denomination)
    ordered.sort(key=lambda denomination: denomination.get("TypeOfDenomination") != _MAIN_DENOMINATION)
    return ordered


def _official_name(denominations: list[dict]) -> str | None:
    officials = [d for d in denominations if d.get("TypeOfDenomination") == _MAIN_DENOMINATION]
    # Préfère la version française si disponible (Language 2 = FR dans KBO).
    officials.sort(key=lambda denomination: denomination.get("Language") != "2")
    for denomination in officials or denominations:
        if denomination.get("Denomination"):
            return denomination["Denomination"]
    return None


def _registered_address(addresses: list[dict]) -> dict | None:
    for address in addresses:
        if address.get("TypeOfAddress") == _REGO:
            address = dict(address)
            address["TypeOfAddressLabel"] = codes.label("TypeOfAddress", _REGO)
            return address
    return None


def transform(doc: dict) -> dict:
    denominations = _order_denominations(doc.get("denominations", []))
    silver = {
        "_id": doc["_id"],
        "EnterpriseNumber": doc.get("EnterpriseNumber"),
        # Codes originaux conservés + labels ajoutés.
        "Status": doc.get("Status"),
        "StatusLabel": codes.label("Status", doc.get("Status")),
        "JuridicalSituation": doc.get("JuridicalSituation"),
        "JuridicalSituationLabel": codes.label("JuridicalSituation", doc.get("JuridicalSituation")),
        "TypeOfEnterprise": doc.get("TypeOfEnterprise"),
        "TypeOfEnterpriseLabel": codes.label("TypeOfEnterprise", doc.get("TypeOfEnterprise")),
        "JuridicalForm": doc.get("JuridicalForm"),
        "JuridicalFormLabel": codes.label("JuridicalForm", doc.get("JuridicalForm")),
        "JuridicalFormCAC": doc.get("JuridicalFormCAC"),
        "JuridicalFormCACLabel": codes.label("JuridicalForm", doc.get("JuridicalFormCAC")),
        # 1. Date normalisée (original conservé).
        "StartDate": normalize_date(doc.get("StartDate")),
        "StartDateOriginal": doc.get("StartDate"),
        # 4. Dénomination principale en tête + nom officiel pratique.
        "name": _official_name(denominations),
        "denominations": denominations,
        # 3. Adresse unique (siège REGO).
        "address": _registered_address(doc.get("addresses", [])),
        # 2. + 5. Activités dédupliquées et labellisées.
        "activities": _decorate_activities(doc.get("activities", [])),
        "contacts": doc.get("contacts", []),
        "establishments": [
            {**establishment, "StartDate": normalize_date(establishment.get("StartDate"))}
            for establishment in doc.get("establishments", [])
        ],
    }
    return silver


def build(limit: int | None = None, batch_size: int = 5000) -> int:
    src = db.bronze()
    dst = db.silver()

    print(f"Silver : {config.BRONZE_COLLECTION} -> {config.SILVER_COLLECTION}")
    dst.drop()

    query: dict = {}
    total_docs = src.estimated_document_count()
    cursor = src.find(query, no_cursor_timeout=True)
    if limit is not None:
        cursor = cursor.limit(limit)
        total_docs = min(total_docs, limit)

    total = 0
    batch: list[dict] = []
    try:
        for doc in tqdm(cursor, total=total_docs, desc="  silver", unit=" doc"):
            batch.append(transform(doc))
            if len(batch) >= batch_size:
                dst.insert_many(batch, ordered=False)
                total += len(batch)
                batch.clear()
        if batch:
            dst.insert_many(batch, ordered=False)
            total += len(batch)
    finally:
        cursor.close()

    print("Création des index Silver...")
    dst.create_index("Status")
    dst.create_index("TypeOfEnterprise")
    dst.create_index("JuridicalForm")
    dst.create_index("activities.NaceCode")
    dst.create_index("StartDate")

    print(f"Silver terminé : {total:,} entreprises.")
    return total
