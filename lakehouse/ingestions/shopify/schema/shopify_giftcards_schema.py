# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Gift Cards GraphQL API.
#  One gift card record per Firehose message.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType,
)

MONEY_TYPE = StructType([
    StructField("amount",       StringType(), True),
    StructField("currencyCode", StringType(), True),
])

GID_TYPE = StructType([
    StructField("id", StringType(), True),
])

SHOPIFY_GIFTCARDS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",                  StringType(), True),
        StructField("balance",             MONEY_TYPE, True),
        StructField("initialValue",        MONEY_TYPE, True),
        StructField("createdAt",           StringType(), True),
        StructField("updatedAt",           StringType(), True),
        StructField("deactivatedAt",       StringType(), True),
        StructField("expiresOn",           StringType(), True),
        StructField("enabled",             StringType(), True),
        StructField("lastCharacters",      StringType(), True),
        StructField("note",                StringType(), True),
        StructField("templateSuffix",      StringType(), True),
        StructField("customer",            GID_TYPE, True),   # nullable — just {id}
        StructField("order",               GID_TYPE, True),   # nullable — just {id}
        StructField("recipientAttributes", StringType(), True),
    ]), True),
])
