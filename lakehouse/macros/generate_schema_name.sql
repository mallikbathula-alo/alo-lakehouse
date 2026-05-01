{% macro generate_schema_name(custom_schema_name, node) -%}
    {#
        Overrides dbt default schema generation.
        In CI: prefixes schema with run-specific suffix for isolation.
        In dev/prod: uses the schema exactly as declared in dbt_project.yml.

        Unity Catalog note: the catalog (alo_dev / alo_prod) is set at the
        profile level. This macro only controls the schema portion.
    #}
    {%- set default_schema = target.schema -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif target.name == 'ci' -%}
        {# CI: schema = ci_<sha>_<custom_schema> for full isolation #}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- else -%}
        {# dev/prod: use the custom schema name directly #}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
