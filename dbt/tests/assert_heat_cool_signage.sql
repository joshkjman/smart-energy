select 
    *
from {{ ref('int_demand_feature_rows') }}
where (heating_degrees > 0 and (temperature_2m > {{ var('base_temperature') }} ))
or (cooling_degrees > 0 and (temperature_2m < {{ var('base_temperature') }} ))