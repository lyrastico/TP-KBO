#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_kbo_strict.py

À placer au même niveau que le notebook .ipynb.

But : tenter de créer les CSV locaux attendus par le TP KBO/BCE uniquement à partir
 de données réellement récupérées en ligne. Aucune donnée de secours/manuelle n'est
 intégrée : si le scraping échoue ou ne donne rien, le script s'arrête avec une erreur.

Sortie : ./data/KBO/
  - enterprise.csv
  - denomination.csv
  - address.csv
  - activity.csv
  - contact.csv
  - establishment.csv
  - code.csv

Dépendances :
  pip install pandas requests beautifulsoup4 lxml

Usage :
  python scrape_kbo_strict.py
  python scrape_kbo_strict.py --force
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data") / "KBO"
RAW_DIR = Path("outputs") / "raw_scraping"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 student-tp-kbo"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,nl;q=0.8,en;q=0.7",
}

# Seulement les numéros d'entreprise demandés par le TP.
# Pas de noms, pas d'adresses, pas de données de secours.
COMPANY_NUMBERS = [
    "0878.065.378",  # Google Belgium
    "0836.157.420",  # Apple Belgium
    "0203.430.576",  # SNCB
]


def normalize_num(num: str) -> str:
    return re.sub(r"\D", "", str(num)).zfill(10)


def dotted_num(num: str) -> str:
    n = normalize_num(num)
    return f"{n[:4]}.{n[4:7]}.{n[7:]}"


def num_for_kbo_url(num: str) -> str:
    return normalize_num(num).lstrip("0")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def kbo_url(num: str, lang: str = "fr") -> str:
    return (
        "https://kbopub.economie.fgov.be/kbopub/"
        f"toonondernemingps.html?lang={lang}&ondernemingsnummer={num_for_kbo_url(num)}"
    )


def fetch(url: str, params: Optional[dict] = None, timeout: int = 30) -> Optional[str]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code >= 400:
            print(f"  ⚠️ HTTP {r.status_code} sur {url}")
            return None
        if not r.text or len(r.text.strip()) < 100:
            print(f"  ⚠️ Réponse vide ou trop courte sur {url}")
            return None
        return r.text
    except Exception as exc:
        print(f"  ⚠️ Requête impossible : {exc}")
        return None


