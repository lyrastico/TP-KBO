#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extraction stricte des comptes annuels NBB/CBSO pour le TP KBO.

Objectif : créer, quand c'est possible, les fichiers attendus par le notebook :
    outputs/nbb/csvs/<numero_sans_points>/<annee>.csv

Le script ne fabrique aucune donnée :
- il télécharge des documents publics depuis Consult si l'API publique est accessible ;
- il peut aussi utiliser les webservices CBSO officiels si tu fournis une clé API ;
- si seul un XBRL est disponible, il convertit les faits XBRL en CSV brut ;
- si seul un PDF est disponible, il le sauvegarde dans outputs/nbb/raw/... mais ne crée pas de faux CSV.

Installation minimale :
    pip install requests beautifulsoup4 pandas lxml

Utilisation :
    python extract_nbb_cbso.py
    python extract_nbb_cbso.py --years 2021 2022 2023 2024
    python extract_nbb_cbso.py --company 0878.065.378
    python extract_nbb_cbso.py --api-key VOTRE_CLE_NBB_CBSO

Notes :
- L'application Consult est gratuite, mais son API publique interne peut changer.
- Les webservices officiels nécessitent une souscription et une clé CBSO.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from lxml import etree

CONSULT_BASE = "https://consult.cbso.nbb.be"
PUBLIC_BASE = f"{CONSULT_BASE}/api/external/broker/public"
WS_BASE = "https://ws.cbso.nbb.be"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,nl;q=0.7",
}

COMPANIES = {
    "Google Belgium": "0878.065.378",
    "Apple Belgium": "0836.157.420",
    "SNCB": "0203.430.576",
}

DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]


@dataclass
class DepositRef:
    raw: dict[str, Any]
    reference: str | None = None
    deposit_id: str | None = None
    period_year: int | None = None
    deposit_date: str | None = None
    label: str | None = None


def clean_num(num: str) -> str:
    return re.sub(r"\D", "", str(num or ""))


def dotted_num(num: str) -> str:
    n = clean_num(num)
    if len(n) == 10:
        return f"{n[:4]}.{n[4:7]}.{n[7:]}"
    return str(num)


def safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:120]


