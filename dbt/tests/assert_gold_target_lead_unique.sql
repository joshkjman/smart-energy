select 
    target_ts,
    lead_days,
    count(*)
from {{ ref('fct_forecast_accuracy') }}
group by target_ts, lead_days
having count(*) > 1