#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Unity Catalog Account-Level Setup — DEV
# Creates storage credential and external location via Databricks CLI.
#
# These are account-level objects — they cannot be created via SQL Warehouse.
# Must be run by a Databricks metastore admin.
#
# Prerequisites:
#   1. Databricks CLI installed: pip install databricks-cli  OR  brew install databricks
#   2. Authenticated: databricks configure --token  (use dev workspace host + admin token)
#   3. The existing Databricks instance profile role already has Unity Catalog
#      trust policy and s3:* access (defined in databricks/iam.tf in alo-terraform):
#        arn:aws:iam::206390103201:role/is-dev-databricks-instance-role and s3://is-dev-lakehouse/*
#
# Usage:
#   chmod +x databricks/permissions/dev_account_setup.sh
#   ./databricks/permissions/dev_account_setup.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "Creating storage credential for dev..."
if databricks storage-credentials get is-dev-aws-storage-credential &>/dev/null; then
  echo "  ✓ already exists, skipping"
else
  databricks storage-credentials create \
    --json '{
      "name": "is-dev-aws-storage-credential",
      "aws_iam_role": {
        "role_arn": "arn:aws:iam::206390103201:role/is-dev-databricks-instance-role"
      },
      "comment": "Storage credential for alo_dev catalog managed location (s3://is-dev-lakehouse)"
    }'
fi

echo "Creating external location for dev..."
if databricks external-locations get alo_dev_managed_location &>/dev/null; then
  echo "  ✓ already exists, skipping"
else
  databricks external-locations create \
    --json '{
      "name": "alo_dev_managed_location",
      "url": "s3://is-dev-lakehouse",
      "credential_name": "is-dev-aws-storage-credential",
      "comment": "Managed location for alo_dev catalog"
    }'
fi

echo "Done. Now run the workspace setup:"
echo "  just run-sql databricks/permissions/dev_workspace_setup.sql"
