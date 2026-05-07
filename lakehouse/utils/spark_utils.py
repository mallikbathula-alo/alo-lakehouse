"""
spark_utils.py
──────────────
Generic PySpark and logging utilities for any Databricks script or dbt Python model.
Not specific to any ingestion pipeline — safe to import from any context.

Compatible with:
  - Databricks cluster (spark_python_task, notebook, dbt Python model)
  - Local Databricks Connect (standalone scripts, examples)

Credential resolution for local runs (first wins):
  1. DATABRICKS_HOST / DATABRICKS_TOKEN env vars
  2. ~/.dbt/profiles.yml  (lakehouse → local target)

Compute mode for local runs (set in .env):
  - Serverless (preferred): DATABRICKS_SERVERLESS_COMPUTE_ID=auto
  - Classic cluster:        DATABRICKS_CLUSTER_ID=<cluster-id>

Exports
-------
    get_logger(name)                → logging.Logger
    get_script_dir()                → str
    get_spark()                     → SparkSession
    dedup(df, *order_cols)          → DataFrame
    preview_table(spark, table, n)  → None
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


# ── Logging ───────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    Returns a Logger that writes timestamped, levelled messages to stdout.
    On Databricks cluster, stdout is captured in driver logs and surfaced in
    the task run UI — unlike plain print(), these include timestamps and level.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


# ── Script directory resolution ───────────────────────────────────────────────

def get_script_dir() -> str:
    """
    Returns the absolute directory of the *calling* script.

    On Databricks cluster, spark_python_task executes the file via exec() so
    __file__ may not be defined. We walk up the call stack to find the first
    frame that has a __file__ in its globals (the actual script being run).
    """
    import inspect
    frame = inspect.currentframe()
    try:
        caller = frame.f_back
        while caller is not None:
            filename = caller.f_globals.get("__file__")
            if filename and not filename.endswith("spark_utils.py"):
                return os.path.dirname(os.path.realpath(filename))
            caller = caller.f_back
    finally:
        del frame  # avoid reference cycles

    raise RuntimeError(
        "Could not determine script directory. "
        "Pass script_dir explicitly to get_spark()."
    )


# ── Credentials (local only) ──────────────────────────────────────────────────

def _load_env() -> None:
    """Load .env from repo root (two levels up from lakehouse/utils/)."""
    try:
        from dotenv import load_dotenv
        repo_root = Path(__file__).resolve().parents[2]
        load_dotenv(repo_root / ".env")
    except ImportError:
        pass  # dotenv not available on cluster; env vars already set


def _read_dbt_profiles() -> dict:
    """Parse ~/.dbt/profiles.yml and return the lakehouse local target config."""
    try:
        import yaml
    except ImportError:
        return {}
    profiles_path = Path.home() / ".dbt" / "profiles.yml"
    if not profiles_path.exists():
        return {}
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)
    try:
        return profiles["lakehouse"]["outputs"]["local"]
    except (KeyError, TypeError):
        return {}


# ── SparkSession ──────────────────────────────────────────────────────────────

def get_spark():
    """
    Returns a SparkSession appropriate for the current execution context.

    Cluster (DATABRICKS_RUNTIME_VERSION is set):
        SparkSession.builder.getOrCreate() — cluster service principal handles
        Unity Catalog auth, no credentials needed.

    Local (Databricks Connect):
        Reads host/token from .env or ~/.dbt/profiles.yml.
        Compute mode controlled by .env:
          - DATABRICKS_SERVERLESS_COMPUTE_ID=auto  → serverless, no cluster needed
          - DATABRICKS_CLUSTER_ID=<id>             → classic cluster, must be running
    """
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()

    # Local — Databricks Connect
    from databricks.connect import DatabricksSession

    _load_env()
    dbt = _read_dbt_profiles()

    host  = os.environ.get("DATABRICKS_HOST") or dbt.get("host")
    token = os.environ.get("DATABRICKS_TOKEN") or dbt.get("token")

    serverless_id = os.environ.get("DATABRICKS_SERVERLESS_COMPUTE_ID")
    cluster_id    = os.environ.get("DATABRICKS_CLUSTER_ID")

    missing = [k for k, v in {
        "DATABRICKS_HOST (env var or profiles.yml → host)": host,
        "DATABRICKS_TOKEN (env var or profiles.yml → token)": token,
    }.items() if not v]

    if missing:
        raise EnvironmentError(
            "Missing required Databricks credentials:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\nSet env vars in .env or ensure ~/.dbt/profiles.yml is configured."
        )

    if not serverless_id and not cluster_id:
        raise EnvironmentError(
            "No compute configured. Set one of:\n"
            "  - DATABRICKS_SERVERLESS_COMPUTE_ID=auto   (serverless, no cluster needed)\n"
            "  - DATABRICKS_CLUSTER_ID=<id>              (classic cluster, must be running)"
        )

    if token and len(token) < 20:
        raise EnvironmentError(
            f"DATABRICKS_TOKEN appears truncated (len={len(token)}). "
            "Check for a stale DATABRICKS_TOKEN env var: run `unset DATABRICKS_TOKEN`"
        )

    if serverless_id:
        return DatabricksSession.builder.serverless(True).getOrCreate()

    return (
        DatabricksSession.builder
        .remote(host=host, token=token, cluster_id=cluster_id)
        .getOrCreate()
    )


# ── Dedup helper ──────────────────────────────────────────────────────────────

def dedup(df, *order_cols):
    """
    Deduplicates a DataFrame by unique_key, keeping one row per key.

    order_cols: Column expressions with ordering applied.
                e.g. col("updated_at").desc_nulls_last(), col("_ingested_at").desc()

    Example:
        from pyspark.sql.functions import col
        dedup(df, col("updated_at").desc_nulls_last(), col("_ingested_at").desc())
    """
    from pyspark.sql.functions import row_number, col
    from pyspark.sql.window import Window

    w = Window.partitionBy("unique_key").orderBy(*order_cols)
    return (
        df.withColumn("_rank", row_number().over(w))
          .filter(col("_rank") == 1)
          .drop("_rank")
    )


# ── Preview helper ────────────────────────────────────────────────────────────

def preview_table(
    spark,
    output_table: str,
    n: int = 5,
    logger: logging.Logger | None = None,
) -> None:
    """Logs row count, prints schema and a sample of any Delta table."""
    log = logger or get_logger("preview")
    df = spark.table(output_table)
    count = df.count()
    log.info("Total rows in %s: %s", output_table, f"{count:,}")
    df.printSchema()
    df.show(n, truncate=80)
