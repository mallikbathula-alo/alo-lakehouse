# lakehouse/examples/

Reference examples for developers learning SparkSQL and PySpark transformations
in this dbt + Databricks project.

These models are **disabled by default** (`enabled: false`) — they will not run
as part of the normal pipeline. Enable them explicitly to experiment.

---

## Files

| File | Demonstrates |
|------|-------------|
| `incremental_merge.sql` | SparkSQL incremental model — merge strategy, `is_incremental()` filter, casting, macros, `cluster_by` |
| `pyspark_transform.py` | dbt Python model — PySpark DataFrame transformations, `dbt.ref()`, `withColumn()`, returning results to Delta |

---

## incremental_merge.sql

Shows the standard pattern for incremental bronze models in this repo:

```
source table (raw)
    │
    ├── Full run:        read all rows, merge into Delta table by unique_key
    └── Incremental run: read only rows where updated_at > current max, merge
```

Key SparkSQL patterns:
- `cast(col as timestamp)` / `cast(to_date(col) as date)` — explicit type casting
- `{% if is_incremental() %}` — conditionally filter new rows on subsequent runs
- `{{ source("schema", "table") }}` — reference a raw source table
- `{{ cents_to_dollars("col") }}` — project macro for monetary conversion
- `cluster_by` — Databricks liquid clustering for faster queries on large tables

### Run it

```bash
# Enable and run against dev
cd lakehouse
dbt run --select incremental_merge --target local \
    --vars '{"DBT_MATERIALIZATION": "table"}'

# Or temporarily override enabled in the command
dbt run --select incremental_merge --target local \
    --vars '{"DBT_MATERIALIZATION": "table"}' \
    --no-version-check
```

> Note: this model reads from `src_shopify_us.orders`. Make sure that source
> is accessible in your target catalog before running.

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
   cp examples/incremental_merge.sql models/bronze/br_my_model.sql
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
