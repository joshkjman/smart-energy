select
    date_trunc('hour', start_time) as target_hour,
    count(*) as settlement_periods,
    case
        when count(*) = 2 then avg(initial_demand_outturn)
    end as avg_initial_demand_outturn
from {{ ref('stg_demand') }}
group by 1
