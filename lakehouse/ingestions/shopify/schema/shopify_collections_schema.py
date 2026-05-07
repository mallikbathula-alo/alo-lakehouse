# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Collections GraphQL API.
#  One collection record per Firehose message.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType,
)

PRODUCTS_COUNT_TYPE = StructType([
    StructField("count",     StringType(), True),
    StructField("precision", StringType(), True),
])

SHOPIFY_COLLECTIONS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",             StringType(), True),
        StructField("handle",         StringType(), True),
        StructField("title",          StringType(), True),
        StructField("description",    StringType(), True),
        StructField("productsCount",  PRODUCTS_COUNT_TYPE, True),
        StructField("sortOrder",      StringType(), True),
        StructField("templateSuffix", StringType(), True),
        StructField("updatedAt",      StringType(), True),
    ]), True),
])
