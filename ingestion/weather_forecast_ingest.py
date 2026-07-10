import datetime as dt
from datetime import timedelta
from ingestion.bronze_io import write_bronze
import openmeteo_requests
import pandas as pd
import json
import pathlib


PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BRONZE_PREFIX = "bronze/weather_forecast"

LAT = 51.5085
LON = -0.1257


HOURLY_VARS = ["temperature_2m"]
MAX_PREVIOUS_DAY = 7

openmeteo = openmeteo_requests.Client()


def fetch_previous_runs(past_days: int) -> pd.DataFrame:
    """Pull Previous Runs for the last `past_days` and return a WIDE dataframe.
    """
    prev_model_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": HOURLY_VARS + [f"{HOURLY_VARS[0]}_previous_day{n}" for n in range(1, MAX_PREVIOUS_DAY + 1)],
        "past_days": past_days,
        "forecast_days": 1,
    }
    prev_model_responses = openmeteo.weather_api(PREV_RUNS_URL, params = prev_model_params)
    prev_model_response = prev_model_responses[0]

    prev_model_hourly = prev_model_response.Hourly()
    prev_model_hourly_data = {
            "date": pd.date_range(
                start = pd.to_datetime(prev_model_hourly.Time(), unit = "s", utc = True),
                end =  pd.to_datetime(prev_model_hourly.TimeEnd(), unit = "s", utc = True),
                freq = pd.Timedelta(seconds = prev_model_hourly.Interval()),
                inclusive = "left"
            )
        }
    
    for i, name in enumerate(prev_model_params['hourly']):
        prev_model_hourly_data[name] = prev_model_hourly.Variables(i).ValuesAsNumpy()

    prev_model_hourly_data_df = pd.DataFrame(data = prev_model_hourly_data)

    return prev_model_hourly_data_df


def reshape_to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide previous_dayN columns into long, issue-stamped records.
    """
    long_df = pd.melt(wide, id_vars=['date'])
    long_df.rename(columns={'date': 'target_ts'}, inplace=True)
    long_df['N'] = long_df['variable'].str.extract(r'previous_day(\d+)').fillna(0).astype(int)
    long_df['issue_ts'] = long_df['target_ts'].dt.normalize() - pd.to_timedelta(long_df['N'], unit='days')

    return long_df


def validate(long_df: pd.DataFrame) -> None:
    """Tripwire on the reshaped frame BEFORE landing. Raise on anything unusable.
    """   
    if long_df.empty:
        raise ValueError('DataFrame is empty')
    
    for required_col in ['target_ts', 'issue_ts', 'value']:
        if required_col not in long_df.columns:
            raise ValueError(f'Missing column {required_col}')



def bronze_key(issue_ts: dt.date) -> str:
    """Deterministic key for one issue_date's forecast records. (Same idea as demand.)         
    """
    return f"{BRONZE_PREFIX}/issue_date={issue_ts:%Y-%m-%d}/forecast.json"



def main() -> None:
    """Backfill entry point: fetch -> reshape -> validate -> land per issue_date.
    """
    prev_model_hourly_data_df = fetch_previous_runs(past_days=30)
    long_df = reshape_to_long(prev_model_hourly_data_df)
    validate(long_df)
    
    for name, group in long_df.groupby('issue_ts'):
        key = bronze_key(name)
        body = '{"data":' + group.to_json(orient='records', date_format='iso') + '}'
        write_bronze(key, body)


if __name__ == "__main__":
    main()

