"""Couche Bronze : ingestion des CSV KBO -> collection enterprise_finale.

Un document par entreprise, avec ses enfants imbriqués (dénominations, adresses,
activités, contacts, établissements). Les données restent brutes : aucune
transformation métier n'est appliquée ici (c'est le rôle du Silver).

Stratégie mémoire : les fichiers enterprise/denomination/address/activity/contact
sont triés par numéro d'entité -> jointure par fusion en streaming (mémoire
constante, supporte les 34 M lignes d'activités). establishment.csv n'est pas trié
par entreprise -> préchargé dans un dictionnaire (1,7 M lignes).
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Iterator

from pymongo import ASCENDING
from tqdm import tqdm

from . import config, db

# Colonnes conservées pour chaque table enfant (hors clé de jointure).
_DENOMINATION_COLS = ["Language", "TypeOfDenomination", "Denomination"]
_ADDRESS_COLS = [
    "TypeOfAddress", "CountryNL", "CountryFR", "Zipcode",
    "MunicipalityNL", "MunicipalityFR", "StreetNL", "StreetFR",
    "HouseNumber", "Box", "ExtraAddressInfo", "DateStrikingOff",
]
_ACTIVITY_COLS = ["ActivityGroup", "NaceVersion", "NaceCode", "Classification"]
_CONTACT_COLS = ["EntityContact", "ContactType", "Value"]


def _clean(value: str | None) -> str | None:
    """Chaîne vide -> None ; sinon valeur nettoyée."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _project(row: dict, cols: list[str]) -> dict:
    return {c: _clean(row.get(c)) for c in cols}


class _ChildStream:
    """Lecteur d'un CSV enfant trié par clé, consommé par fusion.

    take(target) renvoie toutes les lignes dont la clé == target, en ignorant au
    passage les lignes orphelines (clé < target).
    """

    def __init__(self, path: Path, key: str, cols: list[str]):
        self._f = open(path, newline="", encoding="utf-8")
        self._reader = csv.DictReader(self._f)
        self._key = key
        self._cols = cols
        self._cur: dict | None = None
        self._advance()

    def _advance(self) -> None:
        self._cur = next(self._reader, None)

    def take(self, target: str) -> list[dict]:
        while self._cur is not None and self._cur[self._key] < target:
            self._advance()
        rows: list[dict] = []
        while self._cur is not None and self._cur[self._key] == target:
            rows.append(_project(self._cur, self._cols))
            self._advance()
        return rows

    def close(self) -> None:
        self._f.close()


def _write_sorted_establishments(path: Path, tmp_dir: Path) -> Path:
    """establishment.csv n'est pas trié par entreprise. On le trie une fois vers un
    fichier temporaire (pic mémoire transitoire, libéré ensuite) pour le consommer
    ensuite en stream-merge -> mémoire constante pendant l'ingestion principale."""
    rows: list[tuple[str, str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="  tri établissements", unit=" lignes"):
            rows.append((
                row.get("EnterpriseNumber", ""),
                row.get("EstablishmentNumber", "") or "",
                row.get("StartDate", "") or "",
            ))
    rows.sort(key=lambda row: row[0])
    out = tmp_dir / "establishment_sorted.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["EnterpriseNumber", "EstablishmentNumber", "StartDate"])
        writer.writerows(rows)
    rows.clear()  # libère le pic mémoire avant la fusion principale
    return out


def _iter_documents(kbo_dir: Path, tmp_dir: Path, limit: int | None) -> Iterator[dict]:
    est_path = _write_sorted_establishments(kbo_dir / "establishment.csv", tmp_dir)

    denom = _ChildStream(kbo_dir / "denomination.csv", "EntityNumber", _DENOMINATION_COLS)
    addr = _ChildStream(kbo_dir / "address.csv", "EntityNumber", _ADDRESS_COLS)
    acts = _ChildStream(kbo_dir / "activity.csv", "EntityNumber", _ACTIVITY_COLS)
    cont = _ChildStream(kbo_dir / "contact.csv", "EntityNumber", _CONTACT_COLS)
    estab = _ChildStream(est_path, "EnterpriseNumber", ["EstablishmentNumber", "StartDate"])

    try:
        with open(kbo_dir / "enterprise.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if limit is not None and i >= limit:
                    break
                num = row["EnterpriseNumber"]
                yield {
                    "_id": num,
                    "EnterpriseNumber": num,
                    "Status": _clean(row.get("Status")),
                    "JuridicalSituation": _clean(row.get("JuridicalSituation")),
                    "TypeOfEnterprise": _clean(row.get("TypeOfEnterprise")),
                    "JuridicalForm": _clean(row.get("JuridicalForm")),
                    "JuridicalFormCAC": _clean(row.get("JuridicalFormCAC")),
                    "StartDate": _clean(row.get("StartDate")),
                    "denominations": denom.take(num),
                    "addresses": addr.take(num),
                    "activities": acts.take(num),
                    "contacts": cont.take(num),
                    "establishments": estab.take(num),
                }
    finally:
        denom.close()
        addr.close()
        acts.close()
        cont.close()
        estab.close()


def build(limit: int | None = None, batch_size: int = 1000) -> int:
    """Reconstruit intégralement la collection Bronze depuis les CSV KBO."""
    kbo_dir = config.KBO_DIR
    coll = db.bronze()

    print(f"Bronze -> {config.MONGO_DB}.{config.BRONZE_COLLECTION}")
    print(f"Source : {kbo_dir.resolve()}")
    coll.drop()  # rebuild propre et idempotent

    total = 0
    batch: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="kbo_bronze_") as tmp:
        tmp_dir = Path(tmp)
        for doc in tqdm(_iter_documents(kbo_dir, tmp_dir, limit), desc="  entreprises", unit=" doc"):
            batch.append(doc)
            if len(batch) >= batch_size:
                coll.insert_many(batch, ordered=False)
                total += len(batch)
                batch.clear()
        if batch:
            coll.insert_many(batch, ordered=False)
            total += len(batch)

    print("Création des index (Status, TypeOfEnterprise, JuridicalForm, activités)...")
    coll.create_index([("Status", ASCENDING)])
    coll.create_index([("TypeOfEnterprise", ASCENDING)])
    coll.create_index([("JuridicalForm", ASCENDING)])
    coll.create_index([("activities.NaceCode", ASCENDING)])
    coll.create_index([("activities.Classification", ASCENDING)])

    print(f"Bronze terminé : {total:,} entreprises.")
    return total
