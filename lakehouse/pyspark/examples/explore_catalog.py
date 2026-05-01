"""
Example: explore tables in a Unity Catalog schema using Databricks Connect.

Run from repo root:
    just pyspark-run examples/explore_catalog.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.session import get_spark

spark = get_spark()

catalog = os.environ.get("SOURCE_CATALOG", "alo_dev")

print(f"\n── Schemas in {catalog} ──")
spark.sql(f"SHOW SCHEMAS IN {catalog}").show(truncate=False)

print(f"\n── Tables in {catalog}.public ──")
tables = spark.sql(f"SHOW TABLES IN {catalog}.public")
tables.show(truncate=False)

print(f"\n── Sample rows from {catalog}.public.test_products ──")
try:
    spark.table(f"{catalog}.public.test_products").show()
except Exception as e:
    if "TABLE_OR_VIEW_NOT_FOUND" in str(e):
        print(f"  (table not found — run: cd lakehouse && dbt seed --select test_products --target local)")
    else:
        raise
