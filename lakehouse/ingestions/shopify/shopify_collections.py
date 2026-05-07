# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Collections GraphQL → bronze.shopify_gq_collections
#  One collection per record; includes product count and sort order.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_utils_dir = _os.path.abspath(_os.path.join(_script_dir, "../../utils"))
for _p in [_script_dir, _os.path.join(_script_dir, "schema"), _utils_dir]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_collections_schema import SHOPIFY_COLLECTIONS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, current_timestamp
)

log = get_logger("shopify_collections")


def transform(df):
    """
    One row per collection. Dedup by collection_id, keep latest updated_at.
    """
    d = col("data")

    selected = df.select(
        # ── Identifiers ───────────────────────────────────────
        regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("collection_id"),
        d["id"].cast("string").alias("admin_graphql_api_id"),

        # ── Collection metadata ───────────────────────────────
        d["handle"].cast("string").alias("handle"),
        d["title"].cast("string").alias("title"),
        d["description"].cast("string").alias("description"),
        lower(d["sortOrder"]).alias("sort_order"),
        d["templateSuffix"].cast("string").alias("template_suffix"),

        # ── Products count ────────────────────────────────────
        d["productsCount"]["count"].cast("long").alias("products_count"),
        d["productsCount"]["precision"].cast("string").alias("products_count_precision"),

        # ── Timestamps ────────────────────────────────────────
        to_timestamp(d["updatedAt"]).alias("updated_at"),

        # ── Envelope ──────────────────────────────────────────
        col("platform"),
        col("fetched_at").cast("string").alias("fetched_at"),
        d["id"].cast("string").alias("unique_key"),

        # ── Audit ─────────────────────────────────────────────
        current_timestamp().alias("_ingested_at"),
        col("_metadata.file_path").alias("_source_file"),
    )

    return dedup(selected, col("updated_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Collections ingest")
    paths = build_paths(catalog, "collections", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_COLLECTIONS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_COLLECTIONS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
