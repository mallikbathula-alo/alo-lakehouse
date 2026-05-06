# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Fulfillments GraphQL v2 → bronze.shopify_gq_fulfillments_v2
#  Explodes the fulfillments array nested inside each order record.
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

from shopify_fulfillments_schema import SHOPIFY_FULFILLMENTS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, expr,
    current_timestamp, explode_outer, coalesce, lit, size,
    try_element_at, concat
)

log = get_logger("shopify_fulfillments")


def transform(df):
    """
    Explode data.fulfillments array → one row per fulfillment.
    Dedup by (order_id, fulfillment_id), keep latest updated_at.
    """
    d = col("data")

    exploded = (
        df.withColumn("ful", explode_outer(d["fulfillments"]))
          .select(
              # ── Order ─────────────────────────────────────────
              regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("order_id"),
              to_timestamp(d["updatedAt"]).alias("order_updated_at"),

              # ── Fulfillment ───────────────────────────────────
              regexp_extract(col("ful.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("fulfillment_id"),
              col("ful.id").cast("string").alias("admin_graphql_api_id"),
              col("ful.name").cast("string").alias("name"),
              lower(col("ful.status")).alias("status"),

              to_timestamp(col("ful.createdAt")).alias("created_at"),
              to_timestamp(col("ful.updatedAt")).alias("updated_at"),
              to_timestamp(col("ful.inTransitAt")).alias("in_transit_at"),
              to_timestamp(col("ful.estimatedDeliveryAt")).alias("estimated_delivery_at"),
              to_timestamp(col("ful.deliveredAt")).alias("delivered_at"),

              (col("ful.requiresShipping") == "true").alias("requires_shipping"),

              # ── Location / service ────────────────────────────
              regexp_extract(col("ful.location.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("location_id"),
              col("ful.service.handle").cast("string").alias("service_handle"),
              col("ful.service.serviceName").cast("string").alias("service_name"),

              # ── Tracking (first entry) ─────────────────────────
              try_element_at(col("ful.trackingInfo"), lit(1))["company"]
                  .cast("string").alias("tracking_company"),
              try_element_at(col("ful.trackingInfo"), lit(1))["number"]
                  .cast("string").alias("tracking_number"),
              try_element_at(col("ful.trackingInfo"), lit(1))["url"]
                  .cast("string").alias("tracking_url"),

              # ── Latest event status ───────────────────────────
              expr("get(ful.events.edges, 0).node.status").cast("string")
                  .alias("latest_event_status"),

              # ── Line item count ───────────────────────────────
              coalesce(size(col("ful.fulfillmentLineItems.edges")), lit(0))
                  .alias("line_item_count"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              concat(d["id"].cast("string"), lit("_"), col("ful.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    return dedup(exploded, col("updated_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Fulfillments ingest")
    paths = build_paths(catalog, "fulfillments", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_FULFILLMENTS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_FULFILLMENTS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
