select
    temperature_2m
from {{ ref('stg_weather_forecast') }}
where temperature_2m < -30 or temperature_2m > 50