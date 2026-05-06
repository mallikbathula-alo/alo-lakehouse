# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Line Items GraphQL v2 → bronze.shopify_gq_lineitems_v2
#  Explodes the lineItems.edges array nested inside each order record.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_lineitems_schema import SHOPIFY_LINEITEMS_SCHEMA  # noqa: F401

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp,
    current_timestamp, explode_outer, size, coalesce, lit, concat
)


def transform(df):
    """
    Explode data.lineItems.edges → one row per line item.
    Dedup by (order_id, line_item_id), keep latest by order_updated_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

    d = col("data")

    exploded = (
        df.withColumn("edge", explode_outer(d["lineItems"]["edges"]))
          .withColumn("li", col("edge.node"))
          .select(
              # ── Order ─────────────────────────────────────────
              regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("order_id"),
              to_timestamp(d["updatedAt"]).alias("order_updated_at"),
              (d["taxesIncluded"] == "true").alias("order_taxes_included"),

              # ── Line Item ─────────────────────────────────────
              regexp_extract(col("li.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("line_item_id"),
              col("li.id").cast("string").alias("admin_graphql_api_id"),

              col("li.name").cast("string").alias("name"),
              col("li.title").cast("string").alias("title"),
              col("li.variantTitle").cast("string").alias("variant_title"),
              col("li.sku").cast("string").alias("sku"),
              col("li.vendor").cast("string").alias("vendor"),

              col("li.quantity").cast("long").alias("quantity"),
              col("li.currentQuantity").cast("long").alias("current_quantity"),
              col("li.refundableQuantity").cast("long").alias("refundable_quantity"),
              col("li.unfulfilledQuantity").cast("long").alias("unfulfilled_quantity"),
              col("li.nonFulfillableQuantity").cast("long").alias("non_fulfillable_quantity"),

              (col("li.isGiftCard") == "true").alias("is_gift_card"),
              (col("li.taxable") == "true").alias("taxable"),
              (col("li.requiresShipping") == "true").alias("requires_shipping"),

              # ── Prices ────────────────────────────────────────
              col("li.originalTotalSet.shopMoney.amount")
                  .cast("decimal(12,2)").alias("original_total_price"),
              col("li.originalTotalSet.shopMoney.currencyCode")
                  .cast("string").alias("currency"),
              col("li.originalTotalSet.presentmentMoney.amount")
                  .cast("decimal(12,2)").alias("presentment_original_total_price"),
              col("li.originalTotalSet.presentmentMoney.currencyCode")
                  .cast("string").alias("presentment_currency"),

              col("li.totalDiscountSet.shopMoney.amount")
                  .cast("decimal(12,2)").alias("total_discount"),
              col("li.discountedUnitPriceAfterAllDiscountsSet.shopMoney.amount")
                  .cast("decimal(12,2)").alias("discounted_unit_price"),

              # ── Variant / Product ─────────────────────────────
              regexp_extract(col("li.variant.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("variant_id"),
              col("li.variant.price").cast("decimal(12,2)").alias("variant_price"),
              col("li.variant.compareAtPrice").cast("decimal(12,2)").alias("variant_compare_at_price"),
              col("li.variant.taxCode").cast("string").alias("tax_code"),

              regexp_extract(col("li.product.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("product_id"),

              # ── Discount count ────────────────────────────────
              coalesce(size(col("li.discountAllocations")), lit(0))
                  .alias("discount_allocation_count"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              concat(d["id"].cast("string"), lit("_"), col("li.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    w = (
        Window
        .partitionBy("unique_key")
        .orderBy(col("order_updated_at").desc_nulls_last(), col("_ingested_at").desc())
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
        .schema(SHOPIFY_LINEITEMS_SCHEMA)
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
        .schema(SHOPIFY_LINEITEMS_SCHEMA)
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

    parser = argparse.ArgumentParser(description="Shopify Line Items ingest")
    parser.add_argument("--run-mode",       default=None)
    parser.add_argument("--source-catalog", default=None)
    parser.add_argument("--source-date",    default=None)
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")

    _base          = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/lineItems"
    source_path    = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_lineitems"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_lineitems"
    output_table   = f"`{catalog}`.bronze.shopify_gq_lineitems_v2"

    print(f"\n── Shopify Line Items ingest  mode={run_mode}  catalog={catalog} ──")
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
