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

catalog = os.environ.get("SOURCE_CATALOG", "dev")

print(f"\n── Schemas in {catalog} ──")
spark.sql(f"SHOW SCHEMAS IN {catalog}").show(truncate=False)

print(f"\n── Tables in {catalog}.public ──")
spark.sql(f"SHOW TABLES IN {catalog}.public").show(truncate=False)

print(f"\n── Sample rows from {catalog}.public.test_products ──")
spark.table(f"{catalog}.public.test_products").show()
