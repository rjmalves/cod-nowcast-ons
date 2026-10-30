import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest
import xarray as xr

from app.internal.config import Config, PostprocessingConfig, SubgridConfig


@pytest.fixture
def test_data_dir() -> Path:
    """Path to test fixture data directory."""
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture
def test_shapefile_path() -> Path:
    """Path to test shapefile for plotting tests."""
    return (
        Path(__file__).parent
        / "fixtures"
        / "data"
        / "shapes"
        / "test_shapes.shp"
    )


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_subgrid_config() -> SubgridConfig:
    """Sample subgrid configuration for testing."""
    return SubgridConfig(
        name="test_region",
        lat=[-23.0, -20.0],
        lon=[-50.0, -47.0],
    )


@pytest.fixture
def sample_config(test_data_dir: Path, temp_output_dir: Path) -> Config:
    """Sample configuration for testing."""
    return Config(
        mode="inference",
        input=str(test_data_dir),
        output=str(temp_output_dir),
        base_datetime=datetime(2024, 8, 1, 0, 50),
        num_past_samples=6,
        num_future_samples=3,
        subgrids=[
            SubgridConfig(
                name="SE",
                lat=[-23.0, -20.0],
                lon=[-50.0, -47.0],
            )
        ],
        postprocessing=PostprocessingConfig(plots=False, shapefile_path=None),
    )


@pytest.fixture
def sample_cod_dataarray() -> xr.DataArray:
    """
    Create a small synthetic COD DataArray for testing.

    Returns 6 time steps of 10x10 grid with realistic COD values.
    Matches the data structure from real GOES COD parquet files
    by going through the polars -> pandas -> xarray path.
    """
    np.random.seed(42)

    # Create times without timezone (like real data after pandas conversion)
    times_pd = pd.date_range("2024-08-01 00:00", periods=6, freq="10min")
    lats = np.linspace(-23.0, -20.0, 10)
    lons = np.linspace(-50.0, -47.0, 10)

    # Generate realistic COD pattern
    # Use gamma distribution which is common for cloud properties
    data = np.random.gamma(2, 2, size=(6, 10, 10))

    # Add some spatial structure (clouds have coherent patterns)
    from scipy.ndimage import gaussian_filter

    for t in range(6):
        data[t] = gaussian_filter(data[t], sigma=1.5)

    # Add temporal evolution (clouds move)
    for t in range(1, 6):
        # Slight shift to simulate cloud motion
        data[t] = np.roll(data[t], shift=1, axis=1)

    # Create via pandas DataFrame to match real flow
    # Create multi-index dataframe like real data
    time_grid, lat_grid, lon_grid = np.meshgrid(
        times_pd, lats, lons, indexing="ij"
    )
    df = pd.DataFrame(
        {"cod": data.ravel()},
        index=pd.MultiIndex.from_arrays(
            [time_grid.ravel(), lat_grid.ravel(), lon_grid.ravel()],
            names=["time", "latitude", "longitude"],
        ),
    )

    # Convert to xarray (this is how app does it)
    return df.to_xarray()["cod"]


@pytest.fixture
def sample_motion_field() -> np.ndarray:
    """Sample motion field (U, V components) for testing."""
    # Create 2x10x10 array (U and V components)
    np.random.seed(42)
    motion = np.random.randn(2, 10, 10) * 0.5
    return motion


@pytest.fixture
def sample_parquet_data() -> pl.DataFrame:
    """Create a small synthetic parquet-compatible dataframe."""
    np.random.seed(42)

    # Create grid
    n_lat, n_lon = 10, 10
    lats = np.linspace(-23.0, -20.0, n_lat)
    lons = np.linspace(-50.0, -47.0, n_lon)

    # Meshgrid
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

    # Flatten
    lat_flat = lat_grid.flatten()
    lon_flat = lon_grid.flatten()

    # Generate COD values
    cod_flat = np.random.gamma(2, 2, size=len(lat_flat)).astype(np.float32)

    # Create timestamp
    timestamp = datetime(2024, 8, 1, 0, 0)

    return pl.DataFrame(
        {
            "time": [timestamp] * len(lat_flat),
            "latitude": lat_flat,
            "longitude": lon_flat,
            "cod": cod_flat,
        }
    )


@pytest.fixture
def mock_s3_bucket() -> Generator[str, None, None]:
    """
    Create a mock S3 bucket using moto.

    Yields:
        str: Bucket name for testing

    Note:
        This requires moto to be installed: pip install moto[s3]
        Tests using this fixture should be marked with @pytest.mark.s3
    """
    try:
        import boto3
        from moto import mock_aws
    except ImportError:
        pytest.skip("moto not installed - skipping S3 tests")

    # Start mock and keep it active during the test
    mock = mock_aws()
    mock.start()

    try:
        # Create mock S3 client
        s3_client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )

        # Create test bucket
        bucket_name = "test-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        yield bucket_name
    finally:
        mock.stop()


# Markers for different test categories
def pytest_configure(config: pytest.Config) -> None:
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for full pipeline"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take a long time to run"
    )
    config.addinivalue_line(
        "markers", "s3: Tests that require S3/moto (AWS simulation)"
    )
    config.addinivalue_line(
        "markers", "plotting: Tests that generate plots (skip on CI if needed)"
    )
