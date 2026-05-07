#!/usr/bin/env bash
# ── alo-lakehouse local dev bootstrap ────────────────────────────────────────
# Sets up all prerequisites, uv venv, dbt deps, PySpark venv, manifest, profiles.yml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LAKEHOUSE_DIR="$ROOT_DIR/lakehouse"

echo "🏠 alo-lakehouse setup starting..."

# ── 0. Check system prerequisites ─────────────────────────────────────────────
MISSING=()

if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Install from https://brew.sh then re-run."
    exit 1
fi

if ! command -v aws &>/dev/null; then
    MISSING+=("awscli")
fi

if ! command -v just &>/dev/null; then
    MISSING+=("just")
fi

if ! command -v pre-commit &>/dev/null; then
    MISSING+=("pre-commit")
fi

# Databricks CLI (v2 — the Go-based CLI, not the legacy Python one)
if ! command -v databricks &>/dev/null; then
    MISSING+=("databricks-cli")
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "📦 Installing missing tools via Homebrew: ${MISSING[*]}"
    brew install "${MISSING[@]}"
fi

echo "✅ System prerequisites ready."

# ── 1. Install uv ─────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "✅ uv $(uv --version) ready."

# ── 2. Create dbt virtual environment and install deps ────────────────────────
echo "🐍 Setting up dbt Python environment..."
cd "$ROOT_DIR"
uv sync
echo "✅ dbt dependencies installed."

# ── 3. Install dbt packages ───────────────────────────────────────────────────
echo "📦 Installing dbt packages..."
cd "$LAKEHOUSE_DIR"
"$ROOT_DIR/.venv/bin/dbt" deps
echo "✅ dbt packages installed."

# ── 4. Install pre-commit hooks ───────────────────────────────────────────────
echo "🔗 Installing pre-commit hooks..."
cd "$ROOT_DIR"
pre-commit install
echo "✅ Pre-commit hooks installed."

# ── 5. Fetch latest manifest from S3 (for --defer support) ───────────────────
echo "📥 Fetching dev manifest from S3..."
mkdir -p "$LAKEHOUSE_DIR/target"
if aws s3 cp s3://alo-dev-de-docs/manifest.json "$LAKEHOUSE_DIR/target/manifest.json" 2>/dev/null; then
    echo "✅ manifest.json downloaded."
else
    echo "⚠️  Could not fetch manifest (S3 access may not be configured yet). Skipping."
fi

# ── 6. Write local profiles.yml ───────────────────────────────────────────────
DBT_PROFILES_DIR="$HOME/.dbt"
mkdir -p "$DBT_PROFILES_DIR"

if [[ -f "$DBT_PROFILES_DIR/profiles.yml" ]]; then
    echo "ℹ️  profiles.yml already exists at $DBT_PROFILES_DIR/profiles.yml — skipping."
else
    echo "📝 Creating profiles.yml template..."
    cat > "$DBT_PROFILES_DIR/profiles.yml" << 'PROFILES'
lakehouse:
  outputs:
    local:
      type: databricks
      host: dbc-e27abc0b-645c.cloud.databricks.com
      http_path: YOUR_SQL_WAREHOUSE_HTTP_PATH # Databricks → SQL Warehouses → <warehouse> → Connection details → HTTP Path
      token: YOUR_PAT_TOKEN                  # Databricks → Settings → Developer → Access tokens
      catalog: alo_dev
      schema: dbt_YOUR_NAME                  # e.g. dbt_$(whoami)
      threads: 8
      connect_timeout: 60
      connect_retries: 3
  target: local
PROFILES
    echo "✅ profiles.yml created at $DBT_PROFILES_DIR/profiles.yml"
    echo ""
    echo "⚙️  ACTION REQUIRED: Edit $DBT_PROFILES_DIR/profiles.yml with your Databricks connection details."
    echo "   - http_path: Databricks → SQL Warehouses → <warehouse> → Connection details → HTTP Path"
    echo "   - token:     Databricks → Settings → Developer → Access tokens → Generate new token"
    echo "   - schema:    e.g. dbt_$(whoami)"
fi

# ── 7. Create .env for PySpark (if not present) ───────────────────────────────
if [[ ! -f "$ROOT_DIR/.env" ]]; then
    cat > "$ROOT_DIR/.env" << 'DOTENV'
# PySpark / Databricks Connect — required for just pyspark-run / pyspark-shell
# DATABRICKS_HOST and DATABRICKS_TOKEN are read from ~/.dbt/profiles.yml automatically.
# Only DATABRICKS_CLUSTER_ID must be set here.
#
# Find your cluster ID: Databricks → Compute → <cluster> → Configuration → Tags → ClusterId
# Or from the URL: .../clusters/<CLUSTER_ID>
DATABRICKS_CLUSTER_ID=YOUR_CLUSTER_ID
DOTENV
    echo "✅ .env created — edit it and set DATABRICKS_CLUSTER_ID for PySpark."
else
    echo "ℹ️  .env already exists — skipping."
fi

# ── 8. Configure Databricks CLI ───────────────────────────────────────────────
if ! databricks auth profiles 2>/dev/null | grep -q "DEFAULT\|dev\|prod"; then
    echo ""
    echo "⚙️  Databricks CLI not configured. Run the following to configure:"
    echo "   databricks configure"
    echo "   (Enter your workspace host and PAT token when prompted)"
else
    echo "✅ Databricks CLI already configured."
fi

echo ""
echo "🎉 Setup complete! Next steps:"
echo "   1. Edit ~/.dbt/profiles.yml  — fill in http_path, token, schema"
echo "   2. Edit .env                 — fill in DATABRICKS_CLUSTER_ID (for PySpark)"
echo "   3. Run: cd lakehouse && dbt debug"
echo "   4. Run a dbt model:    just run-local <model_name>"
echo "   5. Run a PySpark script: just pyspark-run examples/explore_catalog.py"
