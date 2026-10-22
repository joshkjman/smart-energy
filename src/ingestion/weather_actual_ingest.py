import datetime as dt
import openmeteo_requests
import pandas as pd

from common.openmeteo import LAT, LON, HOURLY_VARS, hourly_to_frame
from ingestion.bronze_io import write_bronze


ARCHIVE_URL   = "https://archive-api.open-meteo.com/v1/archive"
BRONZE_PREFIX = "bronze/weather_actual"
MODEL         = "ecmwf_ifs"

BACKFILL_START = dt.date(2026,7,11)

openmeteo = openmeteo_requests.Client()


def utc_date(days_ago: int) -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).date()


def fetch_actuals(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Pull hourly actuals for [start_date, end_date]. Wide: one column per variable.
    Same openmeteo.weather_api() pattern as the forecast ingest, different URL,
    no previous_dayN variables."""
    actuals_model_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": HOURLY_VARS,
        "start_date": f"{start_date:%Y-%m-%d}",
        "end_date":   f"{end_date:%Y-%m-%d}",
        "models": MODEL,
    }
    actuals_model_responses = openmeteo.weather_api(ARCHIVE_URL, params = actuals_model_params)
    actuals_model_response = actuals_model_responses[0]
    
    actuals_model_hourly_data_df = hourly_to_frame(actuals_model_response, actuals_model_params['hourly'])

    return actuals_model_hourly_data_df


def reshape_to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Melt to (target_ts, variable, value). Your forecast melt minus the
    previous_day(\\d+) extraction and the issue_ts derivation."""
    long_df = pd.melt(wide, id_vars=['date'])
    long_df.rename(columns={'date': 'target_ts'}, inplace=True)
    
    return long_df


def validate(long_df: pd.DataFrame) -> None:
    """Tripwire before landing."""
    if long_df.empty:
        raise ValueError('DataFrame is empty')
    
    for required_col in ['target_ts', 'value']:
        if required_col not in long_df.columns:
            raise ValueError(f'Missing column {required_col}')


def bronze_key(target_date: dt.date) -> str:
    """bronze/weather_actual/target_date=YYYY-MM-DD/actual.json"""
    return f"{BRONZE_PREFIX}/target_date={target_date:%Y-%m-%d}/actuals.json"


def ingest_range(date_from: dt.date, date_to: dt.date) -> None:
    """Fetch, validate, group by target date, land one file each.
    No overlapping chunks — each target date is self-contained."""
    wide_df = fetch_actuals(date_from, date_to)
    long_df = reshape_to_long(wide_df)
    validate(long_df)

    for name, group in long_df.groupby(long_df['target_ts'].dt.date):
        key = bronze_key(name)
        body = '{"data":' + group.to_json(orient='records', date_format='iso') + '}'
        write_bronze(key, body)


def main():
    ingest_range(BACKFILL_START, utc_date(1))


def handler(event, context):
    ingest_range(utc_date(7), utc_date(1))


if __name__ == "__main__":
    main()