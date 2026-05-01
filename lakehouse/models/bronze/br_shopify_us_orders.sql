{{
    config(
        materialized="incremental",
        incremental_strategy="merge",
        unique_key="order_id",
        cluster_by=["created_at_date"],
        tags=["bronze", "shopify-kinesis"],
    )
}}

with source as (

    select *
    from {{ source("src_shopify_us", "orders") }}

    {% if is_incremental() %}
        where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}

),

renamed as (

    select
        id                                          as order_id,
        cast(created_at as timestamp)               as created_at,
        cast(to_date(created_at) as date)           as created_at_date,
        cast(updated_at as timestamp)               as updated_at,
        cast(processed_at as timestamp)             as processed_at,
        customer_id,
        email,
        financial_status,
        fulfillment_status,
        {{ cents_to_dollars("total_price_set.shop_money.amount") }}
                                                    as total_price,
        currency,
        "yoga-us"                                   as platform

    from source

)

select * from renamed
