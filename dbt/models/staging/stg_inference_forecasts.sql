select  cast(from_iso8601_timestamp(r.target_ts) at time zone 'UTC' as timestamp) as target_ts,
        cast(from_iso8601_timestamp(r.issue_ts) at time zone 'UTC' as timestamp) as issue_ts,
        issue_date,
        r.lead_days,
        r.predicted_mw,
        r.model_version
from {{ source('bronze', 'inference_forecasts') }}
cross join unnest(data) as t(r)

