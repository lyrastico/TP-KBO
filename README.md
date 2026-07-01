# TP KBO/BCE — Extraction et analyse de données d'entreprises belges

Projet d'extraction, de consolidation et d'analyse des données publiques de trois
entreprises belges à partir de sources officielles :

| Entreprise | Numéro d'entreprise |
|---|---|
| Google Belgium | `0878.065.378` |
| Apple Belgium | `0836.157.420` |
| SNCB | `0203.430.576` |

## Objectif

À partir du numéro d'entreprise de chaque société, le projet reconstitue un jeu de
données structuré (identité, forme juridique, adresses, activités, publications
légales, comptes annuels) en s'appuyant **uniquement sur des données réellement
récupérées en ligne** — aucune donnée n'est inventée ou saisie manuellement. Si une
source échoue, le script s'arrête ou laisse le champ vide plutôt que de produire une
valeur factice.

## Sources de données

- **KBO / BCE — Banque-Carrefour des Entreprises**
  ([KBO Public Search](https://kbopub.economie.fgov.be)) : identité, forme juridique,
  situation juridique, adresse, établissements.
- **eJustice / Moniteur belge**
  ([ejustice.just.fgov.be](https://www.ejustice.just.fgov.be)) : publications légales
  et statuts.
- **NBB / CBSO — Banque Nationale de Belgique**
  ([consult.cbso.nbb.be](https://consult.cbso.nbb.be)) : comptes annuels déposés
  (XBRL / PDF).

## Structure du projet

```
.
├── scrape_kbo.py            # Scraping strict KBO Public Search + liens eJustice → data/KBO/*.csv
├── extract_nbb_cbso.py      # Extraction des comptes annuels NBB/CBSO (XBRL/PDF) → outputs/nbb/
├── sujet_Louis_barthes.ipynb# Notebook d'analyse : chargement, recherche par entreprise, traduction des codes
├── data/                    # Données brutes KBO (NON versionné — ~2 Go, voir .gitignore)
│   └── KBO/                 #   enterprise, denomination, address, activity, contact, establishment, code
└── outputs/                 # CSV consolidés et exports par entreprise
    ├── apple_belgium/       #   activities, addresses, denominations, enterprise, establishments
    ├── google_belgium/
    ├── nbb/                 #   comptes annuels extraits
    └── *.csv                #   infos générales/juridiques, dirigeants, contacts, publications, etc.
```

> ⚠️ Le dossier `data/` (données brutes KBO Open Data, ~2 Go) n'est pas versionné sur
> GitHub. Il doit être téléchargé séparément ou régénéré via `scrape_kbo.py`.

## Prérequis

- Python 3.10+
- Dépendances :

```bash
pip install pandas requests beautifulsoup4 lxml
```

## Utilisation

### 1. Extraction KBO (identité, adresses, publications légales)

```bash
python scrape_kbo.py           # génère data/KBO/*.csv
python scrape_kbo.py --force   # écrase les CSV existants
```

### 2. Extraction des comptes annuels NBB/CBSO

```bash
python extract_nbb_cbso.py
python extract_nbb_cbso.py --years 2021 2022 2023 2024
python extract_nbb_cbso.py --company 0878.065.378
python extract_nbb_cbso.py --api-key VOTRE_CLE_NBB_CBSO   # webservices officiels (optionnel)
```

### 3. Analyse

Ouvrir `sujet_Louis_barthes.ipynb` dans VS Code ou Jupyter, puis **Restart Kernel →
Run All**. Le notebook :

1. Crée l'entité initiale à partir du catalogue de CSV KBO.
2. Recherche et consolide les données de Google, Apple et la SNCB.
3. Traduit les codes techniques KBO en libellés lisibles (FR / NL).

## Remarques

- L'API publique de Consult (NBB) est gratuite mais peut changer sans préavis ; les
  webservices officiels CBSO nécessitent une souscription et une clé API.
- Le scraping respecte un délai entre requêtes pour ne pas surcharger les services publics.
