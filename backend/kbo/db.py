"""Connexion MongoDB et accès aux collections."""
from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from . import config


@lru_cache(maxsize=1)
def client() -> MongoClient:
    return MongoClient(config.MONGO_URI)


def database() -> Database:
    return client()[config.MONGO_DB]


def bronze() -> Collection:
    return database()[config.BRONZE_COLLECTION]


def silver() -> Collection:
    return database()[config.SILVER_COLLECTION]


def state() -> Collection:
    return database()[config.STATE_COLLECTION]


def gold() -> Collection:
    return database()[config.GOLD_COLLECTION]


def directors() -> Collection:
    return database()[config.DIRECTORS_COLLECTION]


def entity_links() -> Collection:
    return database()[config.LINKS_COLLECTION]


def ping() -> bool:
    """Vérifie que MongoDB répond."""
    client().admin.command("ping")
    return True
