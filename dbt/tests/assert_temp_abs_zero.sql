select
    value
from {{ ref('stg_weather_forecast') }}
where value < -30 or value > 50