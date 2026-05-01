#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Unity Catalog Account-Level Setup — PROD
# Creates storage credential and external location via Databricks CLI.
#
# These are account-level objects — they cannot be created via SQL Warehouse.
# Must be run by a Databricks metastore admin.
#
# Prerequisites:
#   1. Databricks CLI installed: pip install databricks-cli  OR  brew install databricks
#   2. Authenticated: databricks configure --token  (use prod workspace host + admin token)
#   3. IAM role exists in AWS account 715192338314:
#        arn:aws:iam::715192338314:role/alo-prod-unity-catalog-role
#      with s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket
#      on s3://is-prod-lakehouse and s3://is-prod-lakehouse/*
#
# Usage:
#   chmod +x databricks/permissions/prod_account_setup.sh
#   ./databricks/permissions/prod_account_setup.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HOST="https://dbc-adf36112-6a4a.cloud.databricks.com"

echo "Creating storage credential for prod..."
databricks storage-credentials create \
  --host "$HOST" \
  --json '{
    "name": "alo_prod_storage_credential",
    "aws_iam_role": {
      "role_arn": "arn:aws:iam::715192338314:role/alo-prod-unity-catalog-role"
    },
    "comment": "Storage credential for alo_prod catalog managed location (s3://is-prod-lakehouse)"
  }'

echo "Creating external location for prod..."
databricks external-locations create \
  --host "$HOST" \
  --json '{
    "name": "alo_prod_managed_location",
    "url": "s3://is-prod-lakehouse",
    "credential_name": "alo_prod_storage_credential",
    "comment": "Managed location for alo_prod catalog"
  }'

echo "Done. Now run the workspace setup:"
echo "  just run-sql databricks/permissions/prod_workspace_setup.sql"
