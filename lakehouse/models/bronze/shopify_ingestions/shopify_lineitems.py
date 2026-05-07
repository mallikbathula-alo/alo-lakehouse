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
_utils_dir = _os.path.abspath(_os.path.join(_script_dir, "../../../utils"))
for _p in [_script_dir, _os.path.join(_script_dir, "schema"), _utils_dir]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_lineitems_schema import SHOPIFY_LINEITEMS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp,
    current_timestamp, explode_outer, size, coalesce, lit, concat
)

log = get_logger("shopify_lineitems")


def transform(df):
    """
    Explode data.lineItems.edges → one row per line item.
    Dedup by (order_id, line_item_id), keep latest by order_updated_at.
    """
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

    return dedup(exploded, col("order_updated_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Line Items ingest")
    # lineItems uses mixed-case path in S3 to match Kinesis prefix
    paths = build_paths(catalog, "lineItems", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_LINEITEMS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_LINEITEMS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
