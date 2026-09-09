import boto3
import os


s3 = boto3.client('s3')
BRONZE_BUCKET = os.environ['BRONZE_BUCKET']

def write_bronze(key: str, body: str) -> None:
    """Write an already-serialized JSON body to Bronze at `key`.
    """
    s3.put_object(
        Bucket=BRONZE_BUCKET,
        Key=key,
        Body=body.encode('utf-8'),
        ContentType='application/json'
    )
