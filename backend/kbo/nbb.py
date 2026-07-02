"""Scraping des dépôts financiers NBB CBSO (PART 2).

Utilise l'API publique de consultation (celle du site consult.cbso.nbb.be), qui
donne accès aux comptes annuels — données publiques par la loi belge — sans clé ni
authentification. Piloté par la StateDB : pour chaque entreprise `pending`, on liste
ses dépôts publiés, on garde ceux d'exercice >= 2021, on télécharge le CSV comptable
et on le stocke (HDFS/local), puis on passe l'entreprise à `done`.

Endpoints publics (ceux appelés par la SPA Angular du site) :
    Liste des dépôts   GET /api/rs-consult/published-deposits
                           ?page=&size=&enterpriseNumber=&sort=depositDate,desc
    CSV d'un dépôt     GET /api/external/broker/public/deposits/consult/csv/{id}
    (aussi disponibles : /deposits/pdf/{id}, /deposits/xbrl/{id})

Politesse : un délai est respecté entre les requêtes (service public, on ne le
surcharge pas). Un HTTP 429 lève RateLimited ; l'entreprise en cours repasse en
`pending` et le scraping s'arrête proprement. La StateDB (dépôts déjà téléchargés)
permet de reprendre sans tout relancer.
"""
from __future__ import annotations

import re
import time

import requests

from . import config, statedb, storage

CONSULT_BASE = "https://consult.cbso.nbb.be"
PUBLIC_API = f"{CONSULT_BASE}/api"

# En-têtes navigateur : la passerelle Azure du site rejette les requêtes qui ne
# ressemblent pas à l'application web.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,nl;q=0.8,en;q=0.7",
    "Referer": f"{CONSULT_BASE}/",
}

MIN_YEAR = config.NBB_MIN_YEAR
_PAGE_SIZE = 100
_MAX_PAGES = 50  # garde-fou

# Backoff sur 429 : on respecte le signal du serveur en ralentissant avant de réessayer.
_RETRY_BACKOFFS = (10, 20, 40, 60)  # secondes (le bucket se recharge en quelques s)


class RateLimited(Exception):
    """HTTP 429 persistant malgré les temporisations."""


def _clean_num(enterprise_number: str) -> str:
    return re.sub(r"\D", "", enterprise_number)


def _get(session: requests.Session, url: str, accept: str = "application/json") -> requests.Response | None:
    """GET poli : sur 429, attend (Retry-After ou backoff) puis réessaie.

    Renvoie None sur erreur réseau/4xx-5xx. Lève RateLimited si le 429 persiste
    après toutes les temporisations (le scraping s'arrête alors proprement)."""
    for attempt in range(len(_RETRY_BACKOFFS) + 1):
        try:
            response = session.get(url, timeout=30, headers={**BROWSER_HEADERS, "Accept": accept})
        except requests.RequestException as exc:
            print(f"    Erreur réseau: {exc}")
            return None
        if response.status_code != 429:
            break
        if attempt == len(_RETRY_BACKOFFS):
            raise RateLimited(url)
        retry_after = response.headers.get("Retry-After")
        wait = int(retry_after) if (retry_after or "").isdigit() else _RETRY_BACKOFFS[attempt]
        print(f"    [429] rate limit — pause {wait}s puis réessai ({attempt + 1}/{len(_RETRY_BACKOFFS)})")
        time.sleep(wait)
    if response.status_code >= 400:
        return None
    return response


def list_filings(session: requests.Session, enterprise_number: str) -> list[dict]:
    """Liste les dépôts publiés d'une entreprise -> [{id, reference, year, type}]."""
    number = _clean_num(enterprise_number)
    filings: list[dict] = []
    for page in range(_MAX_PAGES):
        url = (f"{PUBLIC_API}/rs-consult/published-deposits"
               f"?page={page}&size={_PAGE_SIZE}&enterpriseNumber={number}&sort=depositDate,desc")
        response = _get(session, url)
        if not response:
            break
        try:
            data = response.json()
        except ValueError:
            break
        for deposit in data.get("content", []):
            deposit_id = deposit.get("id")
            year = deposit.get("periodEndDateYear")
            if deposit_id and year:
                filings.append({
                    "id": deposit_id,
                    "reference": str(deposit.get("reference") or deposit_id),
                    "year": int(year),
                    "type": deposit.get("importFileType"),
                })
        if data.get("last", True) or not data.get("content"):
            break
    return filings


def download_filing(session: requests.Session, deposit_id: str) -> bytes | None:
    """Télécharge le CSV comptable d'un dépôt (codes PCMN et valeurs)."""
    url = f"{PUBLIC_API}/external/broker/public/deposits/consult/csv/{deposit_id}"
    response = _get(session, url, accept="text/csv,*/*")
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
        content = download_filing(session, filing["id"])
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
        time.sleep(delay)

    summary = {"processed": processed_count, "downloaded": downloaded_count, "state": statedb.stats()}
    print(f"\nScraping : {processed_count} entreprises traitées, {downloaded_count} dépôts. "
          f"État : {summary['state']}")
    return summary
