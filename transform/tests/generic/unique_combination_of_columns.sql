{% test unique_combination_of_columns(model, combination_of_columns) %}
    select {{ combination_of_columns | join(', ') }}
    from {{ model }}
    group by all
    having count(*) > 1
{% endtest %}
