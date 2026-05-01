#!/usr/bin/env bash
# ── alo-lakehouse local dev bootstrap ────────────────────────────────────────
# Sets up uv venv, installs deps, fetches manifest, writes profiles.yml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LAKEHOUSE_DIR="$ROOT_DIR/lakehouse"

echo "🏠 alo-lakehouse setup starting..."

# ── 1. Install uv ─────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 2. Create virtual environment and install deps ────────────────────────────
echo "🐍 Setting up Python environment..."
cd "$ROOT_DIR"
uv sync
echo "✅ Dependencies installed."

# ── 3. Install dbt packages ───────────────────────────────────────────────────
echo "📦 Installing dbt packages..."
cd "$LAKEHOUSE_DIR"
"$ROOT_DIR/.venv/bin/dbt" deps
echo "✅ dbt packages installed."

# ── 4. Fetch latest manifest from S3 (for --defer support) ───────────────────
echo "📥 Fetching dev manifest from S3..."
mkdir -p "$LAKEHOUSE_DIR/target"
if aws s3 cp s3://alo-dev-de-docs/manifest.json "$LAKEHOUSE_DIR/target/manifest.json" 2>/dev/null; then
    echo "✅ manifest.json downloaded."
else
    echo "⚠️  Could not fetch manifest (S3 access may not be configured yet). Skipping."
fi

# ── 5. Write local profiles.yml ───────────────────────────────────────────────
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
    echo "⚙️  ACTION REQUIRED: Edit $DBT_PROFILES_DIR/profiles.yml with your Databricks workspace details."
    echo "   - host:      your dev workspace URL"
    echo "   - http_path: your SQL warehouse HTTP path"
    echo "   - token:     your personal access token (PAT)"
    echo "   - schema:    e.g. dbt_$(whoami)"
fi

echo ""
echo "🎉 Setup complete! Next steps:"
echo "   1. Edit ~/.dbt/profiles.yml with your Databricks connection details"
echo "   2. Run: cd lakehouse && dbt debug"
echo "   3. Run a model: just run-local <model_name>"
