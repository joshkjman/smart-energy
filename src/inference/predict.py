"""Batch inference: predict demand across the currently-issued forecast horizon.

Runs daily after weather and demand have landed. Loads the newest published model,
reads the rows whose prediction time has already passed, predicts, and lands one
file per issue date.
"""
import datetime as dt, json, os
import boto3
import lightgbm as lgb
import pandas as pd
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor

BUCKET          = os.environ['BRONZE_BUCKET']
MODEL_PREFIX    = "models/demand_lgbm"
FORECAST_PREFIX = "bronze/inference_forecasts"
WORK_GROUP      = "foresight_queries" 
REGION          = "eu-west-2"

# How old the issue we're serving may be before we refuse to write.
#
# fct_demand_serving now anchors on max(issue_ts) rather than current_date, so
# it can no longer come back empty -- which means a stale dbt build would stop
# raising and start silently rewriting an old partition instead. Nothing would
# advance, every state would report SUCCESS. The age check is what keeps that
# failure loud.
#
# issue_ts is midnight-stamped and the chain fires at 22:10 UTC, so a healthy
# run sees an issue ~22h old and a run that missed a whole day sees ~46h. 36h
# sits between the two: it tolerates a late retry or a post-midnight manual
# invoke (~24h) and rejects a missed day.
MAX_ISSUE_AGE_HOURS = 36

s3 = boto3.client('s3')


def latest_model_version() -> str:
    """Newest version directory under MODEL_PREFIX.

    Versions are UTC ISO timestamps, so lexicographic max == chronological newest.
    """
    common_prefixes = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{MODEL_PREFIX}/", Delimiter="/")
    prefixes = common_prefixes.get('CommonPrefixes', [])

    versions = [prefix['Prefix'].split('/')[-2] for prefix in prefixes]

    if len(versions) == 0:
        raise ValueError(f"Empty list. Couldn't find anything from {MODEL_PREFIX}")

    latest_version = max(versions)
    return latest_version



def load_model(version: str) -> tuple[lgb.Booster, dict]:
    """Fetch that version's model.txt and rebuild the Booster."""
    obj = s3.get_object(Bucket=BUCKET, Key=f"{MODEL_PREFIX}/{version}/model.txt")
    obj_str = obj['Body'].read().decode('utf-8')
    booster = lgb.Booster(model_str=obj_str)

    obj_metadata = s3.get_object(Bucket=BUCKET, Key=f"{MODEL_PREFIX}/{version}/metadata.json")
    obj_metadata_str = obj_metadata['Body'].read().decode('utf-8')
    metadata = json.loads(obj_metadata_str)

    return booster, metadata


def load_serving_rows(categorical_features: list[str]) -> pd.DataFrame:
    """Read gold.fct_demand_serving and apply the model's categorical dtypes."""
    con = connect(
        s3_staging_dir=f"s3://{BUCKET}/athena-results/",
        region_name=REGION,
        schema_name="gold",
        work_group=WORK_GROUP,
        cursor_class=PandasCursor,
    )
    df = con.cursor().execute(
        """
        select *
        from gold.fct_demand_serving
        """
    ).as_pandas()
    con.close()
    df[categorical_features] = df[categorical_features].astype("category")

    return df


def build_forecast_records(df: pd.DataFrame, booster: lgb.Booster, version: str) -> pd.DataFrame:
    """One record per (target_ts, lead_days), carrying the model that made it."""
    output = df[["target_ts", "issue_ts", "lead_days"]].copy()
    output["target_ts"] = output["target_ts"].dt.tz_localize("UTC")
    output["issue_ts"]  = output["issue_ts"].dt.tz_localize("UTC")

    output["predicted_mw"]  = booster.predict(df[booster.feature_name()])
    output["model_version"] = version

    return output


def assert_issue_is_fresh(issue_ts: pd.Timestamp) -> None:
    """Refuse to write if the issue we'd be serving is too old to be tonight's.

    Raises so the Step Functions state fails visibly rather than re-landing a
    partition that is already there.
    """
    age = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - issue_ts.to_pydatetime()
    if age > dt.timedelta(hours=MAX_ISSUE_AGE_HOURS):
        raise ValueError(
            f"Stale serving data: newest issue_ts is {issue_ts} "
            f"({age.total_seconds() / 3600:.1f}h old, limit {MAX_ISSUE_AGE_HOURS}h). "
            "dbt has not rebuilt int_demand_feature_rows, or weather/demand ingestion is behind. "
            "Writing anyway would overwrite an existing partition and advance nothing."
        )


def handler(event, context):
    version = latest_model_version()
    booster, metadata = load_model(version)
    df = load_serving_rows(metadata["categorical_features"])
    if df.empty:
        raise ValueError(
            "fct_demand_serving is returning no rows. int_demand_feature_rows is empty, "
            "or every row is still ahead of its cutoff."
        )

    issue_ts = df["issue_ts"].max()
    assert_issue_is_fresh(issue_ts)

    output = build_forecast_records(df, booster, version)
    issue_date = issue_ts.date()
    body = '{"data":' + output.to_json(orient="records", date_format="iso") + '}'

    key = f"{FORECAST_PREFIX}/issue_date={issue_date}/forecasts.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode('utf-8'),
        ContentType='application/json'
    )