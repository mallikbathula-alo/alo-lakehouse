# Databricks Cluster Setup

Cluster config files for dev (interactive) and prod (job) clusters.
Use the Databricks CLI to create or update clusters from these JSON definitions.

## Cluster Configs

| File | Cluster Name | Purpose | Node Type | DBR |
|------|-------------|---------|-----------|-----|
| `dev_cluster.json` | `alo-lakehouse-dev` | Ad-hoc analysis, PySpark development, debugging | `i3.xlarge` (1–4 autoscale) | 15.4 Photon |
| `prod_cluster.json` | `alo-lakehouse-prod` | Databricks Workflows (daily_run, full_refresh) | `i3.2xlarge` (8 fixed) | 15.4 Photon |

## Prerequisites

Databricks CLI configured:
```bash
databricks configure
# host:  https://dbc-e27abc0b-645c.cloud.databricks.com
# token: <your-pat-token>
```

## Create a Cluster

### Dev cluster (interactive — for local PySpark development)

```bash
databricks clusters create --json @databricks/clusters/dev_cluster.json
```

Note the `cluster_id` from the output — add it to your `.env`:
```bash
DATABRICKS_CLUSTER_ID=<cluster_id_from_output>
```

### Prod cluster (job cluster — used by Databricks Workflows)

```bash
databricks clusters create --json @databricks/clusters/prod_cluster.json
```

## Update an Existing Cluster

```bash
# Get the cluster ID first
databricks clusters list | grep alo-lakehouse

# Edit the JSON, then apply changes
databricks clusters edit --json '{
  "cluster_id": "<existing-cluster-id>",
  ... fields to update ...
}'
```

Or replace the entire config:
```bash
# Add "cluster_id" to the JSON, then:
databricks clusters edit --json @databricks/clusters/dev_cluster.json
```

## Start / Stop a Cluster

```bash
databricks clusters start --cluster-id <cluster-id>
databricks clusters delete --cluster-id <cluster-id>   # permanent delete
```

## Get Cluster ID by Name

```bash
databricks clusters list --output json | \
  python3 -c "import sys,json; clusters=json.load(sys.stdin)['clusters']; \
  [print(c['cluster_id'], c['cluster_name']) for c in clusters if 'alo-lakehouse' in c.get('cluster_name','')]"
```

## Key Config Differences: Dev vs Prod

| Setting | Dev | Prod |
|---------|-----|------|
| `autoscale` | 1–4 workers (scales down when idle) | 8 fixed workers |
| `autotermination_minutes` | 30 min (auto-stops) | Not set (job clusters terminate after run) |
| `data_security_mode` | `USER_ISOLATION` (multi-user safe) | `SINGLE_USER` (job runs as service principal) |
| `node_type_id` | `i3.xlarge` (cost-efficient for dev) | `i3.2xlarge` (more memory for production loads) |
| `spark.sql.shuffle.partitions` | `auto` | `400` (tuned for prod data volumes) |

## Notes

- Both clusters use **DBR 15.4 Photon** — must match `databricks-connect==15.4.x` in `pyproject.toml`.
- When upgrading DBR, update `spark_version` in the JSON **and** `databricks-connect` in `pyproject.toml`.
- The dev cluster uses `USER_ISOLATION` mode which is required for Unity Catalog multi-user access.
- Prod cluster is not meant to be kept running — Databricks Workflows spin it up per job run.
