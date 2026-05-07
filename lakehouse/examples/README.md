# lakehouse/examples/

Reference examples for developers learning SparkSQL and PySpark transformations
in this dbt + Databricks project.

These models are **disabled by default** (`enabled: false`) — they will not run
as part of the normal pipeline. Enable them explicitly to experiment.

---

## Files

| File | Demonstrates |
|------|-------------|
| `sparksql_incremental.sql` | SparkSQL incremental model — VALUES sample data, merge strategy, `is_incremental()`, casting, CASE, `cluster_by` |
| `pyspark_transform.py` | dbt Python model — PySpark DataFrame transformations, `dbt.ref()`, `withColumn()`, returning results to Delta |

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

```bash
cd lakehouse

# Full run — creates the Delta table from scratch
dbt run --select sparksql_incremental --target local

# Incremental run — merges only new rows
dbt run --select sparksql_incremental --target local
```

---

## pyspark_transform.py

Shows how to write a **dbt Python model** that runs PySpark on the Databricks cluster.

Key concepts:
- The `model(dbt, spark)` function signature is fixed — dbt injects both arguments
- `dbt.ref("model_name")` reads an upstream dbt model or seed as a Spark DataFrame
- `dbt.source("schema", "table")` reads a raw source
- Return a Spark DataFrame — dbt writes it to Unity Catalog as a Delta table
- Import PySpark functions **inside** the function body (required for dbt Python models)
- `dbt.config()` sets materialization, tags, and other model config

### When to use Python models vs SQL models

| Use SQL | Use Python |
|---------|-----------|
| Standard SELECT transformations | Complex array/struct manipulation |
| Aggregations, joins, window functions | ML feature engineering |
| 95% of bronze/silver/gold models | Multi-step PySpark logic SQL can't express |

### Run it

First, make sure the `test_products` seed exists:

```bash
cd lakehouse
dbt seed --select test_products --target local
```

Then run the Python model:

```bash
dbt run --select pyspark_transform --target local
```

> Python models execute on the Databricks cluster (not locally). The cluster must
> be running before invoking `dbt run`. Check `DATABRICKS_CLUSTER_ID` in `.env`.

---

## Adapting for production

To turn an example into a real model:

1. Copy the file into the appropriate layer directory:
   ```bash
   cp examples/sparksql_incremental.sql models/bronze/br_my_model.sql
   ```

2. Remove `enabled=false` from the `config()` block

3. Add a properties entry in the layer's `.yml` file:
   ```yaml
   - name: br_my_model
     description: "..."
     config:
       tags: ["bronze"]
   ```

4. Run pre-commit to validate:
   ```bash
   pre-commit run --files models/bronze/br_my_model.sql
   ```
