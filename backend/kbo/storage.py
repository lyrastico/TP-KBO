"""Stockage des dépôts financiers NBB.

Chemin logique : /<enterprise>/nbb/<year>/<reference>.csv

Deux backends (config HDFS_BACKEND) :
    local    miroir sur disque sous HDFS_LOCAL_DIR (par défaut)
    webhdfs  écriture réelle sur HDFS via l'API WebHDFS
"""
from __future__ import annotations

from pathlib import Path

import requests

from . import config


def hdfs_path(enterprise_number: str, year: int, reference: str) -> str:
    """Chemin HDFS logique d'un dépôt."""
    safe_ref = reference.replace("/", "_")
    return f"/{enterprise_number}/nbb/{year}/{safe_ref}.csv"


def _write_local(path: str, content: bytes) -> str:
    dest = config.HDFS_LOCAL_DIR / path.lstrip("/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


def _write_webhdfs(path: str, content: bytes) -> str:
    # WebHDFS CREATE : requête en deux temps (redirection vers le datanode).
    base = f"{config.WEBHDFS_URL}/webhdfs/v1{path}"
    params = {"op": "CREATE", "overwrite": "true", "user.name": config.WEBHDFS_USER}
    response = requests.put(base, params=params, allow_redirects=False, timeout=30)
    if response.status_code == 307:
        location = response.headers["Location"]
        response = requests.put(location, data=content, timeout=60)
    response.raise_for_status()
    return path


def store(enterprise_number: str, year: int, reference: str, content: bytes) -> str:
    """Écrit le dépôt et renvoie le chemin où il a été stocké."""
    path = hdfs_path(enterprise_number, year, reference)
    if config.HDFS_BACKEND == "webhdfs":
        return _write_webhdfs(path, content)
    return _write_local(path, content)
