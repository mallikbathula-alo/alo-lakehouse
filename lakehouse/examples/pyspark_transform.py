"""
pyspark_transform.py
Example: dbt Python model using PySpark

Demonstrates:
  - How to write a dbt Python model (runs on the Databricks cluster, not locally)
  - dbt.config() for materialization and tags
  - dbt.ref() to read from an upstream dbt model or seed
  - Returning a Spark DataFrame — dbt writes it to Unity Catalog as a Delta table
  - Using pyspark.sql.functions for column transformations

The model() function signature is fixed — dbt injects `dbt` and `spark` automatically.
Use dbt.ref() / dbt.source() exactly as you would in a SQL model.

Run:
    dbt run --select pyspark_transform --target local
"""


def model(dbt, spark):
    dbt.config(
        materialized="table",
        tags=["bronze"],
        enabled=False,          # disabled by default — enable to run
    )

    # dbt.ref() reads from the test_products seed table
    # Replace with dbt.ref("your_model") or dbt.source("schema", "table")
    products = dbt.ref("test_products")

    # ── Transformation ────────────────────────────────────────────────────────
    # Import inside the function — required for dbt Python models
    from pyspark.sql import functions as F

    transformed = (
        products
        # Add a derived column: price with 10% tax applied
        .withColumn("price_with_tax", F.round(F.col("price") * 1.1, 2))
        # Add an audit timestamp
        .withColumn("_transformed_at", F.current_timestamp())
    )

    # Return the DataFrame — dbt handles writing it to the Delta table
    return transformed
