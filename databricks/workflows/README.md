# Databricks Workflows

Workflow definitions for the alo-lakehouse dbt pipeline.
Deployed and managed via `scripts/deploy_workflows.py` (Jobs API 2.1).

---

## Table of Contents

- [Workflows](#workflows)
- [Task Topology](#task-topology)
- [Prerequisites](#prerequisites)
- [Deploy Workflows](#deploy-workflows)
- [Manual Trigger](#manual-trigger)
- [Monitor Runs](#monitor-runs)
- [Update a Workflow](#update-a-workflow)
- [Key Config Details](#key-config-details)

---

## Workflows

| File | Job Name | Schedule | Timeout | Cluster |
|------|----------|----------|---------|---------|
| `daily_run.json` | `alo-lakehouse-daily-run` | Daily 4 AM PT | 2 hours | 4× `i3.xlarge` |
| `full_refresh.json` | `alo-lakehouse-full-refresh` | Sundays 1 AM PT | 4 hours | 8× `i3.2xlarge` |

Both workflows use ephemeral job clusters (spun up per run, terminated on completion)
and set `DBT_MATERIALIZATION=table` so all models materialize as Delta tables.

---

## Task Topology

### Daily Run (`daily_run.json`)

```
bronze → silver → gold → dbt_tests
```

Each task runs the corresponding dbt layer tag. Fails fast — downstream tasks are
skipped if an upstream task fails (`run_if: ALL_SUCCESS`).

### Full Refresh (`full_refresh.json`)

```
full_refresh_bronze → full_refresh_silver → full_refresh_gold → dbt_tests_post_refresh
```

Same topology but runs `dbt run --full-refresh` to rebuild all incremental tables from scratch.
Uses larger nodes (`i3.2xlarge` × 8) to handle the increased data volume.

---

## Prerequisites

**1. Databricks CLI configured:**
```bash
databricks configure
# host:  https://dbc-e27abc0b-645c.cloud.databricks.com  (dev)
# host:  https://dbc-adf36112-6a4a.cloud.databricks.com  (prod)
# token: <your-pat-token>
```

**2. AWS SSO authenticated** (needed for `just deploy-workflows`):
```bash
aws sso login --profile alo-is-dev    # dev
aws sso login --profile alo-is-prod   # prod
```

**3. dbt Docker image pushed to ECR** — workflows pull the `alo-lakehouse` image.
Ensure the image exists before deploying:
```bash
just deploy-docker dev    # build + push dev image
just deploy-docker prod   # build + push prod image
```

---

## Deploy Workflows

### Using `just` (recommended)

```bash
just deploy-workflows dev    # deploy to dev workspace
just deploy-workflows prod   # deploy to prod workspace
```

### Using the script directly

```bash
# Dev (reads credentials from ~/.databrickscfg profile alo-dev)
uv run python scripts/deploy_workflows.py --env dev

# Prod (reads credentials from ~/.databrickscfg profile alo-prod)
uv run python scripts/deploy_workflows.py --env prod

# Override credentials via env vars
DATABRICKS_HOST=https://dbc-e27abc0b-645c.cloud.databricks.com \
DATABRICKS_TOKEN=<token> \
uv run python scripts/deploy_workflows.py --env dev
```

The deploy script is **idempotent**:
- If the job name already exists → updates it (`jobs.reset`)
- If the job name doesn't exist → creates it (`jobs.create`)

---

## Manual Trigger

Trigger a workflow run outside the schedule via CLI:

```bash
# Get job ID by name
databricks jobs list | grep alo-lakehouse

# Trigger daily run
databricks jobs run-now --job-id <job-id>

# Trigger full refresh
databricks jobs run-now --job-id <job-id>
```

Or from the Databricks UI: **Workflows** → `alo-lakehouse-daily-run` → **Run now**.

---

## Monitor Runs

```bash
# List recent runs for a job
databricks runs list --job-id <job-id> --limit 5

# Get details of a specific run
databricks runs get --run-id <run-id>

# Cancel a running job
databricks runs cancel --run-id <run-id>
```

Failure alerts are sent to `data-engineering@aloyoga.com`.
Health alert fires if a run exceeds 90 minutes (daily run only).

---

## Update a Workflow

1. Edit the relevant JSON file (`daily_run.json` or `full_refresh.json`)
2. Redeploy:
   ```bash
   just deploy-workflows dev    # test in dev first
   just deploy-workflows prod   # then prod
   ```

The deploy script uses `jobs.reset` which replaces the entire job definition — all task
configs, cluster specs, and schedules are updated in one call.

---

## Key Config Details

### Schedule (Quartz cron)

| Workflow | Cron Expression | Meaning |
|----------|----------------|---------|
| `daily_run` | `0 0 4 * * ?` | Every day at 4:00 AM |
| `full_refresh` | `0 0 1 ? * SUN` | Every Sunday at 1:00 AM |

All times are `America/Los_Angeles` (PT). Adjust `timezone_id` in the JSON to change.

### Environment Variable: `DBT_MATERIALIZATION`

Both workflows set `DBT_MATERIALIZATION=table` in `spark_env_vars`. This overrides the
default `view` materialization so all models are written as Delta tables on the cluster.
See `lakehouse/dbt_project.yml` — models use `env_var('DBT_MATERIALIZATION', 'view')`.

### Cluster Sizing

| Workflow | Node | Workers | Use case |
|----------|------|---------|---------|
| `daily_run` | `i3.xlarge` | 4 | Incremental loads — moderate compute |
| `full_refresh` | `i3.2xlarge` | 8 | Full rebuilds — higher memory + parallelism |

To change cluster size, edit `job_clusters[].new_cluster` in the JSON and redeploy.
