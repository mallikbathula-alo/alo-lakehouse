-- ──────────────────────────────────────────────────────────────────────────────
-- Unity Catalog Workspace Setup — PROD
-- Run AFTER prod_account_setup.sh has completed.
--
-- Executed via SQL Warehouse:
--   just run-sql databricks/permissions/prod_workspace_setup.sql
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. Catalog ────────────────────────────────────────────────────────────────
CREATE CATALOG IF NOT EXISTS alo_prod
  MANAGED LOCATION 's3://is-prod-lakehouse'
  COMMENT 'Alo Yoga lakehouse — production environment';

-- ── 2. Schemas ────────────────────────────────────────────────────────────────
USE CATALOG alo_prod;

CREATE SCHEMA IF NOT EXISTS bronze
  MANAGED LOCATION 's3://is-prod-lakehouse/bronze'
  COMMENT 'Raw ingestion from source systems';

CREATE SCHEMA IF NOT EXISTS silver
  MANAGED LOCATION 's3://is-prod-lakehouse/silver'
  COMMENT 'Cleaned, deduplicated, and conformed data';

CREATE SCHEMA IF NOT EXISTS gold
  MANAGED LOCATION 's3://is-prod-lakehouse/gold'
  COMMENT 'Analytics-ready aggregations for BI tools';

CREATE SCHEMA IF NOT EXISTS mgt
  MANAGED LOCATION 's3://is-prod-lakehouse/mgt'
  COMMENT 'Operational and management tables';

CREATE SCHEMA IF NOT EXISTS snapshots
  MANAGED LOCATION 's3://is-prod-lakehouse/snapshots'
  COMMENT 'SCD Type 2 snapshot tables';

CREATE SCHEMA IF NOT EXISTS public
  MANAGED LOCATION 's3://is-prod-lakehouse/public'
  COMMENT 'Reference / seed tables';

-- ── 3. Catalog-level permissions ──────────────────────────────────────────────
GRANT USE CATALOG, CREATE SCHEMA ON CATALOG alo_prod TO `data_engineering`;
GRANT USE CATALOG ON CATALOG alo_prod TO `data_analyst`;
GRANT USE CATALOG ON CATALOG alo_prod TO `data_scientist`;
GRANT USE CATALOG ON CATALOG alo_prod TO `tableau`;
GRANT USE CATALOG, CREATE SCHEMA ON CATALOG alo_prod TO `fivetran`;
GRANT USE CATALOG ON CATALOG alo_prod TO `thoughtspot`;
GRANT USE CATALOG ON CATALOG alo_prod TO `hex_report`;
GRANT USE CATALOG ON CATALOG alo_prod TO `monte_carlo`;
GRANT USE CATALOG ON CATALOG alo_prod TO `braze`;

-- ── 4. Schema-level permissions ───────────────────────────────────────────────
-- data_engineering: full write access
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.bronze    TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.silver    TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.gold      TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.mgt       TO `data_engineering`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.snapshots TO `data_engineering`;

-- data_analyst: read silver + gold
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.silver TO `data_analyst`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold   TO `data_analyst`;

-- data_scientist: read all layers
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.bronze TO `data_scientist`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.silver TO `data_scientist`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold   TO `data_scientist`;

-- BI tools: read gold
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold TO `tableau`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold TO `thoughtspot`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold TO `hex_report`;

-- Monte Carlo: read bronze/silver/gold for monitoring
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.bronze TO `monte_carlo`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.silver TO `monte_carlo`;
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.gold   TO `monte_carlo`;

-- Braze: read bronze only
GRANT USE SCHEMA, SELECT ON ALL TABLES IN SCHEMA alo_prod.bronze TO `braze`;

-- Fivetran: write to bronze
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA alo_prod.bronze TO `fivetran`;
