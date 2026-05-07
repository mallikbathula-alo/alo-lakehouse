# lakehouse/examples/

Reference examples for developers learning SparkSQL and PySpark in this
dbt + Databricks project. All examples are **self-contained** — no catalog
tables or external sources required.

There are two types of examples:

- **dbt models** (`models/examples/sparksql_incremental.sql`, `models/examples/pyspark_transform.py`) — run via `dbt run`; write to `alo_dev.public` schema so they don't pollute bronze/silver/gold. No file edits required — run as-is.
- **Standalone PySpark scripts** (`explore_catalog.py`) — run via `just pyspark-run`;
  connect to Databricks via Databricks Connect (serverless or classic cluster)

---

## Files

| File | Type | Demonstrates |
|------|------|-------------|
| `sparksql_incremental.sql` | dbt SQL model | SparkSQL incremental merge — VALUES data, `is_incremental()`, casting, CASE, `cluster_by` |
| `pyspark_transform.py` | dbt Python model | PySpark DataFrame API — inline data, `withColumn()`, window dedup, type casting, conditional logic |
| `explore_catalog.py` | Standalone PySpark script | Databricks Connect — `spark.range()`, `createDataFrame()`, `spark.sql()`, DataFrame aggregations |

---

## sparksql_incremental.sql

Shows the standard pattern for incremental bronze models using self-contained
sample data — no catalog tables required.

```
VALUES (sample rows)
    │
    ├── Full run:        materialize all rows into a Delta table (unique_key = order_id)
    └── Incremental run: read only rows where updated_at > current max, merge
```

Key SparkSQL patterns demonstrated:
- `VALUES` clause — inline sample data, no source dependency
- `cast(col as timestamp)` / `cast(to_date(col) as date)` — explicit type casting (no `::` shorthand)
- `{% if is_incremental() %}` — filter new rows on subsequent runs; `{{ this }}` = current Delta table
- `cast(amount_cents / 100.0 as decimal(10, 2))` — arithmetic with precision control
- `upper()`, `case when` — string and conditional functions
- `current_timestamp()` — SparkSQL equivalent of `getdate()` / `now()`
- `cluster_by` — Databricks liquid clustering for faster queries on large tables

### Run it

No prerequisites beyond a working `dbt debug --target local`. Output lands in `alo_dev.public`.

```bash
cd lakehouse

# First run — creates the Delta table in alo_dev.public
dbt run --select sparksql_incremental --target local

# Second run — incremental merge (only rows newer than current max updated_at)
dbt run --select sparksql_incremental --target local
```

---

## pyspark_transform.py

Shows how to write a **dbt Python model** using self-contained sample data —
no catalog tables required.

Key PySpark patterns demonstrated:
- `spark.createDataFrame()` — inline sample data with explicit schema, no `dbt.ref()` dependency
- `F.regexp_extract()` — extract numeric ID from a GraphQL global ID string
- `F.to_timestamp()`, `F.to_date()` — date/time parsing
- `F.round().cast(DecimalType)` — arithmetic with precision control
- `F.when().otherwise()` — conditional column logic
- `F.coalesce()` — null handling / fallback values
- `F.upper()` — string functions
- `F.current_timestamp()` — audit column
- `Window + row_number()` — deduplication by natural key, keeping latest row
- All imports inside `model()` — required for dbt Python models

### When to use Python models vs SQL models

| Use SQL | Use Python |
|---------|-----------|
| Standard SELECT transformations | Complex array/struct manipulation |
| Aggregations, joins, window functions | ML feature engineering |
| 95% of bronze/silver/gold models | Multi-step logic SQL can't express cleanly |

### Run it

No cluster needs to be running — the model is pre-configured for serverless (`submission_method="serverless_cluster"`).
Output lands in `alo_dev.public`.

```bash
cd lakehouse
dbt run --select pyspark_transform --target local
```

> Python models execute on Databricks serverless compute, not locally.
> The `submission_method="serverless_cluster"` config in the model (and `+submission_method` in
> `dbt_project.yml` for all examples) selects the serverless job runner — no `DATABRICKS_CLUSTER_ID` required.

---

## explore_catalog.py

Standalone PySpark script — runs locally via Databricks Connect, compute executes
on Databricks (serverless or classic cluster). Demonstrates the full development loop
without needing any specific catalog tables.

Key patterns:
- `get_spark()` — shared session factory from `lakehouse/utils/spark_utils.py`
- `spark.sql("SHOW SCHEMAS / TABLES")` — catalog exploration
- `spark.range(1, 6)` — generate a sequence DataFrame, no source needed
- `spark.createDataFrame(rows, schema)` — typed inline data
- `withColumn()`, `filter()`, `groupBy().agg()` — DataFrame transformations
- `spark.table("catalog.schema.table")` — read a real Delta table (commented out)

### Run it

```bash
just pyspark-run explore_catalog.py
# or directly:
cd lakehouse && ../.venv/bin/python examples/explore_catalog.py
```

### Compute configuration (`.env`)

```bash
# Option A — Serverless (preferred): no cluster required
DATABRICKS_SERVERLESS_COMPUTE_ID=auto

# Option B — Classic cluster: cluster must be running
# DATABRICKS_CLUSTER_ID=<your-cluster-id>
```

`get_spark()` in `utils/spark_utils.py` checks for `DATABRICKS_SERVERLESS_COMPUTE_ID` first
and falls back to `DATABRICKS_CLUSTER_ID` if not set.

---

## Adapting for production

To turn an example into a real model:

1. Copy the file into the appropriate layer directory:
   ```bash
   cp models/examples/sparksql_incremental.sql models/bronze/br_my_model.sql
   # or for Python:
   cp models/examples/pyspark_transform.py models/bronze/br_my_model.py
   ```

2. Update the `config()` block — change `tags=["example"]` to the correct layer tag and remove
   `submission_method` (Python only, handled by profile default for production):
   ```sql
   -- SQL model
   {{ config(materialized="incremental", ..., tags=["bronze"]) }}
   ```
   ```python
   # Python model
   dbt.config(materialized="table", tags=["bronze"])
   ```

3. Replace the inline `VALUES` / `spark.createDataFrame()` sample data with real sources:
   ```sql
   select * from {{ source("schema", "table") }}
   ```
   ```python
   df = dbt.ref("upstream_model")
   # or
   df = dbt.source("schema", "table")
   ```

4. Add a properties entry in the layer's `.yml` file:
   ```yaml
   - name: br_my_model
     description: "..."
     config:
       tags: ["bronze"]
   ```

5. Run pre-commit to validate:
   ```bash
   pre-commit run --files models/bronze/br_my_model.sql
   ```
