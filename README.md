# alo-lakehouse

Alo Yoga's Databricks Lakehouse — dbt project managing the medallion data platform
(bronze → silver → gold) on **Databricks + Unity Catalog**.

> Migrated from `is-redshift` (AWS Redshift). Uses `dbt-databricks` with separate
> dev and prod Databricks workspaces, Unity Catalog for governance, and Databricks
> Workflows for orchestration.

---

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- [just](https://github.com/casey/just) task runner
- AWS CLI configured with SSO profiles (`alo-is-dev`, `alo-is-prod`)
- Access to Databricks dev workspace (request via IT)

### Setup

```bash
git clone git@github.com:alo-yoga/alo-lakehouse.git
cd alo-lakehouse
./scripts/setup.sh
```

After setup, edit `~/.dbt/profiles.yml`:

```yaml
lakehouse:
  outputs:
    local:
      type: databricks
      host: <your-dev-workspace>.azuredatabricks.net
      http_path: /sql/1.0/warehouses/<warehouse-id>
      token: <your-personal-access-token>
      catalog: alo_dev
      schema: dbt_<your-name>
      threads: 8
  target: local
```

Verify connectivity:

```bash
cd warehouse && dbt debug
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
| Bronze | `warehouse/models/1_bronze/` | `bronze` | Raw ingestion from Shopify, GA4, Braze, Salesforce, etc. |
| Silver Pre | `warehouse/models/2_silver_pre/` | `silver` | Staging, deduplication |
| Silver | `warehouse/models/3_silver/` | `silver` | Core dimensions & business logic |
| Silver Post | `warehouse/models/4_silver_post/` | `silver` | Silver aggregations |
| Gold | `warehouse/models/5_gold/` | `gold` | Analytics-ready tables for BI (Tableau, Thoughtspot, Hex) |
| MGT | `warehouse/models/mgt/` | `mgt` | Operational & management tables |

### Multi-Region Shopify

Four storefronts are managed via `var('shopify_platforms')`:

| Store | Variable | Currency |
|-------|----------|----------|
| US | `src_shopify_us` | USD |
| Canada | `src_shopify_can` | CAD |
| UK | `src_shopify_uk` | GBP |
| International | `src_shopify_intl` | EUR |

---

## Common Commands

```bash
# Local dev
just run-local <model>                # Run model using dev catalog
just run-prod-local <model>           # Run model using prod catalog as source
just run-full-refresh-local <model>   # Full refresh locally

# Databricks Workflow definitions
just deploy-workflows dev             # Push workflow JSON to dev workspace
just deploy-workflows prod            # Push workflow JSON to prod workspace

# dbt (from warehouse/ directory)
dbt run --select tag:bronze           # Run all bronze models
dbt run --select tag:gold             # Run all gold models
dbt test --select <model>             # Run tests for a model
dbt docs generate                     # Generate documentation

# Permissions
just permissions dev true             # Dry-run Unity Catalog permission grants
just permissions prod false           # Apply permissions to prod

# Release
just tag patch                        # Tag + trigger prod deploy
just tag-with-release-doc minor prod  # Tag + generate release notes
just rollback                         # Rollback prod to previous tag
just ebf                              # Emergency bug fix patch
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
│   ├── workflows/
│   │   ├── pr.yaml                     # PR validation
│   │   ├── dev.yaml                    # Deploy to dev
│   │   ├── prod.yaml                   # Deploy to prod (on version tag)
│   │   ├── reusable-workflow.yaml      # Shared deployment logic
│   │   └── support/
│   │       └── profiles.yml.txt        # Databricks profile template (envsubst)
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── databricks/
│   ├── workflows/                      # Databricks Workflow JSON definitions
│   │   ├── daily_run.json
│   │   └── full_refresh.json
│   ├── clusters/                       # Cluster config templates
│   │   ├── dev_cluster.json
│   │   └── prod_cluster.json
│   └── permissions/
│       └── unity_catalog_setup.sql     # One-time catalog/schema bootstrap SQL
├── jobs/
│   └── alo-lakehouse.py                # Airflow DAG (MWAA)
├── montecarlo/
│   ├── montecarlo.yml
│   ├── notifications.yml
│   └── metric_monitor.yml
├── scripts/
│   ├── setup.sh                        # Local dev bootstrap
│   ├── deploy_workflows.py             # Upserts Databricks Workflow definitions
│   ├── permissions/
│   │   └── unity_catalog_permissions.py  # Unity Catalog GRANT management
│   ├── cd/                             # Release scripts (tag, rollback, ebf, release notes)
│   └── templates/
│       └── profiles.yml.txt            # Local profiles template
├── warehouse/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── models/
│   │   ├── sources.yml                 # All source definitions
│   │   ├── 1_bronze/
│   │   ├── 2_silver_pre/
│   │   ├── 3_silver/
│   │   ├── 4_silver_post/
│   │   ├── 5_gold/
│   │   ├── mgt/
│   │   └── c360/
│   ├── macros/
│   ├── snapshots/
│   ├── seeds/
│   ├── tests/generic/
│   └── analyses/
├── .pre-commit-config.yaml
├── .sqlfluff                           # sparksql dialect
├── Dockerfile
├── Justfile
├── pyproject.toml                      # dbt-databricks + databricks-sdk
├── CLAUDE.md
└── README.md
```

---

## Data Quality

[Monte Carlo](https://www.montecarlodata.com/) monitors are defined in `montecarlo/metric_monitor.yml`.
Alerts go to Slack channels `#de-incident` and `#de-oncall-support`.

---

## Contributing

1. Create a feature branch from `main`
2. Follow the [PR template](.github/pull_request_template.md)
3. Pre-commit hooks enforce SQL formatting and model conventions
4. All new models must have a YAML properties file entry
5. Tag models with valid tags (see `.pre-commit-config.yaml`)

---

## AWS Accounts

| Environment | Account ID    |
|------------|---------------|
| Dev        | `206390103201` |
| Prod       | `715192338314` |

Secrets path in AWS Secrets Manager:
- Databricks credentials: `alo/databricks/{env}` → `{"host": ..., "http_path": ..., "token": ...}`
- Monte Carlo: `alo/montecarlo` → `{"api_id": ..., "api_token": ...}`
