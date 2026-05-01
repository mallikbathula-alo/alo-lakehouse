{% macro cents_to_dollars(column_name, scale=2) %}
    round(cast({{ column_name }} as double) / 100.0, {{ scale }})
{% endmacro %}
