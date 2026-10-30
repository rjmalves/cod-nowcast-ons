from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import xarray as xr

from app.internal.config import SubgridConfig
from app.readers import InputData, SubgridInputData


class TestSubgridInputData:
    """Test SubgridInputData dataclass."""

    def test_goes_input_filename(self) -> None:
        """Test GOES filename generation."""
        time1 = datetime(2024, 8, 1, 10, 30)
        filename1 = SubgridInputData.goes_input_filename(time1)
        assert filename1 == "GOES_COD_BR_20240801-1030.parquet"

        time2 = datetime(2024, 12, 31, 23, 59)
        filename2 = SubgridInputData.goes_input_filename(time2)
        assert filename2 == "GOES_COD_BR_20241231-2359.parquet"

    @pytest.mark.integration
    def test_from_parquet_local(
        self, test_data_dir: Path, sample_subgrid_config: SubgridConfig
    ) -> None:
        """Test loading data from local parquet file."""
        # Use test fixture data
        time = datetime(2024, 8, 1, 0, 0)

        # Get test file path
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if not test_files:
            pytest.skip("Test data not available")

        # Rename for test (temporarily)
        import shutil

        expected_name = SubgridInputData.goes_input_filename(time)
        expected_path = test_data_dir / expected_name

        # Copy with expected name if needed
        if not expected_path.exists() and test_files:
            shutil.copy(test_files[0], expected_path)

        try:
            data = SubgridInputData.from_parquet(
                sample_subgrid_config, time, str(test_data_dir)
            )

            assert data.name == sample_subgrid_config.name
            assert data.latitude_range == sample_subgrid_config.lat
            assert data.longitude_range == sample_subgrid_config.lon
            assert data.time == time
            assert isinstance(data.cod, pl.DataFrame)
            assert "latitude" in data.cod.columns
            assert "longitude" in data.cod.columns
            assert "cod" in data.cod.columns
            assert "time" in data.cod.columns
        finally:
            # Cleanup
            if expected_path.exists() and expected_path != test_files[0]:
                expected_path.unlink()

    def test_from_parquet_filters_by_subgrid(
        self, tmp_path: Path, sample_subgrid_config: SubgridConfig
    ) -> None:
        """Test that data is filtered by subgrid bounds."""
        # Create test parquet with data outside and inside bounds
        test_data = pl.DataFrame(
            {
                "latitude": [-25.0, -22.0, -19.0],
                "longitude": [-51.0, -49.0, -48.0],
                "cod": [1.0, 2.0, 3.0],
                "time": [datetime(2024, 8, 1)] * 3,
            }
        )

        test_file = tmp_path / SubgridInputData.goes_input_filename(
            datetime(2024, 8, 1)
        )
        test_data.write_parquet(test_file)

        data = SubgridInputData.from_parquet(
            sample_subgrid_config, datetime(2024, 8, 1), str(tmp_path)
        )

        assert len(data.cod) == 1
        assert all(
            (data.cod["latitude"] >= -23.0) & (data.cod["latitude"] <= -18.0)
        )
        assert all(
            (data.cod["longitude"] >= -50.0) & (data.cod["longitude"] <= -47.0)
        )


