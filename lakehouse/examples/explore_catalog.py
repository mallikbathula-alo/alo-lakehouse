"""
explore_catalog.py
Demonstrates standalone PySpark development via Databricks Connect.

This script is self-contained — spark.range() and spark.createDataFrame() are used
for DataFrame operations so no catalog tables need to exist. Catalog exploration
(SHOW SCHEMAS, SHOW TABLES) simply lists whatever is in the target catalog.

Key patterns demonstrated:
  - get_spark()             — shared session factory from lakehouse/utils/session.py;
                              reads credentials from .env / ~/.dbt/profiles.yml
  - spark.range()           — generate a DataFrame with no source dependency
  - spark.createDataFrame() — inline rows with an explicit StructType schema
  - spark.sql()             — run SQL statements against Unity Catalog
  - DataFrame API           — withColumn, filter, groupBy, agg, show, printSchema
  - spark.table()           — read an existing Delta table by 3-level name

Prerequisites:
  - DATABRICKS_CLUSTER_ID set in .env (cluster must be running)
  - Credentials in ~/.dbt/profiles.yml or DATABRICKS_HOST / DATABRICKS_TOKEN env vars

Run:
    just pyspark-run explore_catalog.py
    # or directly:
    cd lakehouse && ../.venv/bin/python examples/explore_catalog.py
"""

import os
import sys

# Add lakehouse/ to sys.path so `from utils.session import get_spark` resolves
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils.session import get_spark
from pyspark.sql import functions as F, types as T

spark = get_spark()
catalog = os.environ.get("SOURCE_CATALOG", "alo_dev")

# ── 1. Catalog exploration ────────────────────────────────────────────────────
# spark.sql() runs any DDL or query statement against Unity Catalog
print(f"\n── Schemas in {catalog} ──")
spark.sql(f"SHOW SCHEMAS IN {catalog}").show(truncate=False)

print(f"\n── Tables in {catalog}.bronze (first 10) ──")
spark.sql(f"SHOW TABLES IN {catalog}.bronze").show(10, truncate=False)

# ── 2. spark.range() — generate a DataFrame with no source table ──────────────
# Useful for quick tests and transformation experiments without catalog access
print("\n── spark.range() — derive columns from a generated sequence ──")
df = (
    spark.range(1, 6)                                           # produces id: 1..5
    .withColumn("amount_cents", F.col("id") * 1500)
    .withColumn("amount",       F.round(F.col("amount_cents") / 100.0, 2))
    .withColumn("label",        F.concat(F.lit("order_"), F.col("id").cast("string")))
)
df.show()

# ── 3. spark.createDataFrame() — inline rows with an explicit schema ──────────
print("\n── createDataFrame() — typed inline sample data ──")
schema = T.StructType([
    T.StructField("order_id", T.LongType(),   False),
    T.StructField("status",   T.StringType(), True),
    T.StructField("amount",   T.DoubleType(), True),
])
rows = [(1001, "paid", 150.00), (1002, "refunded", 200.50), (1003, "paid", 75.00)]
orders = spark.createDataFrame(rows, schema)
orders.printSchema()
orders.show()

# ── 4. DataFrame API — filter, groupBy, agg ───────────────────────────────────
print("\n── Aggregation — revenue by status ──")
(
    orders
    .filter(F.col("status") == "paid")
    .groupBy("status")
    .agg(
        F.count("order_id").alias("order_count"),
        F.round(F.sum("amount"), 2).alias("total_revenue"),
    )
    .show()
)

# ── 5. spark.table() — read a real Delta table ────────────────────────────────
# Uncomment and substitute a table that exists in your catalog
# print(f"\n── Sample rows from {catalog}.bronze.shopify_gq_orders ──")
# spark.table(f"{catalog}.bronze.shopify_gq_orders").show(5)
