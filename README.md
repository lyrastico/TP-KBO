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

- Python 3.10+
- Docker Desktop (pour MongoDB)

```bash
pip install -r requirements.txt
```

## Installation

1. Copier la configuration et l'ajuster si besoin :

   ```bash
   cp .env.example .env
   ```

2. Démarrer MongoDB (+ interface Mongo Express sur http://localhost:8081) :

   ```bash
   docker compose up -d mongo mongo-express
   ```

   > Les données MongoDB sont stockées sur le disque défini par `MONGO_DATA_HOST`
   > (`.env`), le KBO complet ne tenant pas sur un petit disque système.

3. Placer les CSV KBO Open Data dans `data/KBO/` (`enterprise.csv`, `denomination.csv`,
   `address.csv`, `activity.csv`, `contact.csv`, `establishment.csv`, `code.csv`).

## Utilisation

Le pipeline s'exécute via le module `kbo` :

```bash
python -m kbo ping                 # teste la connexion MongoDB
python -m kbo bronze               # ingestion CSV KBO -> Bronze
python -m kbo silver               # Bronze -> Silver
python -m kbo target-hotels        # ciblage hôtellerie -> StateDB
python -m kbo scrape-nbb           # scraping des dépôts NBB (nécessite une clé, voir plus bas)
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

Le scraping utilise le **webservice officiel NBB CBSO** (`ws.cbso.nbb.be/authentic/…`),
qui nécessite une **clé de souscription gratuite** :

1. Créer un compte sur https://developer.cbso.nbb.be et l'activer.
2. Souscrire au produit de consultation pour obtenir une *Subscription Key*.
3. Renseigner la clé dans `.env` : `NBB_API_KEY=votre_clé`.

Le scraping récupère, pour chaque entreprise cible, les dépôts d'exercice ≥ 2021,
télécharge les données comptables et les stocke sous `/<entreprise>/nbb/<année>/<ref>`
(HDFS ou miroir local selon `HDFS_BACKEND`). Il gère le **rate limit (429)** en
s'arrêtant proprement, et la StateDB permet de **reprendre sans tout relancer**.

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

- **Ingestion mémoire constante** : les CSV KBO étant triés par numéro d'entité,
  le Bronze est construit par **jointure par fusion en streaming** — l'ingestion des
  ~34 M lignes d'activités tient dans une mémoire bornée.
- **HDFS optionnel** : `docker compose --profile hdfs up -d` démarre un cluster HDFS
  (WebHDFS sur http://localhost:9870) ; sinon les dépôts sont écrits dans un miroir local.
- Le dossier `tp_initial/` conserve la première version du TP (notebook Jupyter et
  scripts) à titre de référence ; il n'est plus utilisé par le pipeline.
