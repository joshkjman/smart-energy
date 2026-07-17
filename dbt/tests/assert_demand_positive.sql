-- dbt fails this test if this query returns ANY rows
select
    start_time,
    initial_demand_outturn
from {{ ref('stg_demand') }}
where initial_demand_outturn <= 0