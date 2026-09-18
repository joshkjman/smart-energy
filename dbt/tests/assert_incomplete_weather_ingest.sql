with raw as (
    select
        issue_date,
        regexp_replace(r.variable, '_previous_day\d+$', '') as variable
    from {{ source('bronze', 'weather_forecast') }}
    cross join unnest(data) as t(r)
    where issue_date >= cast(current_date - interval '30' day as varchar)
)
select
    issue_date,
    count(*)                                        as rows_total,
    count_if(variable = 'temperature_2m')            as temperature_rows,
    count_if(variable = 'shortwave_radiation')       as radiation_rows
from raw
group by issue_date
having count(*) <> 384
    or count_if(variable = 'temperature_2m') <> 192
    or count_if(variable = 'shortwave_radiation') <> 192
