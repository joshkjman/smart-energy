select
    date_trunc('hour', start_time) as target_hour,
    avg(initial_demand_outturn) as avg_initial_demand_outturn
from {{ ref('stg_demand') }}
group by 1
