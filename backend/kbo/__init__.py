"""Pipeline KBO/BCE — architecture médaillon (Bronze / Silver) + scraping NBB.

Modules :
    config      Paramètres (env / .env)
    db          Connexion MongoDB
    codes       Chargement de code.csv -> tables de labels
    bronze      Ingestion KBO CSV -> collection Bronze (enterprise_finale)
    silver      Transformation Bronze -> Silver (enterprise_silver)
    hotellerie  Ciblage secteur hôtelier -> StateDB
    statedb     Suivi du scraping (pending / in_progress / done)
    storage     Stockage des dépôts NBB (HDFS ou miroir local)
    nbb         Scraping des dépôts financiers NBB CBSO
    cli         Point d'entrée en ligne de commande
"""

__all__ = ["config", "db"]
