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
_utils_dir = _os.path.abspath(_os.path.join(_script_dir, "../../utils"))
for _p in [_script_dir, _os.path.join(_script_dir, "schema"), _utils_dir]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from shopify_refunds_schema import SHOPIFY_REFUNDS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp, expr,
    current_timestamp, explode_outer, size, coalesce, lit, concat
)

log = get_logger("shopify_refunds")


def transform(df):
    """
    Explode data.refunds array → one row per refund.
    Captures summary refund info; line-item and transaction detail kept as arrays.
    Dedup by (order_id, refund_id), keep latest by created_at.
    """
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

              # ── First / primary refund transaction (get() is NULL-safe for empty arrays) ──
              expr("get(ref.transactions.edges, 0).node.id").cast("string")
                  .alias("transaction_gid"),
              regexp_extract(
                  expr("get(ref.transactions.edges, 0).node.id").cast("string"),
                  r"([0-9]+)$", 1
              ).cast("long").alias("transaction_id"),
              lower(expr("get(ref.transactions.edges, 0).node.kind")).alias("transaction_kind"),
              lower(expr("get(ref.transactions.edges, 0).node.status")).alias("transaction_status"),
              expr("get(ref.transactions.edges, 0).node.gateway").cast("string").alias("gateway"),
              expr("get(ref.transactions.edges, 0).node.amountSet.shopMoney.amount")
                  .cast("decimal(12,2)").alias("amount"),
              expr("get(ref.transactions.edges, 0).node.amountSet.shopMoney.currencyCode")
                  .cast("string").alias("currency"),
              expr("get(ref.transactions.edges, 0).node.amountSet.presentmentMoney.amount")
                  .cast("decimal(12,2)").alias("presentment_amount"),
              expr("get(ref.transactions.edges, 0).node.amountSet.presentmentMoney.currencyCode")
                  .cast("string").alias("presentment_currency"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),
              concat(d["id"].cast("string"), lit("_"), col("ref.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    return dedup(exploded, col("created_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Refunds ingest")
    paths = build_paths(catalog, "refunds", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_REFUNDS_SCHEMA, transform, log)
    else:
        run_batch(spark, paths, SHOPIFY_REFUNDS_SCHEMA, transform, log)

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
