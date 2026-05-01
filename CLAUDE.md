# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **dbt (data build tool) project** managing Alo Yoga's Databricks Lakehouse.
It transforms raw source data through a medallion architecture (bronze → silver → gold)
using 1,200+ SQL models running on **Databricks + Unity Catalog** with **dbt-databricks**.

Migrated from `is-redshift` (AWS Redshift + dbt-redshift). Key differences:
- **Adapter**: `dbt-databricks` (not `dbt-redshift`)
- **Compute**: Databricks SQL Warehouses (not StrongDM tunnels to Redshift)
- **Namespace**: 3-level Unity Catalog (`catalog.schema.table` vs `database.schema.table`)
- **Two workspaces**: separate Databricks workspaces for dev (`alo_dev`) and prod (`alo_prod`)
- **Auth**: Service principal PAT tokens via AWS Secrets Manager (not StrongDM)
- **SQL dialect**: SparkSQL (not Redshift SQL — watch for dialect differences)

## Setup

```bash
./scripts/setup.sh        # Install uv, set up venv, install dbt deps, fetch manifest
source .venv/bin/activate
```

**After setup:** Edit `~/.dbt/profiles.yml` to fill in your dev workspace host,
HTTP path (SQL Warehouse), and personal access token.

### Profile Targets

The dbt profile `lakehouse` has four targets:

| Target  | Environment       | Catalog    | Schema                     | Purpose                      |
|---------|-------------------|------------|----------------------------|------------------------------|
| `local` | Developer machine | `alo_dev`  | `dbt_<yourname>`           | Local development            |
| `ci`    | GitHub Actions    | `alo_dev`  | `ci_<schema>` (ephemeral)  | PR validation (isolated)     |
| `dev`   | Dev workspace     | `alo_dev`  | As configured              | Dev environment deploys      |
| `prod`  | Prod workspace    | `alo_prod` | As configured              | Production deploys           |

The `generate_schema_name` macro controls this: on the `ci` target it prefixes schemas with `ci_` for
run isolation; on `dev`/`prod` it uses the custom schema name directly. CI schemas are dropped after
validation via `drop_ci_catalog_schema`.

## Common Commands

### Local development

```bash
just get-manifest dev                          # Fetch latest manifest from S3
just run-local <model>                         # Run model with dev catalog data
just run-prod-local <model>                    # Run model using prod catalog as source
just run-full-refresh-local <model>            # Full refresh locally
just run-full-refresh-prod-local <model>       # Full refresh using prod data
```

### dbt commands (run from `lakehouse/` directory)

```bash
cd lakehouse
dbt deps                                       # Install dbt packages
dbt run --select <model_name>                  # Run a specific model
dbt test --select <model_name>                 # Test a specific model
dbt compile --select <model_name>              # Compile without running
dbt docs generate                              # Generate docs
dbt snapshot                                   # Run SCD snapshots
```

The `--defer --select state:modified+1` pattern used in CI runs only modified models plus
one layer of downstream dependents, using the production manifest as baseline so unmodified
upstream models resolve to prod tables instead of rebuilding everything.

