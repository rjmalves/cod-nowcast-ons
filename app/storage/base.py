from abc import ABC, abstractmethod

import pandas as pd
import polars as pl


class StorageBackend(ABC):
    """Abstract interface for storage operations."""

    @abstractmethod
    def read_parquet(self, path: str, **kwargs) -> pl.LazyFrame:
        """Read Parquet file and return Polars LazyFrame."""
        pass

    @abstractmethod
    def write_parquet(self, df: pd.DataFrame, path: str, **kwargs) -> None:
        """Write Pandas DataFrame to Parquet."""
        pass

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read file as bytes."""
        pass

    @abstractmethod
    def write_bytes(self, data: bytes, path: str) -> None:
        """Write bytes to file."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directory (or S3 prefix)."""
        pass

    @abstractmethod
    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List files matching pattern."""
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete file or directory."""
        pass

    @abstractmethod
    def join_path(self, *parts: str) -> str:
        """Join path components (OS-aware or S3-aware)."""
        pass

    @abstractmethod
    def get_uri(self, path: str) -> str:
        """Get full URI for the path."""
        pass
