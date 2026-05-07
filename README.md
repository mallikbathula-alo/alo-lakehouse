# alo-lakehouse

Alo Yoga's Databricks Lakehouse — project managing the medallion data platform
(bronze → silver → gold) on **Databricks + Unity Catalog**. This project enable developers run dbt+SparkSQL, dbt+PySpark and classic PySpark jobs 

---

## Introduction

The lakehouse ingests data from multiple source systems, lands it in AWS S3 via streaming
and batch pipelines, then transforms it through a medallion architecture into
analytics-ready tables. An optional consumption layer pushes curated data to downstream
operational stores.

```
┌─────────────────────────────────┐
│         Source Systems          │
│  Shopify · OMS · Anaplan · GA4  │
│  Braze · Salesforce · Aftership │
└────────────┬────────────────────┘
             │
     ┌───────▼────────┐
     │  Ingestion     │
     │  Kinesis +     │
     │  Firehose      │
     │  Meltano       │
     │  FiveTran      │
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │    AWS S3      │
     │  (Raw Files)   │
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │  Databricks    │
     │  AutoLoader    │
     │ (cloudFiles)   │
     └───────┬────────┘
             │
     ┌───────▼────────────────────────────────────────┐
     │               Unity Catalog                    │
     │                                                │
     │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
     │  │  Bronze  │─▶│  Silver  │─▶│     Gold     │  │
     │  │ Raw Data │  │   3NF    │  │ Star Schema  │  │
     │  │          │  │ Modeling │  │  BI-Ready    │  │
     │  └──────────┘  └──────────┘  └──────┬───────┘  │
     └──────────────────────────────────────--┼───────┘
                                              │ (optional)
                                      ┌───────▼────────┐
                                      │  Consumption   │
                                      │  (Redshift,    │
                                      │   Dynamo etc)  │
                                      └───────-────────┘                             
```

| Layer | Tool | Purpose |
|-------|------|---------|
| **Ingestion** | Kinesis + Firehose, Meltano, FiveTran | Stream and batch from source systems to S3 |
| **Bronze** | Databricks AutoLoader (`cloudFiles`) | Raw data landed as Delta tables, schema-on-read |
| **Silver** | dbt (SparkSQL) | Deduplication, 3NF modeling, business logic |
| **Gold** | dbt (SparkSQL) | Star schema aggregations, BI-ready fact/dim tables |

---

## Table of Contents

