# alo-lakehouse

Alo Yoga's Databricks Lakehouse — dbt project managing the medallion data platform
(bronze → silver → gold) on **Databricks + Unity Catalog**.

> Uses `dbt-databricks` with separate dev and prod Databricks workspaces, Unity Catalog
> for governance, and Databricks Workflows for orchestration.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Python Environment](#python-environment)
- [dbt — Sample Runs](#dbt--sample-runs)
- [When to Use dbt Python Models vs Standalone PySpark](#when-to-use-dbt-python-models-vs-standalone-pyspark)
- [PySpark — Sample Runs](#pyspark--sample-runs)
- [Architecture](#architecture)
- [Common Commands](#common-commands)
- [Unity Catalog Setup](#unity-catalog-setup)
- [CI/CD](#cicd)
- [Repository Structure](#repository-structure)
- [Data Quality](#data-quality)
- [AWS Accounts](#aws-accounts)

---

## Quick Start

### Prerequisites

`setup.sh` installs these automatically via Homebrew if missing:

| Tool | Purpose |
|------|---------|
| `uv` | Python package manager (manages single shared venv) |
| `just` | Task runner |
| `awscli` | S3, ECR, Secrets Manager |
| `pre-commit` | SQL linting hooks |
| `databricks` | Databricks CLI v2 (Unity Catalog ops) |

### Setup

```bash
git clone git@github.com:mallikbathula-alo/alo-lakehouse.git
cd alo-lakehouse
./scripts/setup.sh       # installs prerequisites, creates .venv, installs all deps
```

After setup, configure credentials:

**1. dbt + PySpark** — edit `~/.dbt/profiles.yml`:
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

**2. PySpark cluster** — edit `.env` (copy from `.env.example`):
```bash
# Host and token are read from ~/.dbt/profiles.yml automatically
DATABRICKS_CLUSTER_ID=<your-cluster-id>   # Compute → <cluster> → URL: .../clusters/<ID>
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

**Validate your token** before running dbt or PySpark:
```bash
curl -s https://dbc-e27abc0b-645c.cloud.databricks.com/api/2.0/clusters/list \
  -H "Authorization: Bearer <your-pat-token>" | python3 -m json.tool | head -5
# Success: returns JSON with cluster list
# Failure: {"error_code":"PERMISSION_DENIED","message":"Invalid access token..."}
```

> If `DATABRICKS_TOKEN` is set as a shell env var it will override `profiles.yml`.
> Always check with `echo $DATABRICKS_TOKEN` and `unset DATABRICKS_TOKEN` if stale.

Verify dbt connectivity (must run from `lakehouse/`):
```bash
cd lakehouse && dbt debug --target local
```

---

## Python Environment

All dependencies — dbt, databricks-connect, and PySpark utils — share a **single `.venv`**:

| Package | Version | Purpose |
|---------|---------|---------|
| `dbt-databricks` | `1.10.19` | dbt adapter for Databricks |
| `databricks-connect` | `15.4.21` | PySpark local execution via Databricks Connect |
| `python-dotenv` | `>=1.0.0` | Load `.env` for cluster credentials |

> `databricks-connect` version must match your cluster's Databricks Runtime major version.
> Current cluster: **DBR 15.4** → `databricks-connect==15.4.x`.
> When upgrading the cluster runtime, update `databricks-connect` in `pyproject.toml` to match.

PySpark scripts live in `lakehouse/pyspark/` alongside dbt models.

---

## dbt — Sample Runs

All `dbt` commands must be run from the `lakehouse/` directory (where `dbt_project.yml` lives).

### Verify connection

```bash
cd lakehouse && dbt debug --target local
```

### Seed a reference table

```bash
cd lakehouse && dbt seed --select test_products --target local
# Creates alo_dev.public.test_products as a managed Delta table
```

### Run a single model

```bash
# Using just (recommended — handles cd automatically)
just run-local br_shopify_us_orders

# Raw dbt command
cd lakehouse && dbt run --defer --select br_shopify_us_orders --target local --state .
```

### Run a dbt Python model (executes on cluster)

```bash
cd lakehouse && dbt run --select br_test_python --target local
# Reads from test_products seed, adds price_with_tax column
# Inspect compiled output: cat lakehouse/target/run/lakehouse/models/bronze/br_test_python.py
```

### Run with prod data as source

```bash
just run-prod-local br_shopify_us_orders
# Reads from alo_prod.bronze.* — writes to your alo_dev.dbt_<name> schema
```

### Full refresh

```bash
just run-full-refresh-local br_shopify_us_orders
```

### Run an entire layer

```bash
cd lakehouse
dbt run --select tag:bronze --target local
dbt run --select tag:silver --target local
dbt run --select tag:gold   --target local
```

### Run tests

```bash
cd lakehouse
dbt test --select br_test_python       # test a specific model
dbt test --select tag:bronze           # test all bronze models
```

### Run modified models only (same as CI)

```bash
cd lakehouse
dbt run --defer --select state:modified+1 --target local --state .
# Runs only changed models + 1 layer downstream; unmodified upstream resolves to prod
```

### Generate and serve docs

```bash
cd lakehouse && dbt docs generate && dbt docs serve
# Opens http://localhost:8080
```

---

## When to Use dbt Python Models vs Standalone PySpark

**Use dbt Python models by default. Use standalone PySpark scripts only when dbt can't do the job.**

### Use dbt Python models when:

| Scenario | Reason |
|----------|--------|
| Output is a table consumed downstream | Gets `dbt.ref()` lineage, appears in DAG, testable |
| Transformation is part of bronze/silver/gold | Orchestrated automatically with the rest of the pipeline |
| You need complex PySpark logic SQL can't express | ML feature engineering, array explosion, custom UDFs |
| Data quality matters | `dbt test` works on Python model outputs just like SQL |

```python
# lakehouse/models/bronze/br_example.py
def model(dbt, spark):
    dbt.config(materialized="table", tags=["bronze"])
    df = dbt.ref("upstream_model")           # tracked lineage
    return df.withColumn(...)                # runs on cluster, result in Unity Catalog
```

### Use standalone PySpark scripts (`lakehouse/pyspark/`) when:

| Scenario | Reason |
|----------|--------|
| Ad-hoc exploration / analysis | No need to materialize a permanent table |
| ML model training | Output is a model artifact, not a Delta table |
| Streaming jobs | dbt doesn't support streaming |
| Multi-step pipelines with side effects | Writing to external systems, S3, APIs |
| One-off data fixes or backfills | Shouldn't be in the dbt DAG permanently |

```python
# lakehouse/pyspark/my_analysis.py
spark = get_spark()
df = spark.table("alo_dev.bronze.br_shopify_us_orders")
df.filter(...).show()                        # explore only, nothing persisted
```

> **Rule:** If the output is a table that other models or BI tools depend on → dbt Python model.
> If it's exploratory, ML, streaming, or a one-off → standalone script.
> Don't use standalone scripts to produce production tables — you lose lineage, testing,
> documentation, and Monte Carlo monitoring.

---

## PySpark — Sample Runs

PySpark scripts in `lakehouse/pyspark/` use **Databricks Connect** — code runs locally,
compute runs on your Databricks cluster.

> The cluster must be **running** before connecting. DATABRICKS_CLUSTER_ID must be set in `.env`.

### Run the catalog explorer example

```bash
just pyspark-run examples/explore_catalog.py
# Lists schemas in alo_dev, shows tables in public schema
```

Expected output:
```
── Schemas in alo_dev ──
bronze / silver / gold / mgt / public / snapshots

── Tables in alo_dev.public ──
test_products

── Sample rows from alo_dev.public.test_products ──
+----------+----------------+-----------+------+
|product_id|    product_name|   category| price|
+----------+----------------+-----------+------+
|         1| Airlift Legging|    Bottoms|128.00|
|         2|  Define Jacket |       Tops|168.00|
|         3|    Warrior Mat |Accessories| 96.00|
+----------+----------------+-----------+------+
```

### Interactive PySpark shell

```bash
just pyspark-shell
# SparkSession ready — use spark.<tab>
>>> df = spark.table("alo_dev.bronze.br_shopify_us_orders")
>>> df.printSchema()
>>> df.show(5)
```

### Write a custom PySpark script

Create `lakehouse/pyspark/my_analysis.py`:
```python
from utils.session import get_spark

spark = get_spark()

df = spark.table("alo_dev.bronze.br_shopify_us_orders")

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

### Write a dbt Python model (runs on cluster as part of dbt DAG)

Create `lakehouse/models/bronze/br_example.py`:
```python
def model(dbt, spark):
    dbt.config(materialized="table", tags=["bronze"])
    df = dbt.ref("test_products")
    from pyspark.sql import functions as F
    return df.withColumn("price_with_tax", F.round(F.col("price") * 1.1, 2))
```

Run exactly like a SQL model:
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

Managed locations: `s3://is-dev-lakehouse/{schema}` and `s3://is-prod-lakehouse/{schema}`.

### Medallion Layers

| Layer | Directory | Schema | Purpose |
|-------|-----------|--------|---------|
| Bronze | `lakehouse/models/bronze/` | `bronze` | Raw ingestion — Shopify, GA4, Braze, Salesforce |
| Silver | `lakehouse/models/silver/` | `silver` | Staging, deduplication, core dimensions & business logic |
| Gold | `lakehouse/models/gold/` | `gold` | Analytics-ready for BI (Tableau, Thoughtspot, Hex) |
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
# Local dbt development (run from lakehouse/ or use just)
just run-local <model>                  # Run model using dev catalog data
just run-prod-local <model>             # Run using prod catalog as source
just run-full-refresh-local <model>     # Full refresh locally
just get-manifest dev                   # Fetch latest manifest from S3

# PySpark (scripts live in lakehouse/pyspark/)
just pyspark-run <script>               # Run a PySpark script via Databricks Connect
just pyspark-shell                      # Interactive SparkSession

# Databricks Workflows
just deploy-workflows dev               # Push workflow JSON to dev workspace
just deploy-workflows prod              # Push workflow JSON to prod workspace

# SQL runner (for Unity Catalog setup scripts)
just run-sql <file.sql>                 # Execute SQL file against SQL Warehouse

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

## Unity Catalog Setup

See [`databricks/permissions/README.md`](databricks/permissions/README.md) for the full catalog setup guide covering:

- Account group creation
- Storage credential + external location (account-level CLI)
- Catalog, schema, and grant setup (workspace-level SQL)
- Permission model per group
- Troubleshooting common errors

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
│   ├── clusters/                       # Cluster config JSON + setup steps (see README)
│   │   ├── dev_cluster.json            # Interactive cluster for dev/PySpark
│   │   ├── prod_cluster.json           # Job cluster for Databricks Workflows
│   │   └── README.md                   # Steps to create/update clusters via CLI
│   ├── workflows/                      # Databricks Workflow definitions (see README)
│   │   ├── README.md                   # Setup + deploy steps
│   │   ├── daily_run.json              # Daily 4 AM PT: bronze→silver→gold→tests
│   │   └── full_refresh.json           # Sundays 1 AM PT: full rebuild of all layers
│   └── permissions/                    # Unity Catalog setup (see README for full steps)
│       ├── README.md                   # Full catalog setup guide
│       ├── groups_setup.sql            # Account-level group creation
│       ├── dev_account_setup.sh        # Dev storage credential + external location
│       ├── dev_workspace_setup.sql     # Dev catalog, schemas, grants
│       ├── prod_account_setup.sh       # Prod storage credential + external location
│       └── prod_workspace_setup.sql    # Prod catalog, schemas, grants
├── jobs/
│   └── alo-lakehouse.py                # Airflow DAG (MWAA)
├── montecarlo/                         # Data quality monitor definitions
├── scripts/
│   ├── setup.sh                        # Local dev bootstrap (all prerequisites)
│   ├── run_sql.py                      # SQL file runner for setup scripts
│   ├── deploy_workflows.py             # Upserts Databricks Workflow definitions
│   └── permissions/                    # Unity Catalog GRANT management
├── lakehouse/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── models/
│   │   ├── bronze/                     # Raw ingestion (br_ prefix)
│   │   ├── silver/                     # Cleaned, deduped, business logic
│   │   ├── gold/                       # Analytics-ready aggregations
│   │   └── mgt/                        # Operational tables
│   ├── macros/                         # grant_unity_catalog_permissions, generate_schema_name, etc.
│   ├── snapshots/
│   │   ├── c360/                       # Customer 360 SCD snapshots
│   │   └── shopify/                    # Shopify SCD snapshots
│   ├── seeds/
│   │   ├── ecom_shopify/               # Shopify reference data
│   │   ├── holiday_calendar/           # Holiday calendar data
│   │   └── public/                     # General reference tables (e.g. test_products)
│   ├── tests/                          # Custom generic tests
│   ├── analyses/                       # Ad-hoc analysis SQL
│   ├── assets/                         # Static assets (e.g. images for dbt docs)
│   ├── groups/                         # dbt group definitions
│   └── pyspark/
│       ├── utils/session.py            # get_spark() — Databricks Connect session
│       └── examples/explore_catalog.py # Sample catalog explorer
├── .env.example                        # PySpark env var template (copy to .env)
├── .pre-commit-config.yaml
├── .sqlfluff                           # sparksql dialect
├── Dockerfile
├── Justfile
└── pyproject.toml                      # dbt-databricks 1.10.19 + databricks-connect 15.4.21
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
