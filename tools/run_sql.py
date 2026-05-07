"""
run_sql.py — Execute a SQL file against Databricks, statement by statement.

Purpose
-------
Databricks SQL Warehouses do not accept multi-statement queries in a single
request. This script splits a SQL file on semicolons and executes each
statement individually, making it possible to run setup scripts that contain
multiple DDL/DML statements (CREATE CATALOG, CREATE SCHEMA, GRANT, etc.)
from the command line without copy-pasting into the Databricks SQL editor.

Primary use case: applying Unity Catalog setup files under databricks/permissions/
  - databricks/permissions/dev_workspace_setup.sql   — dev catalog, schemas, grants
  - databricks/permissions/prod_workspace_setup.sql  — prod catalog, schemas, grants

Credentials are read from ~/.dbt/profiles.yml (lakehouse → local target).
Account-level operations (storage credentials, external locations) must still
be run via the Databricks CLI — this script only covers workspace-level SQL.

Usage
-----
    just run-sql databricks/permissions/dev_workspace_setup.sql
    just run-sql databricks/permissions/prod_workspace_setup.sql

    # or directly:
    uv run python tools/run_sql.py <path/to/file.sql>
"""

import sys
from pathlib import Path

import yaml
from databricks import sql


def load_credentials() -> dict:
    profiles_path = Path.home() / ".dbt" / "profiles.yml"
    if not profiles_path.exists():
        raise FileNotFoundError(f"profiles.yml not found at {profiles_path}")
    with open(profiles_path) as f:
        profiles = yaml.safe_load(f)
    try:
        return profiles["lakehouse"]["outputs"]["local"]
    except KeyError:
        raise KeyError("Could not find lakehouse → outputs → local in profiles.yml")


def run_sql_file(sql_file: str) -> None:
    creds = load_credentials()
    path = Path(sql_file)

    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    raw = path.read_text()

    # Split on semicolons, skip empty lines and comment-only blocks
    statements = [
        s.strip()
        for s in raw.split(";")
        if s.strip() and not all(
            line.startswith("--") or not line.strip()
            for line in s.strip().splitlines()
        )
    ]

    print(f"Running {len(statements)} statements from {path.name} ...")
    print(f"  host:       {creds['host']}")
    print(f"  http_path:  {creds['http_path']}")
    print()

    with sql.connect(
        server_hostname=creds["host"],
        http_path=creds["http_path"],
        access_token=creds["token"],
    ) as conn:
        with conn.cursor() as cursor:
            for i, stmt in enumerate(statements, 1):
                preview = stmt.replace("\n", " ")[:80]
                print(f"[{i}/{len(statements)}] {preview} ...")
                try:
                    cursor.execute(stmt)
                    print(f"           ✓ ok")
                except Exception as e:
                    print(f"           ✗ ERROR: {e}")
                    raise

    print(f"\nDone — {len(statements)} statements executed successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python tools/run_sql.py <path/to/file.sql>")
        sys.exit(1)
    run_sql_file(sys.argv[1])
