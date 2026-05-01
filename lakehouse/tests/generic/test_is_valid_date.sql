{% test is_valid_date(model, column_name) %}

select {{ column_name }}
from {{ model }}
where
    {{ column_name }} is not null
    and (
        {{ column_name }} < date('2000-01-01')
        or {{ column_name }} > date_add(current_date(), 365)
    )

{% endtest %}
