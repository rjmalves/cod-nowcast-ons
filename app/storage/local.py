import os
from pathlib import Path

import pandas as pd
import polars as pl

from .base import StorageBackend


class LocalBackend(StorageBackend):
    """Local filesystem storage backend."""

    def read_parquet(self, path: str, **kwargs) -> pl.LazyFrame:
        """Read Parquet from local filesystem using Polars."""
        return pl.scan_parquet(path, **kwargs)

    def write_parquet(self, df: pd.DataFrame, path: str, **kwargs) -> None:
        """Write Parquet to local filesystem using Pandas."""
        df.to_parquet(path, **kwargs)

    def read_bytes(self, path: str) -> bytes:
        """Read file as bytes."""
        with open(path, "rb") as f:
            return f.read()

    def write_bytes(self, data: bytes, path: str) -> None:
        """Write bytes to file."""
        self.makedirs(str(Path(path).parent))
        with open(path, "wb") as f:
            f.write(data)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directory."""
        os.makedirs(path, exist_ok=exist_ok)

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List files matching pattern."""
        path_obj = Path(path)
        if not path_obj.exists():
            return []
        return [str(p) for p in path_obj.glob(pattern)]

    def delete(self, path: str) -> None:
        """Delete file."""
        Path(path).unlink(missing_ok=True)

    def join_path(self, *parts: str) -> str:
        """Join path components."""
        return os.path.join(*parts)

    def get_uri(self, path: str) -> str:
        """Get absolute path."""
        return str(Path(path).absolute())
