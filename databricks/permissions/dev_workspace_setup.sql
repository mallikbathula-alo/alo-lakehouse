-- ──────────────────────────────────────────────────────────────────────────────
-- Unity Catalog Workspace Setup — DEV
-- Run AFTER dev_account_setup.sh has completed.
--
-- Executed via SQL Warehouse:
--   just run-sql databricks/permissions/dev_workspace_setup.sql
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. Catalog ────────────────────────────────────────────────────────────────
CREATE CATALOG IF NOT EXISTS alo_dev
  MANAGED LOCATION 's3://is-dev-lakehouse'
  COMMENT 'Alo Yoga lakehouse — development environment';

-- ── 2. Schemas ────────────────────────────────────────────────────────────────
USE CATALOG alo_dev;

CREATE SCHEMA IF NOT EXISTS bronze
  MANAGED LOCATION 's3://is-dev-lakehouse/bronze'
  COMMENT 'Raw ingestion from source systems';

CREATE SCHEMA IF NOT EXISTS silver
  MANAGED LOCATION 's3://is-dev-lakehouse/silver'
  COMMENT 'Cleaned, deduplicated, and conformed data';

CREATE SCHEMA IF NOT EXISTS gold
  MANAGED LOCATION 's3://is-dev-lakehouse/gold'
  COMMENT 'Analytics-ready aggregations for BI tools';

CREATE SCHEMA IF NOT EXISTS mgt
  MANAGED LOCATION 's3://is-dev-lakehouse/mgt'
  COMMENT 'Operational and management tables';

CREATE SCHEMA IF NOT EXISTS snapshots
  MANAGED LOCATION 's3://is-dev-lakehouse/snapshots'
  COMMENT 'SCD Type 2 snapshot tables';

CREATE SCHEMA IF NOT EXISTS public
  MANAGED LOCATION 's3://is-dev-lakehouse/public'
  COMMENT 'Reference / seed tables';

-- ── 3. Catalog-level permissions ──────────────────────────────────────────────
GRANT USE CATALOG, CREATE SCHEMA ON CATALOG alo_dev TO `data_engineering`;
GRANT USE CATALOG ON CATALOG alo_dev TO `data_analyst`;
GRANT USE CATALOG ON CATALOG alo_dev TO `data_scientist`;
GRANT USE CATALOG ON CATALOG alo_dev TO `tableau`;
GRANT USE CATALOG, CREATE SCHEMA ON CATALOG alo_dev TO `fivetran`;
GRANT USE CATALOG ON CATALOG alo_dev TO `thoughtspot`;
GRANT USE CATALOG ON CATALOG alo_dev TO `hex_report`;
GRANT USE CATALOG ON CATALOG alo_dev TO `monte_carlo`;
GRANT USE CATALOG ON CATALOG alo_dev TO `braze`;

-- ── 4. Schema-level permissions ───────────────────────────────────────────────
-- data_engineering: full write access
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.bronze    TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.silver    TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.gold      TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.mgt       TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.snapshots TO `data_engineering`;

-- data_analyst: read silver + gold
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.silver TO `data_analyst`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold   TO `data_analyst`;

-- data_scientist: read all layers
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.bronze TO `data_scientist`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.silver TO `data_scientist`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold   TO `data_scientist`;

-- BI tools: read gold
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold TO `tableau`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold TO `thoughtspot`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold TO `hex_report`;

-- Monte Carlo: read bronze/silver/gold for monitoring
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.bronze TO `monte_carlo`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.silver TO `monte_carlo`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.gold   TO `monte_carlo`;

-- Braze: read bronze only
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_dev.bronze TO `braze`;

-- Fivetran: write to bronze
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_dev.bronze TO `fivetran`;