### Linting

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
pre-commit run --files <path/to/file.sql>      # Lint specific files
uvx pre-commit run --all-files                 # Lint everything
```

SQL files are formatted with **sqlfmt** and linted with **sqlfluff** (sparksql dialect).

## Architecture

### Unity Catalog Namespace

```
alo_dev  (dev workspace)                alo_prod  (prod workspace)
├── bronze    ← raw ingestion           ├── bronze
├── silver    ← cleaned + business      ├── silver
├── gold      ← analytics / BI          ├── gold
├── mgt       ← operational             ├── mgt
├── snapshots ← SCD Type 2             ├── snapshots
└── public    ← seeds / reference      └── public
```

### Medallion Layers

Models live in `lakehouse/models/` organized by layer:

| Directory        | Unity Catalog Schema | Purpose |
|-----------------|---------------------|---------|
| `1_bronze/`     | `bronze`            | Raw ingestion (Shopify, GA4, Braze, etc.) — prefix `br_` |
| `2_silver_pre/` | `silver`            | Initial staging / deduplication |
| `3_silver/`     | `silver`            | Core business logic and dimensions |
| `4_silver_post/`| `silver`            | Silver-layer aggregations |
| `5_gold/`       | `gold`              | Analytics-ready tables for BI tools |
| `mgt/`          | `mgt`               | Operational / management tables |

### Key Conventions

- **Model naming**: layer prefix + source + entity (e.g., `br_shopify_us_orders`, `silver_customers`)
- **Tags**: All models require tags declared in `.pre-commit-config.yaml`'s allowed tag list
- **Properties**: Every model must be listed in a corresponding YAML properties file (enforced by pre-commit)
- **Refs and sources**: Models must use `{{ ref() }}` or `{{ source() }}` — no hardcoded catalog/schema names
- **Materialization**: Views locally; Delta tables in CI/dev/prod — controlled by `DBT_MATERIALIZATION=table` env var (default `view`)
- **Cluster by**: Large incremental tables should declare `cluster_by` for Databricks query performance
- **Column types**: Use SparkSQL types (`string` not `varchar`, `double` not `float8`, etc.)

### SparkSQL vs Redshift SQL — Key Differences

| Redshift                        | SparkSQL (Databricks)                    |
|---------------------------------|------------------------------------------|
| `varchar(256)`                  | `string`                                 |
| `float8`                        | `double`                                 |
| `getdate()`                     | `current_timestamp()`                    |
| `dateadd(day, 1, col)`         | `date_add(col, 1)`                       |
| `datediff('day', a, b)`        | `datediff(b, a)`                         |
| `listagg(col, ',')`            | `collect_list(col)` or `array_join()`    |
| `NVL(a, b)`                    | `coalesce(a, b)`                         |
| `ISNULL(col)`                  | `col IS NULL`                            |
| `top N`                        | `limit N`                                |
| `convert_timezone(...)`        | `convert_timezone(tz, col)` (same)       |

### Multi-Region Shopify

The project handles 4 Shopify storefronts via dbt variables:
- `yoga-us`     → `src_shopify_us`
- `yoga-canada` → `src_shopify_can`
- `yoga-uk`     → `src_shopify_uk`
- `yoga-intl`   → `src_shopify_intl`

Many bronze models loop over `var('shopify_platforms')` to produce per-region outputs.

### Source Catalog Variable

`source_catalog` defaults to `alo_dev`. Pass `--vars '{"source_catalog": "alo_prod"}'`
to read from prod tables during local development.

### Macros (`lakehouse/macros/`)

Key macros:
- `grant_unity_catalog_permissions` — Unity Catalog GRANT statements, runs `on-run-end`
- `drop_ci_catalog_schema` — drops ephemeral CI schema after PR validation
- `generate_schema_name` — controls schema naming per target (CI isolation, dev/prod)
- `create_latest_version_view` — post-hook convenience view for latest snapshot
- `cents_to_dollars` — monetary unit conversion (Shopify API returns cents)
- `case_check` — generates CASE WHEN from a dict mapping

## CI/CD

### Triggers

| Event                                              | Pipeline          | Deploys to |
|----------------------------------------------------|-------------------|------------|
| PR opened / synchronized                           | `pr.yaml`         | CI workspace (ephemeral) |
| PR label `ready for deployment` + approved review  | `dev.yaml`        | `alo_dev`  |
| Version tag `v*.*.*`                               | `prod.yaml`       | `alo_prod` |

### PR Validation (`pr.yaml`)

Runs four parallel jobs when `lakehouse/` files change:
1. **linting** — pre-commit hooks on changed files (sqlfmt, sqlfluff, ruff)
2. **dbt-validate** — `dbt snapshot/seed/run --defer --select state:modified+1`, then `dbt test`, then `drop_ci_catalog_schema`
3. **montecarlo-validate** — dry-run `montecarlo monitors apply` when `montecarlo/` changes
4. **check-pr-title** — conventional commits format (always runs)

### Deployment Pipeline (`reusable-workflow.yaml`)

The shared deployment workflow runs 5 jobs:
1. **deploy-dbt-artifacts** — generate docs + manifest, upload to S3 (`alo-{env}-de-docs/`), apply Unity Catalog permissions
2. **deploy-dbt-image** — build Docker image with dbt+venv, push to ECR (`alo-lakehouse:{tag}`)
3. **deploy-dag** (parallel with step 2) — sync Airflow DAG to MWAA S3 bucket
4. **deploy-databricks-workflows** (after step 2) — upsert Databricks workflow JSON definitions
5. **deploy-montecarlo-monitors** (prod only) — apply monitors with `--auto-yes`

### Release Management

```bash
just tag patch              # Bump patch version, tag, trigger prod deploy
just tag minor              # Bump minor version
just tag major              # Bump major version
just rollback               # Roll back to previous tag
just ebf                    # Emergency bug fix (bypasses normal release flow)
```

## Databricks Workspaces

| Environment | Host                                      | Catalog    | Secrets Path              |
|------------|-------------------------------------------|------------|--------------------------|
| dev        | `dbc-e27abc0b-645c.cloud.databricks.com`  | `alo_dev`  | `alo/databricks/dev`     |
| prod       | `dbc-adf36112-6a4a.cloud.databricks.com`  | `alo_prod` | `alo/databricks/prod`    |

Secrets stored in AWS Secrets Manager as JSON: `{"host": "...", "http_path": "...", "token": "..."}`.

## Databricks Workflow Definitions

JSON workflow definitions live in `databricks/workflows/`. Two schedules:
- **`daily_run.json`** — 4 AM PT daily: `bronze → silver → gold → dbt_tests` (2h timeout, 4×i3.xlarge)
- **`full_refresh.json`** — Sundays 1 AM PT: full rebuild of all layers (4h timeout, 8×i3.2xlarge)

```bash
just deploy-workflows dev    # Push workflow definitions to dev workspace
just deploy-workflows prod   # Push workflow definitions to prod workspace
```

## Airflow (MWAA)

The Airflow DAG at `jobs/alo-lakehouse.py` runs daily at 4 AM PT with this task topology:

```
snapshot → bronze → silver → gold → dbt_tests
```

Each task spawns an ephemeral Databricks cluster via `DatabricksSubmitRunOperator`. The DAG deploys
to MWAA via the reusable workflow. Internal packages `alo_common` and `alo_airflow` are required
in the MWAA environment.

## PySpark / Databricks Connect

Two ways to run PySpark in this repo:

### 1. Standalone scripts (local execution against remote cluster)

Uses **Databricks Connect** — code runs locally, compute runs on Databricks.

```bash
# One-time setup
cp .env.example .env          # fill in DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_CLUSTER_ID
just pyspark-install          # creates pyspark/.venv (isolated from dbt venv)

