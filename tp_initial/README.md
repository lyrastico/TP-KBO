# TP initial (ébauche Jour 1)

Ce dossier contient la **première version** du TP, conservée pour référence. Elle a
été remplacée par le backend `kbo/` (architecture médaillon Bronze → Silver + scraping
NBB) à la racine du projet.

Contenu :

- `sujet_Louis_barthes.ipynb` — notebook d'exploration initial (chargement CSV KBO,
  recherche par entreprise, traduction des codes).
- `scripts/scrape_kbo.py` — scraping strict KBO Public Search + liens eJustice.
- `scripts/extract_nbb_cbso.py` — exploration des endpoints NBB CBSO (a servi à
  identifier l'API ; désormais `kbo/nbb.py` utilise les endpoints officiels).
- `outputs/` — CSV et artefacts produits par ces scripts/notebook.

> Le pipeline courant n'utilise plus ce dossier. Voir le `README.md` racine.
