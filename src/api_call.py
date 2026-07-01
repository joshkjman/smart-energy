import openmeteo_requests
import pandas as pd



openmeteo = openmeteo_requests.Client()

lat = 51.5085
long = -0.1257

# PREVIOUS MODEL RUNS
prev_model_url = "https://previous-runs-api.open-meteo.com/v1/forecast"
prev_model_params = {
	"latitude": lat,
	"longitude": long,
	"hourly": ["temperature_2m", "temperature_2m_previous_day1", "temperature_2m_previous_day2", "temperature_2m_previous_day3"],
	"past_days": 7,
	"forecast_days": 1,
}
prev_model_responses = openmeteo.weather_api(prev_model_url, params = prev_model_params)

prev_model_response = prev_model_responses[0]
print(f"Coordinates: {prev_model_response.Latitude()}°N {prev_model_response.Longitude()}°E")
print(f"Elevation: {prev_model_response.Elevation()} m asl")
print(f"Timezone difference to GMT+0: {prev_model_response.UtcOffsetSeconds()}s")

prev_model_hourly = prev_model_response.Hourly()
prev_model_hourly_temperature_2m = prev_model_hourly.Variables(0).ValuesAsNumpy()
prev_model_hourly_temperature_2m_previous_day1 = prev_model_hourly.Variables(1).ValuesAsNumpy()
prev_model_hourly_temperature_2m_previous_day2 = prev_model_hourly.Variables(2).ValuesAsNumpy()
prev_model_hourly_temperature_2m_previous_day3 = prev_model_hourly.Variables(3).ValuesAsNumpy()

prev_model_hourly_data = {
	"date": pd.date_range(
		start = pd.to_datetime(prev_model_hourly.Time(), unit = "s", utc = True),
		end =  pd.to_datetime(prev_model_hourly.TimeEnd(), unit = "s", utc = True),
		freq = pd.Timedelta(seconds = prev_model_hourly.Interval()),
		inclusive = "left"
	)
}

prev_model_hourly_data["temperature_2m"] = prev_model_hourly_temperature_2m
prev_model_hourly_data["temperature_2m_previous_day1"] = prev_model_hourly_temperature_2m_previous_day1
prev_model_hourly_data["temperature_2m_previous_day2"] = prev_model_hourly_temperature_2m_previous_day2
prev_model_hourly_data["temperature_2m_previous_day3"] = prev_model_hourly_temperature_2m_previous_day3

prev_model_hourly_data_df = pd.DataFrame(data = prev_model_hourly_data)


# HISTORICAL DATA
historical_url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
historic_params = {
	"latitude": lat,
	"longitude": long,
	"start_date": "2026-06-23",
	"end_date": "2026-06-30",
	"hourly": "temperature_2m",
}
historic_responses = openmeteo.weather_api(historical_url, params = historic_params)

historic_response = historic_responses[0]

historic_hourly = historic_response.Hourly()
historic_hourly_temperature_2m = historic_hourly.Variables(0).ValuesAsNumpy()

historic_hourly_data = {
	"date": pd.date_range(
		start = pd.to_datetime(historic_hourly.Time(), unit = "s", utc = True),
		end =  pd.to_datetime(historic_hourly.TimeEnd(), unit = "s", utc = True),
		freq = pd.Timedelta(seconds = historic_hourly.Interval()),
		inclusive = "left"
	)
}

historic_hourly_data["temperature_2m_actual"] = historic_hourly_temperature_2m

historic_hourly_data_df = pd.DataFrame(data = historic_hourly_data)


hourly_data_df = prev_model_hourly_data_df.merge(historic_hourly_data_df, on='date')
print(f'\nHourly data\n{hourly_data_df}')

hourly_data_df['1day_difference'] = abs(hourly_data_df['temperature_2m_previous_day1'] - hourly_data_df['temperature_2m_actual'])
hourly_data_df['2day_difference'] = abs(hourly_data_df['temperature_2m_previous_day2'] - hourly_data_df['temperature_2m_actual'])
hourly_data_df['3day_difference'] = abs(hourly_data_df['temperature_2m_previous_day3'] - hourly_data_df['temperature_2m_actual'])

running_avg = hourly_data_df.groupby(hourly_data_df['date'].dt.date)[['1day_difference', '2day_difference', '3day_difference']].mean()
print(running_avg)
