"""
pyspark_transform.py
Demonstrates PySpark DataFrame transformations in a self-contained dbt Python model.
No external catalog tables required — runs as-is after enabling.

Key patterns demonstrated:
  - spark.createDataFrame() — inline sample data, no dbt.ref() dependency
  - withColumn() — deriving new columns
  - F.col(), F.round(), F.when(), F.coalesce() — column expressions
  - F.to_timestamp(), F.to_date(), F.current_timestamp() — date/time functions
  - F.upper(), F.regexp_extract() — string functions
  - Window functions — row_number() for deduplication
  - cast() — type coercion
  - Returning a Spark DataFrame — dbt writes it to Unity Catalog as a Delta table

The model() function signature is fixed — dbt injects `dbt` and `spark` automatically.
All imports must be inside the function body (required for dbt Python models).

Run:
    cd lakehouse
    dbt run --select pyspark_transform --target local
"""


def model(dbt, spark):
    dbt.config(
        materialized="table",
        tags=["example"],
        submission_method="serverless_cluster",
    )

    # All imports inside the function — required for dbt Python models
    from pyspark.sql import functions as F
    from pyspark.sql import types as T
    from pyspark.sql.window import Window

    # ── Sample data ───────────────────────────────────────────────────────────
    # In production replace with: df = dbt.ref("model_name")
    # or:                          df = dbt.source("schema", "table")
    schema = T.StructType([
        T.StructField("order_id",    T.LongType(),   False),
        T.StructField("customer_id", T.LongType(),   True),
        T.StructField("status",      T.StringType(), True),
        T.StructField("amount_cents",T.IntegerType(),True),
        T.StructField("currency",    T.StringType(), True),
        T.StructField("created_at",  T.StringType(), True),
        T.StructField("updated_at",  T.StringType(), True),
        T.StructField("gql_id",      T.StringType(), True),
    ])

    rows = [
        (1001, 501, "paid",      15000, "USD", "2024-01-15T08:00:00", "2024-01-15T08:00:00", "gid://shopify/Order/1001"),
        (1002, 502, "refunded",  20050, "USD", "2024-01-16T11:30:00", "2024-01-17T09:00:00", "gid://shopify/Order/1002"),
        (1003, 501, "paid",       7500, "USD", "2024-01-17T14:00:00", "2024-01-17T14:00:00", "gid://shopify/Order/1003"),
        (1002, 502, "refunded",  20050, "USD", "2024-01-16T11:30:00", "2024-01-17T09:00:00", "gid://shopify/Order/1002"),  # duplicate
    ]

    df = spark.createDataFrame(rows, schema)

    # ── Transformations ───────────────────────────────────────────────────────

    transformed = df.select(
        # ── Identifiers ───────────────────────────────────────────────────
        F.col("order_id"),
        F.col("customer_id"),

        # ── Extract numeric ID from a GraphQL global ID string ────────────
        # regexp_extract(col, pattern, group) — returns "" on no match
        F.regexp_extract(F.col("gql_id"), r"(\d+)$", 1)
            .cast(T.LongType())
            .alias("gql_numeric_id"),

        # ── Type casting ──────────────────────────────────────────────────
        F.to_timestamp(F.col("created_at")).alias("created_at"),
        F.to_date(F.col("created_at")).alias("order_date"),
        F.to_timestamp(F.col("updated_at")).alias("updated_at"),

        # ── Arithmetic ────────────────────────────────────────────────────
        F.round(F.col("amount_cents") / 100.0, 2)
            .cast(T.DecimalType(10, 2))
            .alias("amount"),
        F.upper(F.col("currency")).alias("currency"),

        # ── Conditional logic ─────────────────────────────────────────────
        F.upper(F.col("status")).alias("status"),
        F.when(F.col("status") == "paid", True)
            .when(F.col("status") == "refunded", False)
            .otherwise(None)
            .alias("is_paid"),

        # ── Null handling ─────────────────────────────────────────────────
        # coalesce() returns the first non-null value
        F.coalesce(F.col("customer_id"), F.lit(0)).alias("customer_id_safe"),

        # ── Audit ─────────────────────────────────────────────────────────
        F.current_timestamp().alias("_ingested_at"),
    )

    # ── Deduplication using Window + row_number() ─────────────────────────────
    # Partition by the natural key, keep the row with the latest updated_at
    window = Window.partitionBy("order_id").orderBy(F.col("updated_at").desc())

    deduped = (
        transformed
        .withColumn("_row_num", F.row_number().over(window))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )

    # Return the DataFrame — dbt writes it to Unity Catalog as a Delta table
    return deduped
