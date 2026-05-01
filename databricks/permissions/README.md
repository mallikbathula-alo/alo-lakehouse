# Unity Catalog Setup

One-time setup to provision the `alo_dev` and `alo_prod` catalogs in Databricks Unity Catalog.
Run these steps when bootstrapping a new environment.

**Requires:** Databricks metastore admin role and AWS credentials for the target account.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step 1 — Create Account Groups](#step-1--create-account-groups)
- [Step 2 — Account-Level Setup (Storage Credential + External Location)](#step-2--account-level-setup-storage-credential--external-location)
- [Step 3 — Workspace-Level Setup (Catalog + Schemas + Grants)](#step-3--workspace-level-setup-catalog--schemas--grants)
- [Catalog Structure](#catalog-structure)
- [Permission Model](#permission-model)
- [Troubleshooting](#troubleshooting)

---

## Overview

Unity Catalog setup is split into two levels:

| Level | Tool | What it creates |
|-------|------|----------------|
| **Account-level** | Databricks CLI | Storage credential, external location (backed by S3) |
| **Workspace-level** | SQL Warehouse (`just run-sql`) | Catalog, schemas, grants |

Account-level objects (`storage-credentials`, `external-locations`) cannot be created via SQL — they require the CLI and metastore admin privileges.

---

## Prerequisites

**1. Databricks CLI configured** for the target workspace:
```bash
databricks configure
# host:  https://dbc-e27abc0b-645c.cloud.databricks.com  (dev)
# host:  https://dbc-adf36112-6a4a.cloud.databricks.com  (prod)
# token: <metastore-admin-pat-token>
```

**2. AWS SSO authenticated:**
```bash
aws sso login --profile alo-is-dev    # for dev
aws sso login --profile alo-is-prod   # for prod
```

**3. Terraform applied** — the S3 bucket and IAM role must exist before running these scripts.
The Terraform resources are in `alo-terraform`:
- S3 bucket: `is-dev-lakehouse` / `is-prod-lakehouse`
- IAM role: `is-dev-databricks-instance-role` / `alo-prod-unity-catalog-role`
- Bucket policy: `databricks_aws_bucket_policy` (grants Databricks access to S3)

---

## Step 1 — Create Account Groups

Groups are account-scoped and shared across dev and prod workspaces. Run once.

```bash
databricks groups create --display-name dev-data-engineering
databricks groups create --display-name data_engineering
databricks groups create --display-name data_analyst
databricks groups create --display-name data_scientist
databricks groups create --display-name tableau
databricks groups create --display-name fivetran
databricks groups create --display-name thoughtspot
databricks groups create --display-name hex_report
databricks groups create --display-name monte_carlo
databricks groups create --display-name braze
```

Or manage groups via the Databricks Account Console at `accounts.cloud.databricks.com`.

Reference: [`groups_setup.sql`](groups_setup.sql)

---

## Step 2 — Account-Level Setup (Storage Credential + External Location)

Creates the S3-backed storage credential and external location. These are prerequisites for
`CREATE CATALOG ... MANAGED LOCATION`.

### Dev

```bash
chmod +x databricks/permissions/dev_account_setup.sh
./databricks/permissions/dev_account_setup.sh
```

What it creates:
| Object | Name | S3 Path |
|--------|------|---------|
| Storage credential | `is-dev-aws-storage-credential` | IAM role: `is-dev-databricks-instance-role` |
| External location | `alo_dev_managed_location` | `s3://is-dev-lakehouse` |

The script is idempotent — it skips creation if the objects already exist.

### Prod

```bash
chmod +x databricks/permissions/prod_account_setup.sh
./databricks/permissions/prod_account_setup.sh
```

| Object | Name | S3 Path |
|--------|------|---------|
| Storage credential | `alo_prod_storage_credential` | IAM role: `alo-prod-unity-catalog-role` |
| External location | `alo_prod_managed_location` | `s3://is-prod-lakehouse` |

**Verify the external location after creation:**
```bash
databricks external-locations validate --name alo_dev_managed_location
databricks external-locations validate --name alo_prod_managed_location
```

---

## Step 3 — Workspace-Level Setup (Catalog + Schemas + Grants)

Creates the catalog, all schemas, and grants group permissions. Run via SQL Warehouse.

### Dev

```bash
just run-sql databricks/permissions/dev_workspace_setup.sql
```

### Prod

```bash
just run-sql databricks/permissions/prod_workspace_setup.sql
```

---

## Catalog Structure

Each catalog maps to a dedicated S3 bucket with per-schema subfolders:

```
alo_dev   →  s3://is-dev-lakehouse/
├── bronze/
├── silver/
├── gold/
├── mgt/
├── snapshots/
└── public/

alo_prod  →  s3://is-prod-lakehouse/
├── bronze/
├── silver/
├── gold/
├── mgt/
├── snapshots/
└── public/
```

---

## Permission Model

| Group | bronze | silver | gold | mgt | snapshots |
|-------|--------|--------|------|-----|-----------|
| `data_engineering` | READ + WRITE | READ + WRITE | READ + WRITE | READ + WRITE | READ + WRITE |
| `fivetran` | READ + WRITE | — | — | — | — |
| `data_analyst` | — | READ | READ | — | — |
| `data_scientist` | READ | READ | READ | — | — |
| `tableau` | — | — | READ | — | — |
| `thoughtspot` | — | — | READ | — | — |
| `hex_report` | — | — | READ | — | — |
| `monte_carlo` | READ | READ | READ | — | — |
| `braze` | READ | — | — | — | — |

> Dev uses `dev-data-engineering` group; prod uses `data_engineering`.

---

## Troubleshooting

**`PERMISSION_DENIED: User does not have CREATE SCHEMA`**
The catalog exists but was created by a different user/service principal.
Transfer ownership via CLI:
```bash
databricks catalogs update alo_dev --owner "<your-email@aloyoga.com>"
```
The workspace SQL also runs `ALTER CATALOG alo_dev OWNER TO dev-data-engineering` to prevent this going forward.

**`AWS IAM role does not have READ permissions`**
The S3 bucket policy hasn't been applied yet. Ensure the Terraform PR in `alo-terraform` is merged and applied:
```bash
cd alo-terraform/global/databricks
terraform apply
```
Then re-run `dev_account_setup.sh`.

**`Catalog 'alo_dev' is not accessible in current workspace`**
The catalog exists at the account level but isn't bound to this workspace:
```bash
databricks catalogs update alo_dev --isolation-mode OPEN
```
