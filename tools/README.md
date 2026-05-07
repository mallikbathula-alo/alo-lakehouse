# tools/

Utility scripts for local development, CI/CD, and Databricks administration.
These are not part of the data pipeline — they support building, deploying, and operating it.

---

## Contents

```
tools/
├── setup.sh                        # Local dev bootstrap — installs all prerequisites
├── run_sql.py                      # Executes SQL files against Databricks SQL Warehouse
├── permissions/
│   └── unity_catalog_permissions.py  # Applies Unity Catalog GRANTs (runs in CI on every deploy)
├── cd/
│   ├── tag.sh                      # Bump semver tag and push (triggers prod deploy)
│   ├── tag_with_release_doc.sh     # Tag + generate and upload release notes
│   ├── release_doc.sh              # Generate release notes between two git tags
│   ├── rollback.sh                 # Roll back prod to the previous tag
│   └── ebf.sh                      # Emergency bug fix (bypasses normal release flow)
└── templates/
    └── profiles.yml.txt            # dbt profiles.yml template written by setup.sh
```

---

## setup.sh

One-time local dev bootstrap. Run after cloning the repo.

```bash
./tools/setup.sh
```

What it does:
1. Installs missing Homebrew packages: `awscli`, `just`, `pre-commit`, `databricks-cli`
2. Installs `uv` (Python package manager)
3. Creates `.venv` and installs all Python dependencies (`uv sync`)
4. Installs dbt packages (`dbt deps`)
5. Installs pre-commit hooks
6. Fetches the latest `manifest.json` from S3 (for `--defer` support)
7. Writes `~/.dbt/profiles.yml` template (if not already present)
8. Creates `.env` template (if not already present)

After running, fill in the placeholders in `~/.dbt/profiles.yml` and `.env`.

---

## run_sql.py

Executes a SQL file against the Databricks SQL Warehouse, statement by statement.
Reads credentials from `~/.dbt/profiles.yml` (the `lakehouse → local` target).

```bash
just run-sql databricks/permissions/dev_workspace_setup.sql
# or directly:
uv run python tools/run_sql.py databricks/permissions/dev_workspace_setup.sql
```

Used for one-off Unity Catalog setup scripts (catalog creation, schema grants, etc.).

---

## permissions/unity_catalog_permissions.py

Applies `GRANT` statements for all Unity Catalog groups across every schema in `alo_dev`
or `alo_prod`. Runs automatically on every deployment via `reusable-workflow.yaml`.

```bash
# Dry-run (print SQL without executing)
just permissions dev true

# Apply to dev
just permissions dev false

# Apply to prod
just permissions prod false
```

The permission matrix is defined at the top of the script in `CATALOG_PERMISSIONS` and
`CATALOG_LEVEL_PERMISSIONS`. Edit those dicts to add/remove group access, then deploy.

---

## cd/ — Release Management

Scripts that manage the release lifecycle. Invoked via `just` targets.

| Script | just target | What it does |
|--------|------------|--------------|
| `tag.sh` | `just tag patch\|minor\|major` | Bumps semver, creates + pushes git tag → triggers prod deploy |
| `tag_with_release_doc.sh` | `just tag-with-release-doc` | Tag + generate and upload release notes to S3 |
| `release_doc.sh` | `just generate-release-notes` | Generates markdown release notes from git log between two tags |
| `rollback.sh` | `just rollback` | Deletes the latest tag, re-tags at the previous one |
| `ebf.sh` | `just ebf` | Emergency bug fix — bypasses normal release flow |

### Normal release flow

```bash
just tag patch      # patch bump  → v1.2.3 → v1.2.4
just tag minor      # minor bump  → v1.2.3 → v1.3.0
just tag major      # major bump  → v1.2.3 → v2.0.0
```

Pushing the tag triggers `.github/workflows/prod.yaml`, which runs the full prod deployment.

### Rollback

```bash
just rollback       # removes latest tag, re-tags at previous commit
```

### Emergency bug fix

```bash
just ebf            # tags directly from current HEAD without going through dev first
```

---

## templates/

| File | Purpose |
|------|---------|
| `profiles.yml.txt` | Template for `~/.dbt/profiles.yml`, written by `setup.sh` on first run |
