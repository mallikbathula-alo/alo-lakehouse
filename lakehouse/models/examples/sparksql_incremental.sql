-- ─────────────────────────────────────────────────────────────────────────────
-- sparksql_incremental.sql
-- Demonstrates SparkSQL incremental model patterns on self-contained sample data.
-- No external sources required — runs as-is after enabling.
--
-- Key patterns demonstrated:
--   - VALUES clause        — inline sample data, no source() dependency
--   - Incremental merge    — materialized="incremental", incremental_strategy="merge"
--   - is_incremental()     — Jinja block that filters new rows on subsequent runs
--   - {{ this }}           — resolves to the current model's Delta table
--   - unique_key           — column used to match existing rows for upsert
--   - cluster_by           — Databricks liquid clustering for query performance
--   - cast()               — explicit type casting; SparkSQL has no :: shorthand
--   - to_date()            — extract a date from a timestamp string
--   - decimal(p, s)        — fixed-precision numeric type for monetary values
--   - upper()              — string function
--   - case when            — conditional column logic
--   - current_timestamp()  — audit column; equivalent of getdate() / now()
--
-- SparkSQL vs standard SQL gotchas:
--   - No ::      → use cast(col as type)
--   - No isnull  → use col is null
--   - No top N   → use limit N
--   - No nvl     → use coalesce(col, fallback)
--   - No varchar → use string
--   - No float8  → use double
--
-- How incremental runs work:
--   1. First run  : full table scan of raw CTE, writes all rows to Delta table
--   2. Subsequent : is_incremental() = true, WHERE clause filters to new rows only,
--                   dbt merges result into existing table on unique_key
--
-- Run:
--     cd lakehouse
--     dbt run --select sparksql_incremental --target local   (first run: full)
--     dbt run --select sparksql_incremental --target local   (subsequent: incremental)
-- ─────────────────────────────────────────────────────────────────────────────

{{
    config(
        materialized="incremental",
        incremental_strategy="merge",
        unique_key="order_id",
        cluster_by=["order_date"],
        tags=["bronze"],
    )
}}

with raw as (

    -- Self-contained sample data using VALUES.
    -- In production, replace with: select * from {{ source("schema", "table") }}
    select *
    from (
        values
            (1001, '2024-01-15T08:00:00', '2024-01-15T08:00:00', 15000, 'paid'),
            (1002, '2024-01-16T11:30:00', '2024-01-17T09:00:00', 20050, 'refunded'),
            (1003, '2024-01-17T14:00:00', '2024-01-17T14:00:00',  7500, 'paid')
    ) as t(order_id, created_at, updated_at, amount_cents, status)

    {% if is_incremental() %}
        -- On incremental runs, only process rows newer than what is already
        -- in the Delta table. {{ this }} resolves to the current model's table.
        where cast(updated_at as timestamp) > (
            select max(updated_at) from {{ this }}
        )
    {% endif %}

),

transformed as (

    select
        -- ── Identifiers ───────────────────────────────────────────────────
        order_id,

        -- ── SparkSQL type casting ─────────────────────────────────────────
        -- Use cast() — SparkSQL does not support :: shorthand
        cast(created_at as timestamp)               as created_at,
        cast(to_date(created_at) as date)           as order_date,
        cast(updated_at as timestamp)               as updated_at,

        -- ── Arithmetic on columns ─────────────────────────────────────────
        -- cents to dollars: divide by 100, cast to decimal with precision
        cast(amount_cents / 100.0 as decimal(10, 2)) as amount,

        -- ── String functions ──────────────────────────────────────────────
        upper(status)                               as status,

        -- ── Conditional logic ─────────────────────────────────────────────
        case
            when status = 'paid'      then true
            when status = 'refunded'  then false
            else null
        end                                         as is_paid,

        -- ── Audit column ──────────────────────────────────────────────────
        -- current_timestamp() is SparkSQL equivalent of getdate() / now()
        current_timestamp()                         as _ingested_at

    from raw

)

select * from transformed
