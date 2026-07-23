select 
    target_ts,
    lead_days,
    count(*)
from {{ ref('fct_demand_features') }}
group by target_ts, lead_days
having count(*) > 1