# TP KBO/BCE — Pipeline médaillon (Bronze / Silver) + scraping financier NBB

Pipeline de traitement des données publiques d'entreprises belges (Banque-Carrefour
des Entreprises / KBO) selon une **architecture médaillon** sur MongoDB, puis scraping
ciblé des comptes annuels déposés à la **Banque Nationale de Belgique (NBB CBSO)** pour
le secteur hôtelier.

## Vue d'ensemble

```
CSV KBO Open Data ──► Bronze ──► Silver ──► Ciblage hôtellerie ──► StateDB ──► Scraping NBB
  (data/KBO)      enterprise_   enterprise_   (NACE 55xxx)        (state_nbb)   (dépôts 2021+)
                    finale        silver
```

- **Bronze** (`enterprise_finale`) : ingestion brute des CSV KBO, un document par
  entreprise avec ses enfants imbriqués (dénominations, adresses, activités, contacts,
  établissements). Aucune transformation métier.
- **Silver** (`enterprise_silver`) : couche nettoyée et enrichie (voir règles ci-dessous).
- **StateDB** (`state_nbb`) : suivi du scraping NBB (`pending` / `in_progress` / `done`),
  avec reprise après interruption.

### Règles de nettoyage Silver

1. **Dates normalisées** : `DD-MM-YYYY` → `YYYY-MM-DD` (l'originale est conservée).
2. **Activités dédupliquées** sur `(NaceCode, Classification)` — les codes de versions
   NACE différentes sont conservés.
3. **Adresse unique** : seul le siège (`TypeOfAddress = REGO`) est gardé.
4. **Dénomination principale** (`TypeOfDenomination = 001`) placée en tête.
5. **Décodage des codes → labels FR** via `code.csv` (forme juridique, statut, NACE…),
   les codes originaux étant conservés.

## Prérequis

- **Python 3.10+**
- **Docker Desktop** (Windows/Mac) ou Docker Engine + plugin Compose (Linux), pour MongoDB
- ~10 Go d'espace disque libre (Bronze + Silver du KBO complet)

## Démarrage rapide (nouvelle machine)

```bash
# 1. Dépendances Python
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env          # puis éditer .env si besoin (voir notes ci-dessous)

# 3. Base de données
docker compose up -d mongo mongo-express      # Mongo Express : http://localhost:8081

# 4. Données KBO -> data/KBO/  (voir "Données KBO" ci-dessous)

# 5. Vérifier que tout répond
python -m kbo ping            # -> "MongoDB : OK"

# 6. Test rapide sur un échantillon (sans charger les 1,95 M)
python -m kbo bronze --limit 5000
python -m kbo silver --limit 5000
python -m kbo state

# 7. Run complet
python -m kbo all             # bronze -> silver -> target-hotels
```

> **Sous Windows**, si `docker` n'est pas reconnu, ajouter au PATH de la session :
> `C:\Program Files\Docker\Docker\resources\bin` (il contient aussi
> `docker-credential-desktop`, requis pour tirer les images).

### Notes de configuration (`.env`)

- **`MONGO_DATA_HOST`** — où MongoDB écrit ses données. Défaut : `./data/mongo`
  (dans le projet). Si le disque système manque de place, pointer vers un autre
  disque (ex. `D:/DockerData/kbo-mongo` sous Windows, `/mnt/data/kbo-mongo` sous Linux).
- Le scraping NBB (`scrape-nbb`) ne nécessite **aucune clé** (API publique).

### Données KBO

Les CSV proviennent du **portail KBO Open Data** (inscription gratuite) :
https://kbopub.economie.fgov.be/kbo-open-data/

Télécharger l'extrait complet (« KBO Open Data — Full »), le décompresser, et placer
les fichiers dans `data/KBO/` :

```
data/KBO/
├── enterprise.csv     denomination.csv    address.csv
├── activity.csv       contact.csv         establishment.csv
└── code.csv
```

Ces fichiers ne sont pas versionnés (trop volumineux, ~2 Go).

## Utilisation

Le pipeline s'exécute via le module `kbo` :

```bash
python -m kbo ping                 # teste la connexion MongoDB
python -m kbo bronze               # ingestion CSV KBO -> Bronze
python -m kbo silver               # Bronze -> Silver
python -m kbo target-hotels        # ciblage hôtellerie -> StateDB
python -m kbo scrape-nbb           # scraping des dépôts NBB (API publique, sans clé)
python -m kbo state                # état de la StateDB

python -m kbo all                  # bronze -> silver -> target-hotels d'affilée
```

Chaque commande accepte `--limit N` pour travailler sur un échantillon (utile en test).

### Ciblage hôtellerie

Filtre appliqué sur le Bronze pour identifier les entreprises hôtelières éligibles :

| Critère | Valeur |
|---|---|
| Statut | `AC` (actif) |
| Type d'entreprise | `2` (personne morale privée) |
| Classification d'activité | `MAIN` |
| Code NACE | dans la liste hôtellerie (`55100`, `55201`…`55900`) |
| Forme juridique | hors entités publiques (services fédéraux, communes, intercommunales…) |

### Scraping NBB CBSO

Le scraping utilise l'**API publique de consultation** (celle du site
consult.cbso.nbb.be). Les comptes annuels déposés sont **publics par la loi belge** :
aucune clé ni authentification n'est requise.

