"""Demand ingestion client (Elexon Insights / BMRS — INDO half-hourly demand outturn).

Bronze-layer ingestion: fetch raw demand outturn from Elexon and land it *as-is*
in S3, partitioned by settlement date. This is a landing zone, NOT a cleaning step
— no reshaping, typing, or feature engineering here (that's Silver/dbt later).

Design constraints (from Phase 1 / Phase 2 decisions):
  - Bronze stays RAW: persist the API response essentially untouched.
  - Idempotent write: a given settlement date always lands at the SAME S3 key,
    so re-running overwrites rather than duplicating.
  - Single observation timestamp -> partition by settlement date.

Developed as a plain local module first; wrapped as a Lambda handler + Terraform later.
"""

from __future__ import annotations
import datetime as dt
import requests

# TODO: confirm these against the live API (call it, inspect the response) before trusting.
BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
DEMAND_OUTTURN_PATH = "/demand/outturn"
BRONZE_PREFIX = "bronze/demand"  # under the project data bucket


def fetch_demand_outturn(date_from: dt.date, date_to: dt.date) -> dict:
    """Fetch INDO half-hourly demand outturn for [date_from, date_to] inclusive.

    Returns the parsed JSON payload as-is (do not reshape here).

    TODO:
      - build the request URL + params (settlementDateFrom/To as YYYY-MM-DD, format=json)
      - GET it; set a sensible timeout
      - raise_for_status() so HTTP errors surface loudly (don't silently land garbage)
      - return response.json()
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

    TODO — decide what 'obviously broken' looks like and assert it, e.g.:
      - payload has the expected top-level shape (a 'data' array?)
      - the array isn't empty
      - each record has the fields we depend on (settlementDate, settlementPeriod, the value)
    Think: what should happen when validation fails? (that's the Phase 2 explain-back)
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

    TODO: return a path like f"{BRONZE_PREFIX}/date={settlement_date:...}/demand.json"
          (pick the partition format — remember how Athena/Glue expect partitions).
    """
    ...


def write_bronze(payload: dict, key: str) -> None:
    """Persist the raw payload to Bronze at `key`.

    TODO:
      - local dev: write to a local file mirroring the key (fast iteration)
      - later: swap for boto3 put_object to the data bucket (SSE on, private)
      - json.dumps the payload; this is the raw landing copy
    """
    ...


def main() -> None:
    """Local entry point: pull a date range and land it. Lambda handler comes later.

    TODO: choose the date range (for backfill vs. the daily incremental pull),
          then fetch -> validate -> for each settlement date, write_bronze(...).
    """
    ...


if __name__ == "__main__":
    main()

payload = fetch_demand_outturn(dt.date(2026,6,1), dt.date(2026,6,1))
print(validate(payload))
