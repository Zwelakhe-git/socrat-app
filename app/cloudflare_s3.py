import boto3
import os
from botocore.config import Config

ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
ACCESS_KEY = os.environ["R2_ACCESS_KEY"]
SECRET_KEY = os.environ["R2_SECRET_KEY"]
BUCKET     = "zvelakeremotestorage"

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="auto",
    config=Config(signature_version="s3v4"),
)