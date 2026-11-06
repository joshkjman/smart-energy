{{ config(
    materialized='view'
) }}

with knowable as (
    select *
    from {{ ref('int_demand_feature_rows') }}
    where cutoff <= current_timestamp
    and demand_lag_mw is not null
)
select *
from knowable
where issue_ts = (select max(issue_ts) from knowable)