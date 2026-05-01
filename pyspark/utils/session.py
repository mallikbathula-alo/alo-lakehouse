"""
Shared SparkSession factory for local PySpark development via Databricks Connect.

Credential resolution order (first wins):
  1. Environment variables: DATABRICKS_HOST, DATABRICKS_TOKEN
  2. ~/.dbt/profiles.yml  (lakehouse → local target)

DATABRICKS_CLUSTER_ID must always be set in .env or as an env var — it is not
in profiles.yml.

Usage:
    from utils.session import get_spark
    spark = get_spark()
    df = spark.table("dev.public.test_products")

Requires:
    - DATABRICKS_CLUSTER_ID in .env (cluster must be running)
    - uv sync --group pyspark (run from repo root)
"""

import os
from pathlib import Path

import yaml
from databricks.connect import DatabricksSession
from dotenv import load_dotenv

load_dotenv()


def _read_dbt_profiles() -> dict:
    """Parse ~/.dbt/profiles.yml and return the lakehouse local target config."""
    profiles_path = Path.home() / ".dbt" / "profiles.yml"
    if not profiles_path.exists():
        return {}
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)
    try:
        return profiles["lakehouse"]["outputs"]["local"]
    except (KeyError, TypeError):
        return {}


def get_spark() -> DatabricksSession:
    dbt = _read_dbt_profiles()

    host = os.environ.get("DATABRICKS_HOST") or dbt.get("host")
    token = os.environ.get("DATABRICKS_TOKEN") or dbt.get("token")
    cluster_id = os.environ.get("DATABRICKS_CLUSTER_ID")

    missing = [k for k, v in {
        "DATABRICKS_HOST (env var or profiles.yml → host)": host,
        "DATABRICKS_TOKEN (env var or profiles.yml → token)": token,
        "DATABRICKS_CLUSTER_ID (env var)": cluster_id,
    }.items() if not v]

    if missing:
        raise EnvironmentError(
            "Missing required Databricks credentials:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\nSet env vars in .env or ensure ~/.dbt/profiles.yml is configured."
        )

    return (
        DatabricksSession.builder
        .remote(host=host, token=token, cluster_id=cluster_id)
        .getOrCreate()
    )
