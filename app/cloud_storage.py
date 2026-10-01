from cloudflare_s3 import s3, BUCKET
import os
import uuid

def upload_to_cloud(file_path: str, key_prefix: str, content_type: str = "application/octet-stream"):
    filename = os.path.basename(file_path)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    key = f"{key_prefix}{uuid.uuid4().hex}.{ext}"
    s3.upload_file(
        file_path,
        BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=3600,
    )
    return {
        "key": key,
        "url": url
    }

def get_file_url(key: str):
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=3600,
    )
    return { "url": url }

def download_file(key: str, local_path: str):
    s3.download_file(BUCKET, key, local_path)

def delete_file(key: str):
    s3.delete_object(Bucket=BUCKET, Key=key)