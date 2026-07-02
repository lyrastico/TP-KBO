"""DAG Airflow — recalcul annuel incrémental de la couche Gold (KBO hôtellerie).

Chaque année, quand de nouveaux comptes annuels sont déposés à la NBB, ce DAG :
  1. liste les entreprises déjà traitées (StateDB status=done) ;
  2. détecte, pour chacune, les dépôts nouveaux vs `filings` déjà connus ;
  3. télécharge uniquement les exercices manquants ;
  4. recalcule la couche Gold des seules entreprises modifiées ;
  5. upsert `hotel_gold`.

Les entreprises sans nouveau dépôt ne sont pas retouchées : le DAG peut tourner
chaque année sans retraiter tout le dataset. La logique vit dans `kbo.incremental`
(réutilisable sans Airflow) ; ce fichier ne fait que l'orchestrer.

Déploiement : copier ce fichier dans le dossier `dags/` d'Airflow, avec le package
`kbo` accessible sur le PYTHONPATH (et `.env` / MongoDB configurés comme pour la CLI).
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from kbo import incremental

DEFAULT_ARGS = {"owner": "kbo", "retries": 1}


def _fetch_new_filings(**context):
    """Étapes 1-3 : renvoie (via XCom) les entreprises ayant de nouveaux dépôts."""
    return incremental.fetch_new_filings()


def _recompute_gold(**context):
    """Étapes 4-5 : recalcule Gold pour les entreprises remontées par la tâche amont."""
    numbers = context["ti"].xcom_pull(task_ids="fetch_new_filings") or []
    return incremental.recompute_gold(numbers)


with DAG(
    dag_id="kbo_gold_refresh",
    description="Recalcul annuel incrémental de la couche Gold KBO hôtellerie",
    default_args=DEFAULT_ARGS,
    schedule="@yearly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["kbo", "gold", "nbb"],
) as dag:
    fetch_new_filings = PythonOperator(
        task_id="fetch_new_filings",
        python_callable=_fetch_new_filings,
    )
    recompute_gold = PythonOperator(
        task_id="recompute_gold",
        python_callable=_recompute_gold,
    )

    fetch_new_filings >> recompute_gold