class TestInputData:
    """Test InputData reader."""

    def test_initialization(self) -> None:
        """Test InputData initialization."""
        reader = InputData("data/input")
        assert reader.path == "data/input"

    def test_index_cols(self) -> None:
        """Test INDEX_COLS constant."""
        assert InputData.INDEX_COLS == ["time", "latitude", "longitude"]

    def test_for_subgrid_returns_xarray(
        self, sample_cod_dataarray: xr.DataArray, tmp_path: Path
    ) -> None:
        """Test that for_subgrid returns xarray DataArray."""
        # Create test parquet files
        subgrid = SubgridConfig(
            name="test", lat=[-23.0, -20.0], lon=[-50.0, -47.0]
        )
        base_time = datetime(2024, 8, 1, 1, 0)

        # Create 6 past time steps
        for i in range(6):
            time = base_time - timedelta(minutes=10 * (6 - i))

            # Generate small test data
            lats = np.linspace(-23.0, -20.0, 5)
            lons = np.linspace(-50.0, -47.0, 5)
            lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

            df = pl.DataFrame(
                {
                    "latitude": lat_grid.flatten(),
                    "longitude": lon_grid.flatten(),
                    "cod": np.random.gamma(2, 2, size=25).astype(np.float32),
                    "time": [time] * 25,
                }
            )

            filename = SubgridInputData.goes_input_filename(time)
            df.write_parquet(tmp_path / filename)

        # Test
        reader = InputData(str(tmp_path))
        result = reader.for_subgrid(subgrid, 6, base_time)

        assert isinstance(result, xr.DataArray)
        assert "time" in result.dims
        assert "latitude" in result.dims
        assert "longitude" in result.dims
        assert result.name == "cod"
        assert result.time.size == 6

    @pytest.mark.integration
    def test_for_subgrid_with_test_data(
        self, test_data_dir: Path, sample_subgrid_config: SubgridConfig
    ) -> None:
        """Test for_subgrid with actual test fixture data."""
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if len(test_files) < 5:
            pytest.skip("Need at least 5 test files")

        # Parse time from last file
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]  # 20240801-0050
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        reader = InputData(str(test_data_dir))
        result = reader.for_subgrid(sample_subgrid_config, 4, base_time)

        assert isinstance(result, xr.DataArray)
        assert result.time.size == 4

        # Check coordinates
        assert result.latitude.min() >= sample_subgrid_config.lat[0]
        assert result.latitude.max() <= sample_subgrid_config.lat[1]
        assert result.longitude.min() >= sample_subgrid_config.lon[0]
        assert result.longitude.max() <= sample_subgrid_config.lon[1]

    def test_for_subgrid_missing_file(self, tmp_path: Path) -> None:
        """Test that missing file raises appropriate error."""
        subgrid = SubgridConfig(
            name="test", lat=[-23.0, -20.0], lon=[-50.0, -47.0]
        )
        reader = InputData(str(tmp_path))
        base_time = datetime(2024, 8, 1, 1, 0)

        with pytest.raises(Exception) as _:  # FileNotFoundError or similar
            reader.for_subgrid(subgrid, 6, base_time)


@pytest.mark.unit
class TestReadersDataFlow:
    """Test data flow through readers."""

    def test_subgrid_data_has_time_column(self, tmp_path: Path) -> None:
        """Test that SubgridInputData adds time column."""
        subgrid = SubgridConfig(
            name="test", lat=[-23.0, -20.0], lon=[-50.0, -47.0]
        )
        time = datetime(2024, 8, 1, 0, 0)

        # Create minimal test file
        df = pl.DataFrame(
            {
                "latitude": [-22.0],
                "longitude": [-49.0],
                "cod": [5.0],
            }
        )

        filename = SubgridInputData.goes_input_filename(time)
        df.write_parquet(tmp_path / filename)

        data = SubgridInputData.from_parquet(subgrid, time, str(tmp_path))

        assert "time" in data.cod.columns
        assert data.cod["time"][0] == time

    def test_input_data_sorts_correctly(self, tmp_path: Path) -> None:
        """Test that InputData sorts by time, lat, lon."""
        subgrid = SubgridConfig(
            name="test", lat=[-23.0, -20.0], lon=[-50.0, -47.0]
        )
        base_time = datetime(2024, 8, 1, 1, 0)

        # Create files with deliberately unsorted data
        for i in range(3):
            time = base_time - timedelta(minutes=10 * (3 - i))

            # Unsorted coordinates
            df = pl.DataFrame(
                {
                    "latitude": [-21.0, -22.0, -20.5],
                    "longitude": [-48.0, -49.0, -48.5],
                    "cod": [1.0, 2.0, 3.0],
                }
            )

            filename = SubgridInputData.goes_input_filename(time)
            df.write_parquet(tmp_path / filename)

        reader = InputData(str(tmp_path))
        result = reader.for_subgrid(subgrid, 3, base_time)

        # Check that result is properly sorted
        # Times should be in order
        assert all(result.time[:-1] <= result.time[1:])
