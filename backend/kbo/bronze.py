"""Couche Bronze : ingestion des CSV KBO -> collection enterprise_finale.

Approche par staging (jointure côté base, mémoire Python constante) :
  1. Chaque CSV est chargé en flux dans une collection `raw_<table>` (lecture
     ligne à ligne + insertion par lots -> aucune donnée n'est accumulée en RAM).
  2. `enterprise_finale` est assemblée entièrement par agrégation MongoDB :
     document de base issu de raw_enterprise, puis pour chaque table enfant un
     `$group` par numéro d'entité suivi d'un `$merge` dans le document parent.

La jointure est donc réalisée par MongoDB (avec spill sur disque si besoin), pas
en mémoire Python. Un document par entreprise, enfants imbriqués, données brutes.
"""
from __future__ import annotations

import csv
from tqdm import tqdm

from . import config, db

# Table parente : clé = numéro d'entreprise, colonnes métier conservées.
_ENTERPRISE = {
    "name": "enterprise",
    "file": "enterprise.csv",
    "key": "EnterpriseNumber",
    "cols": ["Status", "JuridicalSituation", "TypeOfEnterprise",
             "JuridicalForm", "JuridicalFormCAC", "StartDate"],
}

# Tables enfants : (collection cible imbriquée, clé de jointure, colonnes).
_CHILDREN = [
    {"name": "denomination", "file": "denomination.csv", "key": "EntityNumber",
     "field": "denominations", "cols": ["Language", "TypeOfDenomination", "Denomination"]},
    {"name": "address", "file": "address.csv", "key": "EntityNumber",
     "field": "addresses", "cols": ["TypeOfAddress", "CountryNL", "CountryFR", "Zipcode",
                                    "MunicipalityNL", "MunicipalityFR", "StreetNL", "StreetFR",
                                    "HouseNumber", "Box", "ExtraAddressInfo", "DateStrikingOff"]},
    {"name": "activity", "file": "activity.csv", "key": "EntityNumber",
     "field": "activities", "cols": ["ActivityGroup", "NaceVersion", "NaceCode", "Classification"]},
    {"name": "contact", "file": "contact.csv", "key": "EntityNumber",
     "field": "contacts", "cols": ["EntityContact", "ContactType", "Value"]},
    # establishment.csv est clé par le numéro d'entreprise (et non trié) : le
    # $group MongoDB le regroupe sans tri ni chargement en mémoire côté Python.
    {"name": "establishment", "file": "establishment.csv", "key": "EnterpriseNumber",
     "field": "establishments", "cols": ["EstablishmentNumber", "StartDate"]},
]


def _clean(value: str | None) -> str | None:
    """Chaîne vide -> None ; sinon valeur nettoyée."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _raw_name(table: str) -> str:
    return f"raw_{table}"


def _load_raw(spec: dict, limit: int | None, batch_size: int = 5000) -> None:
    """Charge un CSV KBO dans sa collection `raw_<table>`, en flux (RAM constante).

    Le numéro d'entité est stocké dans `_ent` pour uniformiser la jointure."""
    coll = db.database()[_raw_name(spec["name"])]
    coll.drop()
    path = config.KBO_DIR / spec["file"]

    batch: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(tqdm(reader, desc=f"  raw_{spec['name']}", unit=" l")):
            if limit is not None and i >= limit:
                break
            doc = {col: _clean(row.get(col)) for col in spec["cols"]}
            doc["_ent"] = row[spec["key"]]
            batch.append(doc)
            if len(batch) >= batch_size:
                coll.insert_many(batch, ordered=False)
                batch.clear()
        if batch:
            coll.insert_many(batch, ordered=False)

    coll.create_index("_ent")


def _assemble(target_name: str) -> None:
    """Assemble enterprise_finale à partir des collections raw_* (100 % MongoDB)."""
    database = db.database()
    database[target_name].drop()

    # 1. Document de base : une entreprise par ligne de raw_enterprise, enfants vides.
    base_projection: dict = {"_id": "$_ent", "EnterpriseNumber": "$_ent"}
    for col in _ENTERPRISE["cols"]:
        base_projection[col] = f"${col}"
    for child in _CHILDREN:
        base_projection[child["field"]] = {"$literal": []}
    database[_raw_name("enterprise")].aggregate(
        [
            {"$project": base_projection},
            {"$merge": {"into": target_name, "on": "_id",
                        "whenMatched": "replace", "whenNotMatched": "insert"}},
        ],
        allowDiskUse=True,
    )

    # 2. Chaque enfant : regroupé par entité puis fusionné dans le parent.
    #    whenNotMatched=discard écarte les entités qui ne sont pas des entreprises
    #    (ex. activités/adresses rattachées à un établissement).
    for child in _CHILDREN:
        pushed = {col: f"${col}" for col in child["cols"]}
        database[_raw_name(child["name"])].aggregate(
            [
                {"$group": {"_id": "$_ent", child["field"]: {"$push": pushed}}},
                {"$merge": {"into": target_name, "on": "_id",
                            "whenMatched": "merge", "whenNotMatched": "discard"}},
            ],
            allowDiskUse=True,
        )


def _index_target(target_name: str) -> None:
    coll = db.database()[target_name]
    coll.create_index("Status")
    coll.create_index("TypeOfEnterprise")
    coll.create_index("JuridicalForm")
    coll.create_index("activities.NaceCode")
    coll.create_index("activities.Classification")


def _drop_raw() -> None:
    for spec in [_ENTERPRISE, *_CHILDREN]:
        db.database()[_raw_name(spec["name"])].drop()


def build(limit: int | None = None, keep_staging: bool = False) -> int:
    """Reconstruit la collection Bronze depuis les CSV KBO via staging MongoDB."""
    print(f"Bronze -> {config.MONGO_DB}.{config.BRONZE_COLLECTION}")
    print(f"Source : {config.KBO_DIR.resolve()}")

    print("Chargement des CSV dans les collections raw_* ...")
    for spec in [_ENTERPRISE, *_CHILDREN]:
        _load_raw(spec, limit)

    print("Assemblage de enterprise_finale (jointure MongoDB) ...")
    _assemble(config.BRONZE_COLLECTION)

    print("Création des index ...")
    _index_target(config.BRONZE_COLLECTION)

    if not keep_staging:
        print("Suppression des collections raw_* ...")
        _drop_raw()

    total = db.bronze().estimated_document_count()
    print(f"Bronze terminé : {total:,} entreprises.")
    return total
