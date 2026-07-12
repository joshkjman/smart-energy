with raw as (
    select unnest(data) as r          -- explode the 48-row array into rows
    from {{ source('bronze', 'demand') }}
)
select
    -- TODO: project r.settlementDate, r.settlementPeriod, r.initialDemandOutturn, etc.
    -- TODO: cast the timestamps (startTime / publishTime) to proper TIMESTAMP
    -- TODO: rename to snake_case column names you want in Silver
    -- think: what's the grain here, and what do you actually need downstream?
from raw