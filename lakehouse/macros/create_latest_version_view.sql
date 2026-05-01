{% macro create_latest_version_view(source_relation, view_name) %}
    {#
        Creates (or replaces) a convenience view pointing to the latest
        snapshot version of a table. Databricks / Unity Catalog syntax.
    #}
    {% set view_sql %}
        create or replace view {{ target.catalog }}.{{ target.schema }}.{{ view_name }}
        as select * from {{ source_relation }}
    {% endset %}

    {% if execute %}
        {% do run_query(view_sql) %}
        {{ log("Created view: " ~ view_name, info=True) }}
    {% endif %}
{% endmacro %}
