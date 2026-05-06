# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Refunds GraphQL API v2.
#  Each firehose record wraps one order with its refunds array.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType, ArrayType
)

MONEY_TYPE = StructType([
    StructField("amount",       StringType(), True),
    StructField("currencyCode", StringType(), True),
])

MONEY_BAG_TYPE = StructType([
    StructField("presentmentMoney", MONEY_TYPE, True),
    StructField("shopMoney",        MONEY_TYPE, True),
])

REFUND_TRANSACTION_NODE_TYPE = StructType([
    StructField("id",                StringType(), True),
    StructField("kind",              StringType(), True),
    StructField("status",            StringType(), True),
    StructField("gateway",           StringType(), True),
    StructField("errorCode",         StringType(), True),
    StructField("authorizationCode", StringType(), True),
    StructField("test",              StringType(), True),
    StructField("createdAt",         StringType(), True),
    StructField("processedAt",       StringType(), True),
    StructField("parentTransaction", StructType([
        StructField("id", StringType(), True),
    ]), True),
    StructField("amountSet", MONEY_BAG_TYPE, True),
])

REFUND_LINE_ITEM_NODE_TYPE = StructType([
    StructField("id",           StringType(), True),
    StructField("quantity",     StringType(), True),
    StructField("restockType",  StringType(), True),
    StructField("restocked",    StringType(), True),
    StructField("location",  StructType([StructField("id", StringType(), True)]), True),
    StructField("lineItem",  StructType([StructField("id", StringType(), True)]), True),
    StructField("subtotalSet",  MONEY_BAG_TYPE, True),
    StructField("totalTaxSet",  MONEY_BAG_TYPE, True),
])

REFUND_TYPE = StructType([
    StructField("id",          StringType(), True),
    StructField("createdAt",   StringType(), True),
    StructField("updatedAt",   StringType(), True),
    StructField("note",        StringType(), True),
    StructField("staffMember", StructType([
        StructField("id",        StringType(), True),
        StructField("email",     StringType(), True),
        StructField("firstName", StringType(), True),
        StructField("lastName",  StringType(), True),
    ]), True),
    StructField("orderAdjustments", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", StringType(), True),
        ])), True),
    ]), True),
    StructField("refundLineItems", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", REFUND_LINE_ITEM_NODE_TYPE, True),
        ])), True),
    ]), True),
    StructField("transactions", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", REFUND_TRANSACTION_NODE_TYPE, True),
        ])), True),
    ]), True),
])

SHOPIFY_REFUNDS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",        StringType(), True),   # order GID
        StructField("updatedAt", StringType(), True),
        StructField("refunds",   ArrayType(REFUND_TYPE), True),
    ]), True),
])
