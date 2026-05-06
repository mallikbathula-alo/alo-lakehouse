# ============================================================
## ─────────────────────────────────────────────────────────────
#  PySpark schema for the Shopify Orders GraphQL API v2 response.
#  Consumed by ../shopify_orders_schema_v2.py (transform + main).
## ─────────────────────────────────────────────────────────────

from pyspark.sql.types import (
    StructType, StructField,
    StringType, LongType, DoubleType,
    BooleanType, ArrayType, IntegerType
)

# ── Reusable sub-types ────────────────────────────────────────

MONEY_TYPE = StructType([
    StructField("amount",       StringType(), True),
    StructField("currencyCode", StringType(), True),
])

MONEY_BAG_TYPE = StructType([
    StructField("presentmentMoney", MONEY_TYPE, True),
    StructField("shopMoney",        MONEY_TYPE, True),
])

MONEY_BAG_SNAKE_TYPE = StructType([
    StructField("presentment_money", StructType([
        StructField("amount",        StringType(), True),
        StructField("currency_code", StringType(), True),
    ]), True),
    StructField("shop_money", StructType([
        StructField("amount",        StringType(), True),
        StructField("currency_code", StringType(), True),
    ]), True),
])

ADDRESS_TYPE = StructType([
    StructField("id",            StringType(), True),
    StructField("name",          StringType(), True),
    StructField("firstName",     StringType(), True),
    StructField("lastName",      StringType(), True),
    StructField("first_name",    StringType(), True),
    StructField("last_name",     StringType(), True),
    StructField("address1",      StringType(), True),
    StructField("address2",      StringType(), True),
    StructField("city",          StringType(), True),
    StructField("zip",           StringType(), True),
    StructField("province",      StringType(), True),
    StructField("provinceCode",  StringType(), True),
    StructField("province_code", StringType(), True),
    StructField("country",       StringType(), True),
    StructField("country_code",  StringType(), True),
    StructField("phone",         StringType(), True),
    StructField("latitude",      DoubleType(), True),
    StructField("longitude",     DoubleType(), True),
])

TAX_LINE_TYPE = StructType([
    StructField("title",           StringType(), True),
    StructField("rate",            DoubleType(), True),
    StructField("rate_percentage", DoubleType(), True),
    StructField("source",          StringType(), True),
    StructField("channelLiable",   BooleanType(), True),
    StructField("price_set",       MONEY_BAG_SNAKE_TYPE, True),
])

SHIPPING_LINE_NODE_TYPE = StructType([
    StructField("id",                          StringType(), True),
    StructField("code",                        StringType(), True),
    StructField("title",                       StringType(), True),
    StructField("source",                      StringType(), True),
    StructField("phone",                       StringType(), True),
    StructField("carrierIdentifier",           StringType(), True),
    StructField("deliveryCategory",            StringType(), True),
    StructField("requestedFulfillmentService", StringType(), True),
    StructField("discountedPriceSet",          MONEY_BAG_TYPE, True),
    StructField("originalPriceSet",            MONEY_BAG_TYPE, True),
    StructField("tax_lines",                   ArrayType(TAX_LINE_TYPE), True),
])

SHIPPING_LINE_EDGE_TYPE = StructType([
    StructField("node", SHIPPING_LINE_NODE_TYPE, True),
])

# ── Root schema ───────────────────────────────────────────────

