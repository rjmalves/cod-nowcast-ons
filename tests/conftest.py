import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest
import shapefile
import xarray as xr

from cod_nowcast_ons._config import Subgrid
from tests.fixtures.goes_cod.materialize import (
    FRAMES_PREFIX,
    SOURCE,
    materialize,
)

_WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)
_POINTS: list[tuple[float, float]] = [
    (-50.0, -23.0),
    (-47.0, -23.0),
    (-47.0, -20.0),
    (-50.0, -20.0),
    (-50.0, -23.0),
]


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Folder of the frames materialized from the committed text source.

    The frames are written under the gold layout, so the returned
    ``goes_processed`` folder is the one that the frame reader reads.
    """
    root = tmp_path / "frames"
    root.mkdir()
    materialize(SOURCE, root)
    return root / FRAMES_PREFIX


@pytest.fixture(scope="session")
def generated_shapefile(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the one-polygon test shapefile once per session.

    Returns the path of the generated ``test_shapes.shp``.
    """
    base = tmp_path_factory.mktemp("shapefile") / "test_shapes"
    w = shapefile.Writer(str(base), shapeType=shapefile.POLYGON)
    w.field("name", "C", size=50)
    w.poly([_POINTS])
    w.record("TestRegion")
    w.close()
    base.with_suffix(".prj").write_text(_WGS84_PRJ, encoding="ascii")
    return base.with_suffix(".shp")


@pytest.fixture
def test_shapefile_path(generated_shapefile: Path) -> Path:
    """Path to test shapefile for plotting tests."""
    return generated_shapefile


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_subgrid_config() -> Subgrid:
    """Sample subgrid configuration for testing."""
    return Subgrid(
        name="test_region",
        lat=(-23.0, -20.0),
        lon=(-50.0, -47.0),
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

    # Convert to xarray (this is how the frame reader does it)
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


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the switch that rewrites the regression golden."""
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite tests/regression/golden/cod_regression.json and fail",
    )


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
