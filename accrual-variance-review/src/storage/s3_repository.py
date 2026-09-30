"""S3 repository: source-file/object layer. Atlas never stores raw files.

S3_BACKEND=local stores objects under a local directory and exists ONLY for
unit tests / offline development (non-production).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from src.config import Settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class S3Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = settings.s3_backend
        if self.backend == "local":
            self.root = Path(settings.local_s3_root) / (settings.s3_bucket or "demo-bucket")
        else:
            import boto3
            self.client = boto3.client("s3", region_name=settings.aws_region)
            self.bucket = settings.s3_bucket

    # --- helpers ------------------------------------------------------------
    def _full_key(self, key: str) -> str:
        """All demo objects live under the configured demo prefix."""
        return f"{self.settings.s3_prefix}{key}"

    def _path(self, full_key: str) -> Path:
        return self.root / full_key

    # --- operations -----------------------------------------------------------
    def put(self, key: str, data: bytes) -> str:
        full = self._full_key(key)
        if self.backend == "local":
            p = self._path(full)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        else:
            self.client.put_object(Bucket=self.bucket, Key=full, Body=data)
        return self.uri(full)

    def get(self, key: str) -> bytes:
        full = self._full_key(key)
        if self.backend == "local":
            return self._path(full).read_bytes()
        return self.client.get_object(Bucket=self.bucket, Key=full)["Body"].read()

    def exists(self, key: str) -> bool:
        full = self._full_key(key)
        if self.backend == "local":
            return self._path(full).exists()
        try:
            self.client.head_object(Bucket=self.bucket, Key=full)
            return True
        except Exception:
            return False

    def hash(self, key: str) -> str:
        return sha256_bytes(self.get(key))

    def list_keys(self, subprefix: str = "") -> list[str]:
        full = self._full_key(subprefix)
        if self.backend == "local":
            base = self._path(full)
            if not base.exists():
                return []
            return [str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file()]
        keys, token = [], None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": full}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return keys

    def delete_prefix(self, subprefix: str = "") -> int:
        """Delete only objects under the demo prefix (+ subprefix)."""
        if self.settings.s3_prefix not in ("", None) or self.backend == "local":
            pass  # prefix guard below enforces scoping
        keys = [k for k in self.list_keys(subprefix)
                if k.startswith(self.settings.s3_prefix)]
        if self.backend == "local":
            for k in keys:
                self._path(k).unlink(missing_ok=True)
        else:
            for k in keys:
                self.client.delete_object(Bucket=self.bucket, Key=k)
        return len(keys)

    def uri(self, full_key: str) -> str:
        if self.backend == "local":
            bucket = self.settings.s3_bucket or "demo-bucket"
        else:
            bucket = self.bucket
        return f"s3://{bucket}/{full_key}"

    def health(self) -> bool:
        if self.backend == "local":
            self.root.mkdir(parents=True, exist_ok=True)
            return True
        self.client.head_bucket(Bucket=self.bucket)
        return True
