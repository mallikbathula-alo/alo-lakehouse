# alo-lakehouse

Alo Yoga's Databricks Lakehouse — dbt project managing the medallion data platform
(bronze → silver → gold) on **Databricks + Unity Catalog**.

> Migrated from `is-redshift` (AWS Redshift). Uses `dbt-databricks` with separate
> dev and prod Databricks workspaces, Unity Catalog for governance, and Databricks
> Workflows for orchestration.

---

## Quick Start

### Prerequisites

`setup.sh` installs these automatically via Homebrew if missing:

| Tool | Purpose |
|------|---------|
| `uv` | Python package manager |
| `just` | Task runner |
| `awscli` | S3, ECR, Secrets Manager |
| `pre-commit` | SQL linting hooks |
| `databricks` | Databricks CLI v2 (Unity Catalog ops) |

### Setup

```bash
git clone git@github.com:mallikbathula-alo/alo-lakehouse.git
cd alo-lakehouse
./scripts/setup.sh
```

After setup, configure credentials:

**1. dbt** — edit `~/.dbt/profiles.yml`:
```yaml
lakehouse:
  outputs:
    local:
      type: databricks
      host: dbc-e27abc0b-645c.cloud.databricks.com
      http_path: /sql/1.0/warehouses/<warehouse-id>   # SQL Warehouses → Connection details
      token: <your-pat-token>                          # Settings → Developer → Access tokens
      catalog: alo_dev
      schema: dbt_<yourname>                           # e.g. dbt_mallik
      threads: 8
      connect_timeout: 60
      connect_retries: 3
  target: local
```

**2. PySpark** — edit `.env`:
```bash
# Host and token are read from ~/.dbt/profiles.yml automatically
DATABRICKS_CLUSTER_ID=<your-cluster-id>   # Compute → <cluster> → URL
```

**3. Databricks CLI** — run once:
```bash
databricks configure
# host:  https://dbc-e27abc0b-645c.cloud.databricks.com
# token: <your-pat-token>
```

**4. AWS SSO**:
```bash
aws sso login --profile alo-is-dev
```

Verify dbt connectivity:
```bash
cd lakehouse && dbt debug
```

---

## dbt — Sample Runs

### Run a single model

```bash
# Using just (recommended)
just run-local br_shopify_us_orders

# Equivalent dbt command
cd lakehouse && dbt run --defer --select br_shopify_us_orders --target local --state .
```

### Run with prod data as source

```bash
just run-prod-local br_shopify_us_orders
# Reads from alo_prod.bronze.* — writes results to your alo_dev.dbt_<name> schema
```

### Full refresh (rebuild table from scratch)

```bash
just run-full-refresh-local br_shopify_us_orders
```

### Run an entire layer

```bash
cd lakehouse

# All bronze models
dbt run --select tag:bronze --target local

# All silver models
dbt run --select tag:silver --target local

# All gold models
dbt run --select tag:gold --target local
```

### Run tests

```bash
cd lakehouse

# Test a single model
dbt test --select br_shopify_us_orders

# Test all models with a tag
dbt test --select tag:bronze
```

### Seed a reference table

```bash
cd lakehouse && dbt seed --select test_products --target local
# Creates alo_dev.public.test_products as a managed Delta table
```

### Compile without running (check SQL output)

```bash
cd lakehouse && dbt compile --select br_shopify_us_orders
# Output: lakehouse/target/compiled/...
```

### Run modified models only (same as CI)

```bash
cd lakehouse
dbt run --defer --select state:modified+1 --target local --state .
# Only runs models you changed + 1 layer downstream
# Unmodified upstream models resolve to prod tables via --defer
```

### Generate and serve docs

```bash
cd lakehouse && dbt docs generate && dbt docs serve
# Opens http://localhost:8080
```

---

## PySpark — Sample Runs

PySpark uses an isolated venv (`pyspark/.venv`) with `databricks-connect`.
Code runs locally; compute runs on your Databricks cluster.

