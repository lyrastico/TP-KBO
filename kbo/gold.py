"""Couche Gold : comptes annuels NBB -> ratios financiers consolidés (hotel_gold).

On lit les CSV PCMN bruts déposés en couche « HDFS » (chemins listés dans la
StateDB, cf. PART 2), on en extrait les postes comptables qui nous intéressent, on
calcule les ratios par exercice, et on consolide **un seul document par entreprise**
dans MongoDB (`hotel_gold`). Le tableau `years` porte tous les exercices, ce qui
évite les jointures multi-documents et donne l'historique complet en une requête.

Format des CSV NBB (séparateur virgule, deux colonnes `"clé","valeur"`) :
    - un bloc d'en-tête métadonnées (clés en toutes lettres : "Model code", ...)
    - puis les postes comptables : `"<code PCMN>","<montant>"`.

Mapping PCMN -> champ métier (cf. énoncé). La réalité des dépôts est que les
modèles complets rapportent souvent des **codes agrégés** (`10/15`, `54/58`,
`60/61`) plutôt que les codes unitaires. Chaque champ est donc résolu en
privilégiant l'agrégat normalisé quand il existe, sinon en sommant les composants.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from pymongo import ASCENDING, UpdateOne

from . import config, db, statedb

# --- Extraction des postes comptables --------------------------------------

def _to_float(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def parse_csv(content: bytes) -> tuple[dict[str, float], dict[str, str]]:
    """Parse un CSV NBB -> (postes {code_pcmn: montant}, métadonnées {clé: valeur}).

    Un poste est une ligne dont la première colonne commence par un chiffre
    (ex. "70", "10/15", "14P") ; tout le reste est une métadonnée d'en-tête.
    """
    text = content.decode("utf-8-sig", errors="replace")
    values: dict[str, float] = {}
    meta: dict[str, str] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        key, raw = row[0].strip(), row[1]
        if not key:
            continue
        if key[0].isdigit():
            amount = _to_float(raw)
            if amount is not None:
                values[key] = amount
        else:
            meta[key] = raw.strip()
    return values, meta


def _first(values: dict[str, float], *codes: str) -> float | None:
    """Premier code présent parmi une liste de candidats (agrégat -> unitaire)."""
    for code in codes:
        if code in values:
            return values[code]
    return None


def _sum(values: dict[str, float], codes: list[str]) -> float | None:
    present = [values[c] for c in codes if c in values]
    return sum(present) if present else None


def extract_accounts(values: dict[str, float]) -> dict[str, float | None]:
    """Postes métier issus des codes PCMN (cf. tableau de l'énoncé)."""
    tresorerie = _first(values, "54/58")
    if tresorerie is None:
        tresorerie = _sum(values, ["54", "55"])
    fonds_propres = _first(values, "10/15")
    if fonds_propres is None:
        fonds_propres = _sum(values, ["10", "11", "12", "13", "14", "15"])
    return {
        "ca": _first(values, "70"),
        "achats": _first(values, "60", "60/61"),
        "variation_stocks": _first(values, "71"),
        "ebit": _first(values, "9901"),
        "resultat_net": _first(values, "9904"),
        "tresorerie": tresorerie,
        "dettes_financieres": _sum(values, ["17", "43"]),
        "fonds_propres": fonds_propres,
        "capital_souscrit": _first(values, "100", "10"),
    }


# --- Ratios ----------------------------------------------------------------

def _div(numerator: float | None, denominator: float | None, factor: float = 1.0) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator * factor, 2)


def compute_ratios(acc: dict[str, float | None]) -> dict[str, float | None]:
    """Ratios financiers d'un exercice (None si donnée manquante / division par 0)."""
    return {
        "marge_nette_pct": _div(acc["resultat_net"], acc["ca"], 100),
        "roe_pct": _div(acc["resultat_net"], acc["fonds_propres"], 100),
        "ratio_liquidite": _div(acc["tresorerie"], acc["dettes_financieres"]),
        "taux_endettement_pct": _div(acc["dettes_financieres"], acc["fonds_propres"], 100),
    }


