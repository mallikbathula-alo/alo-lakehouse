# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Line Items GraphQL API v2.
#  Each firehose record wraps one order with its lineItems edges.
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

TAX_LINE_TYPE = StructType([
    StructField("title",         StringType(), True),
    StructField("rate",          StringType(), True),
    StructField("channelLiable", StringType(), True),
    StructField("priceSet",      MONEY_BAG_TYPE, True),
])

DISCOUNT_ALLOCATION_TYPE = StructType([
    StructField("allocatedAmountSet", MONEY_BAG_TYPE, True),
])

LINE_ITEM_PROPERTY_TYPE = StructType([
    StructField("name",  StringType(), True),
    StructField("value", StringType(), True),
])

LINE_ITEM_NODE_TYPE = StructType([
    StructField("id",                    StringType(), True),
    StructField("name",                  StringType(), True),
    StructField("title",                 StringType(), True),
    StructField("variantTitle",          StringType(), True),
    StructField("sku",                   StringType(), True),
    StructField("vendor",                StringType(), True),
    StructField("quantity",              StringType(), True),
    StructField("currentQuantity",       StringType(), True),
    StructField("refundableQuantity",    StringType(), True),
    StructField("unfulfilledQuantity",   StringType(), True),
    StructField("nonFulfillableQuantity", StringType(), True),
    StructField("isGiftCard",            StringType(), True),
    StructField("taxable",               StringType(), True),
    StructField("requiresShipping",      StringType(), True),
    StructField("originalTotalSet",      MONEY_BAG_TYPE, True),
    StructField("totalDiscountSet",      MONEY_BAG_TYPE, True),
    StructField("discountedUnitPriceAfterAllDiscountsSet", MONEY_BAG_TYPE, True),
    StructField("taxLines",              ArrayType(TAX_LINE_TYPE), True),
    StructField("discountAllocations",   ArrayType(DISCOUNT_ALLOCATION_TYPE), True),
    StructField("properties",            ArrayType(LINE_ITEM_PROPERTY_TYPE), True),
    StructField("variant", StructType([
        StructField("id",             StringType(), True),
        StructField("price",          StringType(), True),
        StructField("compareAtPrice", StringType(), True),
        StructField("taxCode",        StringType(), True),
    ]), True),
    StructField("product", StructType([
        StructField("id", StringType(), True),
    ]), True),
])

SHOPIFY_LINEITEMS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",           StringType(), True),   # order GID
        StructField("updatedAt",    StringType(), True),
        StructField("taxesIncluded", StringType(), True),
        StructField("lineItems", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", LINE_ITEM_NODE_TYPE, True),
            ])), True),
        ]), True),
    ]), True),
])
