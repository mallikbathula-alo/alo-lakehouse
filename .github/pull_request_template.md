## Summary
<!-- What does this PR do? Why is it needed? -->

## Changes
<!-- List the models, macros, seeds, or scripts changed -->

## Testing
<!-- How was this validated? -->
- [ ] `dbt run --select <models>` passed locally
- [ ] `dbt test --select <models>` passed locally
- [ ] CI dbt-validate job passed
- [ ] Reviewed compiled SQL in `warehouse/target/compiled/`

## Checklist
- [ ] All new models have a properties YAML entry
- [ ] Models are tagged with valid tags (see `.pre-commit-config.yaml`)
- [ ] No hardcoded catalog/schema names (using `{{ ref() }}` / `{{ source() }}`)
- [ ] Incremental models have a proper `is_incremental()` filter
- [ ] Large tables use `cluster_by` for query performance
- [ ] Monte Carlo monitors updated if new critical tables added

## Unity Catalog Impact
<!-- Does this add new schemas or change permissions? -->
- [ ] No Unity Catalog changes
- [ ] New schema added — `databricks/permissions/unity_catalog_setup.sql` updated
- [ ] Permission changes — `scripts/permissions/unity_catalog_permissions.py` updated

## Deployment Notes
<!-- Anything special needed for dev/prod deploy? Full refresh required? -->
