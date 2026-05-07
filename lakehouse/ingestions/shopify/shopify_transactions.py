# ============================================================
## ─────────────────────────────────────────────────────────────
#  Shopify Transactions GraphQL v2 → bronze.shopify_gq_transactions_v2
#  Explodes the transactions array nested inside each order record.
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

from shopify_transactions_schema import SHOPIFY_TRANSACTIONS_SCHEMA  # noqa: F401
from ingest_utils import get_logger, get_spark, parse_ingest_args, build_paths, dedup, run_streaming, run_batch, preview_table  # noqa: E501

from pyspark.sql.functions import (
    col, regexp_extract, lower, to_timestamp,
    current_timestamp, explode_outer, concat, lit
)

log = get_logger("shopify_transactions")


def transform(df):
    """
    Explode data.transactions array → one row per transaction.
    Dedup by (order_id, transaction_id), keep latest by processed_at.
    """
    d = col("data")

    exploded = (
        df.withColumn("txn", explode_outer(d["transactions"]))
          .select(
              # ── Order (parent) ────────────────────────────────
              regexp_extract(d["id"].cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("order_id"),
              to_timestamp(d["updatedAt"]).alias("order_updated_at"),

              # ── Transaction ───────────────────────────────────
              regexp_extract(col("txn.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("transaction_id"),

              col("txn.id").cast("string").alias("admin_graphql_api_id"),

              lower(col("txn.kind")).alias("kind"),
              lower(col("txn.status")).alias("status"),
              col("txn.gateway").cast("string").alias("gateway"),
              col("txn.paymentId").cast("string").alias("payment_id"),
              col("txn.errorCode").cast("string").alias("error_code"),
              col("txn.authorizationCode").cast("string").alias("authorization_code"),
              col("txn.authorizationExpiresAt").cast("string").alias("authorization_expires_at"),
              col("txn.receiptJson").cast("string").alias("receipt"),

              (col("txn.test") == "true").alias("test"),

              to_timestamp(col("txn.createdAt")).alias("created_at"),
              to_timestamp(col("txn.processedAt")).alias("processed_at"),

              regexp_extract(col("txn.parentTransaction.id").cast("string"), r"([0-9]+)$", 1)
                  .cast("long").alias("parent_transaction_id"),

              col("txn.amountSet.shopMoney.amount").cast("decimal(12,2)").alias("amount"),
              col("txn.amountSet.shopMoney.currencyCode").cast("string").alias("currency"),
              col("txn.amountSet.presentmentMoney.amount").cast("decimal(12,2)").alias("presentment_amount"),
              col("txn.amountSet.presentmentMoney.currencyCode").cast("string").alias("presentment_currency"),

              # ── Envelope ──────────────────────────────────────
              col("platform"),
              col("fetched_at").cast("string").alias("fetched_at"),

              # ── Dedup key ─────────────────────────────────────
              concat(d["id"].cast("string"), lit("_"), col("txn.id").cast("string")).alias("unique_key"),

              # ── Audit ─────────────────────────────────────────
              current_timestamp().alias("_ingested_at"),
              col("_metadata.file_path").alias("_source_file"),
          )
    )

    return dedup(exploded, col("processed_at").desc_nulls_last(), col("_ingested_at").desc())


def main():
    catalog, run_mode, source_date = parse_ingest_args("Shopify Transactions ingest")
    paths = build_paths(catalog, "transactions", source_date)

    log.info("mode=%s  catalog=%s  source=%s", run_mode, catalog, paths["source_path"])
    spark = get_spark(_script_dir)
    log.info("SparkSession ready (Spark %s)", spark.version)

    if run_mode == "streaming":
        run_streaming(spark, paths, SHOPIFY_TRANSACTIONS_SCHEMA, transform, log, cluster_cols=["created_at", "order_updated_at"])
    else:
        run_batch(spark, paths, SHOPIFY_TRANSACTIONS_SCHEMA, transform, log, cluster_cols=["created_at", "order_updated_at"])

    preview_table(spark, paths["output_table"], n=5, logger=log)


if __name__ == "__main__":
    main()
