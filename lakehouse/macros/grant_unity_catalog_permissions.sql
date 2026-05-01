{% macro grant_unity_catalog_permissions(schemas, group_name) %}
    {#
        Grants SELECT on all schemas touched in this run to the specified group.
        Called via on-run-end in dbt_project.yml.

        Skipped for local target — Unity Catalog groups only exist in shared
        dev/prod workspaces, not personal developer catalogs.

        Unity Catalog syntax (each statement must be run separately):
          GRANT USAGE ON SCHEMA <catalog>.<schema> TO <principal>
          GRANT SELECT ON ALL TABLES IN SCHEMA <catalog>.<schema> TO <principal>
    #}
    {% if target.name == 'local' %}
        {{ log("Skipping Unity Catalog grants for local target.", info=True) }}
    {% else %}
        {% set principals = [
            'data_engineering',
            'data_analyst',
            'data_scientist',
            'tableau',
            'fivetran',
            'thoughtspot',
            'hex_report',
            'monte_carlo',
        ] %}

        {% set catalog = target.catalog %}

        {% for schema in schemas %}
            {% for principal in principals %}
                {% if execute %}
                    {% do run_query("grant usage on schema " ~ catalog ~ "." ~ schema ~ " to `" ~ principal ~ "`") %}
                    {% do run_query("grant select on all tables in schema " ~ catalog ~ "." ~ schema ~ " to `" ~ principal ~ "`") %}
                    {{ log("Granted SELECT on " ~ catalog ~ "." ~ schema ~ " to " ~ principal, info=True) }}
                {% endif %}
            {% endfor %}
        {% endfor %}
    {% endif %}
{% endmacro %}
