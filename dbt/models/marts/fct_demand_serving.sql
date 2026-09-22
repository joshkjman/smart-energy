{{ config(
    materialized='view'
) }}

select *
from {{ ref('int_demand_feature_rows') }}
where issue_ts = cast(current_date as timestamp)
and cutoff <= current_timestamp
and demand_lag_mw is not null