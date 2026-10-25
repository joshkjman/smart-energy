select f.target_ts,
        f.issue_ts,
        f.lead_days,
        f.temperature_2m as forecast_temp,
        f.shortwave_radiation as forecast_rad,
        a.temperature_2m as actual_temp,
        a.shortwave_radiation as actual_rad,
        f.temperature_2m - a.temperature_2m as temp_error_c,
        f.shortwave_radiation - a.shortwave_radiation as rad_error_wm2
from {{ ref('stg_weather_forecast') }} f
left join {{ ref('stg_weather_actual') }} a 
on f.target_ts = a.target_ts
