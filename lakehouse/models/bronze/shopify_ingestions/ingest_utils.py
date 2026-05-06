"""
ingest_utils.py
───────────────
Shared utilities for Shopify GraphQL AutoLoader ingestion scripts.
Compatible with Databricks cluster (spark_python_task) and local
Databricks Connect execution.

Usage in each ingest script:
    from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch
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
        # Walk up until we find a frame whose __file__ is not ingest_utils itself
        caller = frame.f_back
        while caller is not None:
            filename = caller.f_globals.get("__file__")
            if filename and not filename.endswith("ingest_utils.py"):
                return os.path.dirname(os.path.realpath(filename))
            caller = caller.f_back
    finally:
        del frame   # avoid reference cycles

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
        Loads pyspark/utils/session.py which reads host/token from .env and
        ~/.dbt/profiles.yml and connects via gRPC.
        script_dir must be the shopify_ingestions/ directory so we can locate
        the pyspark/ package four levels up.
    """
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()

    if script_dir is None:
        script_dir = get_script_dir()

    import sys
    pyspark_dir = os.path.abspath(os.path.join(script_dir, "../../../../pyspark"))
    if pyspark_dir not in sys.path:
        sys.path.insert(0, pyspark_dir)
    from utils.session import get_spark as _connect
    return _connect()


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_ingest_args(description: str) -> tuple[str, str, str]:
    """
    Standard CLI argument parser for all Shopify ingest scripts.

    Priority: CLI args > env vars > defaults
    Returns: (catalog, run_mode, source_date)
    """
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--run-mode",       default=None, help="batch | streaming")
    parser.add_argument("--source-catalog", default=None, help="Unity Catalog name, e.g. alo_dev")
    parser.add_argument("--source-date",    default=None, help="yyyy/mm/dd path suffix to limit source files")
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")
    return catalog, run_mode, source_date


# ── Path builder ──────────────────────────────────────────────────────────────

def build_paths(catalog: str, dataset: str, source_date: str = "") -> dict:
    """
    Returns the standard set of AutoLoader paths for a Shopify GraphQL dataset.

    Args:
        catalog:     Unity Catalog name (e.g. 'alo_dev')
        dataset:     GraphQL dataset name matching the Kinesis S3 prefix
                     (e.g. 'orders', 'customers', 'lineItems')
        source_date: Optional yyyy/mm/dd suffix to limit files processed
                     (e.g. '2026/05/01'). Empty = read entire dataset.

    Returns dict with keys:
        source_path, checkpoint_loc, schema_loc, output_table
    """
    # dataset in path preserves original casing (lineItems); table name is lower
    base = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/{dataset}"
    table_name = dataset.lower()
    return {
        "source_path":    f"{base}/{source_date}" if source_date else base,
        "checkpoint_loc": f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_{table_name}",
        "schema_loc":     f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_{table_name}",
        "output_table":   f"`{catalog}`.bronze.shopify_gq_{table_name}_v2",
    }


# ── Dedup helper ──────────────────────────────────────────────────────────────

def dedup(df, *order_cols):
    """
    Deduplicates df by unique_key, keeping one row per key.

    order_cols: Column expressions with ordering applied
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


# ── AutoLoader streaming runner ───────────────────────────────────────────────

def run_streaming(
    spark,
    paths: dict,
    ingest_schema,
    transform_fn,
    logger: logging.Logger | None = None,
) -> None:
    """
    Runs an AutoLoader streaming ingest using foreachBatch + trigger(availableNow=True).

    Processes all new files since the last checkpoint, then terminates — behaves
    like a scheduled incremental batch while retaining AutoLoader state.

    Args:
        spark:          SparkSession
        paths:          Dict from build_paths() — source_path, schema_loc,
                        checkpoint_loc, output_table
        ingest_schema:  PySpark StructType to enforce on source JSON
        transform_fn:   Callable(batch_df: DataFrame) → DataFrame
                        Applied inside foreachBatch on each micro-batch.
        logger:         Optional logger; creates one if None.
    """
    log = logger or get_logger("run_streaming")
    log.info("AutoLoader source      : %s", paths["source_path"])
    log.info("Checkpoint             : %s", paths["checkpoint_loc"])
    log.info("Output table           : %s", paths["output_table"])

    raw_stream = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format",           "json")
        .option("cloudFiles.schemaLocation",   paths["schema_loc"])
        .option("cloudFiles.inferColumnTypes", "false")   # enforce provided schema
        .option("recursiveFileLookup",         "true")    # traverse yyyy/mm/dd/hh
        .schema(ingest_schema)
        .load(paths["source_path"])
    )

    output_table = paths["output_table"]

    def _process_batch(batch_df, batch_id):
        raw_count = batch_df.count()
        log.info("Batch %s: %s raw rows ingested", batch_id, f"{raw_count:,}")
        if raw_count == 0:
            return
        final = transform_fn(batch_df)
        written = final.count()
        (
            final.write
            .format("delta")
            .mode("append")
            .option("mergeSchema", "true")
            .saveAsTable(output_table)
        )
        log.info("Batch %s: %s rows written → %s", batch_id, f"{written:,}", output_table)

    query = (
        raw_stream.writeStream
        .foreachBatch(_process_batch)
        .option("checkpointLocation", paths["checkpoint_loc"])
        .trigger(availableNow=True)
        .start()
    )
    query.awaitTermination()
    log.info("Streaming complete")


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batch(
    spark,
    paths: dict,
    ingest_schema,
    transform_fn,
    logger: logging.Logger | None = None,
) -> None:
    """
    Batch ingest — reads all JSON files directly, overwrites the output table.
    Use for local Databricks Connect runs (just pyspark-run ...).

    Args: same as run_streaming (paths dict, schema, transform_fn).
    """
    log = logger or get_logger("run_batch")
    log.info("Batch read from : %s", paths["source_path"])

    raw = (
        spark.read
        .format("json")
        .option("recursiveFileLookup", "true")
        .schema(ingest_schema)
        .load(paths["source_path"])
    )
    final = transform_fn(raw)
    (
        final.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(paths["output_table"])
    )
    log.info("Batch write complete → %s", paths["output_table"])


# ── Preview helper ────────────────────────────────────────────────────────────

def preview_table(spark, output_table: str, n: int = 5, logger: logging.Logger | None = None) -> None:
    """Logs row count, prints schema and a sample of the output table."""
    log = logger or get_logger("preview")
    final = spark.table(output_table)
    count = final.count()
    log.info("Total rows in %s: %s", output_table, f"{count:,}")
    final.printSchema()
    final.show(n, truncate=80)