- [Quick Start](#quick-start)
- [Python Environment](#python-environment)
- [Example Runs](#example-runs)
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
./tools/setup.sh       # installs prerequisites, creates .venv, installs all deps
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

**2. PySpark compute** — edit `.env` (copy from `.env.example`):
```bash
# Host and token are read from ~/.dbt/profiles.yml automatically

# Option A — Serverless (preferred): no cluster required
DATABRICKS_SERVERLESS_COMPUTE_ID=auto

# Option B — Classic cluster: cluster must be running
# DATABRICKS_CLUSTER_ID=<your-cluster-id>   # Compute → <cluster> → URL: .../clusters/<ID>
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

PySpark scripts live in `lakehouse/examples/` alongside dbt models.

---

## Example Runs

Reference examples live in [`lakehouse/examples/`](lakehouse/examples/README.md) — see that README for full details on each file and the patterns it demonstrates.

| Example | Type | Run command |
|---------|------|-------------|
| `sparksql_incremental.sql` | dbt SQL model | `cd lakehouse && dbt run --select sparksql_incremental --target local` |
| `pyspark_transform.py` | dbt Python model | `cd lakehouse && dbt run --select pyspark_transform --target local` |
| `explore_catalog.py` | Standalone PySpark script | `just pyspark-run explore_catalog.py` |

> All examples are self-contained — no catalog tables required.
> dbt examples are disabled by default (`enabled=false`) so they never run in the pipeline.

### Prerequisites

```bash
# 1. Verify dbt connection
cd lakehouse && dbt debug --target local

# 2. For standalone PySpark scripts — configure compute in .env:
#    Serverless (preferred, no cluster needed):
DATABRICKS_SERVERLESS_COMPUTE_ID=auto
#    Classic cluster (must be running):
# DATABRICKS_CLUSTER_ID=<your-cluster-id>
```

### dbt SQL model

```bash
cd lakehouse

# Full run — creates the Delta table from scratch
dbt run --select sparksql_incremental --target local

# Incremental run — merges only new rows
dbt run --select sparksql_incremental --target local
```

### dbt Python model

Python models execute on Databricks compute (serverless or classic cluster).

```bash
cd lakehouse && dbt run --select pyspark_transform --target local
```

### Standalone PySpark script

Runs locally via Databricks Connect — compute executes on Databricks serverless or a classic cluster.

```bash
just pyspark-run explore_catalog.py
```

### Interactive PySpark shell

```bash
just pyspark-shell
# SparkSession ready — use spark.<tab>
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

# PySpark (scripts live in lakehouse/examples/)
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

PR labeled "ready for deployment" + approved review
  └── Deploy to dev workspace
        ├── dbt docs + manifest → S3
        └── Databricks Workflows upsert (dev)

git tag v*.*.*
  └── Deploy to prod workspace
        ├── dbt docs + manifest → S3
        └── Databricks Workflows upsert (prod)
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
│   └── deploy_workflows.py             # Upserts workflow definitions to target workspace
│   └── permissions/                    # Unity Catalog setup (see README for full steps)
│       ├── README.md                   # Full catalog setup guide
│       ├── groups_setup.sql            # Account-level group creation
│       ├── dev_account_setup.sh        # Dev storage credential + external location
│       ├── dev_workspace_setup.sql     # Dev catalog, schemas, grants
│       ├── prod_account_setup.sh       # Prod storage credential + external location
│       └── prod_workspace_setup.sql    # Prod catalog, schemas, grants
├── tools/                              # Dev, deployment, and admin utilities (see tools/README.md)
│   ├── setup.sh                        # Local dev bootstrap (installs all prerequisites)
│   ├── run_sql.py                      # Executes SQL files against Databricks SQL Warehouse
│   ├── permissions/
│   │   └── unity_catalog_permissions.py  # Applies Unity Catalog GRANTs (runs in CI)
│   ├── cd/                             # Release management: tag, rollback, ebf, release notes
│   └── templates/                      # dbt profiles.yml template
├── lakehouse/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── ingestions/
│   │   └── shopify/                    # Shopify GraphQL AutoLoader ingest scripts (spark_python_task)
│   ├── models/
│   │   ├── bronze/                     # Raw ingestion dbt models (br_ prefix)
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
│   ├── utils/
│   │   ├── spark_utils.py              # get_spark(), get_logger(), dedup(), preview_table() — usable from any script
│   │   └── ingest_utils.py             # Shopify AutoLoader helpers (paths, args, streaming/batch runners)
│   └── examples/                       # Developer reference examples (see examples/README.md)
│       ├── sparksql_incremental.sql    # SparkSQL incremental dbt model (self-contained)
│       ├── pyspark_transform.py        # PySpark dbt Python model (self-contained)
│       └── explore_catalog.py          # Standalone Databricks Connect script
├── .env.example                        # PySpark env var template (copy to .env)
├── .pre-commit-config.yaml
├── .sqlfluff                           # sparksql dialect
├── Justfile
└── pyproject.toml                      # dbt-databricks 1.10.19 + databricks-connect 15.4.21
```

---

## Data Quality

Data quality is enforced via `dbt test` — generic and custom tests defined alongside models
in YAML properties files. Tests run as part of the CI/CD pipeline after every deployment.

---

## AWS Accounts

| Environment | Account ID     |
|------------|----------------|
| Dev        | `206390103201` |
| Prod       | `715192338314` |

Secrets in AWS Secrets Manager:
- `alo/databricks/{env}` → `{"host": ..., "http_path": ..., "token": ...}`
