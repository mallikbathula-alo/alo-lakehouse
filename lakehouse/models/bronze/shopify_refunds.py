# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Refunds GraphQL v2 → bronze.shopify_gq_refunds_v2
#  Explodes the refunds array nested inside each order record.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_refunds_schema import SHOPIFY_REFUNDS_SCHEMA  # noqa: F401

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp,
    current_timestamp, explode_outer, size, coalesce, lit
)


def transform(df):
    """
    Explode data.refunds array → one row per refund.
    Captures summary refund info; line-item and transaction detail kept as arrays.
    Dedup by (order_id, refund_id), keep latest by created_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

    d = col("data")

    exploded = (
        df.withColumn("ref", explode_outer(d["refunds"]))
          .select(
              # ── Order ─────────────────────────────────────────
              regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("order_id"),
              to_timestamp(d["updatedAt"]).alias("order_updated_at"),

              # ── Refund ────────────────────────────────────────
              regexp_extract(col("ref.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("refund_id"),

              col("ref.id").cast("string").alias("admin_graphql_api_id"),
              col("ref.note").cast("string").alias("note"),

              to_timestamp(col("ref.createdAt")).alias("created_at"),
              to_timestamp(col("ref.updatedAt")).alias("updated_at"),

              # ── Staff member ──────────────────────────────────
              regexp_extract(col("ref.staffMember.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("staff_member_id"),
              col("ref.staffMember.email").cast("string").alias("staff_member_email"),
              col("ref.staffMember.firstName").cast("string").alias("staff_member_first_name"),
              col("ref.staffMember.lastName").cast("string").alias("staff_member_last_name"),

              # ── Refund line items summary ─────────────────────
              coalesce(size(col("ref.refundLineItems.edges")), lit(0)).alias("refund_line_item_count"),

              # ── First / primary refund transaction ────────────
              col("ref.transactions.edges")[0]["node"]["id"].cast("string")
                  .alias("transaction_gid"),
              regexp_extract(
                  col("ref.transactions.edges")[0]["node"]["id"].cast("string"),
                  r"([0-9]+)$", 1
              ).cast("long").alias("transaction_id"),
              lower(col("ref.transactions.edges")[0]["node"]["kind"]).alias("transaction_kind"),
              lower(col("ref.transactions.edges")[0]["node"]["status"]).alias("transaction_status"),
              col("ref.transactions.edges")[0]["node"]["gateway"].cast("string").alias("gateway"),
              col("ref.transactions.edges")[0]["node"]["amountSet"]["shopMoney"]["amount"]
                  .cast("decimal(12,2)").alias("amount"),
              col("ref.transactions.edges")[0]["node"]["amountSet"]["shopMoney"]["currencyCode"]
                  .cast("string").alias("currency"),
              col("ref.transactions.edges")[0]["node"]["amountSet"]["presentmentMoney"]["amount"]
                  .cast("decimal(12,2)").alias("presentment_amount"),
              col("ref.transactions.edges")[0]["node"]["amountSet"]["presentmentMoney"]["currencyCode"]
                  .cast("string").alias("presentment_currency"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              (d["id"].cast("string") + "_" + col("ref.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    w = (
        Window
        .partitionBy("unique_key")
        .orderBy(col("created_at").desc_nulls_last(), col("_ingested_at").desc())
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
        .schema(SHOPIFY_REFUNDS_SCHEMA)
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
        .schema(SHOPIFY_REFUNDS_SCHEMA)
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

    parser = argparse.ArgumentParser(description="Shopify Refunds ingest")
    parser.add_argument("--run-mode",       default=None)
    parser.add_argument("--source-catalog", default=None)
    parser.add_argument("--source-date",    default=None)
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")

    _base          = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/refunds"
    source_path    = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_refunds"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_refunds"
    output_table   = f"`{catalog}`.bronze.shopify_gq_refunds_v2"

    print(f"\n── Shopify Refunds ingest  mode={run_mode}  catalog={catalog} ──")
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
