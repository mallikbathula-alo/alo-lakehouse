# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Customers GraphQL API v2.
#  One customer record per firehose message.
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType, ArrayType
)

MONEY_TYPE = StructType([
    StructField("amount",       StringType(), True),
    StructField("currencyCode", StringType(), True),
])

MAILING_ADDRESS_TYPE = StructType([
    StructField("id",            StringType(), True),
    StructField("name",          StringType(), True),
    StructField("firstName",     StringType(), True),
    StructField("lastName",      StringType(), True),
    StructField("company",       StringType(), True),
    StructField("address1",      StringType(), True),
    StructField("address2",      StringType(), True),
    StructField("city",          StringType(), True),
    StructField("zip",           StringType(), True),
    StructField("province",      StringType(), True),
    StructField("provinceCode",  StringType(), True),
    StructField("country",       StringType(), True),
    StructField("countryCodeV2", StringType(), True),
    StructField("phone",         StringType(), True),
    StructField("latitude",      StringType(), True),
    StructField("longitude",     StringType(), True),
])

METAFIELD_DEFINITION_TYPE = StructType([
    StructField("id", StringType(), True),
])

METAFIELD_NODE_TYPE = StructType([
    StructField("key",         StringType(), True),
    StructField("jsonValue",   StringType(), True),
    StructField("createdAt",   StringType(), True),
    StructField("description", StringType(), True),
    StructField("definition",  METAFIELD_DEFINITION_TYPE, True),
])

SHOPIFY_CUSTOMERS_SCHEMA = StructType([
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),
    StructField("data", StructType([
        StructField("id",               StringType(), True),
        StructField("email",            StringType(), True),
        StructField("firstName",        StringType(), True),
        StructField("lastName",         StringType(), True),
        StructField("phone",            StringType(), True),
        StructField("note",             StringType(), True),
        StructField("state",            StringType(), True),
        StructField("taxExempt",        StringType(), True),
        StructField("verifiedEmail",    StringType(), True),
        StructField("dataSaleOptOut",   StringType(), True),
        StructField("numberOfOrders",   StringType(), True),
        StructField("multipassIdentifier", StringType(), True),
        StructField("createdAt",        StringType(), True),
        StructField("updatedAt",        StringType(), True),
        StructField("tags",             ArrayType(StringType()), True),
        StructField("amountSpent",      MONEY_TYPE, True),
        StructField("statistics", StructType([
            StructField("predictedSpendTier", StringType(), True),
        ]), True),
        StructField("defaultAddress",   MAILING_ADDRESS_TYPE, True),
        StructField("addresses",        ArrayType(MAILING_ADDRESS_TYPE), True),
        StructField("emailMarketingConsent", StructType([
            StructField("marketingState",    StringType(), True),
            StructField("marketingOptInLevel", StringType(), True),
            StructField("consentUpdatedAt",  StringType(), True),
        ]), True),
        StructField("smsMarketingConsent", StructType([
            StructField("marketingState",    StringType(), True),
            StructField("marketingOptInLevel", StringType(), True),
            StructField("consentUpdatedAt",  StringType(), True),
        ]), True),
        StructField("lastOrder", StructType([
            StructField("id",   StringType(), True),
            StructField("name", StringType(), True),
        ]), True),
        StructField("metafields", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", METAFIELD_NODE_TYPE, True),
            ])), True),
        ]), True),
    ]), True),
])
