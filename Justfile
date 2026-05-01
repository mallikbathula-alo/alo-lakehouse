export aws_prod   := "715192338314"
export aws_dev    := "206390103201"
export tag        := "latest"
export git_commit_sha := `git rev-parse --short HEAD 2>/dev/null || echo 'unknown'`
export root       := `pwd`

# ── Setup ──────────────────────────────────────────────────────────────────────

dbt-deps:
    cd lakehouse && dbt deps

setup:
    ./scripts/setup.sh

# ── Authentication ─────────────────────────────────────────────────────────────
# Login to AWS via SSO and authenticate Docker to ECR
# (No StrongDM needed — Databricks connects over HTTPS using PAT / service principal)

ecr-login env:
    aws sso login --profile alo-is-{{env}} || true
    aws ecr get-login-password --region us-east-1 --profile alo-is-{{env}} | \
        docker login --username AWS --password-stdin \
        "$aws_{{env}}.dkr.ecr.us-east-1.amazonaws.com"

# ── Manifest fetch ─────────────────────────────────────────────────────────────

get-manifest env="dev":
    aws s3 cp s3://alo-{{env}}-de-docs/manifest.json ./lakehouse/target/manifest.json \
        --profile alo-is-{{env}}

# ── Docker ─────────────────────────────────────────────────────────────────────

build env: (ecr-login env)
    cp ./scripts/templates/profiles.yml.txt ./profiles.yml
    docker build \
        --platform linux/x86_64 \
        --build-arg env={{env}} \
        -t alo-lakehouse:$tag \
        -t $aws_{{env}}.dkr.ecr.us-east-1.amazonaws.com/alo-lakehouse:$tag \
        .

push env: (build env)
    docker push $aws_{{env}}.dkr.ecr.us-east-1.amazonaws.com/alo-lakehouse:$tag

deploy-docker env tag="latest":
    just tag=$tag push {{env}}

# ── dbt Docs & Manifest ────────────────────────────────────────────────────────

deploy-dbt-docs-manifest env: (ecr-login env)
    cd lakehouse && \
    uv run dbt deps && \
    uv run dbt docs generate --target {{env}} --vars '{"source_catalog": "alo_{{env}}"}' && \
    aws s3 cp ./target/manifest.json s3://alo-{{env}}-de-docs/manifest.json \
        --profile alo-is-{{env}} && \
    aws s3 sync ./target s3://alo-{{env}}-de-docs/ \
        --profile alo-is-{{env}}

# ── Databricks Workflows ───────────────────────────────────────────────────────

deploy-workflows env="dev":
    uv run python scripts/deploy_workflows.py --env {{env}}

# ── SQL Runner ────────────────────────────────────────────────────────────────

run-sql file:
    uv run python scripts/run_sql.py {{file}}

# ── Permissions ────────────────────────────────────────────────────────────────

permissions env dry-run="true":
    uv run ./scripts/permissions/unity_catalog_permissions.py \
        --env {{env}} \
        --dry-run {{dry-run}}

# ── Local Development ─────────────────────────────────────────────────────────

run-local model:
    cd lakehouse && dbt run --defer --select {{model}} --target local --state .

run-full-refresh-local model:
    cd lakehouse && dbt run --defer --select {{model}} --target local --state . --full-refresh

run-prod-local model:
    cd lakehouse && dbt run --defer --select {{model}} --target local --state . \
        --vars '{"source_catalog": "alo_prod"}'

run-full-refresh-prod-local model:
    cd lakehouse && dbt run --defer --select {{model}} --target local --state . \
        --vars '{"source_catalog": "alo_prod"}' --full-refresh

# ── PySpark / Databricks Connect ─────────────────────────────────────────────
# Uses the shared .venv (databricks-connect ships with dbt-databricks 1.10+).
# Requires: .env with DATABRICKS_CLUSTER_ID

pyspark-run script:
    cd lakehouse/pyspark && ../../.venv/bin/python {{script}}

pyspark-shell:
    cd lakehouse/pyspark && ../../.venv/bin/python -c "\
        from utils.session import get_spark; \
        spark = get_spark(); \
        print('SparkSession ready — use spark.<tab>'); \
        import code; code.interact(local=locals())"

# ── Release Management ────────────────────────────────────────────────────────

tag type:
    cd scripts/cd && ./tag.sh {{type}}

tag-with-release-doc type env="dev":
    cd scripts/cd && ./tag_with_release_doc.sh "{{type}}" "{{env}}"

generate-release-notes env previous_tag="" latest_tag="": (ecr-login env)
    cd scripts/cd && ./release_doc.sh "{{env}}" "{{previous_tag}}" "{{latest_tag}}"

upload-release-notes env: (ecr-login env)
    aws s3 cp ./release_notes s3://alo-{{env}}-de-docs/release_notes --recursive \
        --profile alo-is-{{env}}

delete-release-notes:
    rm -rf ./release_notes

generate-upload-and-delete-release-notes env previous_tag="" latest_tag="": \
    (generate-release-notes env previous_tag latest_tag) \
    (upload-release-notes env) \
    delete-release-notes

rollback:
    scripts/cd/rollback.sh

ebf:
    scripts/cd/ebf.sh
