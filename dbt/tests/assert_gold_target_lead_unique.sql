select 
    target_ts,
    lead_days,
    count(*)
from {{ ref('int_demand_feature_rows') }}
group by target_ts, lead_days
having count(*) > 1