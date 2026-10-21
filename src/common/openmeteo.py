import pandas as pd


LAT = 51.5085
LON = -0.1257

HOURLY_VARS = ["temperature_2m", "shortwave_radiation"]

def hourly_to_frame(response, var_names: list[str]) -> pd.DataFrame:
    """Turn an Open-Meteo response's Hourly() block into a wide frame
    indexed by a 'date' column.

    var_names MUST be in the same order as the request's `hourly` parameter.
    The API returns values positionally and Variables(i) is matched by index,
    so a reordered list silently mislabels every column.
    """
    hourly = response.Hourly()
    hourly_data = {
        "date": pd.date_range(
            start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
            end =  pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
            freq = pd.Timedelta(seconds = hourly.Interval()),
            inclusive = "left"
        )
    }

    for i, name in enumerate(var_names):
        hourly_data[name] = hourly.Variables(i).ValuesAsNumpy()
    
    hourly_data_df = pd.DataFrame(data = hourly_data)

    return hourly_data_df