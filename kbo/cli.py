"""Point d'entrée en ligne de commande du pipeline KBO.

Usage :
    python -m kbo ping
    python -m kbo bronze            [--limit N]
    python -m kbo silver            [--limit N]
    python -m kbo target-hotels     [--limit N]
    python -m kbo scrape-nbb        [--limit N] [--delay 0.5]
    python -m kbo state
    python -m kbo all               [--limit N]   (bronze -> silver -> target-hotels)
"""
from __future__ import annotations

import argparse
import sys

from . import db

# Console Windows en cp1252 : force l'UTF-8 pour les emojis/accents des messages.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _cmd_ping(_args) -> None:
    db.ping()
    print("MongoDB : OK")


def _cmd_bronze(args) -> None:
    from . import bronze
    bronze.build(limit=args.limit, keep_staging=args.keep_staging)


def _cmd_silver(args) -> None:
    from . import silver
    silver.build(limit=args.limit)


def _cmd_target(args) -> None:
    from . import hotellerie
    hotellerie.target(limit=args.limit)


def _cmd_scrape(args) -> None:
    import time

    from . import nbb, statedb
    if not args.loop:
        nbb.scrape(limit=args.limit, delay=args.delay)
        return
    # Boucle de reprise : relance jusqu'à ce que la StateDB soit vidée.
    while True:
        nbb.scrape(delay=args.delay)
        if statedb.stats().get("pending", 0) == 0:
            print("Scraping terminé : plus rien en pending.")
            break
        time.sleep(args.cooldown)


def _cmd_state(_args) -> None:
    from . import statedb
    print("StateDB :", statedb.stats())


def _cmd_all(args) -> None:
    from . import bronze, hotellerie, silver
    bronze.build(limit=args.limit)
    silver.build(limit=args.limit)
    hotellerie.target()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kbo", description="Pipeline KBO Bronze/Silver + scraping NBB")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ping_parser = subparsers.add_parser("ping", help="Teste la connexion MongoDB")
    ping_parser.set_defaults(func=_cmd_ping)

    bronze_parser = subparsers.add_parser("bronze", help="Ingestion CSV KBO -> Bronze (enterprise_finale)")
    bronze_parser.add_argument("--limit", type=int, default=None, help="Limiter les lignes par CSV (test)")
    bronze_parser.add_argument("--keep-staging", action="store_true",
                               help="Conserver les collections raw_* (étage brut)")
    bronze_parser.set_defaults(func=_cmd_bronze)

    silver_parser = subparsers.add_parser("silver", help="Bronze -> Silver (enterprise_silver)")
    silver_parser.add_argument("--limit", type=int, default=None)
    silver_parser.set_defaults(func=_cmd_silver)

    target_parser = subparsers.add_parser("target-hotels", help="Ciblage hôtellerie -> StateDB")
    target_parser.add_argument("--limit", type=int, default=None)
    target_parser.set_defaults(func=_cmd_target)

    scrape_parser = subparsers.add_parser("scrape-nbb", help="Scraping des dépôts NBB des entreprises pending")
    scrape_parser.add_argument("--limit", type=int, default=None)
    scrape_parser.add_argument("--delay", type=float, default=0.5, help="Délai entre requêtes (s)")
    scrape_parser.add_argument("--loop", action="store_true",
                               help="Relancer jusqu'à ce que la StateDB soit vidée")
    scrape_parser.add_argument("--cooldown", type=int, default=60,
                               help="Pause entre deux passes en mode --loop (s)")
    scrape_parser.set_defaults(func=_cmd_scrape)

    state_parser = subparsers.add_parser("state", help="Affiche l'état de la StateDB")
    state_parser.set_defaults(func=_cmd_state)

    all_parser = subparsers.add_parser("all", help="bronze -> silver -> target-hotels")
    all_parser.add_argument("--limit", type=int, default=None)
    all_parser.set_defaults(func=_cmd_all)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
