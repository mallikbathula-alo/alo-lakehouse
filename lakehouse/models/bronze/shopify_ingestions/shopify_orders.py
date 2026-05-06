# ============================================================
## ─────────────────────────────────────────────────────────────
#  Transforms for the Shopify Orders GraphQL API v2 response.
#  Mirrors the dbt 'is-redshift/warehouse/models/1_bronze/shopify-graphql-kinesis/br_gq_shopify_order.sql'
#  CTE, selecting and casting fields to match the final dbt model schema.
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

from shopify_orders_schema import SHOPIFY_ORDERS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, when, split, regexp_replace,
    array_join, try_element_at, to_timestamp, expr,
    current_timestamp, coalesce, lit
)

log = get_logger("shopify_orders")


## ─────────────────────────────────────────────────────────────
## EQUIVALENT SPARK TRANSFORMATION (mirrors dbt unpack CTE)
## ─────────────────────────────────────────────────────────────

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
        d["currentTotalTaxSet"]["shopMoney"]["amount"].cast("decimal(8,2)").alias("current_total_tax"),
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
        try_element_at(d["paymentGatewayNames"], lit(1)).cast("string").alias("gateway"),
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
        dedup(df, col("updated_at").desc(), col("_ingested_at").desc())
        .withColumn("source_name_adj",        source_name_adj)
        .withColumn("is_gift_redemption",     is_gift)
        .withColumn("shipping_cost_adj",      shipping_cost_adj)
        .withColumn("subtotal_price_adj",     subtotal_adj.cast("decimal(10,2)"))
        .withColumn("total_line_items_price", total_line_items_price)
    )


## ─────────────────────────────────────────────────────────────
## MAIN
##   batch mode (default):  just pyspark-run ../models/bronze/shopify_ingestions/shopify_orders.py
##   streaming mode:        RUN_MODE=streaming just pyspark-run ...
## ─────────────────────────────────────────────────────────────

def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Orders ingest")
    paths = build_paths(catalog, "orders", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    transform_fn = lambda df: transform_final(transform_unpack(df))  # noqa: E731

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_ORDERS_SCHEMA, transform_fn, log)
    else:
        run_batch(spark, paths, SHOPIFY_ORDERS_SCHEMA, transform_fn, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
