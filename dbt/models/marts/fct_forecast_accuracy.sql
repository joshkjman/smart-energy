select  
    f.issue_date,
    f.issue_ts,
    f.target_ts,
    f.lead_days,
    f.model_version,
    f.predicted_mw,
    d.avg_initial_demand_outturn as actual_mw,
    (d.avg_initial_demand_outturn - f.predicted_mw) as signed_error_mw,
    abs(d.avg_initial_demand_outturn - f.predicted_mw) as abs_error_mw
from {{ ref('stg_inference_forecasts') }} f
left join {{ ref('int_demand_hourly') }} d
on f.target_ts = d.target_hour