# Run a script
just pyspark-run examples/explore_catalog.py

# Interactive shell
just pyspark-shell
```

Scripts live in `pyspark/`. Import `from utils.session import get_spark` to get a configured `SparkSession`. The cluster must be **running** in the Databricks workspace before connecting.

`databricks-connect` bundles its own PySpark — **do not** install `pyspark` separately in the same environment.

### 2. dbt Python models (run on cluster as part of the dbt DAG)

Create a `.py` file in `lakehouse/models/` alongside SQL models:

```python
def model(dbt, spark):
    dbt.config(materialized="table", tags=["bronze"])
    df = dbt.ref("some_upstream_model")          # or dbt.source(...)
    return df.withColumn("new_col", ...)
```

Run exactly like SQL models:
```bash
dbt run --select br_test_python
```

Python models execute on the Databricks cluster (not locally). They support `dbt.ref()`, `dbt.source()`, and `dbt.config()` but not incremental strategies — use `materialized="table"`.

## Monte Carlo

Data quality monitors live in `montecarlo/`. Monitors cover: freshness (12–24h intervals),
volume anomaly detection, schema change detection, and numeric metric anomalies.
Alert routing goes to `#de-incident` and `#de-oncall-support` Slack channels.

Changes are validated via dry-run in CI and deployed to prod only on prod releases.
