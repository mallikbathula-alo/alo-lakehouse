# Analyses

Ad-hoc SQL analyses that reference dbt models via `{{ ref() }}`.
These are compiled by dbt but not run as part of the pipeline.

Use for exploratory queries, data validation scripts, and one-off investigations
that you want version-controlled and templated.

```bash
# Compile an analysis (does not run it)
cd warehouse && dbt compile --select analysis_name
# Result: warehouse/target/compiled/lakehouse/analyses/analysis_name.sql
```
