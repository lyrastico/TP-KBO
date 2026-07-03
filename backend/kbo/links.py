"""Liens d'une entreprise : liens entre entités (kbopub) + liens externes officiels.

Deux natures de liens, exposés par un seul endpoint `/links` :

  - **Liens entre entités** : relations juridiques entre numéros BCE (absorption,
    scission, relation inconnue, ...). Contenu *dynamique* → scrapé depuis kbopub
    (section « Liens entre entités »), puis **persisté** dans la collection
    `entity_links` (même logique « scrape une fois » que les dirigeants).

  - **Liens externes** : registres publics officiels (Moniteur belge, comptes
    annuels BNB, actes notariés/statuts, répertoire des employeurs). Leurs URLs
    sont **déterministes** à partir du numéro BCE : on les construit directement,
    aucun scraping requis. Ce sont les « documents juridiques » et « publications »
    de l'entreprise.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from . import db

KBOPUB_URL = "https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_BCE_RE = re.compile(r"\d{4}\.\d{3}\.\d{3}")
_SINCE_RE = re.compile(r"depuis le\s+(.+)$", re.IGNORECASE)
_NAME_RE = re.compile(r"\(([^)]+)\)")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --- Liens externes (URLs déterministes) -----------------------------------

def external_links(enterprise_number: str) -> list[dict]:
    """Registres publics officiels de l'entreprise, catégorisés.

    `category` sépare les documents juridiques (statuts/actes, comptes annuels)
    des publications (Moniteur belge) et des autres registres.
    """
    d = re.sub(r"\D", "", enterprise_number)
    return [
        {
            "label": "Publications au Moniteur belge",
            "url": f"https://www.ejustice.just.fgov.be/cgi_tsv/list.pl?language=fr&btw={d}&page=1&view_numac={d}#SUM",
            "category": "publications",
        },
        {
            "label": "Publications des comptes annuels (BNB)",
            "url": f"https://consult.cbso.nbb.be/consult-enterprise/{d}",
            "category": "documents",
        },
        {
            "label": "Statuts et actes notariés",
            "url": f"https://statuts.notaire.be/stapor_v1/enterprise/{d}/statutes",
            "category": "documents",
        },
        {
            "label": "Répertoire des employeurs",
            "url": f"https://employer-identification-consult.socialsecurity.be/employer/enterprise/{d}",
            "category": "registres",
        },
    ]


# --- Liens entre entités (scrape kbopub) -----------------------------------

def parse_entity_links(html: str) -> list[dict]:
    """Extrait la section « Liens entre entités » -> [{number, name, relation, since}].

    Chaque ligne est une phrase du type « 0426.959.158 (IBIS HOTELS BELGIUM) est
    absorbée par cette entité depuis le 31 juillet 2004 ». On isole le numéro BCE
    lié, sa dénomination (entre parenthèses), la date d'effet, et on conserve la
    phrase complète comme libellé de relation.
    """
    soup = BeautifulSoup(html, "lxml")
    heading = next(
        (h for h in soup.find_all("h2") if "liens entre" in h.get_text(strip=True).lower()),
        None,
    )
    if heading is None:
        return []
    start_row = heading.find_parent("tr")
    result: list[dict] = []
    for row in start_row.find_next_siblings("tr"):
        # Fin de section : cellule de titre suivante (classe "I").
        if row.find("td", class_="I"):
            break
        text = _clean(row.get_text(" ", strip=True))
        number_match = _BCE_RE.search(text)
        if not number_match:
            continue
        number = number_match.group(0)
        name_match = _NAME_RE.search(text)
        since_match = _SINCE_RE.search(text)
        since = since_match.group(1).strip() if since_match else None
        # Relation = phrase sans la queue « depuis le ... » (déjà portée par `since`).
        relation = _SINCE_RE.sub("", text).strip() if since else text
        result.append({
            "number": number,
            "name": name_match.group(1).strip() if name_match else None,
            "relation": relation,
            "since": since,
        })
    return result


def _dedupe_by_number(entity_links: list[dict]) -> list[dict]:
    """Une ligne par entité liée. kbopub liste chaque relation dans les deux sens
    (« X liée à cette entité » et « cette entité liée à X ») : on ne garde que la
    première occurrence de chaque numéro, en préservant l'ordre d'apparition."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for link in entity_links:
        number = link.get("number")
        if number in seen:
            continue
        seen.add(number)
        deduped.append(link)
    return deduped


def scrape_entity_links(enterprise_number: str) -> list[dict]:
    """Interroge kbopub et renvoie les liens entre entités (peut être vide)."""
    digits = re.sub(r"\D", "", enterprise_number)
    response = requests.get(
        KBOPUB_URL,
        params={"lang": "fr", "ondernemingsnummer": digits},
        headers=_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = "windows-1252"  # kbopub sert la page en Latin-1
    return _dedupe_by_number(parse_entity_links(response.text))


def _annotate_in_db(entity_links: list[dict]) -> list[dict]:
    """Ajoute `in_db` à chaque lien : l'entité liée est-elle présente en Silver ?

    Beaucoup d'entités liées ont été absorbées/radiées (ex. sociétés absorbées) et
    ne figurent donc pas dans l'export KBO Open Data courant : leur fiche n'existe
    pas chez nous. Ce drapeau permet au frontend de ne rendre cliquables que les
    entités réellement consultables. Calculé à la lecture (jamais persisté) pour
    rester juste après un ré-import.
    """
    # Dédoublonnage aussi à la lecture : les documents persistés avant l'ajout du
    # dédoublonnage à l'écriture contiennent encore les deux sens de chaque relation.
    entity_links = _dedupe_by_number(entity_links)
    numbers = list({link["number"] for link in entity_links if link.get("number")})
    if not numbers:
        return entity_links
    present = {
        doc["_id"]
        for doc in db.silver().find({"_id": {"$in": numbers}}, {"_id": 1})
    }
    return [{**link, "in_db": link.get("number") in present} for link in entity_links]


def get_or_scrape(enterprise_number: str) -> dict:
    """Renvoie les liens (entités persistés + externes déterministes).

    Les liens entre entités sont scrapés une seule fois puis persistés dans
    `entity_links` ; les liens externes sont toujours reconstruits à la volée.
    Le drapeau `in_db` de chaque entité liée est recalculé à chaque lecture.
    """
    external = external_links(enterprise_number)
    cached = db.entity_links().find_one({"_id": enterprise_number})
    if cached:
        return {
            "enterprise_number": enterprise_number,
            "entity_links": _annotate_in_db(cached.get("entity_links", [])),
            "external_links": external,
            "cached": True,
            "scraped_at": cached.get("scraped_at"),
        }
    entity = scrape_entity_links(enterprise_number)
    scraped_at = datetime.now(timezone.utc)
    db.entity_links().update_one(
        {"_id": enterprise_number},
        {"$set": {
            "enterprise_number": enterprise_number,
            "entity_links": entity,
            "scraped_at": scraped_at,
            "source": "kbopub",
        }},
        upsert=True,
    )
    return {
        "enterprise_number": enterprise_number,
        "entity_links": _annotate_in_db(entity),
        "external_links": external,
        "cached": False,
        "scraped_at": scraped_at,
    }
