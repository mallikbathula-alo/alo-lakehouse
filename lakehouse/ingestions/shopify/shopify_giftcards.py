# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Gift Cards GraphQL → bronze.shopify_gq_giftcards
#  One gift card per record; balance, customer, and order references.
## ─────────────────────────────────────────────────────────────

import os as _os
import sys as _sys
try:
    _script_dir = _os.path.dirname(_os.path.realpath(__file__))
except NameError:
    import inspect as _inspect
    _script_dir = _os.path.dirname(_os.path.realpath(_inspect.getfile(_inspect.currentframe())))
_utils_dir = _os.path.abspath(_os.path.join(_script_dir, "../../utils"))
for _p in [_script_dir, _os.path.join(_script_dir, "schema"), _utils_dir]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_giftcards_schema import SHOPIFY_GIFTCARDS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, to_timestamp, current_timestamp
)

log = get_logger("shopify_giftcards")


def transform(df):
    """
    One row per gift card. Dedup by gift_card_id, keep latest updated_at.
    customer and order are nullable GQL ID references.
    """
    d = col("data")

    selected = df.select(
        # ── Identifiers ───────────────────────────────────────
        regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("gift_card_id"),
        d["id"].cast("string").alias("admin_graphql_api_id"),

        # ── Balance ───────────────────────────────────────────
        d["balance"]["amount"].cast("decimal(12,2)").alias("balance"),
        d["balance"]["currencyCode"].cast("string").alias("currency"),

        # ── Initial value ─────────────────────────────────────
        d["initialValue"]["amount"].cast("decimal(12,2)").alias("initial_value"),
        d["initialValue"]["currencyCode"].cast("string").alias("initial_value_currency"),

        # ── Status ────────────────────────────────────────────
        (d["enabled"] == "true").alias("enabled"),
        d["lastCharacters"].cast("string").alias("last_characters"),
        d["note"].cast("string").alias("note"),
        d["templateSuffix"].cast("string").alias("template_suffix"),

        # ── Timestamps ────────────────────────────────────────
        to_timestamp(d["createdAt"]).alias("created_at"),
        to_timestamp(d["updatedAt"]).alias("updated_at"),
        d["deactivatedAt"].cast("string").alias("deactivated_at"),
        d["expiresOn"].cast("string").alias("expires_on"),

        # ── Associated customer (nullable) ────────────────────
        regexp_extract(d["customer"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("customer_id"),

        # ── Associated order (nullable) ───────────────────────
        regexp_extract(d["order"]["id"].cast("string"), r"([0-9]+)$", 1)
            .cast("long").alias("order_id"),

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
    catalog, run_mode, source_date = parse_ingest_args("Shopify Gift Cards ingest")
    # Kinesis stream prefix uses camelCase: shopify/graphql/giftCards
    paths = build_paths(catalog, "giftCards", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_GIFTCARDS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_GIFTCARDS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
