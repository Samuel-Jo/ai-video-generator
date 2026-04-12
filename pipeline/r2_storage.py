"""
Cloudflare R2 storage helper (S3-compatible via boto3)
"""
import os
import boto3
from botocore.config import Config
from pathlib import Path

ACCOUNT_ID  = os.getenv("CF_ACCOUNT_ID", "54c94df856ee25ab1799026177ed07f1")
ACCESS_KEY  = os.getenv("R2_ACCESS_KEY_ID", "")
SECRET_KEY  = os.getenv("R2_SECRET_ACCESS_KEY", "")
BUCKET_NAME = os.getenv("R2_BUCKET", os.getenv("R2_BUCKET_NAME", "aivideo"))
ENDPOINT    = os.getenv("R2_ENDPOINT", f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com")
PUBLIC_URL  = os.getenv("R2_PUBLIC_URL", "")   # optional: custom public domain

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def upload_video(local_path: Path, key: str) -> str:
    """Upload file to R2. Returns presigned download URL (1 hour)."""
    client = _get_client()
    client.upload_file(
        str(local_path),
        BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    if PUBLIC_URL:
        return f"{PUBLIC_URL.rstrip('/')}/{key}"
    # Generate presigned URL valid for 3 hours
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=10800,
    )
    return url


def is_configured() -> bool:
    return bool(ACCOUNT_ID and ACCESS_KEY and SECRET_KEY)
