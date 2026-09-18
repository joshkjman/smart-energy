import datetime as dt
import requests
import json
import pathlib

from collections import defaultdict
from ingestion.bronze_io import write_bronze
from datetime import timedelta


BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
DEMAND_OUTTURN_PATH = "/demand/outturn"
BRONZE_PREFIX = "bronze/demand"

BACKFILL_START = dt.date(2024,7,1)
BACKFILL_END = dt.date(2026,7,11)


def fetch_demand_outturn(date_from: dt.date, date_to: dt.date) -> dict:
    """Fetch INDO half-hourly demand outturn for [date_from, date_to] inclusive.

    Returns the parsed JSON payload as-is (do not reshape here).
    """
    api_params = {"settlementDateFrom": f"{date_from:%Y-%m-%d}", "settlementDateTo": f"{date_to:%Y-%m-%d}" , "format": 'json'}
    headers = {"accept": "application/json"}
    response = requests.get(BASE_URL + DEMAND_OUTTURN_PATH, params=api_params, headers=headers)
    response.raise_for_status()
    return response.json()


def validate(payload: dict) -> None:
    """Light contract check on what Elexon returned, BEFORE we trust/land it.

    Raise on anything that means the pull is unusable. Keep it light — this is a
    tripwire, not a full schema (Pydantic contracts come later in the plan).
    """
    if 'data' not in payload:
        raise ValueError('Top level payload shape incorrect')
    
    payload_data = payload['data']
    if not payload_data:
        raise ValueError('No data in payload')
        
    for row in payload_data:
        for col_check in ['settlementDate', 'settlementPeriod', 'initialDemandOutturn']:
            if col_check not in row:
                raise ValueError(f'Missing {col_check} data')


def bronze_key(settlement_date: dt.date) -> str:
    """Deterministic S3 key for one settlement date's raw demand.

    Same date in -> same key out, so re-runs overwrite (idempotency).
    """
    return f"{BRONZE_PREFIX}/settlement_date={settlement_date:%Y-%m-%d}/demand.json"


def daterange_chunks(start: dt.date, end: dt.date, chunk_days: int):
    """Yield (chunk_start, chunk_end) inclusive windows, each ≤ chunk_days wide.
    Last window clamps to `end`."""
    cur = start
    while cur <= end:
        hi = min(cur + timedelta(days=(chunk_days - 1)) , end)
        yield (cur, hi)
        cur = hi + timedelta(days=1)


def ingest_range(date_from: dt.date, date_to: dt.date) -> None:
    """Fetch, validate and land every settlement date in [date_from, date_to]"""
    for low, high in daterange_chunks(date_from, date_to, 28): # calls function on every iteration, with yield, returning one date range at a time
        payload = fetch_demand_outturn(low, high)
        validate(payload)

        grouped_day = defaultdict(list)
        for d in payload['data']:
            grouped_day[d['settlementDate']].append(d)

        for k, v in grouped_day.items():
            write_payload = {'data': v}
            key = bronze_key(dt.date.fromisoformat(k))
            body = json.dumps(write_payload)
            write_bronze(key, body)


def main() -> None:
    """Local entry point: pull a date range and land it."""
    ingest_range(BACKFILL_START, BACKFILL_END)

    
def handler(event, context):
    today = dt.datetime.now(dt.timezone.utc).date()
    diff = dt.timedelta(days=7)
    ingest_range(today-diff, today)


if __name__ == "__main__":
    ingest_range(dt.date(2026,7,12), dt.datetime.now(dt.timezone.utc).date())
    #main()