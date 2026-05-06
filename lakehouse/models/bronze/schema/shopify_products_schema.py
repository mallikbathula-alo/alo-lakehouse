# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Products GraphQL API v2.
#  One product record per firehose message; variants are nested.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType, ArrayType
)

SELECTED_OPTION_TYPE = StructType([
    StructField("name",  StringType(), True),
    StructField("value", StringType(), True),
    StructField("optionValue", StructType([
        StructField("id",          StringType(), True),
        StructField("name",        StringType(), True),
        StructField("hasVariants", StringType(), True),
    ]), True),
])

INVENTORY_ITEM_TYPE = StructType([
    StructField("id",               StringType(), True),
    StructField("requiresShipping", StringType(), True),
    StructField("measurement", StructType([
        StructField("weight", StructType([
            StructField("unit",  StringType(), True),
            StructField("value", StringType(), True),
        ]), True),
    ]), True),
])

VARIANT_NODE_TYPE = StructType([
    StructField("id",               StringType(), True),
    StructField("title",            StringType(), True),
    StructField("displayName",      StringType(), True),
    StructField("sku",              StringType(), True),
    StructField("barcode",          StringType(), True),
    StructField("price",            StringType(), True),
    StructField("compareAtPrice",   StringType(), True),
    StructField("taxCode",          StringType(), True),
    StructField("taxable",          StringType(), True),
    StructField("position",         StringType(), True),
    StructField("inventoryPolicy",  StringType(), True),
    StructField("inventoryQuantity", StringType(), True),
    StructField("createdAt",        StringType(), True),
    StructField("updatedAt",        StringType(), True),
    StructField("image",            StringType(), True),   # null or struct — keep as string
    StructField("selectedOptions",  ArrayType(SELECTED_OPTION_TYPE), True),
    StructField("inventoryItem",    INVENTORY_ITEM_TYPE, True),
    StructField("metafields", StructType([
        StructField("edges", ArrayType(StructType([
            StructField("node", StringType(), True),
        ])), True),
    ]), True),
])

PRODUCT_OPTION_TYPE = StructType([
    StructField("id",       StringType(), True),
    StructField("name",     StringType(), True),
    StructField("position", StringType(), True),
    StructField("values",   ArrayType(StringType()), True),
])

COLLECTION_NODE_TYPE = StructType([
    StructField("id",    StringType(), True),
    StructField("title", StringType(), True),
])

CHANNEL_NODE_TYPE = StructType([
    StructField("channel", StructType([
        StructField("name", StringType(), True),
    ]), True),
])

# config_metafields_1/2/3 share the same shape: {edges: []}
EMPTY_EDGES_TYPE = StructType([
    StructField("edges", ArrayType(StructType([
        StructField("node", StringType(), True),
    ])), True),
])

SHOPIFY_PRODUCTS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",               StringType(), True),
        StructField("title",            StringType(), True),
        StructField("handle",           StringType(), True),
        StructField("status",           StringType(), True),
        StructField("productType",      StringType(), True),
        StructField("vendor",           StringType(), True),
        StructField("descriptionHtml",  StringType(), True),
        StructField("templateSuffix",   StringType(), True),
        StructField("onlineStoreUrl",   StringType(), True),
        StructField("publishedAt",      StringType(), True),
        StructField("createdAt",        StringType(), True),
        StructField("updatedAt",        StringType(), True),
        StructField("tracksInventory",  StringType(), True),
        StructField("totalInventory",   StringType(), True),
        StructField("tags",             ArrayType(StringType()), True),
        StructField("options",          ArrayType(PRODUCT_OPTION_TYPE), True),
        StructField("variants", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", VARIANT_NODE_TYPE, True),
            ])), True),
        ]), True),
        StructField("collections", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", COLLECTION_NODE_TYPE, True),
            ])), True),
        ]), True),
        StructField("channels", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", CHANNEL_NODE_TYPE, True),
            ])), True),
        ]), True),
        StructField("media",             EMPTY_EDGES_TYPE, True),
        StructField("config_metafields_1", EMPTY_EDGES_TYPE, True),
        StructField("config_metafields_2", EMPTY_EDGES_TYPE, True),
        StructField("config_metafields_3", EMPTY_EDGES_TYPE, True),
    ]), True),
])
