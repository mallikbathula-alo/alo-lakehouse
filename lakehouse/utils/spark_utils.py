"""
spark_utils.py
──────────────
Generic PySpark and logging utilities for any Databricks script or dbt Python model.
Not specific to any ingestion pipeline — safe to import from any context.

Compatible with:
  - Databricks cluster (spark_python_task, notebook, dbt Python model)
  - Local Databricks Connect (standalone scripts via utils/session.py)

Exports
-------
    get_logger(name)                → logging.Logger
    get_script_dir()                → str
    get_spark(script_dir)           → SparkSession
    dedup(df, *order_cols)          → DataFrame
    preview_table(spark, table, n)  → None
"""

from __future__ import annotations

import logging
import os


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
    frame that has a __file__ in its globals (the actual script being run),
    then fall back to inspect if nothing is found.
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


# ── SparkSession ──────────────────────────────────────────────────────────────

def get_spark(script_dir: str | None = None):
    """
    Returns a SparkSession appropriate for the current execution context.

    Cluster (DATABRICKS_RUNTIME_VERSION is set):
        Uses SparkSession.builder.getOrCreate(). The cluster's service principal
        handles Unity Catalog auth — no credentials needed.

    Local (Databricks Connect):
        Uses lakehouse/utils/session.py which reads host/token from .env and
        ~/.dbt/profiles.yml and connects via serverless or classic cluster.
    """
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()

    import sys
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from session import get_spark as _connect
    return _connect()


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
