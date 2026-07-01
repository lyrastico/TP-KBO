"""Chargement de code.csv en tables de correspondance code -> label.

code.csv : colonnes (Category, Code, Language, Description).
On construit un dictionnaire {(Category, Code): DescriptionFR} avec repli NL/EN.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from . import config

_PREFERRED_LANG = ("FR", "NL", "EN", "DE")


@lru_cache(maxsize=1)
def _load(path: str) -> dict[tuple[str, str], dict[str, str]]:
    table: dict[tuple[str, str], dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["Category"], row["Code"])
            table.setdefault(key, {})[row["Language"]] = row["Description"]
    return table


def label(category: str, code: str | None, lang: str = "FR") -> str | None:
    """Retourne le libellé d'un code pour une catégorie donnée (FR par défaut)."""
    if not code:
        return None
    langs = _load(str(config.KBO_DIR / "code.csv")).get((category, code))
    if not langs:
        return None
    if lang in langs:
        return langs[lang]
    for fallback in _PREFERRED_LANG:
        if fallback in langs:
            return langs[fallback]
    return next(iter(langs.values()), None)


def nace_label(nace_version: str | None, nace_code: str | None, lang: str = "FR") -> str | None:
    """Libellé NACE : la catégorie dépend de la version (Nace2003/2008/2025)."""
    if not nace_code:
        return None
    if nace_version:
        found = label(f"Nace{nace_version}", nace_code, lang)
        if found:
            return found
    # Repli : cherche le code dans n'importe quelle version NACE connue.
    for version in ("2025", "2008", "2003"):
        found = label(f"Nace{version}", nace_code, lang)
        if found:
            return found
    return None
