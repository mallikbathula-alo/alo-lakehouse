#!/usr/bin/env python3
"""
unity_catalog_permissions.py
────────────────────────────
Applies Unity Catalog permissions (GRANT / REVOKE) across all schemas in
the alo_dev or alo_prod catalog.

Replaces scripts/permissions/database_permission.py from is-redshift with
Unity Catalog compatible SQL via the Databricks SDK.

Usage:
    python scripts/permissions/unity_catalog_permissions.py --env dev --dry-run true
    python scripts/permissions/unity_catalog_permissions.py --env prod --dry-run false
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import ExecuteStatementRequest, StatementState

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Permission Matrix ─────────────────────────────────────────────────────────
# Structure:
#   catalog → schema → principal → [privileges]
#
# Unity Catalog privileges:
#   USE CATALOG, USE SCHEMA, SELECT, MODIFY, CREATE TABLE, etc.

CATALOG_PERMISSIONS: dict[str, dict] = {
    "alo_dev": {
        "*": {  # applies to all schemas
            "data_engineering": ["USE SCHEMA", "SELECT", "MODIFY", "CREATE TABLE"],
            "data_analyst":     ["USE SCHEMA", "SELECT"],
            "data_scientist":   ["USE SCHEMA", "SELECT"],
            "tableau":          ["USE SCHEMA", "SELECT"],
            "fivetran":         ["USE SCHEMA", "SELECT"],
            "thoughtspot":      ["USE SCHEMA", "SELECT"],
            "hex_report":       ["USE SCHEMA", "SELECT"],
            "monte_carlo":      ["USE SCHEMA", "SELECT"],
        },
        "bronze": {
            "braze": ["USE SCHEMA", "SELECT"],
        },
    },
    "alo_prod": {
        "*": {
            "data_engineering": ["USE SCHEMA", "SELECT", "MODIFY", "CREATE TABLE"],
            "data_analyst":     ["USE SCHEMA", "SELECT"],
            "data_scientist":   ["USE SCHEMA", "SELECT"],
            "tableau":          ["USE SCHEMA", "SELECT"],
            "fivetran":         ["USE SCHEMA", "SELECT"],
            "thoughtspot":      ["USE SCHEMA", "SELECT"],
            "hex_report":       ["USE SCHEMA", "SELECT"],
            "monte_carlo":      ["USE SCHEMA", "SELECT"],
        },
        "bronze": {
            "braze": ["USE SCHEMA", "SELECT"],
        },
    },
}

CATALOG_LEVEL_PERMISSIONS: dict[str, dict] = {
    "alo_dev": {
        "data_engineering": ["USE CATALOG", "CREATE SCHEMA"],
        "data_analyst":     ["USE CATALOG"],
        "data_scientist":   ["USE CATALOG"],
        "tableau":          ["USE CATALOG"],
        "fivetran":         ["USE CATALOG", "CREATE SCHEMA"],
        "thoughtspot":      ["USE CATALOG"],
        "hex_report":       ["USE CATALOG"],
        "monte_carlo":      ["USE CATALOG"],
        "braze":            ["USE CATALOG"],
    },
    "alo_prod": {
        "data_engineering": ["USE CATALOG", "CREATE SCHEMA"],
        "data_analyst":     ["USE CATALOG"],
        "data_scientist":   ["USE CATALOG"],
        "tableau":          ["USE CATALOG"],
        "fivetran":         ["USE CATALOG", "CREATE SCHEMA"],
        "thoughtspot":      ["USE CATALOG"],
        "hex_report":       ["USE CATALOG"],
        "monte_carlo":      ["USE CATALOG"],
        "braze":            ["USE CATALOG"],
    },
}

SCHEMAS = ["bronze", "silver", "gold", "mgt", "snapshots", "public"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client(env: str) -> WorkspaceClient:
    """
    Build a Databricks WorkspaceClient.
    Reads DATABRICKS_HOST and DATABRICKS_TOKEN from the environment (set by CI)
    or falls back to ~/.databrickscfg profile.
    """
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if host and token:
        return WorkspaceClient(host=host, token=token)

    # Fall back to profile-based auth (local dev)
    profile = f"alo-{env}"
    log.info("No DATABRICKS_HOST/TOKEN in env — using profile: %s", profile)
    return WorkspaceClient(profile=profile)


def execute_sql(client: WorkspaceClient, warehouse_id: str, sql: str, dry_run: bool) -> None:
    if dry_run:
        log.info("[DRY RUN] %s", sql.strip())
        return

    resp = client.statement_execution.execute_statement(
        ExecuteStatementRequest(
            warehouse_id=warehouse_id,
            statement=sql,
            wait_timeout="30s",
        )
    )

    if resp.status and resp.status.state not in (
        StatementState.SUCCEEDED, StatementState.PENDING, StatementState.RUNNING
    ):
        log.error("Statement failed: %s\nSQL: %s", resp.status, sql)
        sys.exit(1)

    log.info("OK: %s", sql.strip()[:120])


def find_warehouse_id(client: WorkspaceClient) -> str:
    warehouses = list(client.warehouses.list())
    if not warehouses:
        raise RuntimeError("No SQL warehouses found in workspace.")
    # Prefer a running warehouse
    for wh in warehouses:
        if wh.state and wh.state.value == "RUNNING":
            return wh.id
    return warehouses[0].id


# ── Main Logic ────────────────────────────────────────────────────────────────

def apply_permissions(env: str, dry_run: bool) -> None:
    catalog = f"alo_{env}"
    client = get_client(env)
    warehouse_id = find_warehouse_id(client)

    log.info("Applying permissions to catalog: %s (dry_run=%s)", catalog, dry_run)

    # ── Catalog-level grants ──────────────────────────────────────────────────
    for principal, privileges in CATALOG_LEVEL_PERMISSIONS.get(catalog, {}).items():
        privs = ", ".join(privileges)
        sql = f"GRANT {privs} ON CATALOG `{catalog}` TO `{principal}`;"
        execute_sql(client, warehouse_id, sql, dry_run)

    # ── Schema-level grants ───────────────────────────────────────────────────
    schema_perms = CATALOG_PERMISSIONS.get(catalog, {})
    wildcard_perms: dict = schema_perms.get("*", {})

    for schema in SCHEMAS:
        # Merge wildcard + schema-specific permissions
        merged: dict[str, list[str]] = {}
        for principal, privs in wildcard_perms.items():
            merged.setdefault(principal, []).extend(privs)
        for principal, privs in schema_perms.get(schema, {}).items():
            merged.setdefault(principal, []).extend(privs)

        for principal, privileges in merged.items():
            unique_privs = list(dict.fromkeys(privileges))  # dedup, preserve order
            privs_str = ", ".join(unique_privs)
            sql = (
                f"GRANT {privs_str} "
                f"ON SCHEMA `{catalog}`.`{schema}` "
                f"TO `{principal}`;"
            )
            execute_sql(client, warehouse_id, sql, dry_run)

        # Grant SELECT on all existing tables in schema
        for principal in merged:
            sql = (
                f"GRANT SELECT ON ALL TABLES "
                f"IN SCHEMA `{catalog}`.`{schema}` "
                f"TO `{principal}`;"
            )
            execute_sql(client, warehouse_id, sql, dry_run)

    log.info("✅ Permissions applied successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Unity Catalog permissions.")
    parser.add_argument(
        "--env", choices=["dev", "prod"], required=True, help="Target environment"
    )
    parser.add_argument(
        "--dry-run",
        choices=["true", "false"],
        default="true",
        help="Print SQL without executing (default: true)",
    )
    args = parser.parse_args()

    dry_run = args.dry_run.lower() == "true"
    apply_permissions(env=args.env, dry_run=dry_run)


if __name__ == "__main__":
    main()