def _marge_brute(acc: dict[str, float | None], values: dict[str, float]) -> float | None:
    """Marge brute = CA - Achats + Variation stocks quand le CA est publié.

    Les petites structures (schémas abrégé/micro) ne publient pas le CA isolé mais
    déclarent directement la marge brute d'exploitation (code PCMN 9900) : on
    l'utilise en repli, ce qui couvre la grande majorité des dépôts.
    """
    if acc["ca"] is not None:
        return round(acc["ca"] - (acc["achats"] or 0) + (acc["variation_stocks"] or 0), 2)
    return _first(values, "9900")


# --- Type de schéma de dépôt -----------------------------------------------
# La distinction full/abrégé/micro n'est pas donnée telle quelle : on l'approxime
# par le niveau de détail du dépôt (nombre de postes PCMN renseignés), qui tiere
# nettement les modèles observés (~250 / ~100 / ~70). Le `model_code` brut est
# conservé par exercice pour permettre un remappage ultérieur si besoin.

def schema_type(values: dict[str, float]) -> str:
    n = len(values)
    if n >= 150:
        return "full"
    if n >= 90:
        return "abrege"
    return "micro"


# --- Construction d'un exercice --------------------------------------------

def build_year(content: bytes, fallback_year: int | None = None) -> dict | None:
    """Un objet exercice (postes + ratios) à partir d'un CSV de dépôt."""
    values, meta = parse_csv(content)
    if not values:
        return None
    end_date = meta.get("Accounting period end date", "")
    year = int(end_date[:4]) if end_date[:4].isdigit() else fallback_year
    if year is None:
        return None
    acc = extract_accounts(values)
    return {
        "year": year,
        **acc,
        "marge_brute": _marge_brute(acc, values),
        "ratios": compute_ratios(acc),
        "model_code": meta.get("Model code"),
        "reference": meta.get("Reference number"),
        "schema_type": schema_type(values),
    }


# --- Build de la couche Gold -----------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_indexes() -> None:
    db.gold().create_index([("enterprise_number", ASCENDING)], unique=True)


def build_document(enterprise: dict) -> dict | None:
    """Consolide un document Gold pour une entreprise à partir de ses dépôts StateDB.

    Renvoie None si aucun exercice exploitable (pas de dépôt lisible).
    """
    enterprise_number = enterprise["_id"]
    by_year: dict[int, dict] = {}
    for filing in enterprise.get("filings", []):
        path = filing.get("path")
        if not path:
            continue
        try:
            content = Path(path).read_bytes()
        except OSError:
            continue
        year_doc = build_year(content, fallback_year=filing.get("year"))
        if year_doc is None:
            continue
        year = year_doc["year"]
        # En cas de dépôts multiples pour un même exercice (initial + correction),
        # on garde la référence la plus récente (tri lexicographique croissant).
        kept = by_year.get(year)
        if kept is None or str(year_doc["reference"] or "") >= str(kept["reference"] or ""):
            by_year[year] = year_doc
    if not by_year:
        return None
    years = [by_year[y] for y in sorted(by_year)]
    return {
        "enterprise_number": enterprise_number,
        "name": enterprise.get("name"),
        "years": years,
        "schema_type": years[-1]["schema_type"],  # schéma de l'exercice le plus récent
        "last_updated": _now(),
    }


def build(limit: int | None = None, batch_size: int = 500) -> dict:
    """Reconstruit la couche Gold pour les entreprises `done` ayant des dépôts."""
    ensure_indexes()
    query = {"status": statedb.DONE, "filings.0": {"$exists": True}}
    cursor = db.state().find(query)
    if limit:
        cursor = cursor.limit(limit)

    operations: list[UpdateOne] = []
    processed, with_data, year_count = 0, 0, 0
    for enterprise in cursor:
        processed += 1
        document = build_document(enterprise)
        if document is None:
            continue
        with_data += 1
        year_count += len(document["years"])
        operations.append(UpdateOne(
            {"enterprise_number": document["enterprise_number"]},
            {"$set": document},
            upsert=True,
        ))
        if len(operations) >= batch_size:
            db.gold().bulk_write(operations, ordered=False)
            operations.clear()
            print(f"  ... {processed} entreprises traitées")
    if operations:
        db.gold().bulk_write(operations, ordered=False)

    summary = {"processed": processed, "with_data": with_data, "years": year_count}
    print(f"\nGold : {processed} entreprises · {with_data} avec données · {year_count} exercices "
          f"-> collection '{config.GOLD_COLLECTION}'")
    return summary