> The cluster must be **running** in the Databricks workspace before connecting.

### Install PySpark venv (one-time, or after `./scripts/setup.sh`)

```bash
just pyspark-install
```

### Run the catalog explorer example

```bash
just pyspark-run examples/explore_catalog.py
# Lists schemas and tables in alo_dev, prints row counts for bronze tables
```

Expected output:
```
Schemas in alo_dev:
  - bronze
  - silver
  - gold
  - public

Tables in alo_dev.bronze:
  br_shopify_us_orders        → 1,234,567 rows
  br_shopify_us_customers     → 89,432 rows
  ...
```

### Interactive PySpark shell

```bash
just pyspark-shell
# SparkSession ready — use spark.<tab>
>>> spark.catalog.listDatabases()
>>> df = spark.table("alo_dev.bronze.br_shopify_us_orders")
>>> df.printSchema()
>>> df.show(5)
```

### Write a custom PySpark script

Create `pyspark/my_analysis.py`:
```python
from utils.session import get_spark

spark = get_spark()

# Read from Unity Catalog
df = spark.table("alo_dev.bronze.br_shopify_us_orders")

# Transform
revenue_by_month = (
    df.filter("financial_status = 'paid'")
    .groupBy("date_trunc('month', created_at)")
    .agg({"total_price": "sum"})
)

revenue_by_month.show(12)
```

Run it:
```bash
just pyspark-run my_analysis.py
```

### dbt Python model (runs on cluster as part of the dbt DAG)

Create `lakehouse/models/bronze/br_example.py`:
```python
def model(dbt, spark):
    dbt.config(materialized="table", tags=["bronze"])

    df = dbt.ref("some_upstream_model")
    return df.withColumn("processed_at", spark.sql("SELECT current_timestamp()").collect()[0][0])
```

Run like any SQL model:
```bash
cd lakehouse && dbt run --select br_example --target local
```

---

## Architecture

### Unity Catalog Structure

```
alo_dev  (Dev Databricks Workspace)     alo_prod  (Prod Databricks Workspace)
├── bronze    ← raw source data         ├── bronze
├── silver    ← cleaned + conformed     ├── silver
├── gold      ← BI / analytics layer    ├── gold
├── mgt       ← operational tables      ├── mgt
├── snapshots ← SCD Type 2             ├── snapshots
└── public    ← seeds + reference      └── public
```

### Medallion Layers

| Layer | Directory | Schema | Purpose |
|-------|-----------|--------|---------|
| Bronze | `lakehouse/models/1_bronze/` | `bronze` | Raw ingestion from Shopify, GA4, Braze, Salesforce, etc. |
| Silver Pre | `lakehouse/models/2_silver_pre/` | `silver` | Staging, deduplication |
| Silver | `lakehouse/models/3_silver/` | `silver` | Core dimensions & business logic |
| Silver Post | `lakehouse/models/4_silver_post/` | `silver` | Silver aggregations |
| Gold | `lakehouse/models/5_gold/` | `gold` | Analytics-ready tables for BI (Tableau, Thoughtspot, Hex) |
| MGT | `lakehouse/models/mgt/` | `mgt` | Operational & management tables |

### Multi-Region Shopify

Four storefronts managed via `var('shopify_platforms')`:

| Store | Variable | Currency |
|-------|----------|----------|
| US | `src_shopify_us` | USD |
| Canada | `src_shopify_can` | CAD |
| UK | `src_shopify_uk` | GBP |
| International | `src_shopify_intl` | EUR |

---

## Common Commands

