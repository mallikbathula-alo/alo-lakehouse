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
for _p in [_script_dir, _os.path.join(_script_dir, "schema")]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_customers_schema import SHOPIFY_CUSTOMERS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, array_join,
    current_timestamp, when
)

log = get_logger("shopify_customers")


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

    return dedup(selected, col("updated_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Customers ingest")
    paths = build_paths(catalog, "customers", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_CUSTOMERS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_CUSTOMERS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
