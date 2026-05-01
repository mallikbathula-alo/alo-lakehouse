"""
Example dbt Python model using PySpark.

This runs on the Databricks cluster (not locally) as part of the dbt DAG.
Use dbt.ref() and dbt.source() exactly like SQL models.

Run:
    dbt run --select br_test_python
"""


def model(dbt, spark):
    dbt.config(
        materialized="table",
        tags=["bronze"],
    )

    # Read from the seed table created earlier
    products = dbt.ref("test_products")

    # Example transformation: add a margin column
    from pyspark.sql import functions as F

    return products.withColumn(
        "price_with_tax", F.round(F.col("price") * 1.1, 2)
    )
