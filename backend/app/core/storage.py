"""
Storage abstraction: S3-compatible (MinIO) + local filesystem fallback.
"""
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
from ..config import settings

try:
    import boto3
    from botocore.client import Config as BotoConfig
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

class StorageService:
    def __init__(self):
        self.local_path = Path(settings.LOCAL_STORAGE_PATH)
        self.local_path.mkdir(parents=True, exist_ok=True)
        self.use_s3 = False
        self.s3_client = None
        if HAS_BOTO and settings.S3_ENDPOINT:
            try:
                # Only use S3 if endpoint reachable and bucket configured
                # For sandbox, we fallback to local if S3 not reachable
                # Check if we should use S3: env var USE_S3=true or S3 endpoint contains minio and we are not in sandbox without docker
                # For simplicity, use S3 if S3_ACCESS_KEY != "" and we can attempt connection
                # In sandbox, S3 will fail, so we catch and fallback
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=settings.S3_ENDPOINT,
                    aws_access_key_id=settings.S3_ACCESS_KEY,
                    aws_secret_access_key=settings.S3_SECRET_KEY,
                    region_name=settings.S3_REGION,
                    config=BotoConfig(signature_version='s3v4'),
                    use_ssl=settings.S3_USE_SSL
                )
                # Test list buckets (may fail)
                # We don't fail init, just set use_s3 True and handle errors per op
                self.use_s3 = True
            except Exception:
                self.use_s3 = False

    def _local_file_path(self, key: str) -> Path:
        # Sanitize key: remove leading slash, prevent traversal
        safe_key = key.lstrip("/").replace("..", "")
        return self.local_path / safe_key

    def generate_key(self, prefix: str, extension: str = "") -> str:
        uid = str(uuid.uuid4())
        ext = f".{extension.lstrip('.')}" if extension else ""
        return f"{prefix.rstrip('/')}/{uid}{ext}"

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        if self.use_s3 and self.s3_client:
            try:
                self.s3_client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=content_type)
                return
            except Exception as e:
                # Fallback to local on failure
                print(f"S3 put failed {e}, falling back to local")
                self.use_s3 = False
        # Local fallback
        path = self._local_file_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        if self.use_s3 and self.s3_client:
            try:
                resp = self.s3_client.get_object(Bucket=settings.S3_BUCKET, Key=key)
                return resp['Body'].read()
            except Exception:
                pass
        path = self._local_file_path(key)
        if not path.exists():
            raise FileNotFoundError(f"key {key} not found")
        return path.read_bytes()

    def put_file(self, key: str, file_path: str, content_type: str = "application/octet-stream"):
        if self.use_s3 and self.s3_client:
            try:
                self.s3_client.upload_file(file_path, settings.S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
                return
            except Exception as e:
                print(f"S3 upload failed {e}, fallback local")
                self.use_s3 = False
        dest = self._local_file_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

    def get_file(self, key: str, dest_path: str):
        if self.use_s3 and self.s3_client:
            try:
                self.s3_client.download_file(settings.S3_BUCKET, key, dest_path)
                return
            except Exception:
                pass
        src = self._local_file_path(key)
        if not src.exists():
            raise FileNotFoundError(f"key {key} not found")
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_path)

    def exists(self, key: str) -> bool:
        if self.use_s3 and self.s3_client:
            try:
                self.s3_client.head_object(Bucket=settings.S3_BUCKET, Key=key)
                return True
            except Exception:
                pass
        return self._local_file_path(key).exists()

    def delete(self, key: str):
        if self.use_s3 and self.s3_client:
            try:
                self.s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
            except Exception:
                pass
        path = self._local_file_path(key)
        if path.exists():
            path.unlink()

    def generate_presigned_url(self, key: str, expiry_sec: int = 900) -> str:
        if self.use_s3 and self.s3_client:
            try:
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': settings.S3_BUCKET, 'Key': key},
                    ExpiresIn=expiry_sec
                )
                return url
            except Exception:
                pass
        # For local fallback, return a local API URL that serves file via backend
        # This will be handled by backend endpoint /api/v1/storage/{key}
        # For now return a placeholder that indicates local path
        return f"/api/v1/internal-storage/{key}"

    def get_size(self, key: str) -> int:
        if self.use_s3 and self.s3_client:
            try:
                resp = self.s3_client.head_object(Bucket=settings.S3_BUCKET, Key=key)
                return resp['ContentLength']
            except Exception:
                pass
        path = self._local_file_path(key)
        if path.exists():
            return path.stat().st_size
        raise FileNotFoundError(key)

storage_service = StorageService()
