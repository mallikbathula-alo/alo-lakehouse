-- ─────────────────────────────────────────────────────────────────────────────
-- incremental_merge.sql
-- Example: SparkSQL incremental model with merge strategy
--
-- Demonstrates:
--   - Incremental materialization with merge strategy (upsert by unique_key)
--   - is_incremental() filter to process only new/changed rows
--   - SparkSQL casting: timestamp, date
--   - Macro usage: cents_to_dollars()
--   - cluster_by for Databricks liquid clustering
--   - source() reference pattern
-- ─────────────────────────────────────────────────────────────────────────────

{{
    config(
        materialized="incremental",
        incremental_strategy="merge",
        unique_key="order_id",
        cluster_by=["created_at_date"],
        tags=["bronze"],
        enabled=false,
    )
}}

with source as (

    -- {{ source() }} resolves to the raw table defined in sources.yml
    -- On incremental runs, only rows newer than the current max are read
    select *
    from {{ source("src_shopify_us", "orders") }}

    {% if is_incremental() %}
        -- SparkSQL: use subquery against {{ this }} (the existing Delta table)
        where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}

),

renamed as (

    select
        id                                              as order_id,

        -- SparkSQL casting: cast() instead of :: syntax
        cast(created_at as timestamp)                   as created_at,
        cast(to_date(created_at) as date)               as created_at_date,
        cast(updated_at as timestamp)                   as updated_at,
        cast(processed_at as timestamp)                 as processed_at,

        customer_id,
        email,
        financial_status,
        fulfillment_status,

        -- Macro: converts cents (integer) to dollars (decimal)
        {{ cents_to_dollars("total_price_set.shop_money.amount") }}
                                                        as total_price,
        currency,
        "yoga-us"                                       as platform

    from source

)

select * from renamed
