import datetime as dt
import openmeteo_requests
import pandas as pd

from datetime import timedelta
from ingestion.bronze_io import write_bronze


PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BRONZE_PREFIX = "bronze/weather_forecast"

LAT = 51.5085
LON = -0.1257

HOURLY_VARS = ["temperature_2m", "shortwave_radiation"]
MAX_PREVIOUS_DAY = 7

BACKFILL_START = dt.date(2026,7,11)
BACKFILL_END = dt.datetime.now(dt.timezone.utc).date()

openmeteo = openmeteo_requests.Client()


def fetch_previous_runs(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """Pull Previous Runs between start_date and end_date, and return a WIDE dataframe."""
    prev_model_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": HOURLY_VARS + [f"{var}_previous_day{n}" for var in HOURLY_VARS for n in range(1, MAX_PREVIOUS_DAY + 1)],
        "start_date": f"{start_date:%Y-%m-%d}",
        "end_date":   f"{end_date:%Y-%m-%d}",
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
    """Melt the wide previous_dayN columns into long, issue-stamped records."""
    long_df = pd.melt(wide, id_vars=['date'])
    long_df.rename(columns={'date': 'target_ts'}, inplace=True)
    long_df['N'] = long_df['variable'].str.extract(r'previous_day(\d+)').fillna(0).astype(int)
    long_df['issue_ts'] = long_df['target_ts'].dt.normalize() - pd.to_timedelta(long_df['N'], unit='days')

    return long_df


def validate(long_df: pd.DataFrame) -> None:
    """Tripwire on the reshaped frame BEFORE landing. Raise on anything unusable."""   
    if long_df.empty:
        raise ValueError('DataFrame is empty')
    
    for required_col in ['target_ts', 'issue_ts', 'value']:
        if required_col not in long_df.columns:
            raise ValueError(f'Missing column {required_col}')


def bronze_key(issue_ts: dt.date) -> str:
    """Deterministic key for one issue_date's forecast records. (Same idea as demand.)"""
    return f"{BRONZE_PREFIX}/issue_date={issue_ts:%Y-%m-%d}/forecast.json"


def daterange_chunks(start: dt.date, end: dt.date, chunk_days: int):
    """Yield overlapping (chunk_start, chunk_end) TARGET-date windows, inclusive,
    each <= chunk_days wide.

    A window [lo, hi] can only write issue dates lo .. hi - MAX_PREVIOUS_DAY complete,
    because each issue date needs its full target span. So consecutive windows overlap
    by MAX_PREVIOUS_DAY (next start = previous end + 1 - MAX_PREVIOUS_DAY), which makes
    those writable issue ranges tile with no gaps. Stops once no complete issue date
    remains (start + MAX_PREVIOUS_DAY > end); the last window clamps to `end`.

    Not the same as demand_ingest.daterange_chunks, which does not overlap.
    """
    cur = start
    while cur + timedelta(days=MAX_PREVIOUS_DAY) <= end:
        hi = min(cur + timedelta(days=(chunk_days - 1)) , end)
        yield (cur, hi)
        cur = hi + timedelta(days=1) - timedelta(days=MAX_PREVIOUS_DAY)


def ingest_range(date_from: dt.date, date_to: dt.date) -> None:
    """Fetch, validate and land every ISSUE date in [date_from, date_to], inclusive.

    Issue date D needs targets D .. D + MAX_PREVIOUS_DAY, so the target window fetched
    runs MAX_PREVIOUS_DAY past date_to. Those future target dates are fetchable: a run
    issued on date_to already contains its forward predictions.
    """
    for low, high in daterange_chunks(date_from, date_to  + timedelta(days=MAX_PREVIOUS_DAY), 30): # calls function on every iteration, with yield, returning one date range at a time
        prev_model_hourly_data_df = fetch_previous_runs(low, high)
        long_df = reshape_to_long(prev_model_hourly_data_df)
        validate(long_df)

        # An issue_date can only be written complete if its full target span
        # (D .. D+7) sits inside this chunk. Writing the others would land a
        # truncated file under a key the next chunk also owns -- last write wins,
        # and the partial one silently survives.
        write_from = pd.Timestamp(low, tz='UTC')
        write_to = pd.Timestamp(high, tz='UTC') - timedelta(days=MAX_PREVIOUS_DAY)
        long_df_corrected = long_df[(long_df['issue_ts'] >= write_from) & (long_df['issue_ts'] <= write_to)]
        
        for name, group in long_df_corrected.groupby('issue_ts'):
            key = bronze_key(name)
            body = '{"data":' + group.to_json(orient='records', date_format='iso') + '}'
            write_bronze(key, body)


def main() -> None:
    """Local entry point: pull a date range and land it."""
    ingest_range(BACKFILL_START, BACKFILL_END)


if __name__ == "__main__":
    main()

