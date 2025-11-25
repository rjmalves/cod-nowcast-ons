from .base import StorageBackend
from .local import LocalBackend
from .s3 import S3Backend


class StorageFactory:
    """Factory for creating appropriate storage backend."""

    _local_backend: LocalBackend | None = None
    _s3_backend: S3Backend | None = None

    @classmethod
    def get_storage(cls, path: str) -> StorageBackend:
        """
        Get appropriate storage backend based on path.

        Args:
            path: File path or S3 URI (s3://bucket/key)

        Returns:
            StorageBackend instance (LocalBackend or S3Backend)

        Examples:
            >>> storage = StorageFactory.get_storage("data/input")
            >>> isinstance(storage, LocalBackend)
            True

            >>> storage = StorageFactory.get_storage("s3://my-bucket/data")
            >>> isinstance(storage, S3Backend)
            True
        """
        if path.startswith("s3://"):
            if cls._s3_backend is None:
                cls._s3_backend = S3Backend()
            return cls._s3_backend
        else:
            if cls._local_backend is None:
                cls._local_backend = LocalBackend()
            return cls._local_backend

    @classmethod
    def clear_cache(cls):
        """Clear cached backend instances (useful for testing)."""
        cls._local_backend = None
        cls._s3_backend = None
