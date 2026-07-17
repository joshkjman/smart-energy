select 
    target_ts,
    issue_ts,
    variable,
    count(*)
from {{ ref('stg_weather_forecast') }}
group by target_ts, issue_ts, variable
having count(*) > 1