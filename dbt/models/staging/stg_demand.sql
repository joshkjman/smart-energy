with raw as (
    select unnest(data) as r          -- explode the 48-row array into rows
    from {{ source('bronze', 'demand') }}
)
select
    r.publishTime at time zone 'UTC' as publish_time,
    r.startTime at time zone 'UTC' as start_time,
    r.settlementDate as settlement_date,
    r.settlementPeriod as settlement_period,
    r.initialDemandOutturn as initial_demand_outturn,
    r.initialTransmissionSystemDemandOutturn as initial_transmission_system_demand_outturn,
from raw