```bash
# Local dbt development
just run-local <model>                  # Run model using dev catalog data
just run-prod-local <model>             # Run using prod catalog as source
just run-full-refresh-local <model>     # Full refresh locally
just get-manifest dev                   # Fetch latest manifest from S3

# PySpark
just pyspark-install                    # Set up isolated pyspark/.venv
just pyspark-run <script>               # Run a PySpark script
just pyspark-shell                      # Interactive SparkSession

# Databricks Workflows
just deploy-workflows dev               # Push workflow JSON to dev workspace
just deploy-workflows prod              # Push workflow JSON to prod workspace

# Linting
pre-commit run --files <file.sql>       # Lint specific file
uvx pre-commit run --all-files          # Lint everything

# Permissions
just permissions dev true               # Dry-run Unity Catalog permission grants
just permissions prod false             # Apply permissions to prod

# Release
just tag patch                          # Bump patch, tag, trigger prod deploy
just tag minor                          # Bump minor version
just rollback                           # Rollback prod to previous tag
just ebf                                # Emergency bug fix
```

---

## CI/CD

```
PR opened
  └── Linting (sqlfmt + sqlfluff + ruff + pre-commit-dbt)
  └── dbt validate (--defer --select state:modified+1 against dev workspace)
  └── Monte Carlo dry-run (if montecarlo/ changed)

PR labeled "ready for deployment" + approved review
  └── Deploy to dev workspace
        ├── dbt docs + manifest → S3
        ├── Docker image → ECR (dev)
        ├── DAG → MWAA S3 (dev)
        └── Databricks Workflows upsert (dev)

git tag v*.*.*
  └── Deploy to prod workspace
        ├── dbt docs + manifest → S3
        ├── Docker image → ECR (prod)
        ├── DAG → MWAA S3 (prod)
        ├── Databricks Workflows upsert (prod)
        └── Monte Carlo monitors apply
```

---

## Repository Structure

```
alo-lakehouse/
├── .github/
│   ├── actions/dbt/action.yml          # Composite: AWS OIDC + Databricks auth + dbt setup
│   └── workflows/
│       ├── pr.yaml                     # PR validation
│       ├── dev.yaml                    # Deploy to dev
│       ├── prod.yaml                   # Deploy to prod (on version tag)
│       └── reusable-workflow.yaml      # Shared deployment logic
├── databricks/
│   ├── workflows/                      # Databricks Workflow JSON definitions
│   │   ├── daily_run.json
│   │   └── full_refresh.json
│   └── permissions/                    # Unity Catalog setup scripts
├── jobs/
│   └── alo-lakehouse.py                # Airflow DAG (MWAA)
├── montecarlo/                         # Data quality monitor definitions
├── pyspark/
│   ├── utils/session.py                # get_spark() — Databricks Connect session
│   ├── examples/explore_catalog.py     # Sample catalog explorer script
│   └── requirements.txt                # Isolated deps (databricks-connect)
├── scripts/
│   ├── setup.sh                        # Local dev bootstrap (all prerequisites)
│   ├── deploy_workflows.py             # Upserts Databricks Workflow definitions
│   └── permissions/                    # Unity Catalog GRANT management
├── lakehouse/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── models/
│   │   ├── sources.yml
│   │   ├── 1_bronze/
│   │   ├── 2_silver_pre/
│   │   ├── 3_silver/
│   │   ├── 4_silver_post/
│   │   ├── 5_gold/
│   │   └── mgt/
│   ├── macros/
│   ├── snapshots/
│   ├── seeds/
│   └── analyses/
├── .env.example                        # PySpark env var template
├── .pre-commit-config.yaml
├── .sqlfluff                           # sparksql dialect
├── Dockerfile
├── Justfile
└── pyproject.toml
```

---

## Data Quality

[Monte Carlo](https://www.montecarlodata.com/) monitors in `montecarlo/` cover freshness,
volume anomaly detection, schema changes, and metric anomalies.
Alerts route to `#de-incident` and `#de-oncall-support` Slack channels.

---

## AWS Accounts

| Environment | Account ID     |
|------------|----------------|
| Dev        | `206390103201` |
| Prod       | `715192338314` |

Secrets in AWS Secrets Manager:
- `alo/databricks/{env}` → `{"host": ..., "http_path": ..., "token": ...}`
- `alo/montecarlo` → `{"api_id": ..., "api_token": ...}`
