# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Fulfillments GraphQL API v2.
#  Each firehose record wraps one order with its fulfillments array.
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

TRACKING_INFO_TYPE = StructType([
    StructField("company", StringType(), True),
    StructField("number",  StringType(), True),
    StructField("url",     StringType(), True),
])

FULFILLMENT_LINE_ITEM_NODE_TYPE = StructType([
    StructField("id",               StringType(), True),
    StructField("quantity",         StringType(), True),
    StructField("lineItem",         StructType([StructField("id", StringType(), True)]), True),
    StructField("originalTotalSet", MONEY_BAG_TYPE, True),
])

FULFILLMENT_EVENT_NODE_TYPE = StructType([
    StructField("status", StringType(), True),
])

FULFILLMENT_TYPE = StructType([
    StructField("id",                  StringType(), True),
    StructField("name",                StringType(), True),
    StructField("status",              StringType(), True),
    StructField("createdAt",           StringType(), True),
    StructField("updatedAt",           StringType(), True),
    StructField("inTransitAt",         StringType(), True),
    StructField("estimatedDeliveryAt", StringType(), True),
    StructField("deliveredAt",         StringType(), True),
    StructField("requiresShipping",    StringType(), True),
    StructField("location",  StructType([StructField("id", StringType(), True)]), True),
    StructField("service", StructType([
        StructField("id",          StringType(), True),
        StructField("handle",      StringType(), True),
        StructField("serviceName", StringType(), True),
    ]), True),
    StructField("trackingInfo", ArrayType(TRACKING_INFO_TYPE), True),
    StructField("fulfillmentLineItems", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", FULFILLMENT_LINE_ITEM_NODE_TYPE, True),
        ])), True),
    ]), True),
    StructField("events", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", FULFILLMENT_EVENT_NODE_TYPE, True),
        ])), True),
    ]), True),
])

SHOPIFY_FULFILLMENTS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",           StringType(), True),   # order GID
        StructField("updatedAt",    StringType(), True),
        StructField("fulfillments", ArrayType(FULFILLMENT_TYPE), True),
    ]), True),
])
