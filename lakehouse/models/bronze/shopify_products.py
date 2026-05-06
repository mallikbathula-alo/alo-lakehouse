# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Products GraphQL v2 → bronze.shopify_gq_products_v2
#  One row per product variant (explodes variants.edges).
#  Product-level metadata is repeated on each variant row.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_products_schema import SHOPIFY_PRODUCTS_SCHEMA  # noqa: F401

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, array_join,
    current_timestamp, explode_outer, expr, concat, lit
)


def transform(df):
    """
    Explode data.variants.edges → one row per (product, variant).
    Dedup by (product_id, variant_id), keep latest updated_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

    d = col("data")

    exploded = (
        df.withColumn("edge", explode_outer(d["variants"]["edges"]))
          .withColumn("v", col("edge.node"))
          .select(
              # ── Product ───────────────────────────────────────
              regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("product_id"),
              d["id"].cast("string").alias("product_gid"),

              d["title"].cast("string").alias("title"),
              d["handle"].cast("string").alias("handle"),
              lower(d["status"]).alias("status"),
              d["productType"].cast("string").alias("product_type"),
              d["vendor"].cast("string").alias("vendor"),
              d["descriptionHtml"].cast("string").alias("description_html"),
              d["onlineStoreUrl"].cast("string").alias("online_store_url"),
              d["templateSuffix"].cast("string").alias("template_suffix"),
              (d["tracksInventory"] == "true").alias("tracks_inventory"),
              d["totalInventory"].cast("long").alias("total_inventory"),

              to_timestamp(d["createdAt"]).alias("product_created_at"),
              to_timestamp(d["updatedAt"]).alias("product_updated_at"),
              to_timestamp(d["publishedAt"]).alias("published_at"),

              array_join(d["tags"], ",").alias("tags"),

              # ── Variant ───────────────────────────────────────
              regexp_extract(col("v.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("variant_id"),
              col("v.id").cast("string").alias("variant_gid"),

              col("v.title").cast("string").alias("variant_title"),
              col("v.displayName").cast("string").alias("display_name"),
              col("v.sku").cast("string").alias("sku"),
              col("v.barcode").cast("string").alias("barcode"),
              col("v.price").cast("decimal(12,2)").alias("price"),
              col("v.compareAtPrice").cast("decimal(12,2)").alias("compare_at_price"),
              col("v.taxCode").cast("string").alias("tax_code"),
              (col("v.taxable") == "true").alias("taxable"),
              col("v.position").cast("long").alias("position"),
              lower(col("v.inventoryPolicy")).alias("inventory_policy"),
              col("v.inventoryQuantity").cast("long").alias("inventory_quantity"),

              to_timestamp(col("v.createdAt")).alias("variant_created_at"),
              to_timestamp(col("v.updatedAt")).alias("variant_updated_at"),

              # ── Inventory item ────────────────────────────────
              regexp_extract(col("v.inventoryItem.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("inventory_item_id"),
              (col("v.inventoryItem.requiresShipping") == "true").alias("requires_shipping"),
              col("v.inventoryItem.measurement.weight.value").cast("decimal(10,3)").alias("weight"),
              col("v.inventoryItem.measurement.weight.unit").cast("string").alias("weight_unit"),

              # ── Selected options (first two cover most products) ──
              expr("filter(v.selectedOptions, o -> o.name = 'Color')[0].value")
                  .cast("string").alias("option_color"),
              expr("filter(v.selectedOptions, o -> o.name = 'Size')[0].value")
                  .cast("string").alias("option_size"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              concat(d["id"].cast("string"), lit("_"), col("v.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    w = (
        Window
        .partitionBy("unique_key")
        .orderBy(col("variant_updated_at").desc_nulls_last(), col("_ingested_at").desc())
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
        .schema(SHOPIFY_PRODUCTS_SCHEMA)
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
        .schema(SHOPIFY_PRODUCTS_SCHEMA)
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

    parser = argparse.ArgumentParser(description="Shopify Products ingest")
    parser.add_argument("--run-mode",       default=None)
    parser.add_argument("--source-catalog", default=None)
    parser.add_argument("--source-date",    default=None)
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")

    _base          = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/products"
    source_path    = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_products"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_products"
    output_table   = f"`{catalog}`.bronze.shopify_gq_products_v2"

    print(f"\n── Shopify Products ingest  mode={run_mode}  catalog={catalog} ──")
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