SHOPIFY_ORDERS_SCHEMA = StructType([

    # Firehose wrapper
    StructField("fetched_at", StringType(), True),
    StructField("platform",   StringType(), True),
    StructField("version",    StringType(), True),

    StructField("data", StructType([

        # Identifiers
        StructField("id",                 StringType(), True),
        StructField("number",             LongType(),   True),
        StructField("name",               StringType(), True),
        StructField("confirmationNumber", StringType(), True),

        # Status
        StructField("displayFinancialStatus",   StringType(),  True),
        StructField("displayFulfillmentStatus", StringType(),  True),
        StructField("confirmed",                BooleanType(), True),
        StructField("test",                     BooleanType(), True),
        StructField("estimatedTaxes",           BooleanType(), True),
        StructField("taxesIncluded",            BooleanType(), True),

        # Timestamps
        StructField("createdAt",   StringType(), True),
        StructField("updatedAt",   StringType(), True),
        StructField("processedAt", StringType(), True),
        StructField("closedAt",    StringType(), True),
        StructField("cancelledAt", StringType(), True),

        # Cancel info
        StructField("cancelReason", StringType(), True),
        # FIX ❌: was StringType — confirmed struct in data
        StructField("cancellation", StructType([
            StructField("staffNote", StringType(), True),
        ]), True),

        # Customer
        StructField("customer", StructType([
            StructField("id", StringType(), True),
        ]), True),
        StructField("customerAcceptsMarketing", BooleanType(), True),
        StructField("customerLocale",           StringType(),  True),
        StructField("email",                    StringType(),  True),
        StructField("phone",                    StringType(),  True),

        # Customer journey — FIX ❌: lastVisit was StringType, confirmed struct in data
        StructField("customerJourneySummary", StructType([
            StructField("customerOrderIndex", IntegerType(), True),
            StructField("daysToConversion",   DoubleType(),  True),
            StructField("momentsCount", StructType([
                StructField("count",     IntegerType(), True),
                StructField("precision", StringType(),  True),
            ]), True),
            StructField("lastVisit", StructType([           # ← was StringType
                StructField("landingPage",  StringType(), True),   # → landing_site in dbt
                StructField("referrerUrl",  StringType(), True),   # → landing_site_ref in dbt
                StructField("sourceType",   StringType(), True),
                StructField("source",       StringType(), True),
            ]), True),
        ]), True),

        # Currency
        StructField("currencyCode",            StringType(), True),
        StructField("presentmentCurrencyCode", StringType(), True),

        # Money totals
        StructField("totalPriceSet",            MONEY_BAG_TYPE, True),
        StructField("subtotalPriceSet",         MONEY_BAG_TYPE, True),
        StructField("totalTaxSet",              MONEY_BAG_TYPE, True),
        StructField("totalDiscountsSet",        MONEY_BAG_TYPE, True),
        StructField("totalShippingPriceSet",    MONEY_BAG_TYPE, True),
        StructField("totalTipReceivedSet",      MONEY_BAG_TYPE, True),
        StructField("totalOutstandingSet",      MONEY_BAG_TYPE, True),
        StructField("currentTotalPriceSet",     MONEY_BAG_TYPE, True),
        StructField("currentSubtotalPriceSet",  MONEY_BAG_TYPE, True),
        StructField("currentTotalTaxSet",       MONEY_BAG_TYPE, True),
        StructField("currentTotalDiscountsSet", MONEY_BAG_TYPE, True),
        StructField("currentShippingPriceSet",  MONEY_BAG_TYPE, True),
        StructField("originalTotalDutiesSet",   MONEY_BAG_TYPE, True),
        StructField("currentTotalDutiesSet",    MONEY_BAG_TYPE, True),

        # Weight
        StructField("totalWeight", StringType(), True),

        # Addresses
        StructField("shippingAddress", ADDRESS_TYPE, True),
        StructField("billingAddress",  ADDRESS_TYPE, True),

        # Tax lines
        StructField("taxLines", ArrayType(TAX_LINE_TYPE), True),

        # Shipping lines
        StructField("shippingLines", StructType([
            StructField("edges", ArrayType(SHIPPING_LINE_EDGE_TYPE), True),
        ]), True),

        # Discount applications
        StructField("discountApplications", StructType([
            StructField("edges", ArrayType(StructType([
                StructField("node", StringType(), True),
            ])), True),
        ]), True),

        # Discount codes
        StructField("discountCodes", ArrayType(StringType()), True),

        # Custom attributes
        StructField("customAttributes", ArrayType(StructType([
            StructField("key",   StringType(), True),
            StructField("value", StringType(), True),
        ])), True),

        # Tags
        StructField("tags", ArrayType(StringType()), True),

        # Payment
        StructField("paymentGatewayNames", ArrayType(StringType()), True),
        StructField("poNumber",            StringType(), True),
        StructField("note",                StringType(), True),

        # Source / attribution
        StructField("sourceName",          StringType(), True),
        StructField("sourceIdentifier",    StringType(), True),
        StructField("registeredSourceUrl", StringType(), True),
        StructField("referrerUrl",         StringType(), True),   # FIX ❌: was missing
        StructField("statusPageUrl",       StringType(), True),
        StructField("clientIp",            StringType(), True),

        # App
        StructField("app", StructType([
            StructField("id", StringType(), True),
        ]), True),
        StructField("merchantOfRecordApp", StringType(), True),

        # Retail / staff — FIX ⚠️: both were StringType, confirmed structs in data
        StructField("retailLocation", StructType([       # → location_id in dbt
            StructField("id", StringType(), True),
        ]), True),
        StructField("staffMember", StructType([          # → user_id in dbt
            StructField("id", StringType(), True),
        ]), True),

        # Purchasing entity
        StructField("purchasingEntity", StructType([
            StructField("__typename", StringType(), True),
        ]), True),

    ]), True),
])
