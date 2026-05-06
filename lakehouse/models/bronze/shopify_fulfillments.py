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
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_fulfillments_schema import SHOPIFY_FULFILLMENTS_SCHEMA  # noqa: F401

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp,
    current_timestamp, explode_outer, coalesce, lit, size,
    try_element_at
)


def transform(df):
    """
    Explode data.fulfillments array → one row per fulfillment.
    Dedup by (order_id, fulfillment_id), keep latest updated_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

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
              col("ful.events.edges")[0]["node"]["status"].cast("string")
                  .alias("latest_event_status"),

              # ── Line item count ───────────────────────────────
              coalesce(size(col("ful.fulfillmentLineItems.edges")), lit(0))
                  .alias("line_item_count"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              (d["id"].cast("string") + "_" + col("ful.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    w = (
        Window
        .partitionBy("unique_key")
        .orderBy(col("updated_at").desc_nulls_last(), col("_ingested_at").desc())
    )

    return (
        exploded
        .withColumn("_rank", row_number().over(w))
        .filter(col("_rank") == 1)
        .drop("_rank")
    )


def _run_streaming(spark, source_path, schema_loc, checkpoint_loc, output_table):
    raw_stream = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format",           "json")
        .option("cloudFiles.schemaLocation",   schema_loc)
        .option("cloudFiles.inferColumnTypes", "false")
        .option("recursiveFileLookup",         "true")
        .schema(SHOPIFY_FULFILLMENTS_SCHEMA)
        .load(source_path)
    )

    def process_batch(batch_df, batch_id):
        row_count = batch_df.count()
        print(f"   Batch {batch_id}: {row_count:,} raw rows")
        if row_count == 0:
            return
        final = transform(batch_df)
        (
            final.write
            .format("delta")
            .mode("append")
            .option("mergeSchema", "true")
            .saveAsTable(output_table)
        )
        print(f"   Batch {batch_id}: {final.count():,} rows written")

    query = (
        raw_stream.writeStream
        .foreachBatch(process_batch)
        .option("checkpointLocation", checkpoint_loc)
        .trigger(availableNow=True)
        .start()
    )
    query.awaitTermination()
    print("── [streaming] Complete ──")


def _run_batch(spark, source_path, output_table):
    print(f"\n── [batch] Reading from: {source_path} ──")
    raw = (
        spark.read
        .format("json")
        .option("recursiveFileLookup", "true")
        .schema(SHOPIFY_FULFILLMENTS_SCHEMA)
        .load(source_path)
    )
    final = transform(raw)
    (
        final.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(output_table)
    )
    print("── [batch] Write complete ──")


def _get_spark_session():
    import os
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    else:
        import sys
        _pyspark_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../pyspark")
        sys.path.insert(0, os.path.abspath(_pyspark_dir))
        from utils.session import get_spark
        return get_spark()


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Shopify Fulfillments ingest")
    parser.add_argument("--run-mode",       default=None)
    parser.add_argument("--source-catalog", default=None)
    parser.add_argument("--source-date",    default=None)
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")

    _base          = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/fulfillments"
    source_path    = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_fulfillments"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_fulfillments"
    output_table   = f"`{catalog}`.bronze.shopify_gq_fulfillments_v2"

    print(f"\n── Shopify Fulfillments ingest  mode={run_mode}  catalog={catalog} ──")
    spark = _get_spark_session()
    print(f"   SparkSession ready  (Spark {spark.version})")

    if run_mode == "streaming":
        _run_streaming(spark, source_path, schema_loc, checkpoint_loc, output_table)
    else:
        _run_batch(spark, source_path, output_table)

    final = spark.table(output_table)
    print(f"\n── Output table: {output_table}  ({final.count():,} total rows) ──")
    final.printSchema()
    final.show(5, truncate=80)


if __name__ == "__main__":
    main()
