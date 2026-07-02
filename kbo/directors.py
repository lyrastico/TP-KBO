"""Dirigeants (fonctions) d'une entreprise, scrapés depuis kbopub (BCE Public Search).

Source : page publique https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html
La section « Fonctions » liste les mandataires (Administrateur, Gérant, ...) avec
leur nom et la date depuis laquelle ils exercent.

Les dirigeants ne sont scrapés qu'**une seule fois** par entreprise : le résultat
est persisté dans la collection `directors` et servi tel quel ensuite (cf. énoncé,
« persiste en base après scrape »).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from . import db

KBOPUB_URL = "https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_FUNCTION_CELL = {"QL", "RL"}  # classes des cellules d'une ligne de fonction


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_name(text: str) -> str:
    # "Froidbise ,   Claude" -> "Froidbise, Claude"
    return _clean(text).replace(" ,", ",")


def parse(html: str) -> list[dict]:
    """Extrait les fonctions de la page kbopub -> [{function, name, since}]."""
    soup = BeautifulSoup(html, "lxml")
    heading = next((h for h in soup.find_all("h2") if h.get_text(strip=True) == "Fonctions"), None)
    if heading is None:
        return []
    start_row = heading.find_parent("tr")
    result: list[dict] = []
    for row in start_row.find_next_siblings("tr"):
        # Fin de section : prochain titre h2 (cellule de classe "I").
        if row.find("td", class_="I"):
            break
        cells = [c for c in row.find_all("td") if set(c.get("class") or []) & _FUNCTION_CELL]
        if len(cells) < 2:
            continue
        function = _clean(cells[0].get_text())
        name = _clean_name(cells[1].get_text())
        if not function or not name:
            continue
        since = _clean(cells[2].get_text()) if len(cells) > 2 else None
        result.append({"function": function, "name": name, "since": since})
    return result


def scrape(enterprise_number: str) -> list[dict]:
    """Interroge kbopub et renvoie la liste des fonctions (peut être vide)."""
    digits = re.sub(r"\D", "", enterprise_number)
    response = requests.get(
        KBOPUB_URL,
        params={"lang": "fr", "ondernemingsnummer": digits},
        headers=_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return parse(response.text)


def get_or_scrape(enterprise_number: str) -> dict:
    """Renvoie les dirigeants persistés ; scrape et persiste au premier appel."""
    cached = db.directors().find_one({"_id": enterprise_number})
    if cached:
        return {
            "enterprise_number": enterprise_number,
            "directors": cached.get("directors", []),
            "cached": True,
            "scraped_at": cached.get("scraped_at"),
        }
    directors = scrape(enterprise_number)
    scraped_at = datetime.now(timezone.utc)
    db.directors().update_one(
        {"_id": enterprise_number},
        {"$set": {
            "enterprise_number": enterprise_number,
            "directors": directors,
            "scraped_at": scraped_at,
            "source": "kbopub",
        }},
        upsert=True,
    )
    return {
        "enterprise_number": enterprise_number,
        "directors": directors,
        "cached": False,
        "scraped_at": scraped_at,
    }