def ensure_dirs(root: Path) -> dict[str, Path]:
    dirs = {
        "csvs": root / "outputs" / "nbb" / "csvs",
        "raw": root / "outputs" / "nbb" / "raw",
        "debug": root / "outputs" / "nbb" / "debug",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response | None:
    try:
        r = session.request(method, url, timeout=30, **kwargs)
        return r
    except requests.RequestException as exc:
        print(f"    ⚠️ requête échouée: {url} -> {exc}")
        return None


def discover_public_api_paths(session: requests.Session, debug_dir: Path) -> list[str]:
    """Télécharge la page Consult et ses JS pour lister les chemins API vus dans le front."""
    found: set[str] = set()
    html_resp = request(session, "GET", CONSULT_BASE + "/")
    if not html_resp or html_resp.status_code >= 400:
        return []

    (debug_dir / "consult_index.html").write_text(html_resp.text, encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html_resp.text, "html.parser")
    scripts = []
    for tag in soup.find_all("script"):
        src = tag.get("src")
        if src and src.endswith(".js"):
            scripts.append(urljoin(CONSULT_BASE + "/", src))

    api_pattern = re.compile(r"(?:https?://consult\.cbso\.nbb\.be)?(/api/external/broker/public[^'\"`\\\s)]+)")
    for js_url in scripts:
        r = request(session, "GET", js_url)
        if not r or r.status_code >= 400:
            continue
        js_name = safe_filename(js_url.split("/")[-1])
        (debug_dir / js_name).write_text(r.text, encoding="utf-8", errors="ignore")
        for m in api_pattern.finditer(r.text):
            found.add(m.group(1))

    paths = sorted(found)
    (debug_dir / "api_paths_found.txt").write_text("\n".join(paths), encoding="utf-8")
    return paths


def flatten_json(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from flatten_json(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from flatten_json(item)


def infer_year_from_any(obj: dict[str, Any]) -> int | None:
    text = json.dumps(obj, ensure_ascii=False)
    # Privilégie dates de clôture / exercice.
    key_candidates = [
        "periodEndDate", "period_end_date", "endDate", "end_date", "closingDate",
        "accountingPeriodEndDate", "financialYearEndDate", "exerciseEndDate",
        "dateEnd", "endExerciseDate",
    ]
    for key in key_candidates:
        val = obj.get(key)
        if isinstance(val, str):
            m = re.search(r"(20\d{2}|19\d{2})", val)
            if m:
                return int(m.group(1))
        elif isinstance(val, int) and 1900 <= val <= 2100:
            return int(val)

    # Fallback : cherche une année plausible dans l'objet.
    years = [int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", text)]
    years = [y for y in years if 1999 <= y <= 2100]
    if years:
        # Souvent plusieurs dates : dépôt + exercice. On prend la plus petite année récente plausible.
        return sorted(years)[0]
    return None


def extract_ref(obj: dict[str, Any]) -> tuple[str | None, str | None]:
    ref_keys = [
        "referenceNumber", "reference", "depositReference", "depositReferenceNumber",
        "filingReference", "number", "idReference",
    ]
    id_keys = ["id", "uuid", "depositId", "documentId", "identifier"]

    ref = None
    dep_id = None
    for k in ref_keys:
        v = obj.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            ref = str(v).strip()
            break
    for k in id_keys:
        v = obj.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            dep_id = str(v).strip()
            break

    # Si l'objet contient un UUID dans un lien ou un champ quelconque.
    if not dep_id:
        text = json.dumps(obj, ensure_ascii=False)
        m = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
        if m:
            dep_id = m.group(0)
    return ref, dep_id


def looks_like_deposit(obj: dict[str, Any]) -> bool:
    text = json.dumps(obj, ensure_ascii=False).lower()
    if any(word in text for word in ["deposit", "depot", "dépôt", "annual", "account", "jaarrekening", "comptes"]):
        ref, dep_id = extract_ref(obj)
        return bool(ref or dep_id)
    ref, dep_id = extract_ref(obj)
    return bool(ref and infer_year_from_any(obj))


def parse_deposits_json(data: Any) -> list[DepositRef]:
    refs: list[DepositRef] = []
    seen: set[str] = set()
    for obj in flatten_json(data):
        if not looks_like_deposit(obj):
            continue
        ref, dep_id = extract_ref(obj)
        year = infer_year_from_any(obj)
        deposit_date = None
        for k in ["depositDate", "filingDate", "date", "publicationDate"]:
            if isinstance(obj.get(k), str):
                deposit_date = obj[k]
                break
        key = f"{ref}|{dep_id}|{year}|{deposit_date}"
        if key in seen:
            continue
        seen.add(key)
        refs.append(DepositRef(raw=obj, reference=ref, deposit_id=dep_id, period_year=year, deposit_date=deposit_date))
    return refs


def public_deposit_search(session: requests.Session, enterprise_number: str, debug_dir: Path) -> list[DepositRef]:
    """Essaie plusieurs endpoints publics possibles de Consult."""
    n = clean_num(enterprise_number)
    candidates = [
        f"{PUBLIC_BASE}/legalEntities/{n}/deposits",
        f"{PUBLIC_BASE}/legalentities/{n}/deposits",
        f"{PUBLIC_BASE}/legal-entities/{n}/deposits",
        f"{PUBLIC_BASE}/legalEntity/{n}/references",
        f"{PUBLIC_BASE}/legalEntities/{n}/references",
        f"{PUBLIC_BASE}/enterprise/{n}/deposits",
        f"{PUBLIC_BASE}/enterprises/{n}/deposits",
        f"{PUBLIC_BASE}/deposits?enterpriseNumber={n}",
        f"{PUBLIC_BASE}/deposits?legalEntityNumber={n}",
        f"{PUBLIC_BASE}/deposits/search?enterpriseNumber={n}",
        f"{PUBLIC_BASE}/search/deposits?enterpriseNumber={n}",
        f"{PUBLIC_BASE}/legalentities?enterpriseNumber={n}",
    ]

    refs: list[DepositRef] = []
    log_lines = []
    for url in candidates:
        r = request(session, "GET", url, headers={**HEADERS, "Accept": "application/json,*/*"})
        status = r.status_code if r else "ERR"
        ctype = r.headers.get("content-type", "") if r else ""
        log_lines.append(f"{status}\t{ctype}\t{url}")
        if not r or r.status_code >= 400:
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        out = debug_dir / f"public_search_{n}_{safe_filename(url.split(PUBLIC_BASE)[-1])}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed = parse_deposits_json(data)
        if parsed:
            refs.extend(parsed)

    (debug_dir / f"public_search_attempts_{n}.txt").write_text("\n".join(log_lines), encoding="utf-8")

    # Déduplication.
    uniq: list[DepositRef] = []
    seen: set[str] = set()
    for d in refs:
        key = f"{d.reference}|{d.deposit_id}|{d.period_year}"
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    return uniq


def official_ws_references(session: requests.Session, enterprise_number: str, api_key: str, debug_dir: Path) -> list[DepositRef]:
    """Utilise le webservice officiel authentic si une clé CBSO est fournie."""
    n = clean_num(enterprise_number)
    url = f"{WS_BASE}/authentic/legalEntity/{n}/references"
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "NBB-CBSO-Subscription-Key": api_key,
        "X-Request-Id": str(uuid.uuid4()),
    }
    r = request(session, "GET", url, headers=headers)
    if not r:
        return []
    (debug_dir / f"official_refs_{n}_status.txt").write_text(f"{r.status_code}\n{r.text[:2000]}", encoding="utf-8", errors="ignore")
    if r.status_code >= 400:
        print(f"    ⚠️ Webservice officiel refusé ({r.status_code}). Vérifie la clé API / subscription.")
        return []
    try:
        data = r.json()
    except ValueError:
        print("    ⚠️ Webservice officiel: réponse non JSON.")
        return []
    (debug_dir / f"official_refs_{n}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return parse_deposits_json(data)


def content_kind(resp: requests.Response) -> str:
    ctype = resp.headers.get("content-type", "").lower()
    head = resp.content[:100].lower()
    if b"%pdf" in head or "pdf" in ctype:
        return "pdf"
    if b"<xbrl" in head or b"xbrl" in head or "xbrl" in ctype or "xml" in ctype:
        return "xbrl"
    if "csv" in ctype or b"," in resp.content[:200] or b";" in resp.content[:200]:
        return "csv"
    if "zip" in ctype or resp.content[:2] == b"PK":
        return "zip"
    if "json" in ctype:
        return "json"
    return "bin"


def possible_public_download_urls(deposit: DepositRef) -> list[tuple[str, str]]:
    ids = [x for x in [deposit.deposit_id, deposit.reference] if x]
    urls: list[tuple[str, str]] = []
    for dep_id in ids:
        for fmt in ["csv", "xbrl", "pdf"]:
            urls.extend([
                (fmt, f"{PUBLIC_BASE}/deposits/{fmt}/{dep_id}"),
                (fmt, f"{PUBLIC_BASE}/deposits/{dep_id}/{fmt}"),
                (fmt, f"{PUBLIC_BASE}/deposits/{dep_id}/file/{fmt}"),
                (fmt, f"{PUBLIC_BASE}/documents/{dep_id}/{fmt}"),
            ])
    return urls


def official_ws_accounting_data(session: requests.Session, deposit: DepositRef, api_key: str) -> list[tuple[str, bytes, str]]:
    """Télécharge accountingData via webservice officiel. Retourne (kind, content, source_url)."""
    if not deposit.reference:
        return []
    ref = deposit.reference
    results = []
    # Les Accept précis peuvent varier selon l'abonnement et la représentation disponible.
    accepts = [
        ("csv", "text/csv,application/csv,*/*"),
        ("xbrl", "application/xbrl+xml,application/xml,text/xml,*/*"),
        ("json", "application/json,*/*"),
        ("pdf", "application/pdf,*/*"),
    ]
    url = f"{WS_BASE}/authentic/deposit/{ref}/accountingData"
    for expected, accept in accepts:
        headers = {
            **HEADERS,
            "Accept": accept,
            "NBB-CBSO-Subscription-Key": api_key,
            "X-Request-Id": str(uuid.uuid4()),
        }
        r = request(session, "GET", url, headers=headers)
        if r and r.status_code < 400 and r.content:
            kind = content_kind(r)
            results.append((kind if kind != "bin" else expected, r.content, url))
    return results


def xbrl_to_csv(xbrl_bytes: bytes, out_csv: Path) -> int:
    """Convertit un XBRL en CSV brut de faits comptables. Ne calcule rien."""
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(xbrl_bytes, parser=parser)
    rows = []
    for el in root.iter():
        context = el.attrib.get("contextRef")
        if not context:
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        # On garde surtout les faits numériques, mais aussi quelques textes courts utiles.
        numeric = bool(re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text.replace(" ", "")))
        if not numeric and len(text) > 120:
            continue
        qname = etree.QName(el)
        rows.append({
            "concept": qname.localname,
            "namespace": qname.namespace or "",
            "value": text,
            "contextRef": context,
            "unitRef": el.attrib.get("unitRef", ""),
            "decimals": el.attrib.get("decimals", ""),
            "precision": el.attrib.get("precision", ""),
        })
    if not rows:
        return 0
    pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
    return len(rows)


def save_zip_members(content: bytes, dest_dir: Path) -> list[Path]:
    zip_path = dest_dir / "download.zip"
    zip_path.write_bytes(content)
    out_paths = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = safe_filename(Path(info.filename).name)
                out = dest_dir / name
                out.write_bytes(zf.read(info.filename))
                out_paths.append(out)
    except zipfile.BadZipFile:
        pass
    return out_paths


def download_for_deposit(
    session: requests.Session,
    deposit: DepositRef,
    company_num: str,
    year: int,
    dirs: dict[str, Path],
    api_key: str | None = None,
) -> bool:
    """Télécharge un dépôt et crée le CSV attendu si possible."""
    n = clean_num(company_num)
    csv_dir = dirs["csvs"] / n
    raw_dir = dirs["raw"] / n / str(year)
    csv_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target_csv = csv_dir / f"{year}.csv"

    if target_csv.exists() and target_csv.stat().st_size > 0:
        print(f"    ✅ déjà présent: {target_csv}")
        return True

    downloads: list[tuple[str, bytes, str]] = []

    # 1) API publique Consult.
    for expected, url in possible_public_download_urls(deposit):
        r = request(session, "GET", url, headers={**HEADERS, "Accept": "*/*"})
        if not r or r.status_code >= 400 or not r.content:
            continue
        kind = content_kind(r)
        # Évite de prendre une page HTML d'erreur.
        if kind == "bin" and b"<html" in r.content[:500].lower():
            continue
        downloads.append((kind if kind != "bin" else expected, r.content, url))
        break

    # 2) Webservice officiel si clé API fournie.
    if api_key and not downloads:
        downloads.extend(official_ws_accounting_data(session, deposit, api_key))

    if not downloads:
        print("    ⚠️ aucun document téléchargeable trouvé pour ce dépôt")
        return False

    made_csv = False
    for kind, content, source in downloads:
        src_file = raw_dir / "source_url.txt"
        src_file.write_text(source, encoding="utf-8")

        if kind == "csv":
            target_csv.write_bytes(content)
            print(f"    ✅ CSV téléchargé: {target_csv}")
            made_csv = True
            break
        elif kind == "xbrl":
            xbrl_path = raw_dir / f"{year}.xbrl"
            xbrl_path.write_bytes(content)
            rows = xbrl_to_csv(content, target_csv)
            if rows:
                print(f"    ✅ XBRL converti en CSV brut: {target_csv} ({rows} faits)")
                made_csv = True
                break
            print(f"    ⚠️ XBRL sauvegardé mais non convertible: {xbrl_path}")
        elif kind == "pdf":
            pdf_path = raw_dir / f"{year}.pdf"
            pdf_path.write_bytes(content)
            print(f"    ℹ️ PDF sauvegardé uniquement: {pdf_path}")
        elif kind == "zip":
            extracted = save_zip_members(content, raw_dir)
            print(f"    ℹ️ ZIP sauvegardé/extrait dans {raw_dir}")
            for p in extracted:
                if p.suffix.lower() in [".csv", ".txt"]:
                    target_csv.write_bytes(p.read_bytes())
                    print(f"    ✅ CSV extrait du ZIP: {target_csv}")
                    made_csv = True
                    break
                if p.suffix.lower() in [".xbrl", ".xml"]:
                    rows = xbrl_to_csv(p.read_bytes(), target_csv)
                    if rows:
                        print(f"    ✅ XBRL du ZIP converti en CSV brut: {target_csv} ({rows} faits)")
                        made_csv = True
                        break
            if made_csv:
                break
        elif kind == "json":
            json_path = raw_dir / f"{year}.json"
            json_path.write_bytes(content)
            print(f"    ℹ️ JSON sauvegardé: {json_path}")
        else:
            bin_path = raw_dir / f"{year}.bin"
            bin_path.write_bytes(content)
            print(f"    ℹ️ fichier brut sauvegardé: {bin_path}")

    return made_csv


def select_deposits_by_year(refs: list[DepositRef], years: list[int]) -> dict[int, DepositRef]:
    """Sélectionne un dépôt par année. Si plusieurs, prend le plus récent par date de dépôt connue."""
    by_year: dict[int, list[DepositRef]] = {y: [] for y in years}
    for d in refs:
        if d.period_year in by_year:
            by_year[d.period_year].append(d)
    selected: dict[int, DepositRef] = {}
    for y, items in by_year.items():
        if not items:
            continue
        items = sorted(items, key=lambda x: x.deposit_date or "", reverse=True)
        selected[y] = items[0]
    return selected


def write_manifest(company_name: str, company_num: str, refs: list[DepositRef], selected: dict[int, DepositRef], dirs: dict[str, Path]) -> None:
    n = clean_num(company_num)
    manifest_dir = dirs["raw"] / n
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in refs:
        rows.append({
            "company": company_name,
            "enterprise_number": dotted_num(company_num),
            "reference": d.reference,
            "deposit_id": d.deposit_id,
            "period_year": d.period_year,
            "deposit_date": d.deposit_date,
            "selected": "yes" if any(s is d for s in selected.values()) else "no",
            "raw_json": json.dumps(d.raw, ensure_ascii=False),
        })
    pd.DataFrame(rows).to_csv(manifest_dir / "deposits_manifest.csv", index=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extracteur strict NBB/CBSO pour le TP KBO")
    p.add_argument("--root", default=".", help="Dossier racine du TP, par défaut le dossier courant")
    p.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS, help="Années à récupérer")
    p.add_argument("--company", action="append", help="Entreprise à récupérer: numéro BCE avec ou sans points. Répétable.")
    p.add_argument("--api-key", default=None, help="Clé API CBSO officielle si tu en as une")
    p.add_argument("--no-public", action="store_true", help="Désactive la tentative via l'application publique Consult")
    p.add_argument("--discover-only", action="store_true", help="Télécharge seulement les JS Consult et liste les endpoints API trouvés")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    dirs = ensure_dirs(root)
    session = requests.Session()
    session.headers.update(HEADERS)

    print("=== Extracteur NBB/CBSO strict ===")
    print(f"Dossier TP : {root}")
    print(f"Années     : {args.years}")
    print()

    print("Découverte des endpoints publics Consult...")
    paths = discover_public_api_paths(session, dirs["debug"])
    if paths:
        print(f"  ✅ {len(paths)} chemins API trouvés dans le front Consult")
        for path in paths[:10]:
            print(f"    {path}")
        if len(paths) > 10:
            print("    ...")
    else:
        print("  ⚠️ aucun chemin API trouvé automatiquement")

    if args.discover_only:
        print(f"\nRésultats debug dans : {dirs['debug']}")
        return 0

    companies: dict[str, str]
    if args.company:
        companies = {f"Entreprise {dotted_num(c)}": c for c in args.company}
    else:
        companies = COMPANIES

    total_csv = 0
    total_missing = 0

    for name, num in companies.items():
        print(f"\n--- {name} ({dotted_num(num)}) ---")
        refs: list[DepositRef] = []

        if not args.no_public:
            print("  Recherche via Consult public...")
            public_refs = public_deposit_search(session, num, dirs["debug"])
            print(f"    dépôts/références trouvés via Consult: {len(public_refs)}")
            refs.extend(public_refs)

        if args.api_key:
            print("  Recherche via webservice officiel CBSO...")
            official_refs = official_ws_references(session, num, args.api_key, dirs["debug"])
            print(f"    dépôts/références trouvés via webservice: {len(official_refs)}")
            refs.extend(official_refs)

        # Dédup.
        uniq = []
        seen = set()
        for d in refs:
            key = f"{d.reference}|{d.deposit_id}|{d.period_year}"
            if key not in seen:
                seen.add(key)
                uniq.append(d)
        refs = uniq

        selected = select_deposits_by_year(refs, args.years)
        write_manifest(name, num, refs, selected, dirs)

        if not refs:
            print("  ❌ aucune référence de dépôt trouvée. Regarde outputs/nbb/debug/ pour les réponses HTTP.")
            total_missing += len(args.years)
            continue

        print("  Années trouvées:", ", ".join(str(y) for y in sorted({d.period_year for d in refs if d.period_year})) or "non détectées")

        for year in args.years:
            print(f"  {year}:")
            dep = selected.get(year)
            if not dep:
                print("    ⚠️ aucun dépôt correspondant à cette année")
                total_missing += 1
                continue
            ok = download_for_deposit(session, dep, num, year, dirs, api_key=args.api_key)
            if ok:
                total_csv += 1
            else:
                total_missing += 1

    print("\n=== Résumé ===")
    print(f"CSV créés/téléchargés : {total_csv}")
    print(f"Années manquantes     : {total_missing}")
    print(f"CSV attendus dans     : {dirs['csvs']}")
    print(f"Fichiers bruts/debug  : {dirs['raw']} et {dirs['debug']}")
    if total_csv == 0:
        print("\nAucun CSV n'a été créé. Ce n'est pas un échec silencieux : l'API publique a probablement changé ou n'expose pas les documents sans interaction.")
        print("Dans ce cas, utilise Consult manuellement ou une clé API CBSO officielle avec --api-key.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
