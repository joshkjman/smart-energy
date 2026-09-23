import datetime as dt, json
import boto3
import os
import lightgbm as lgb
from athena import get_athena_connection
from train import load_features, fit_model, FEATURES, PARAMS

BUCKET_NAME = os.environ['BRONZE_BUCKET']
MODEL_PREFIX = "models/demand_lgbm"
MIN_TRAINING_ROWS = 100_000        # refuse to publish a model fitted on too little


def publish(regressor, df, version: str) -> None:
    """Upload model.txt + metadata.json under MODEL_PREFIX/<version>/."""
    model_body = regressor.booster_.model_to_string()

    metadata = {
        "features": FEATURES,
        "params": PARAMS,
        "row count": df.shape[0],
        "max(target_ts)": df['target_ts'].max().isoformat(),
        "lightgbm version": lgb.__version__,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()
    }
    metadata_body = json.dumps(metadata)

    s3_client = boto3.client('s3')
    response = s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=f"{MODEL_PREFIX}/{version}/model.txt",
        Body=model_body.encode('utf-8'),
        ContentType='text/plain',
    )
    response_metadata = s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=f"{MODEL_PREFIX}/{version}/metadata.json",
        Body=metadata_body.encode('utf-8'),
        ContentType='application/json'
    )


def main() -> None:
    """Load -> sanity-check row count -> fit -> publish."""
    con = get_athena_connection()
    df = load_features(con)
    con.close()

    if len(df) < MIN_TRAINING_ROWS:
        raise ValueError(f"Only {len(df)} rows, expected >= {MIN_TRAINING_ROWS}")

    if df['target_ts'].max() < dt.datetime.today() - dt.timedelta(weeks=3):
        raise ValueError(f"Data (target_ts) is more than 3 weeks old")

    regressor = fit_model(df, FEATURES, PARAMS)
    publish(regressor, df, f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H%M%SZ}")


if __name__ == "__main__":
    main()