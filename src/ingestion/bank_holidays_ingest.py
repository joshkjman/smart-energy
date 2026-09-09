import requests
import json

from ingestion.bronze_io import write_bronze

BANK_HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"
BRONZE_PREFIX = "bronze/bank_holidays"
DIVISION = "england-and-wales"


def fetch_bank_holidays() -> dict:
    """GET the GOV.UK bank-holidays feed and return the parsed JSON as-is.
    """
    response = requests.get(BANK_HOLIDAYS_URL)
    return response.json()
    


def validate(payload: dict) -> None:
    """Tripwire before landing. Raise on anything unusable.
    """
    ew_payload = payload['england-and-wales']

    if 'division' not in ew_payload.keys():
        raise ValueError('Division key is not in payload')
    
    if len(ew_payload['events']) == 0:
        raise ValueError('Events list is empty')
    
    for event in ew_payload['events']:
        for check in ('title', 'date'):
            if check not in event.keys():
                raise ValueError(f'{check} missing from event: {event}')


def bronze_key() -> str:
    """Deterministic Bronze key for the holidays table.
    """
    return f"{BRONZE_PREFIX}/bank_holidays.json"


def main() -> None:
    """Entry point: fetch -> validate -> land the raw payload.
    """
    payload = fetch_bank_holidays()
    validate(payload)
    key = bronze_key()
    write_bronze(key, json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
