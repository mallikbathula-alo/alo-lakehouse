{% macro case_check(column, mapping, else_value='other') %}
    {#
        Generates a CASE WHEN expression from a dict mapping.
        Usage: {{ case_check('status_code', {'1': 'active', '2': 'inactive'}) }}
    #}
    case
        {% for key, value in mapping.items() %}
            when {{ column }} = '{{ key }}' then '{{ value }}'
        {% endfor %}
        else '{{ else_value }}'
    end
{% endmacro %}
