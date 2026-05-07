"""
ingest_utils.py
───────────────
Shopify GraphQL AutoLoader ingestion helpers.
Specific to the AutoLoader pipeline pattern — path conventions, CLI args,
streaming/batch runners.

Generic utilities (get_logger, get_spark, get_script_dir, dedup, preview_table)
are in spark_utils.py and re-exported here for backward compatibility with
existing ingest scripts.

Usage in each ingest script:
    from ingest_utils import (
        get_logger, get_spark, parse_ingest_args,
        build_paths, dedup, run_streaming, run_batch, preview_table,
    )
"""

from __future__ import annotations

import logging
import os

# Re-export generic utilities so existing ingest scripts don't need to change
from spark_utils import get_logger, get_script_dir, get_spark, dedup, preview_table

__all__ = [
    # generic — from spark_utils
    "get_logger",
    "get_script_dir",
    "get_spark",
    "dedup",
    "preview_table",
    # ingest-specific
    "parse_ingest_args",
    "build_paths",
    "run_streaming",
    "run_batch",
]


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
    base = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/{dataset}"
    table_name = dataset.lower()
    return {
        "source_path":    f"{base}/{source_date}" if source_date else base,
        "checkpoint_loc": f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_{table_name}",
        "schema_loc":     f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_{table_name}",
        "output_table":   f"`{catalog}`.bronze.shopify_gq_{table_name}",
    }


# ── AutoLoader streaming runner ───────────────────────────────────────────────

# Default liquid clustering columns for all Shopify ingest tables.
# created_at — most queries filter by date range
# updated_at — used in incremental dedup logic
_DEFAULT_CLUSTER_COLS: list[str] = ["created_at", "updated_at"]


def run_streaming(
    spark,
    paths: dict,
    ingest_schema,
    transform_fn,
    logger: logging.Logger | None = None,
    cluster_cols: list[str] | None = None,
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
        cluster_cols:   Liquid clustering columns (Databricks Delta).
                        Defaults to ["created_at", "updated_at"].
                        Pass [] to disable clustering.
    """
    log = logger or get_logger("run_streaming")
    cols = cluster_cols if cluster_cols is not None else _DEFAULT_CLUSTER_COLS

    log.info("AutoLoader source      : %s", paths["source_path"])
    log.info("Checkpoint             : %s", paths["checkpoint_loc"])
    log.info("Output table           : %s", paths["output_table"])
    log.info("Cluster by             : %s", cols or "none")

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
        writer = final.write.format("delta").mode("append").option("mergeSchema", "true")
        if cols:
            writer = writer.clusterBy(*cols)
        writer.saveAsTable(output_table)
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
    cluster_cols: list[str] | None = None,
) -> None:
    """
    Batch ingest — reads all JSON files directly, overwrites the output table.
    Use for local Databricks Connect runs (just pyspark-run ...).

    Args:
        spark, paths, ingest_schema, transform_fn, logger: same as run_streaming.
        cluster_cols: Liquid clustering columns. Defaults to ["created_at", "updated_at"].
                      Pass [] to disable clustering.
    """
    log = logger or get_logger("run_batch")
    cols = cluster_cols if cluster_cols is not None else _DEFAULT_CLUSTER_COLS

    log.info("Batch read from : %s", paths["source_path"])
    log.info("Cluster by      : %s", cols or "none")

    raw = (
        spark.read
        .format("json")
        .option("recursiveFileLookup", "true")
        .schema(ingest_schema)
        .load(paths["source_path"])
    )
    final = transform_fn(raw)
    writer = (
        final.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
    )
    if cols:
        writer = writer.clusterBy(*cols)
    writer.saveAsTable(paths["output_table"])
    log.info("Batch write complete → %s", paths["output_table"])
