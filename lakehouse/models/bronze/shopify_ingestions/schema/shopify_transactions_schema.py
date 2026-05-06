# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Transactions GraphQL API v2.
#  Each firehose record wraps one order with its transactions array.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType, BooleanType, ArrayType
)

MONEY_TYPE = StructType([
    StructField("amount",       StringType(), True),
    StructField("currencyCode", StringType(), True),
])

MONEY_BAG_TYPE = StructType([
    StructField("presentmentMoney", MONEY_TYPE, True),
    StructField("shopMoney",        MONEY_TYPE, True),
])

TRANSACTION_TYPE = StructType([
    StructField("id",                     StringType(),  True),
    StructField("kind",                   StringType(),  True),
    StructField("status",                 StringType(),  True),
    StructField("gateway",                StringType(),  True),
    StructField("paymentId",              StringType(),  True),
    StructField("test",                   StringType(),  True),   # Shopify returns "true"/"false" strings
    StructField("createdAt",              StringType(),  True),
    StructField("processedAt",            StringType(),  True),
    StructField("authorizationExpiresAt", StringType(),  True),
    StructField("receiptJson",            StringType(),  True),   # serialised JSON blob
    StructField("errorCode",              StringType(),  True),
    StructField("authorizationCode",      StringType(),  True),
    StructField("parentTransaction", StructType([
        StructField("id", StringType(), True),
    ]), True),
    StructField("amountSet", MONEY_BAG_TYPE, True),
])

SHOPIFY_TRANSACTIONS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",           StringType(), True),   # order GID
        StructField("updatedAt",    StringType(), True),
        StructField("transactions", ArrayType(TRANSACTION_TYPE), True),
    ]), True),
])