```bash
python -m kbo scrape-nbb              # toutes les entreprises pending
python -m kbo scrape-nbb --limit 3    # test sur 3 entreprises
python -m kbo scrape-nbb --delay 1    # ralentir (politesse envers le service public)
```

Pour chaque entreprise cible, le scraper liste les dépôts publiés, garde ceux
d'exercice ≥ 2021, télécharge le **CSV comptable** (codes PCMN et valeurs) et le stocke
sous `/<entreprise>/nbb/<année>/<référence>.csv` (HDFS ou miroir local selon
`HDFS_BACKEND`). Il respecte un délai entre les requêtes, gère le **rate limit (429)**
en s'arrêtant proprement, et la StateDB permet de **reprendre sans tout relancer**.

## Structure du projet

```
.
├── kbo/                     # Backend du pipeline
│   ├── config.py            #   configuration (env / .env)
│   ├── db.py                #   connexion MongoDB
│   ├── codes.py             #   code.csv -> labels FR
│   ├── bronze.py            #   ingestion CSV -> Bronze (jointure par fusion en streaming)
│   ├── silver.py            #   Bronze -> Silver (5 règles de nettoyage)
│   ├── hotellerie.py        #   ciblage secteur hôtelier -> StateDB
│   ├── statedb.py           #   suivi du scraping
│   ├── storage.py           #   stockage des dépôts (HDFS / local)
│   ├── nbb.py               #   scraping NBB CBSO
│   └── cli.py               #   point d'entrée `python -m kbo`
├── data/                    # CSV bruts KBO (non versionnés)
├── logs/                    # logs d'exécution (non versionnés)
├── tp_initial/              # TP initial (notebook + scripts d'exploration) — archivé
├── docker-compose.yml       # MongoDB (+ Mongo Express, HDFS optionnel)
├── requirements.txt
├── .env.example
└── README.md
```

## Notes techniques

- **Ingestion mémoire constante** : chaque CSV est chargé en flux dans une collection
  `raw_*` (lecture ligne à ligne + insertion par lots), puis `enterprise_finale` est
  assemblée par **jointure côté MongoDB** (`$group` + `$merge`). La jointure des ~34 M
  lignes d'activités est portée par la base (spill disque), pas par la mémoire Python.
  `--keep-staging` conserve les collections `raw_*` comme étage brut.
- **HDFS optionnel** : `docker compose --profile hdfs up -d` démarre un cluster HDFS
  (WebHDFS sur http://localhost:9870) ; sinon les dépôts sont écrits dans un miroir local.
- Le dossier `tp_initial/` conserve la première version du TP (notebook Jupyter et
  scripts) à titre de référence ; il n'est plus utilisé par le pipeline.
