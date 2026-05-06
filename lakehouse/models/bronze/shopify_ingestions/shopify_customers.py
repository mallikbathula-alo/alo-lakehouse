# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Customers GraphQL v2 → bronze.shopify_gq_customers_v2
#  One customer per record; metafields pivoted to named columns.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_customers_schema import SHOPIFY_CUSTOMERS_SCHEMA  # noqa: F401

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, array_join,
    current_timestamp, filter as spark_filter, transform as spark_transform,
    when
)


def _metafield(metafields_col, key):
    """Extract the jsonValue of a named metafield from the edges array."""
    from pyspark.sql.functions import expr
    # get() returns NULL for out-of-bounds instead of throwing
    return expr(
        f"get(filter({metafields_col}.edges, e -> e.node.key = '{key}'), 0).node.jsonValue"
    ).cast("string")


def transform(df):
    """
    One row per customer. Dedup by customer_id, keep latest updated_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

    d = col("data")
    mf = "data.metafields"   # metafields path for expr calls

    selected = df.select(
        # ── Identifiers ───────────────────────────────────────
        regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("customer_id"),
        d["id"].cast("string").alias("admin_graphql_api_id"),

        # ── PII ───────────────────────────────────────────────
        d["email"].cast("string").alias("email"),
        d["firstName"].cast("string").alias("first_name"),
        d["lastName"].cast("string").alias("last_name"),
        d["phone"].cast("string").alias("phone"),
        d["note"].cast("string").alias("note"),

        # ── Status ────────────────────────────────────────────
        lower(d["state"]).alias("state"),
        (d["taxExempt"] == "true").alias("tax_exempt"),
        (d["verifiedEmail"] == "true").alias("verified_email"),
        (d["dataSaleOptOut"] == "true").alias("data_sale_opt_out"),

        # ── Order stats ───────────────────────────────────────
        d["numberOfOrders"].cast("long").alias("orders_count"),
        d["amountSpent"]["amount"].cast("decimal(14,2)").alias("total_spent"),
        d["amountSpent"]["currencyCode"].cast("string").alias("currency"),

        # ── Predicted spend tier ──────────────────────────────
        lower(d["statistics"]["predictedSpendTier"]).alias("predicted_spend_tier"),

        # ── Marketing consent ─────────────────────────────────
        lower(d["emailMarketingConsent"]["marketingState"]).alias("email_marketing_state"),
        lower(d["emailMarketingConsent"]["marketingOptInLevel"]).alias("email_opt_in_level"),
        to_timestamp(d["emailMarketingConsent"]["consentUpdatedAt"]).alias("email_consent_updated_at"),
        lower(d["smsMarketingConsent"]["marketingState"]).alias("sms_marketing_state"),

        # ── Default address summary ───────────────────────────
        d["defaultAddress"]["address1"].cast("string").alias("default_address1"),
        d["defaultAddress"]["city"].cast("string").alias("default_city"),
        d["defaultAddress"]["zip"].cast("string").alias("default_zip"),
        d["defaultAddress"]["province"].cast("string").alias("default_province"),
        d["defaultAddress"]["country"].cast("string").alias("default_country"),
        d["defaultAddress"]["countryCodeV2"].cast("string").alias("default_country_code"),

        # ── Last order ────────────────────────────────────────
        regexp_extract(d["lastOrder"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("last_order_id"),
        d["lastOrder"]["name"].cast("string").alias("last_order_name"),

        # ── Timestamps ────────────────────────────────────────
        to_timestamp(d["createdAt"]).alias("created_at"),
        to_timestamp(d["updatedAt"]).alias("updated_at"),

        # ── Tags ──────────────────────────────────────────────
        array_join(d["tags"], ",").alias("tags"),

        # ── Loyalty metafields (LoyaltyLion) ──────────────────
        _metafield(mf, "points_total").alias("loyalty_points_total"),
        _metafield(mf, "points_approved").alias("loyalty_points_approved"),
        _metafield(mf, "points_pending").alias("loyalty_points_pending"),
        _metafield(mf, "points_spent").alias("loyalty_points_spent"),
        _metafield(mf, "points_lifetime").alias("loyalty_points_lifetime"),
        _metafield(mf, "rewards_claimed").alias("loyalty_rewards_claimed"),
        _metafield(mf, "loyalty_tier").alias("loyalty_tier"),
        _metafield(mf, "enroll_date").alias("loyalty_enroll_date"),
        _metafield(mf, "tier_expiration_date").alias("loyalty_tier_expiration_date"),

        # ── Envelope ──────────────────────────────────────────
        col("platform"),
        col("fetched_at").cast("string").alias("fetched_at"),
        d["id"].cast("string").alias("unique_key"),

        # ── Audit ─────────────────────────────────────────────
        current_timestamp().alias("_ingested_at"),
        col("_metadata.file_path").alias("_source_file"),
    )

    w = (
        Window
        .partitionBy("unique_key")
        .orderBy(col("updated_at").desc_nulls_last(), col("_ingested_at").desc())
    )

    return (
        selected
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
        .schema(SHOPIFY_CUSTOMERS_SCHEMA)
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
        .schema(SHOPIFY_CUSTOMERS_SCHEMA)
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
        _pyspark_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../../../pyspark")
        sys.path.insert(0, os.path.abspath(_pyspark_dir))
        from utils.session import get_spark
        return get_spark()


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Shopify Customers ingest")
    parser.add_argument("--run-mode",       default=None)
    parser.add_argument("--source-catalog", default=None)
    parser.add_argument("--source-date",    default=None)
    args, _ = parser.parse_known_args()

    catalog     = args.source_catalog or os.environ.get("SOURCE_CATALOG", "alo_dev")
    run_mode    = (args.run_mode      or os.environ.get("RUN_MODE",       "batch")).lower()
    source_date = args.source_date    or os.environ.get("SOURCE_DATE",    "")

    _base          = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/customers"
    source_path    = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_customers"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_customers"
    output_table   = f"`{catalog}`.bronze.shopify_gq_customers_v2"

    print(f"\n── Shopify Customers ingest  mode={run_mode}  catalog={catalog} ──")
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
