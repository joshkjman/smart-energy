"""Weather forecast ingestion — Open-Meteo *Previous Runs* (historical backfill).

This is the BACKFILL client: Previous Runs returns, for a window of target times,
the forecast for each target *as issued* N days before the most recent run
(temperature_2m_previous_day1..N). One call therefore carries MANY issue dates.

Contrast with the live/daily client (regular forecast API, separate file): that one
pulls a single latest run = one issue date, forecasting forward.

Bronze-layer rules (same as demand):
- Land the data faithfully — no cleaning/typing (that's Silver/dbt).
- The ONE transform allowed here is demultiplexing: melt the wide previous_dayN
    columns into long records, each carrying its true issue_ts. Values untouched.
- Idempotent: a given issue_date always lands at the SAME key.
- Partition by ISSUE_DATE (not target date) — Bronze = "what we knew, when".

LEAKAGE NOTE: this client does NOT enforce point-in-time safety. It lands every
run with its honest issue_ts. The "issue_ts + publication_lag <= prediction_time"
filter is a GOLD concern, applied when features are assembled — never here.
"""
import datetime as dt
from datetime import timedelta

import openmeteo_requests
import pandas as pd
import json
import pathlib

# TODO: confirm archive depth for the chosen model (GFS) before locking a backfill window.
PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BRONZE_PREFIX = "bronze/weather_forecast"

# GB-aggregate: national target, so a single representative point is defensible for v1.
# (You reasoned this in Phase 1 — national demand needs the least spatial resolution.)
LAT = 51.5085
LON = -0.1257

# Which forecast variables we pull, and how many previous-run offsets (lead days) to request.
HOURLY_VARS = ["temperature_2m"]          # extend later (wind, cloud, etc.)
MAX_PREVIOUS_DAY = 7                       # previous_day1 .. previous_day7

openmeteo = openmeteo_requests.Client()


def fetch_previous_runs(past_days: int) -> pd.DataFrame:
    """Pull Previous Runs for the last `past_days` and return a WIDE dataframe.

    Reuse the openmeteo_requests pattern from src/api_call.py. The frame should have
    a `date` column (target_ts, hourly, UTC) plus one column per variable per offset:
    temperature_2m, temperature_2m_previous_day1, ... _previous_day{MAX_PREVIOUS_DAY}.

    FAST GEAR — this is the same plumbing you already wrote in api_call.py; lift it.
    TODO:
        - build the hourly list: base var + f"{var}_previous_day{n}" for n in 1..MAX
        - call the client, take response[0], build the date range from Time()/Interval()
        - assemble the wide dict -> DataFrame and return it
    """
    var = 'temperature_2m'
    prev_model_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": [var] + [f"{var}_previous_day{n}" for n in range(1, MAX_PREVIOUS_DAY + 1)],
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


def reshape_to_long(wide: pd.DataFrame, base_run_date: dt.date) -> pd.DataFrame:
    """Melt the wide previous_dayN columns into long, issue-stamped records.
    """
    long_df = pd.melt(wide, id_vars=['date'])
    long_df.rename(columns={'date': 'target_ts'}, inplace=True)
    long_df['N'] = long_df['variable'].str.extract(r'previous_day(\d+)').fillna(0).astype(int)
    long_df['issue_ts'] = pd.Timestamp(base_run_date, tz='UTC') - pd.to_timedelta(long_df['N'], unit='days')

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


def write_bronze(records, key: str) -> None:
    """Persist to Bronze at `key`. (This is identical to demand's — candidate to
    factor into a shared ingestion util later; duplicate for now, note the TODO.)

    TODO: local dev -> data/<key>; later -> boto3 put_object (SSE on, private).
    """
    path = pathlib.Path(f'data/{key}')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f: 
        f.write('{"data":' + records.to_json(orient='records', date_format='iso') + '}')


def main() -> None:
    """Backfill entry point: fetch -> reshape -> validate -> land per issue_date.

    TODO:
        - pick past_days (backfill window)
        - fetch wide, reshape to long, validate
        - group the long frame BY issue_date and write each group to its own key
    """
    prev_model_hourly_data_df = fetch_previous_runs(3)

    long_df = reshape_to_long(prev_model_hourly_data_df, dt.date.today())
    validate(long_df)
    
    for name, group in long_df.groupby('issue_ts'):
        key = bronze_key(name)
        write_bronze(group, key)


if __name__ == "__main__":
    main()

