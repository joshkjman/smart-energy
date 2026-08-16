select *
from {{ ref('fct_demand_features') }}
where demand_lag_ts > cutoff
or ((target_ts - interval '168' hour) > cutoff and lag_7d is not null)
or ((target_ts - interval '336' hour) > cutoff and lag_14d is not null)
or issue_ts > date_add('day', -lead_days, target_ts)
or cutoff > date_add('day', -lead_days, target_ts)