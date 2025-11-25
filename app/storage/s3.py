import re

import boto3
import pandas as pd
import polars as pl
import s3fs  # type: ignore
from botocore.exceptions import ClientError

from .base import StorageBackend


class S3Backend(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(self):
        """Initialize S3 client and filesystem."""
        self.s3_client = boto3.client("s3")
        self.s3fs = s3fs.S3FileSystem()

    def _parse_s3_uri(self, path: str) -> tuple[str, str]:
        """Parse s3://bucket/key into (bucket, key)."""
        match = re.match(r"s3://([^/]+)/(.*)", path)
        if not match:
            raise ValueError(f"Invalid S3 URI: {path}")
        return match.group(1), match.group(2)

    def read_parquet(self, path: str, **kwargs) -> pl.LazyFrame:
        """Read Parquet from S3 using Polars with s3fs."""
        return pl.scan_parquet(
            path,
            **kwargs,
        )

    def write_parquet(self, df: pd.DataFrame, path: str, **kwargs) -> None:
        """Write Parquet to S3 using Pandas with s3fs."""
        with self.s3fs.open(path, "wb") as f:
            df.to_parquet(f, **kwargs)

    def read_bytes(self, path: str) -> bytes:
        """Read file from S3 as bytes."""
        bucket, key = self._parse_s3_uri(path)
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def write_bytes(self, data: bytes, path: str) -> None:
        """Write bytes to S3."""
        bucket, key = self._parse_s3_uri(path)
        self.s3_client.put_object(Bucket=bucket, Key=key, Body=data)

    def exists(self, path: str) -> bool:
        """Check if S3 object exists."""
        bucket, key = self._parse_s3_uri(path)
        try:
            self.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """S3 doesn't need directory creation (flat namespace)."""
        pass

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List S3 objects matching pattern."""
        bucket, prefix = self._parse_s3_uri(path)

        if pattern != "*":
            prefix = f"{prefix.rstrip('/')}/{pattern.replace('*', '')}"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=bucket, Prefix=prefix
            )
            if "Contents" not in response:
                return []

            return [
                f"s3://{bucket}/{obj['Key']}" for obj in response["Contents"]
            ]
        except ClientError:
            return []

    def delete(self, path: str) -> None:
        """Delete S3 object."""
        bucket, key = self._parse_s3_uri(path)
        self.s3_client.delete_object(Bucket=bucket, Key=key)

    def join_path(self, *parts: str) -> str:
        """Join S3 path components."""
        clean_parts = []
        for i, part in enumerate(parts):
            if i == 0 and part.startswith("s3://"):
                clean_parts.append(part)
            else:
                clean_parts.append(part.lstrip("/"))

        if clean_parts[0].startswith("s3://"):
            bucket_and_prefix = clean_parts[0]
            remaining = "/".join(clean_parts[1:])
            return f"{bucket_and_prefix.rstrip('/')}/{remaining}"
        else:
            return "/".join(clean_parts)

    def get_uri(self, path: str) -> str:
        """Get full S3 URI."""
        return path if path.startswith("s3://") else f"s3://{path}"