def extract_kv_from_html(html: str) -> Dict[str, str]:
    """Extraction générique de paires libellé/valeur depuis tableaux HTML."""
    soup = BeautifulSoup(html, "lxml")
    kv: Dict[str, str] = {}

    for tr in soup.select("tr"):
        cells = [clean_text(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            key = cells[0].rstrip(" :")
            value = " | ".join(cells[1:])
            if key and value and len(key) < 140:
                kv[key] = value

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = clean_text(dt.get_text(" ")).rstrip(" :")
            value = clean_text(dd.get_text(" "))
            if key and value:
                kv[key] = value

    return kv


def first_matching(kv: Dict[str, str], patterns: List[str]) -> str:
    for pat in patterns:
        rgx = re.compile(pat, re.I)
        for key, value in kv.items():
            if rgx.search(key):
                return value
    return ""


def html_has_company_data(html: str, num: str, kv: Dict[str, str]) -> bool:
    plain = normalize_num(num)
    dotted = dotted_num(num)
    text = clean_text(BeautifulSoup(html, "lxml").get_text(" "))
    has_num = plain in re.sub(r"\D", "", text) or dotted in text
    has_kv = len(kv) >= 3
    looks_blocked = any(
        marker.lower() in text.lower()
        for marker in ["captcha", "access denied", "forbidden", "robot", "too many requests"]
    )
    return has_num and has_kv and not looks_blocked


def scrape_kbo_company(num: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    url = kbo_url(num)
    print(f"→ KBO Public Search : {dotted_num(num)}")
    html = fetch(url)
    if not html:
        raise RuntimeError(f"Impossible de récupérer la page KBO pour {dotted_num(num)}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"kbo_{normalize_num(num)}.html"
    raw_path.write_text(html, encoding="utf-8")

    kv = extract_kv_from_html(html)
    if not html_has_company_data(html, num, kv):
        raise RuntimeError(
            f"La page KBO récupérée pour {dotted_num(num)} ne contient pas de données exploitables. "
            f"HTML sauvegardé dans {raw_path}"
        )

    name = first_matching(kv, [r"d[ée]nomination", r"naam", r"name"])
    legal_form = first_matching(kv, [r"forme juridique", r"rechtsvorm", r"legal form"])
    situation = first_matching(kv, [r"situation juridique", r"juridische toestand", r"status"])
    start_date = first_matching(kv, [r"date de d[ée]but", r"begindatum", r"start"])
    enterprise_type = first_matching(kv, [r"type d.?entreprise", r"type onderneming"])
    address = first_matching(kv, [r"adresse", r"adres", r"address"])

    # Seules les valeurs réellement extraites sont écrites.
    data = {
        "EnterpriseNumber": dotted_num(num),
        "Name": name,
        "LegalForm": legal_form,
        "JuridicalSituation": situation,
        "StartDate": start_date,
        "TypeOfEnterprise": enterprise_type,
        "Address": address,
        "KboUrl": url,
    }

    required_any = [name, legal_form, situation, start_date, enterprise_type, address]
    if not any(required_any):
        raise RuntimeError(f"Aucun champ métier extrait pour {dotted_num(num)}")

    return data, kv


def scrape_ejustice_links(num: str) -> List[Dict[str, str]]:
    n = normalize_num(num).lstrip("0")
    url = "https://www.ejustice.just.fgov.be/cgi_tsv/list.pl"
    params = {"language": "fr", "btw": n}
    html = fetch(url, params=params)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    rows: List[Dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        txt = clean_text(a.get_text(" "))
        href = a["href"]
        if not txt and not href:
            continue
        if "tsv" in href.lower() or "article" in href.lower() or "pdf" in href.lower():
            if href.startswith("/"):
                href = "https://www.ejustice.just.fgov.be" + href
            elif href.startswith("."):
                href = "https://www.ejustice.just.fgov.be/cgi_tsv/" + href.lstrip("./")
            rows.append({
                "EnterpriseNumber": dotted_num(num),
                "Source": "eJustice / Moniteur belge",
                "Title": txt or "Lien publication",
                "Url": href,
            })
        if len(rows) >= 20:
            break
    return rows


def split_address(address: str) -> Dict[str, str]:
    """Découpage léger, uniquement à partir de l'adresse scrapée. Peut rester incomplet."""
    result = {
        "Zipcode": "",
        "Municipality": "",
        "Street": "",
        "HouseNumber": "",
        "ExtraAddressInfo": address or "",
    }
    if not address:
        return result

    # Exemples : "Rue X 12 1000 Bruxelles" ou "Rue X 12, 1000 Bruxelles".
    zip_match = re.search(r"\b(\d{4})\b\s+([^,|]+)", address)
    if zip_match:
        result["Zipcode"] = zip_match.group(1)
        result["Municipality"] = clean_text(zip_match.group(2))

    before_zip = address
    if zip_match:
        before_zip = address[: zip_match.start()].strip(" ,|")
    house_match = re.search(r"(.+?)\s+(\d+[A-Za-z]?(?:/\d+)?)\s*$", before_zip)
    if house_match:
        result["Street"] = clean_text(house_match.group(1))
        result["HouseNumber"] = clean_text(house_match.group(2))
    else:
        result["Street"] = clean_text(before_zip)

    return result


def build_tables(companies: List[Dict[str, str]]) -> Dict[str, pd.DataFrame]:
    enterprise_rows = []
    denomination_rows = []
    address_rows = []
    contact_rows = []
    establishment_rows = []
    activity_rows = []
    code_rows = []

    for c in companies:
        num = dotted_num(c["EnterpriseNumber"])
        plain = normalize_num(num)
        addr = split_address(c.get("Address", ""))

        enterprise_rows.append({
            "EnterpriseNumber": num,
            "TypeOfEnterprise": c.get("TypeOfEnterprise", ""),
            "JuridicalSituation": c.get("JuridicalSituation", ""),
            "StartDate": c.get("StartDate", ""),
            "LegalForm": c.get("LegalForm", ""),
            "Source": c.get("KboUrl", ""),
        })

        denomination_rows.append({
            "EnterpriseNumber": num,
            "Language": "",
            "TypeOfDenomination": "",
            "Denomination": c.get("Name", ""),
            "Source": c.get("KboUrl", ""),
        })

        address_rows.append({
            "EnterpriseNumber": num,
            "TypeOfAddress": "",
            "CountryNL": "",
            "CountryFR": "",
            "Zipcode": addr["Zipcode"],
            "MunicipalityNL": addr["Municipality"],
            "MunicipalityFR": addr["Municipality"],
            "StreetNL": addr["Street"],
            "StreetFR": addr["Street"],
            "HouseNumber": addr["HouseNumber"],
            "Box": "",
            "ExtraAddressInfo": addr["ExtraAddressInfo"],
            "DateStrikingOff": "",
            "Source": c.get("KboUrl", ""),
        })

        # Pas de site web inventé. Contact vide si non trouvé dans la page KBO.
        contact_rows.append({
            "EnterpriseNumber": num,
            "EntityContact": "",
            "ContactType": "",
            "Value": "",
            "Source": "",
        })

        establishment_rows.append({
            "EnterpriseNumber": num,
            "EstablishmentNumber": plain,
            "StartDate": c.get("StartDate", ""),
            "Source": c.get("KboUrl", ""),
        })

        # NACE non inventé : ligne vide pour compatibilité structurelle seulement.
        activity_rows.append({
            "EnterpriseNumber": num,
            "ActivityGroup": "",
            "NaceVersion": "",
            "NaceCode": "",
            "Classification": "",
            "Source": c.get("KboUrl", ""),
        })

    # Codes uniquement techniques, pas de valeurs métier inventées.
    code_rows.extend([
        {"Category": "TypeOfDenomination", "Code": "", "DescriptionFR": "", "DescriptionNL": ""},
        {"Category": "TypeOfAddress", "Code": "", "DescriptionFR": "", "DescriptionNL": ""},
        {"Category": "ContactType", "Code": "", "DescriptionFR": "", "DescriptionNL": ""},
        {"Category": "ActivityGroup", "Code": "", "DescriptionFR": "", "DescriptionNL": ""},
    ])

    return {
        "enterprise": pd.DataFrame(enterprise_rows),
        "denomination": pd.DataFrame(denomination_rows),
        "address": pd.DataFrame(address_rows),
        "activity": pd.DataFrame(activity_rows),
        "contact": pd.DataFrame(contact_rows),
        "establishment": pd.DataFrame(establishment_rows),
        "code": pd.DataFrame(code_rows),
    }


def validate_tables(tables: Dict[str, pd.DataFrame]) -> None:
    enterprise = tables["enterprise"]
    denomination = tables["denomination"]
    if enterprise.empty or denomination.empty:
        raise RuntimeError("Aucune entreprise exploitable : aucun CSV ne sera écrit.")

    has_name = denomination["Denomination"].fillna("").str.strip().ne("").any()
    has_core = enterprise[["TypeOfEnterprise", "JuridicalSituation", "StartDate", "LegalForm"]].fillna("").apply(
        lambda col: col.astype(str).str.strip().ne("")
    ).any().any()
    if not has_name and not has_core:
        raise RuntimeError("Données KBO trop vides : aucun champ réel n'a été extrait.")


def save_tables(tables: Dict[str, pd.DataFrame], force: bool = False) -> None:
    validate_tables(tables)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        path = OUT_DIR / f"{name}.csv"
        if path.exists() and not force:
            print(f"⚠️ Existe déjà, non écrasé : {path}  (utilise --force pour écraser)")
            continue
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"✅ Créé : {path} ({len(df)} lignes)")


def save_external_exports(kv_by_num: Dict[str, Dict[str, str]], ejustice_rows: List[Dict[str, str]], force: bool = False) -> None:
    out = Path("outputs")
    out.mkdir(exist_ok=True)

    kv_rows = []
    for num, kv in kv_by_num.items():
        for key, value in kv.items():
            kv_rows.append({"EnterpriseNumber": dotted_num(num), "Field": key, "Value": value})
    if kv_rows:
        path = out / "kbo_public_search_scrape.csv"
        if force or not path.exists():
            pd.DataFrame(kv_rows).to_csv(path, index=False, encoding="utf-8-sig")
            print(f"✅ Export scraping KBO : {path}")

    if ejustice_rows:
        path = out / "ejustice_publications_links.csv"
        if force or not path.exists():
            pd.DataFrame(ejustice_rows).to_csv(path, index=False, encoding="utf-8-sig")
            print(f"✅ Export liens eJustice : {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère des CSV KBO minimalistes par scraping strict, sans données de secours.")
    parser.add_argument("--force", action="store_true", help="Écrase les CSV existants dans data/KBO")
    args = parser.parse_args()

    print("=" * 78)
    print("Scraping KBO strict → CSV locaux pour le TP")
    print("Aucune donnée de secours ne sera utilisée.")
    print("=" * 78)
    print(f"Dossier de sortie : {OUT_DIR.resolve()}")

    scraped_companies: List[Dict[str, str]] = []
    kv_by_num: Dict[str, Dict[str, str]] = {}
    ejustice_rows: List[Dict[str, str]] = []
    failures: List[str] = []

    for num in COMPANY_NUMBERS:
        try:
            company, kv = scrape_kbo_company(num)
            scraped_companies.append(company)
            kv_by_num[num] = kv
            time.sleep(0.7)
            ejustice_rows.extend(scrape_ejustice_links(num))
            time.sleep(0.7)
        except Exception as exc:
            failures.append(f"{dotted_num(num)} : {exc}")
            print(f"❌ {failures[-1]}")

    if not scraped_companies:
        print("\nÉchec : aucune entreprise n'a été récupérée. Aucun CSV n'a été créé.")
        print("Détails :")
        for f in failures:
            print(f"  - {f}")
        return 2

    tables = build_tables(scraped_companies)
    save_tables(tables, force=args.force)
    save_external_exports(kv_by_num, ejustice_rows, force=args.force)

    if failures:
        print("\nAttention : certaines entreprises n'ont pas été récupérées :")
        for f in failures:
            print(f"  - {f}")
        print("Les CSV contiennent uniquement les entreprises réellement scrapées.")

    print("\nTerminé.")
    print("Maintenant dans VS Code : ouvre le notebook, puis fais Kernel > Restart Kernel > Run All.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
