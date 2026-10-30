with joined as (
select  
    f.issue_date,
    f.issue_ts,
    f.target_ts,
    f.lead_days,
    f.model_version,
    f.predicted_mw,
    d.avg_initial_demand_outturn as actual_mw,
    coalesce(feat.lag_7d, feat.lag_14d) as baseline_mw
from {{ ref('stg_inference_forecasts') }} f
left join {{ ref('int_demand_hourly') }} d
on f.target_ts = d.target_hour
left join {{ ref('int_demand_feature_rows') }} feat
on f.target_ts = feat.target_ts 
and f.lead_days = feat.lead_days
)
select
    j.*,
    (actual_mw - predicted_mw) as signed_error_mw,
    abs(actual_mw - predicted_mw) as abs_error_mw,
    actual_mw - baseline_mw as baseline_signed_error_mw,
    abs(actual_mw - baseline_mw) as baseline_abs_error_mw
from joined j