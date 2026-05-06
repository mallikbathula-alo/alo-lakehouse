# ============================================================
## ─────────────────────────────────────────────────────────────
#  Transforms for the Shopify Orders GraphQL API v2 response.
#  Mirrors the dbt 'is-redshift/warehouse/models/1_bronze/shopify-graphql-kinesis/br_gq_shopify_order.sql'
#  CTE, selecting and casting fields to match the final dbt model schema.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
# __file__ is not defined when Databricks runs the script via exec(); use inspect as fallback
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_sys.path.insert(0, _os.path.join(_script_dir, "schema"))

from shopify_orders_schema import SHOPIFY_ORDERS_SCHEMA  # noqa: F401


## ─────────────────────────────────────────────────────────────
## EQUIVALENT SPARK TRANSFORMATION (mirrors dbt unpack CTE)
## ─────────────────────────────────────────────────────────────

from pyspark.sql.functions import (
    col, regexp_extract, lower, when, split, regexp_replace,
    array_join, element_at, to_timestamp, expr,
    current_timestamp, coalesce, lit
)


def transform_unpack(df):
    """
    Mirrors the dbt 'unpack' CTE exactly.
    Input df has schema: fetched_at / platform / data.*
    """

    d = col("data")   # shorthand

    return df.select(
        # ── Identifiers ───────────────────────────────────────
        d["id"].cast("string").alias("admin_graphql_api_id"),

        regexp_extract(d["app"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("app_id"),

        regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("order_id"),

        d["number"].cast("long").alias("number"),

        d["name"].cast("string").alias("name"),

        # order_number: matches the CASE WHEN in the unpack CTE
        # (split_part is 1-indexed in Redshift; split() is 0-indexed in Spark)
        when(d["number"].isNotNull(), d["number"])
            .when(lower(d["name"]).startswith("exchl"),      split(d["name"], "-")[1])
            .when(lower(d["name"]).startswith("lgc-exchl"),  split(d["name"], "-")[2])
            .when(lower(d["name"]).startswith("#"),
                  regexp_replace(split(d["name"], "#")[1], "[^0-9]", ""))
            .when(lower(d["name"]).startswith("lgc"),        split(d["name"], "-")[1])
            .otherwise(regexp_replace(lower(d["name"]), "[^0-9]", ""))
            .cast("long").alias("order_number"),

        d["confirmationNumber"].cast("string").alias("confirmation_number"),

        # ── Customer ──────────────────────────────────────────
        regexp_extract(d["customer"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("customer_id"),

        d["customerAcceptsMarketing"].cast("boolean").alias("buyer_accepts_marketing"),
        d["customerLocale"].cast("string").alias("customer_locale"),
        d["email"].cast("string").alias("email"),
        d["phone"].cast("string").alias("phone"),
        d["clientIp"].cast("string").alias("browser_ip"),

        # ── Customer journey ──────────────────────────────────
        lower(d["customerJourneySummary"]["lastVisit"]["landingPage"].cast("string"))
            .alias("landing_site"),
        lower(d["customerJourneySummary"]["lastVisit"]["referrerUrl"].cast("string"))
            .alias("landing_site_ref"),

        # ── Status ────────────────────────────────────────────
        lower(d["displayFinancialStatus"].cast("string")).alias("financial_status"),
        lower(d["displayFulfillmentStatus"].cast("string")).alias("fulfillment_status"),
        d["confirmed"].cast("boolean").alias("confirmed"),
        d["test"].cast("boolean").alias("test"),
        d["estimatedTaxes"].cast("boolean").alias("estimated_taxes"),
        d["taxesIncluded"].cast("boolean").alias("taxes_included"),

        # ── Cancel ────────────────────────────────────────────
        d["cancelReason"].cast("string").alias("cancel_reason"),
        d["cancelledAt"].cast("string").alias("cancelled_at"),
        d["cancellation"]["staffNote"].cast("string").alias("cancellation_staff_note"),

        # ── Timestamps ────────────────────────────────────────
        to_timestamp(d["createdAt"]).alias("created_at"),
        to_timestamp(d["updatedAt"]).alias("updated_at"),
        to_timestamp(d["processedAt"]).alias("processed_at"),
        d["closedAt"].cast("string").alias("closed_at"),

        # ── Money totals ──────────────────────────────────────
        d["currencyCode"].cast("string").alias("currency"),
        d["presentmentCurrencyCode"].cast("string").alias("presentment_currency"),

        d["subtotalPriceSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("subtotal_price"),
        d["totalPriceSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("total_price"),
        d["totalPriceSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("total_price_usd"),
        d["totalTaxSet"]["shopMoney"]["amount"].cast("decimal(8,2)").alias("total_tax"),
        d["totalDiscountsSet"]["shopMoney"]["amount"].cast("string").alias("total_discounts"),
        d["totalShippingPriceSet"]["shopMoney"]["amount"].cast("decimal(8,2)").alias("total_shipping_cost"),
        d["currentShippingPriceSet"]["shopMoney"]["amount"].cast("decimal(8,2)").alias("current_shipping_cost"),
        d["currentSubtotalPriceSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("current_subtotal_price"),
        d["currentTotalPriceSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("current_total_price"),
        d["currentTotalTaxSet"]["shopMoney"]["amount"].cast("int").alias("current_total_tax"),
        d["currentTotalDiscountsSet"]["shopMoney"]["amount"].cast("decimal(10,2)").alias("current_total_discounts"),
        d["totalOutstandingSet"]["shopMoney"]["amount"].cast("string").alias("total_outstanding"),
        d["totalTipReceivedSet"]["shopMoney"]["amount"].cast("decimal(8,2)").alias("total_tip_received"),
        d["totalWeight"].cast("long").alias("total_weight"),

        # Current duties (serialise to string — null in most records)
        d["currentTotalDutiesSet"].cast("string").alias("current_total_duties_set"),
        d["originalTotalDutiesSet"].cast("string").alias("original_total_duties_set"),

        # ── Retail / staff ────────────────────────────────────
        regexp_extract(d["retailLocation"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("location_id"),

        regexp_extract(d["staffMember"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("string").alias("user_id"),

        # ── Payment ───────────────────────────────────────────
        element_at(d["paymentGatewayNames"], 1).cast("string").alias("gateway"),
        d["paymentGatewayNames"].alias("payment_gateway_names"),
        d["poNumber"].cast("string").alias("po_number"),
        d["discountCodes"].alias("discount_codes"),
        d["note"].cast("string").alias("note"),

        # ── Source / attribution ──────────────────────────────
        d["sourceName"].cast("string").alias("source_name"),
        d["sourceIdentifier"].cast("string").alias("source_identifier"),
        d["registeredSourceUrl"].cast("string").alias("source_url"),
        d["referrerUrl"].cast("string").alias("referring_site"),
        d["statusPageUrl"].cast("string").alias("order_status_url"),

        # ── Tags (matches dbt: translate(json_serialize(tags), '[]\"', '')) ──
        array_join(d["tags"], ",").alias("tags"),

        # ── Addresses (keep as struct for downstream) ─────────
        d["billingAddress"].alias("billing_address"),
        d["shippingAddress"].alias("shipping_address"),

        # ── Money sets (keep as struct) ───────────────────────
        d["currentSubtotalPriceSet"].alias("current_subtotal_price_set"),
        d["currentTotalDiscountsSet"].alias("current_total_discounts_set"),
        d["currentTotalPriceSet"].alias("current_total_price_set"),
        d["currentTotalTaxSet"].alias("current_total_tax_set"),
        d["subtotalPriceSet"].alias("subtotal_price_set"),
        d["totalDiscountsSet"].alias("total_discounts_set"),
        d["totalPriceSet"].alias("total_price_set"),
        d["totalShippingPriceSet"].alias("total_shipping_price_set"),
        d["totalTaxSet"].alias("total_tax_set"),

        # ── Firehose envelope ─────────────────────────────────
        col("platform"),
        d["id"].cast("string").alias("unique_key"),

        # ── Audit (replaces Redshift loaded_at) ───────────────
        current_timestamp().alias("_ingested_at"),
        col("_metadata.file_path").alias("_source_file"),   # input_file_name() not supported in UC
    )


def transform_final(df):
    """
    Mirrors the outer SELECT with source_name_adj and is_gift_redemption.
    Applies dedup by unique_key (order_id), keeping latest updated_at.
    """
    from pyspark.sql.functions import row_number
    from pyspark.sql.window import Window

    # Dedup — mirrors: row_number() over (partition by unique_key order by updated_at desc, loaded_at desc)
    w = Window.partitionBy("unique_key").orderBy(
        col("updated_at").desc(),
        col("_ingested_at").desc()     # replaces loaded_at
    )

    # source_name_adj
    sn = lower(col("source_name"))
    source_name_adj = (
        when(sn == "pos",           "retail")
        .when(sn == "web",          "web")
        .when(sn == "580111",       "web")
        .when(sn == "1820463",      "web")
        .when(sn == "2883061",      "app")
        .when(sn == "1844269",      "borderfree")
        .when(sn == "2399288",      "the_yes")
        .when(sn == "3890849",      "web")
        .when(sn == "5254677",      "verishop")
        .when(lower(split(col("source_name"), " ")[0]) == "facebook",  "facebook")
        .when(lower(split(col("source_name"), " ")[0]) == "instagram", "instagram")
        .when(lower(split(col("source_name"), " ")[0]) == "tiktok",    "tiktok")
        .when(sn == "1498281",      "global_e")
        .when(sn == "checkout_next","web")
        .otherwise(sn)
        .cast("string")
    )

    # is_gift_redemption — checks if payment_gateway_names array contains 'gift_card'
    is_gift = expr("array_contains(payment_gateway_names, 'gift_card')").cast("boolean")

    # Computed money fields (mirrors dbt)
    subtotal     = col("subtotal_price")
    total_disc   = col("total_discounts").cast("decimal(10,2)")
    ship_total   = col("total_shipping_cost")
    ship_current = col("current_shipping_cost")

    shipping_cost_adj = when(ship_current > 0, ship_total - ship_current).otherwise(lit(0)).cast("decimal(8,2)")

    # subtotal_price_adj — exchl orders add back discounts
    subtotal_adj = (
        when(lower(col("name")).startswith("exchl"),
             coalesce(subtotal, lit(0)) + coalesce(total_disc, lit(0)))
        .otherwise(coalesce(subtotal, lit(0)))
    )

    total_line_items_price = (subtotal + (total_disc - shipping_cost_adj)).cast("decimal(10,2)")

    return (
        df
        .withColumn("_rank", row_number().over(w))
        .filter(col("_rank") == 1)
        .drop("_rank")
        .withColumn("source_name_adj",        source_name_adj)
        .withColumn("is_gift_redemption",     is_gift)
        .withColumn("shipping_cost_adj",      shipping_cost_adj)
        .withColumn("subtotal_price_adj",     subtotal_adj.cast("decimal(10,2)"))
        .withColumn("total_line_items_price", total_line_items_price)
    )


## ─────────────────────────────────────────────────────────────
## RUN MODES
## ─────────────────────────────────────────────────────────────

def _run_streaming(spark, source_path, schema_loc, checkpoint_loc, output_table):
    """
    AutoLoader streaming mode — intended to run as a Databricks Job directly on
    the cluster. NOT compatible with Databricks Connect (foreachBatch requires
    the cluster to call back to local Python, which is not supported).

    trigger=availableNow processes all new files since the last checkpoint then
    stops, behaving like a scheduled incremental batch while retaining state.
    """
    print(f"\n── [streaming] AutoLoader source : {source_path} ──")

    raw_stream = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format",           "json")
        .option("cloudFiles.schemaLocation",   schema_loc)
        .option("cloudFiles.inferColumnTypes", "false")  # enforce provided schema
        .option("recursiveFileLookup",         "true")   # traverse yyyy/mm/dd/hr
        .schema(SHOPIFY_ORDERS_SCHEMA)
        .load(source_path)
    )

    # transform_unpack is streaming-safe (pure column selects)
    unpacked_stream = transform_unpack(raw_stream)

    # transform_final uses row_number() — not allowed directly in streaming;
    # foreachBatch executes it as a regular batch on each micro-batch
    def process_batch(batch_df, batch_id):
        row_count = batch_df.count()
        print(f"   Batch {batch_id}: {row_count:,} unpacked rows")
        if row_count == 0:
            return
        final_batch = transform_final(batch_df)
        (
            final_batch.write
            .format("delta")
            .mode("append")
            .option("mergeSchema", "true")
            .saveAsTable(output_table)
        )
        print(f"   Batch {batch_id}: {final_batch.count():,} rows written")

    print(f"── [streaming] Writing to {output_table}  (trigger=availableNow) ──")
    query = (
        unpacked_stream.writeStream
        .foreachBatch(process_batch)
        .option("checkpointLocation", checkpoint_loc)
        .trigger(availableNow=True)
        .start()
    )
    query.awaitTermination()
    print("── [streaming] Complete ──")


def _run_batch(spark, source_path, output_table):
    """
    Batch mode — reads all JSON files directly via spark.read.
    Use this for manual runs via Databricks Connect (just pyspark-run).
    Overwrites the output table on each run (no checkpoint state).
    """
    print(f"\n── [batch] Reading JSON files from : {source_path} ──")

    raw = (
        spark.read
        .format("json")
        .option("recursiveFileLookup", "true")   # traverse yyyy/mm/dd/hr subfolders
        .schema(SHOPIFY_ORDERS_SCHEMA)
        .load(source_path)
    )

    print("── [batch] Applying transforms ──")
    unpacked = transform_unpack(raw)
    final    = transform_final(unpacked)

    print(f"── [batch] Writing to {output_table} ──")
    (
        final.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(output_table)
    )
    print("── [batch] Write complete ──")


## ─────────────────────────────────────────────────────────────
## MAIN
##   batch mode (default):  just pyspark-run ../models/bronze/shopify_orders.py
##   streaming mode:        RUN_MODE=streaming just pyspark-run ../models/bronze/shopify_orders.py
## ─────────────────────────────────────────────────────────────

def _get_spark_session():
    """
    Returns the appropriate SparkSession depending on where the code runs:

    - On a Databricks cluster (Job/notebook): DATABRICKS_RUNTIME_VERSION is set
      by the platform → use SparkSession.builder.getOrCreate(). No credentials
      needed; the cluster's service principal handles Unity Catalog auth.

    - Local machine (Databricks Connect): DATABRICKS_RUNTIME_VERSION is absent
      → use utils/session.py which reads host/token from .env + profiles.yml
      and connects remotely via gRPC.
    """
    import os
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        # Running on cluster — Spark is already available
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    else:
        # Running locally via Databricks Connect
        import sys
        _pyspark_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../pyspark")
        sys.path.insert(0, os.path.abspath(_pyspark_dir))
        from utils.session import get_spark
        return get_spark()


def main():
    import os

    catalog      = os.environ.get("SOURCE_CATALOG", "alo_dev")
    preview_rows = int(os.environ.get("PREVIEW_ROWS", "5"))
    # RUN_MODE=streaming → AutoLoader readStream (Databricks Job on cluster)
    # RUN_MODE=batch     → spark.read.json (Databricks Connect / manual run)
    run_mode     = os.environ.get("RUN_MODE", "batch").lower()
    # SOURCE_DATE: optional yyyy/mm/dd/hh suffix to limit batch reads to one hour
    # e.g. SOURCE_DATE=2026/05/05/23 reads only that hour's files
    source_date  = os.environ.get("SOURCE_DATE", "")

    # ── Paths ────────────────────────────────────────────────────
    _base        = f"/Volumes/{catalog}/bronze/firehouse/kinesis/shopify/graphql/orders"
    source_path  = f"{_base}/{source_date}" if source_date else _base
    checkpoint_loc = f"/Volumes/{catalog}/bronze/_autoloader_checkpoints/shopify_graphql_orders"
    schema_loc     = f"/Volumes/{catalog}/bronze/_autoloader_schema/shopify_graphql_orders"
    output_table   = f"`{catalog}`.bronze.shopify_gq_orders_v2"

    print(f"\n── Connecting to Databricks cluster ──")
    spark = _get_spark_session()
    print(f"   SparkSession ready  (Spark {spark.version})  mode={run_mode}")

    if run_mode == "streaming":
        _run_streaming(spark, source_path, schema_loc, checkpoint_loc, output_table)
    else:
        _run_batch(spark, source_path, output_table)

    # ── Preview results from the output table ────────────────────
    final = spark.table(output_table)

    print("\n── Output schema ──")
    final.printSchema()

    total = final.count()
    print(f"\n── Total rows in {output_table}: {total:,} ──")

    print(f"\n── Sample ({preview_rows} rows, latest first) ──")
    (
        final
        .select(
            "order_id", "order_number", "name", "email",
            "financial_status", "fulfillment_status",
            "total_price", "currency", "source_name_adj",
            "created_at", "updated_at", "platform",
        )
        .orderBy(col("updated_at").desc())
        .show(preview_rows, truncate=False)
    )


if __name__ == "__main__":
    main()
