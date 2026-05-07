# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Locations GraphQL API.
#  One location record per Firehose message.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType,
)

LOCATION_ADDRESS_TYPE = StructType([
    StructField("address1",     StringType(), True),
    StructField("address2",     StringType(), True),
    StructField("city",         StringType(), True),
    StructField("province",     StringType(), True),
    StructField("provinceCode", StringType(), True),
    StructField("country",      StringType(), True),
    StructField("countryCode",  StringType(), True),
    StructField("zip",          StringType(), True),
    StructField("phone",        StringType(), True),
])

SHOPIFY_LOCATIONS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",                   StringType(), True),
        StructField("name",                 StringType(), True),
        StructField("isActive",             StringType(), True),
        StructField("isFulfillmentService", StringType(), True),
        StructField("createdAt",            StringType(), True),
        StructField("updatedAt",            StringType(), True),
        StructField("address",              LOCATION_ADDRESS_TYPE, True),
    ]), True),
])
