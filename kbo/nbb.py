"""Scraping des dépôts financiers NBB CBSO (PART 2).

Piloté par la StateDB : pour chaque entreprise `pending`, on liste ses dépôts,
on garde ceux d'exercice >= 2021, on télécharge les données comptables et on les
stocke (HDFS/local), puis on passe l'entreprise à `done`.

API officielle NBB CBSO (webservice "authentic", production) — nécessite une clé
de souscription gratuite (https://developer.cbso.nbb.be), passée dans le header
`NBB-CBSO-Subscription-Key`. Sans clé, l'API renvoie 403.

Endpoints (guide technique CBSO v0.94) :
    Références d'une entité   GET /authentic/legalEntity/{numero}/references
    Données d'un dépôt        GET /authentic/deposit/{reference}/accountingData
                              Accept: application/json | application/pdf | application/x.zip+xbrl

Gestion du rate limit : un HTTP 429 lève RateLimited ; l'entreprise en cours est
remise en `pending` et le scraping s'arrête proprement. La StateDB (dépôts déjà
téléchargés) permet de reprendre sans tout relancer.
"""
from __future__ import annotations

import json
import re
import time

import requests

from . import config, statedb, storage

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 kbo-tp"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,nl;q=0.8,en;q=0.7",
}

MIN_YEAR = 2021
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class RateLimited(Exception):
    """HTTP 429 renvoyé par le NBB."""


class MissingApiKey(Exception):
    """Aucune clé de souscription NBB CBSO configurée."""


def _clean_num(num: str) -> str:
    return re.sub(r"\D", "", num)


def _auth_headers(extra: dict | None = None) -> dict:
    headers = dict(HEADERS)
    if config.NBB_API_KEY:
        headers["NBB-CBSO-Subscription-Key"] = config.NBB_API_KEY
    if extra:
        headers.update(extra)
    return headers


def _get(session: requests.Session, url: str, headers: dict, **kwargs) -> requests.Response | None:
    """GET avec détection du rate limit. Renvoie None sur erreur réseau/4xx-5xx."""
    try:
        response = session.get(url, timeout=30, headers=headers, **kwargs)
    except requests.RequestException as exc:
        print(f"    Erreur réseau: {exc}")
        return None
    if response.status_code == 429:
        raise RateLimited(url)
    if response.status_code == 403:
        raise MissingApiKey(url)
    if response.status_code >= 400:
        return None
    return response


def _infer_year(deposit: dict) -> int | None:
    for key in ("PeriodEndDate", "periodEndDate", "accountingYearEndDate", "ExerciseEndDate",
                "EndDate", "endDate", "ClosingDate"):
        value = deposit.get(key)
        if isinstance(value, str):
            match = re.search(r"(20\d{2}|19\d{2})", value)
            if match:
                return int(match.group(1))
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", json.dumps(deposit, ensure_ascii=False))]
    return min(years) if years else None


def _extract_reference(deposit: dict) -> str | None:
    for key in ("ReferenceNumber", "referenceNumber", "Reference", "reference", "id"):
        value = deposit.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    match = _UUID_RE.search(json.dumps(deposit, ensure_ascii=False))
    return match.group(0) if match else None


def _as_list(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("References", "references", "content", "items", "deposits", "results", "data"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
        return [data]
    return []


def list_filings(session: requests.Session, enterprise_number: str) -> list[dict]:
    """Liste les dépôts (références) d'une entité -> [{reference, year}]."""
    number = _clean_num(enterprise_number)
    url = f"{config.NBB_WS_BASE}/{config.NBB_WS_API}/legalEntity/{number}/references"
    response = _get(session, url, headers=_auth_headers({"Accept": "application/json"}))
    if not response:
        return []
    try:
        data = response.json()
    except ValueError:
        return []
    filings = []
    for deposit in _as_list(data):
        reference = _extract_reference(deposit)
        year = _infer_year(deposit)
        if reference and year:
            filings.append({"reference": reference, "year": year})
    return filings


def download_filing(session: requests.Session, reference: str) -> bytes | None:
    """Télécharge les données comptables (JSON) d'un dépôt."""
    url = f"{config.NBB_WS_BASE}/{config.NBB_WS_API}/deposit/{reference}/accountingData"
    response = _get(session, url, headers=_auth_headers({"Accept": "application/json"}))
    if response and response.content:
        return response.content
    return None


def _scrape_enterprise(session: requests.Session, enterprise: dict, delay: float) -> int:
    """Scrape une entreprise. Lève RateLimited pour arrêter proprement."""
    enterprise_number = enterprise["_id"]
    statedb.mark_in_progress(enterprise_number)

    filings = [f for f in list_filings(session, enterprise_number) if f["year"] >= MIN_YEAR]
    downloaded_count = 0
    for filing in filings:
        reference, year = filing["reference"], filing["year"]
        if statedb.is_filing_downloaded(enterprise_number, reference):
            downloaded_count += 1
            continue
        content = download_filing(session, reference)
        if content is None:
            continue
        path = storage.store(enterprise_number, year, reference, content)
        statedb.add_filing(enterprise_number, reference, year, path)
        downloaded_count += 1
        time.sleep(delay)

    statedb.mark_done(enterprise_number, downloaded_count)
    return downloaded_count


def scrape(limit: int | None = None, delay: float = 0.5) -> dict:
    """Scrape les entreprises `pending` de la StateDB. S'arrête proprement sur 429."""
    if not config.NBB_API_KEY:
        raise MissingApiKey(
            "NBB_API_KEY manquante. Crée un compte sur https://developer.cbso.nbb.be, "
            "souscris au produit de consultation, puis renseigne la clé dans .env (NBB_API_KEY)."
        )

    statedb.ensure_indexes()
    session = requests.Session()

    processed_count, downloaded_count = 0, 0
    pending_enterprises = list(statedb.iter_pending(limit))
    print(f"À scraper (pending) : {len(pending_enterprises)}")

    for enterprise in pending_enterprises:
        enterprise_number = enterprise["_id"]
        try:
            filings_downloaded = _scrape_enterprise(session, enterprise, delay)
            downloaded_count += filings_downloaded
            processed_count += 1
            print(f"  [OK] {enterprise_number} ({enterprise.get('name') or ''}) : {filings_downloaded} dépôt(s)")
        except RateLimited:
            statedb.mark_pending(enterprise_number)
            print(f"  [429] Too Many Requests sur {enterprise_number} — arrêt, reprise possible plus tard.")
            break
        except MissingApiKey:
            statedb.mark_pending(enterprise_number)
            print("  [403] Forbidden — clé NBB invalide ou produit non souscrit. Arrêt.")
            break
        time.sleep(delay)

    summary = {"processed": processed_count, "downloaded": downloaded_count, "state": statedb.stats()}
    print(f"\nScraping : {processed_count} entreprises traitées, {downloaded_count} dépôts. "
          f"État : {summary['state']}")
    return summary
