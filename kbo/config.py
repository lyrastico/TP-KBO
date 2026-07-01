"""Configuration centralisée, lue depuis l'environnement (.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


# --- MongoDB ---------------------------------------------------------------
MONGO_URI = _get("MONGO_URI", "mongodb://root:example@localhost:27017/")
MONGO_DB = _get("MONGO_DB", "kbo")
BRONZE_COLLECTION = _get("BRONZE_COLLECTION", "enterprise_finale")
SILVER_COLLECTION = _get("SILVER_COLLECTION", "enterprise_silver")
STATE_COLLECTION = _get("STATE_COLLECTION", "state_nbb")

# --- Données KBO -----------------------------------------------------------
KBO_DIR = Path(_get("KBO_DIR", "data/KBO"))

# --- Scraping NBB ----------------------------------------------------------
# Année d'exercice minimale des dépôts à récupérer.
NBB_MIN_YEAR = int(_get("NBB_MIN_YEAR", "2021"))

# --- Stockage HDFS ---------------------------------------------------------
HDFS_BACKEND = _get("HDFS_BACKEND", "local").lower()
HDFS_LOCAL_DIR = Path(_get("HDFS_LOCAL_DIR", "data/hdfs"))
WEBHDFS_URL = _get("WEBHDFS_URL", "http://localhost:9870")
WEBHDFS_USER = _get("WEBHDFS_USER", "root")

# --- Secteur hôtelier (PART 2) ---------------------------------------------
# Codes NACE retenus pour le ciblage hôtellerie.
HOTEL_NACE_CODES = {
    "55100",  # Hôtels et hébergement similaire
    "55201",  # Auberges de jeunesse
    "55202",  # Centres et villages de vacances
    "55203",  # Gîtes de vacances, appartements et meublés de vacances
    "55204",  # Chambres d'hôtes
    "55209",  # Autres hébergements de courte durée n.c.a.
    "55300",  # Terrains de camping et parcs pour caravanes
    "55400",  # Intermédiation pour l'hébergement (Nace2025, type Airbnb/Booking)
    "55900",  # Autres hébergements
}

# Formes juridiques exclues (entités publiques / services fédéraux / collectivités).
EXCLUDED_JURIDICAL_FORMS = {
    "110", "114", "116", "117",                     # entités publiques
    "301", "302", "303",                            # services fédéraux
    "310", "320", "330", "340", "350",              # autorités régionales
    "400", "411", "412", "413", "414", "415",       # communes, CPAS, intercommunales
    "416", "417", "418", "419", "420",
}
