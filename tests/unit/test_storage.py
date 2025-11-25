from pathlib import Path

import pytest

from app.storage import LocalBackend, S3Backend, StorageFactory


class TestStorageFactory:
    """Test the storage factory pattern."""

    def test_get_local_storage(self):
        """Test that local paths return LocalBackend."""
        storage = StorageFactory.get_storage("data/input")
        assert isinstance(storage, LocalBackend)

    def test_get_s3_storage(self):
        """Test that S3 URIs return S3Backend."""
        storage = StorageFactory.get_storage("s3://bucket/path")
        assert isinstance(storage, S3Backend)

    def test_singleton_local(self):
        """Test that local backend is singleton."""
        storage1 = StorageFactory.get_storage("path1")
        storage2 = StorageFactory.get_storage("path2")
        assert storage1 is storage2

    def test_singleton_s3(self):
        """Test that S3 backend is singleton."""
        storage1 = StorageFactory.get_storage("s3://bucket1/path")
        storage2 = StorageFactory.get_storage("s3://bucket2/path")
        assert storage1 is storage2

    def test_clear_cache(self):
        """Test clearing cached backends."""
        storage1 = StorageFactory.get_storage("path")
        StorageFactory.clear_cache()
        storage2 = StorageFactory.get_storage("path")
        assert storage1 is not storage2


class TestLocalBackend:
    """Test local filesystem backend."""

    def test_join_path(self):
        """Test path joining."""
        storage = LocalBackend()
        path = storage.join_path("data", "input", "file.parquet")
        assert "data" in path
        assert "input" in path
        assert "file.parquet" in path

    def test_exists(self, tmp_path):
        """Test file existence check."""
        storage = LocalBackend()

        # Test non-existent file
        assert not storage.exists(str(tmp_path / "nonexistent.txt"))

        # Create file and test
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        assert storage.exists(str(test_file))

    def test_makedirs(self, tmp_path):
        """Test directory creation."""
        storage = LocalBackend()
        new_dir = tmp_path / "nested" / "directory"

        storage.makedirs(str(new_dir))
        assert new_dir.exists()

        # Test exist_ok
        storage.makedirs(str(new_dir), exist_ok=True)

    def test_write_read_bytes(self, tmp_path):
        """Test writing and reading bytes."""
        storage = LocalBackend()
        test_file = tmp_path / "test.bin"
        test_data = b"test data content"

        storage.write_bytes(test_data, str(test_file))
        assert test_file.exists()

        read_data = storage.read_bytes(str(test_file))
        assert read_data == test_data

    def test_delete(self, tmp_path):
        """Test file deletion."""
        storage = LocalBackend()
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        assert test_file.exists()
        storage.delete(str(test_file))
        assert not test_file.exists()

    def test_write_read_parquet(self, tmp_path, sample_parquet_data):
        """Test parquet I/O operations."""
        storage = LocalBackend()
        test_file = tmp_path / "test.parquet"

        # Convert to pandas for writing
        df_pd = sample_parquet_data.to_pandas()
        storage.write_parquet(df_pd, str(test_file))
        assert test_file.exists()

        # Read back using polars scan
        df_lazy = storage.read_parquet(str(test_file))
        df_read = df_lazy.collect()

        assert len(df_read) == len(sample_parquet_data)
        assert "latitude" in df_read.columns
        assert "longitude" in df_read.columns
        assert "cod" in df_read.columns

    def test_list_files(self, tmp_path):
        """Test listing files with pattern."""
        storage = LocalBackend()

        # Create test files
        (tmp_path / "file1.parquet").write_text("test")
        (tmp_path / "file2.parquet").write_text("test")
        (tmp_path / "file3.txt").write_text("test")

        # List parquet files
        files = storage.list_files(str(tmp_path), "*.parquet")
        assert len(files) == 2
        assert all("parquet" in f for f in files)

    def test_get_uri(self, tmp_path):
        """Test getting absolute URI."""
        storage = LocalBackend()
        uri = storage.get_uri(str(tmp_path / "test.txt"))
        assert Path(uri).is_absolute()


class TestS3Backend:
    """Test S3 storage backend."""

    def test_parse_s3_uri(self):
        """Test S3 URI parsing."""
        storage = S3Backend()
        bucket, key = storage._parse_s3_uri(
            "s3://my-bucket/path/to/file.parquet"
        )
        assert bucket == "my-bucket"
        assert key == "path/to/file.parquet"

    def test_parse_s3_uri_invalid(self):
        """Test that invalid URIs raise ValueError."""
        storage = S3Backend()
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            storage._parse_s3_uri("not-an-s3-uri")

    def test_join_path_s3(self):
        """Test S3 path joining."""
        storage = S3Backend()
        path = storage.join_path(
            "s3://bucket/prefix", "subfolder", "file.parquet"
        )
        assert path == "s3://bucket/prefix/subfolder/file.parquet"

    def test_join_path_no_prefix(self):
        """Test path joining without s3:// prefix."""
        storage = S3Backend()
        path = storage.join_path("bucket", "path", "file.parquet")
        assert "/" in path
        assert "bucket" in path

    def test_get_uri(self):
        """Test getting S3 URI."""
        storage = S3Backend()

        # With s3:// prefix
        uri1 = storage.get_uri("s3://bucket/key")
        assert uri1 == "s3://bucket/key"

        # Without prefix
        uri2 = storage.get_uri("bucket/key")
        assert uri2 == "s3://bucket/key"

    @pytest.mark.s3
    def test_s3_operations_with_moto(self, mock_s3_bucket):
        """Test S3 operations with mocked S3 (requires moto)."""
        storage = S3Backend()
        bucket = mock_s3_bucket

        # Test write/read bytes
        test_data = b"test content"
        test_key = f"s3://{bucket}/test/file.txt"

        storage.write_bytes(test_data, test_key)
        read_data = storage.read_bytes(test_key)
        assert read_data == test_data

        # Test exists
        assert storage.exists(test_key)
        assert not storage.exists(f"s3://{bucket}/nonexistent.txt")

        # Test delete
        storage.delete(test_key)
        assert not storage.exists(test_key)

    @pytest.mark.s3
    def test_s3_parquet_with_moto(self, mock_s3_bucket, sample_parquet_data):
        """Test S3 parquet operations with mocked S3."""
        storage = S3Backend()
        bucket = mock_s3_bucket
        test_key = f"s3://{bucket}/data/test.parquet"

        # Write parquet
        df_pd = sample_parquet_data.to_pandas()
        storage.write_parquet(df_pd, test_key)

        # Read parquet
        df_lazy = storage.read_parquet(test_key)
        df_read = df_lazy.collect()

        assert len(df_read) == len(sample_parquet_data)
        assert "cod" in df_read.columns


@pytest.mark.unit
class TestStorageIntegration:
    """Integration tests across storage backends."""

    def test_factory_returns_correct_backend(self):
        """Test factory pattern with both backend types."""
        local = StorageFactory.get_storage("/local/path")
        s3 = StorageFactory.get_storage("s3://bucket/path")

        assert type(local).__name__ == "LocalBackend"
        assert type(s3).__name__ == "S3Backend"
        assert local is not s3
