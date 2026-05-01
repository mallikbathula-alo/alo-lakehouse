FROM --platform=linux/x86_64 public.ecr.aws/docker/library/python:3.10-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG env=dev
WORKDIR /app

RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Install dependencies using uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Setup dbt config directories
RUN mkdir -p /root/.dbt /root/.edr /root/.mcd

# Copy Databricks profiles template (injected at runtime via CI env vars)
COPY ./profiles.yml /root/.dbt/profiles.yml

# Copy lakehouse dbt project
COPY lakehouse .

ENV PATH="/app/.venv/bin:$PATH"

# Install dbt packages
RUN dbt deps

ENTRYPOINT ["dbt"]
