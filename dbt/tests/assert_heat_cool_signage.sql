select 
    *
from {{ ref('fct_demand_features') }}
where (heating_degrees > 0 and (temperature_2m > {{ var('base_temperature') }} ))
or (cooling_degrees > 0 and (temperature_2m < {{ var('base_temperature') }} ))