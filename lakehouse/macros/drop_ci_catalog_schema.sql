{% macro drop_ci_catalog_schema() %}
    {#
        Drops the ephemeral CI schema created during PR validation runs.
        Called by the dbt-validate GitHub Actions job via:
          dbt run-operation drop_ci_catalog_schema --target ci
    #}
    {% if target.name == 'ci' %}
        {% set drop_sql %}
            drop schema if exists {{ target.catalog }}.{{ target.schema }} cascade
        {% endset %}

        {% if execute %}
            {% do run_query(drop_sql) %}
            {{ log("Dropped CI schema: " ~ target.catalog ~ "." ~ target.schema, info=True) }}
        {% endif %}
    {% else %}
        {{ log("Skipping schema drop — not a CI target (target=" ~ target.name ~ ")", info=True) }}
    {% endif %}
{% endmacro %}
