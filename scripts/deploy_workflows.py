#!/usr/bin/env python3
"""
deploy_workflows.py
────────────────────
Upserts Databricks Workflow (Jobs API 2.1) definitions from
databricks/workflows/*.json into the target workspace.

Usage:
    DATABRICKS_HOST=... DATABRICKS_TOKEN=... python scripts/deploy_workflows.py --env dev
    python scripts/deploy_workflows.py --env prod   # uses DATABRICKS_* env vars or profile
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobSettings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

WORKFLOWS_DIR = Path(__file__).parent.parent / "databricks" / "workflows"


def get_client(env: str) -> WorkspaceClient:
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    if host and token:
        return WorkspaceClient(host=host, token=token)
    return WorkspaceClient(profile=f"alo-{env}")


def deploy(env: str) -> None:
    client = get_client(env)
    workflow_files = list(WORKFLOWS_DIR.glob("*.json"))

    if not workflow_files:
        log.warning("No workflow JSON files found in %s", WORKFLOWS_DIR)
        return

    # Build a map of existing jobs: name → job_id
    existing: dict[str, int] = {}
    for job in client.jobs.list():
        if job.settings and job.settings.name:
            existing[job.settings.name] = job.job_id

    for wf_file in workflow_files:
        definition = json.loads(wf_file.read_text())

        # Inject environment-specific values
        definition.setdefault("tags", {})["env"] = env
        job_name = definition.get("name", wf_file.stem)

        if job_name in existing:
            job_id = existing[job_name]
            log.info("Updating existing job '%s' (id=%s)...", job_name, job_id)
            client.jobs.reset(job_id=job_id, new_settings=JobSettings.from_dict(definition))
            log.info("✅ Updated: %s", job_name)
        else:
            log.info("Creating new job '%s'...", job_name)
            created = client.jobs.create(**definition)
            log.info("✅ Created: %s (id=%s)", job_name, created.job_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Databricks Workflow definitions.")
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    args = parser.parse_args()
    deploy(env=args.env)


if __name__ == "__main__":
    main()
