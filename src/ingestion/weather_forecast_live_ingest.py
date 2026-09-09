import datetime as dt

import openmeteo_requests
import pandas as pd

from ingestion.bronze_io import write_bronze

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
BRONZE_PREFIX = "bronze/weather_forecast"

LAT = 51.5085
LON = -0.1257

HOURLY_VARS = ["temperature_2m"]
openmeteo = openmeteo_requests.Client()


def fetch_forecast(forecast_days: int) -> pd.DataFrame:
    """Pull the latest run and return a WIDE frame: `date` (target_ts, hourly UTC)
    plus one column per HOURLY_VAR. No previous_dayN columns.

    Mechanical lift of the backfill's fetch — same client/date_range/enumerate
    pattern, minus the offset columns.
    """
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": HOURLY_VARS,
        "forecast_days": forecast_days,
        "past_days": 0,
    }
    responses = openmeteo.weather_api(FORECAST_URL, params=params)
    response = responses[0]

    hourly = response.Hourly()
    data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )
    }
    for i, name in enumerate(HOURLY_VARS):
        data[name] = hourly.Variables(i).ValuesAsNumpy()

    return pd.DataFrame(data=data)


def reshape_to_long(wide: pd.DataFrame, run_date: dt.date) -> pd.DataFrame:
    """Wide -> long, matching the backfill schema: target_ts, issue_ts, variable, value.

    TODO:
      - melt on the VARIABLE columns (id_vars=['date']) -> (variable, value)
        NOTE: this melts a DIFFERENT axis than the backfill (issue axis there).
      - rename date -> target_ts
      - issue_ts is a SINGLE constant for every row: pd.Timestamp(run_date, tz='UTC')
        (day resolution, so it lines up with the backfill's issue_ts)
    """
    long_df = pd.melt(wide, id_vars=['date'])
    long_df.rename(columns={'date': 'target_ts'}, inplace=True)
    long_df['issue_ts'] = pd.Timestamp(run_date, tz='UTC')

    return long_df
    


def validate(long_df: pd.DataFrame) -> None:
    """Same tripwire as the backfill: raise on empty frame or missing required cols
    (target_ts, issue_ts, value). Keep it light — Pydantic contracts come later.
    """
    if long_df.empty:
        raise ValueError("DataFrame is empty")
    for required_col in ["target_ts", "issue_ts", "value"]:
        if required_col not in long_df.columns:
            raise ValueError(f"Missing column {required_col}")


def bronze_key(issue_ts: dt.date) -> str:
    """Deterministic key for one issue_date's forecast. Identical to the backfill's
    (same partition space) so both sources interleave cleanly.
    """
    return f"{BRONZE_PREFIX}/issue_date={issue_ts:%Y-%m-%d}/forecast.json"


def main() -> None:
    """Live entry point: fetch -> reshape (run_date=today) -> validate -> land.

    TODO:
      - fetch_forecast(7), reshape with run_date = today, validate
      - group by issue_ts and write each group (here that's exactly ONE group)
      - serialize the body the same way the backfill does:
        '{"data":' + group.to_json(orient='records', date_format='iso') + '}'
    """
    df = fetch_forecast(7)
    long_df = reshape_to_long(df, dt.date.today())
    validate(long_df)
    
    for name, group in long_df.groupby('issue_ts'):
        key = bronze_key(name)
        body = '{"data":' + group.to_json(orient='records', date_format='iso') + '}'
        write_bronze(key, body)



if __name__ == "__main__":
    main()

