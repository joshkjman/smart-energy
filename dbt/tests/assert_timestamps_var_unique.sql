select 
    target_ts,
    issue_ts,
    count(*)
from {{ ref('stg_weather_forecast') }}
group by target_ts, issue_ts
having count(*) > 1