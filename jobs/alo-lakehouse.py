"""
alo-lakehouse.py
────────────────
Airflow DAG orchestrating the alo-lakehouse dbt pipeline on MWAA.
Mirrors the structure of is-redshift but targets Databricks via
the DatabricksSubmitRunOperator (or DbtDatabricksRunOperator).

Topology:
  snapshots → bronze → silver_pre → silver → silver_post → gold + c360 + mgt
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator

# ── Constants ─────────────────────────────────────────────────────────────────
ENV = os.environ.get("ENV", "dev")
ECR_IMAGE = f"715192338314.dkr.ecr.us-east-1.amazonaws.com/alo-lakehouse:latest"
DATABRICKS_CONN_ID = f"databricks_{ENV}"

DBT_RUN_CMD = "/app/.venv/bin/dbt run --target {target} --select {selector} --vars '{{\"source_catalog\": \"alo_{env}\"}}'"
DBT_TEST_CMD = "/app/.venv/bin/dbt test --target {target} --select {selector}"

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ["data-engineering@aloyoga.com"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_dbt_task(
    dag: DAG,
    task_id: str,
    selector: str,
    target: str = ENV,
    full_refresh: bool = False,
    run_tests: bool = False,
    extra_vars: dict | None = None,
) -> DatabricksSubmitRunOperator:
    """
    Creates a DatabricksSubmitRunOperator that runs a dbt command
    inside the alo-lakehouse Docker container on a Databricks cluster.
    """
    vars_str = f'"source_catalog": "alo_{target}"'
    if extra_vars:
        for k, v in extra_vars.items():
            vars_str += f', "{k}": "{v}"'

    fr_flag = "--full-refresh" if full_refresh else ""
    run_cmd = f"/app/.venv/bin/dbt run --target {target} --select {selector} --vars '{{{vars_str}}}' {fr_flag}".strip()

    commands = [run_cmd]
    if run_tests:
        test_cmd = f"/app/.venv/bin/dbt test --target {target} --select {selector}"
        commands.append(test_cmd)

    return DatabricksSubmitRunOperator(
        task_id=task_id,
        dag=dag,
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 4,
            "custom_tags": {"dag": "alo-lakehouse", "task": task_id},
        },
        notebook_task=None,
        spark_submit_task=None,
        # Use container_task or python_wheel_task depending on your Databricks setup
        # For Docker-based dbt, use a script task with the ECR image
    )


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="alo_lakehouse",
    description="Daily dbt medallion pipeline for alo-lakehouse on Databricks",
    schedule_interval="0 4 * * *",   # 4 AM PT
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["alo-lakehouse", "dbt", "databricks"],
    max_active_runs=1,
) as dag:

    # ── Snapshots ─────────────────────────────────────────────────────────────
    snapshot_task = DatabricksSubmitRunOperator(
        task_id="dbt_snapshot",
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 2,
        },
        spark_python_task={
            "python_file": "dbfs:/alo-lakehouse/run_dbt.py",
            "parameters": [
                "snapshot", "--target", ENV
            ],
        },
    )

    # ── Bronze ────────────────────────────────────────────────────────────────
    bronze_task = DatabricksSubmitRunOperator(
        task_id="dbt_bronze",
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 4,
        },
        spark_python_task={
            "python_file": "dbfs:/alo-lakehouse/run_dbt.py",
            "parameters": [
                "run", "--select", "tag:bronze", "--target", ENV
            ],
        },
    )

    # ── Silver ────────────────────────────────────────────────────────────────
    silver_task = DatabricksSubmitRunOperator(
        task_id="dbt_silver",
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 4,
        },
        spark_python_task={
            "python_file": "dbfs:/alo-lakehouse/run_dbt.py",
            "parameters": [
                "run", "--select", "tag:silver", "--target", ENV
            ],
        },
    )

    # ── Gold ──────────────────────────────────────────────────────────────────
    gold_task = DatabricksSubmitRunOperator(
        task_id="dbt_gold",
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 4,
        },
        spark_python_task={
            "python_file": "dbfs:/alo-lakehouse/run_dbt.py",
            "parameters": [
                "run", "--select", "tag:gold", "--target", ENV
            ],
        },
    )

    # ── dbt Tests ─────────────────────────────────────────────────────────────
    test_task = DatabricksSubmitRunOperator(
        task_id="dbt_tests",
        databricks_conn_id=DATABRICKS_CONN_ID,
        new_cluster={
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 2,
        },
        spark_python_task={
            "python_file": "dbfs:/alo-lakehouse/run_dbt.py",
            "parameters": ["test", "--target", ENV],
        },
    )

    # ── DAG Dependencies ──────────────────────────────────────────────────────
    snapshot_task >> bronze_task >> silver_task >> gold_task >> test_task
