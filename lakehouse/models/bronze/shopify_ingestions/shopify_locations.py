# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Locations GraphQL → bronze.shopify_gq_locations
#  One location per record; address flattened to top-level columns.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
for _p in [_script_dir, _os.path.join(_script_dir, "schema")]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_locations_schema import SHOPIFY_LOCATIONS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, to_timestamp, current_timestamp, when
)

log = get_logger("shopify_locations")


def transform(df):
    """
    One row per location. Address struct flattened to individual columns.
    Dedup by location_id, keep latest updated_at.
    """
    d = col("data")
    a = col("data.address")

    selected = df.select(
        # ── Identifiers ───────────────────────────────────────
        regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("location_id"),
        d["id"].cast("string").alias("admin_graphql_api_id"),

        # ── Location metadata ─────────────────────────────────
        d["name"].cast("string").alias("name"),
        (d["isActive"] == "true").alias("is_active"),
        (d["isFulfillmentService"] == "true").alias("is_fulfillment_service"),

        # ── Address (flattened) ───────────────────────────────
        a["address1"].cast("string").alias("address1"),
        a["address2"].cast("string").alias("address2"),
        a["city"].cast("string").alias("city"),
        a["province"].cast("string").alias("province"),
        a["provinceCode"].cast("string").alias("province_code"),
        a["country"].cast("string").alias("country"),
        a["countryCode"].cast("string").alias("country_code"),
        a["zip"].cast("string").alias("zip"),
        # Normalize empty-string phone to NULL
        when(a["phone"] == "", None)
            .otherwise(a["phone"].cast("string")).alias("phone"),

        # ── Timestamps ────────────────────────────────────────
        to_timestamp(d["createdAt"]).alias("created_at"),
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
    catalog, run_mode, source_date = parse_ingest_args("Shopify Locations ingest")
    paths = build_paths(catalog, "locations", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_LOCATIONS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_LOCATIONS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
