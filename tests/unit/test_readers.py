from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import xarray as xr
from nwp_core.contracts import registry
from nwp_core.errors import ObjectNotFoundError
from nwp_core.storage import Storage, StorageLocation, open_storage

from cod_nowcast_ons._config import Subgrid
from cod_nowcast_ons._frames import (
    FRAMES_PREFIX,
    InputData,
    SubgridInputData,
    frame_key,
)
from tests.fixtures.goes_cod.criteria import nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source

_, _, _FRAMES = load_source(SOURCE)
AWARE_SLOTS = [nominal_slot(frame.name) for frame in _FRAMES]
SLOTS = [slot.replace(tzinfo=None) for slot in AWARE_SLOTS]


def _storage(root: Path) -> Storage:
    return open_storage(StorageLocation(uri=str(root)))


def _write_frame(root: Path, time: datetime, frame: pl.DataFrame) -> None:
    (root / FRAMES_PREFIX).mkdir(exist_ok=True)
    frame.write_parquet(root / frame_key(time))


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

    def test_frame_key_equals_the_goes_cod_frames_key(self) -> None:
        """The frame key is the key the goes.cod_frames contract renders."""
        template = registry().get("goes.cod_frames", "1.0").template
        for slot in AWARE_SLOTS:
            assert frame_key(slot) == template.render({"cycle": slot})
            assert frame_key(slot.replace(tzinfo=None)) == frame_key(slot)

    @pytest.mark.integration
    def test_from_storage_reads_the_fixture_frame(
        self, layout_root: Path, sample_subgrid_config: Subgrid
    ) -> None:
        """Test loading a frame of the fixture layout through storage."""
        data = SubgridInputData.from_storage(
            sample_subgrid_config, SLOTS[0], _storage(layout_root)
        )

        assert data.name == sample_subgrid_config.name
        assert data.latitude_range == sample_subgrid_config.lat
        assert data.longitude_range == sample_subgrid_config.lon
        assert data.time == SLOTS[0]
        assert isinstance(data.cod, pl.DataFrame)
        assert "latitude" in data.cod.columns
        assert "longitude" in data.cod.columns
        assert "cod" in data.cod.columns
        assert "time" in data.cod.columns
        assert len(data.cod) > 0

    def test_from_storage_filters_by_subgrid(
        self, tmp_path: Path, sample_subgrid_config: Subgrid
    ) -> None:
        """Test that data is filtered by subgrid bounds."""
        time = datetime(2024, 8, 1)
        _write_frame(
            tmp_path,
            time,
            pl.DataFrame(
                {
                    "latitude": [-25.0, -22.0, -19.0],
                    "longitude": [-51.0, -49.0, -48.0],
                    "cod": [1.0, 2.0, 3.0],
                    "time": [time] * 3,
                }
            ),
        )

        data = SubgridInputData.from_storage(
            sample_subgrid_config, time, _storage(tmp_path)
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

    def test_initialization(self, tmp_path: Path) -> None:
        """Test InputData initialization."""
        storage = _storage(tmp_path)
        reader = InputData(storage)
        assert reader.storage is storage

    def test_index_cols(self) -> None:
        """Test INDEX_COLS constant."""
        assert InputData.INDEX_COLS == ["time", "latitude", "longitude"]

    def test_for_subgrid_returns_xarray(self, tmp_path: Path) -> None:
        """Test that for_subgrid returns xarray DataArray."""
        subgrid = Subgrid(name="test", lat=(-23.0, -20.0), lon=(-50.0, -47.0))
        base_time = datetime(2024, 8, 1, 1, 0)
        slots = [base_time - timedelta(minutes=10 * (6 - i)) for i in range(6)]

        lats = np.linspace(-23.0, -20.0, 5)
        lons = np.linspace(-50.0, -47.0, 5)
        lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
        for time in slots:
            _write_frame(
                tmp_path,
                time,
                pl.DataFrame(
                    {
                        "latitude": lat_grid.flatten(),
                        "longitude": lon_grid.flatten(),
                        "cod": np.random.gamma(2, 2, size=25).astype(
                            np.float32
                        ),
                        "time": [time] * 25,
                    }
                ),
            )

        result = InputData(_storage(tmp_path)).for_subgrid(subgrid, slots)

        assert isinstance(result, xr.DataArray)
        assert "time" in result.dims
        assert "latitude" in result.dims
        assert "longitude" in result.dims
        assert result.name == "cod"
        assert result.time.size == 6

    @pytest.mark.integration
    def test_for_subgrid_with_test_data(
        self, layout_root: Path, sample_subgrid_config: Subgrid
    ) -> None:
        """Test for_subgrid with actual test fixture data."""
        reader = InputData(_storage(layout_root))
        result = reader.for_subgrid(sample_subgrid_config, SLOTS[:4])

        assert isinstance(result, xr.DataArray)
        assert result.time.size == 4

        assert result.latitude.min() >= sample_subgrid_config.lat[0]
        assert result.latitude.max() <= sample_subgrid_config.lat[1]
        assert result.longitude.min() >= sample_subgrid_config.lon[0]
        assert result.longitude.max() <= sample_subgrid_config.lon[1]

    def test_for_subgrid_missing_frame_raises_object_not_found(
        self, tmp_path: Path
    ) -> None:
        """Test that a missing frame raises the storage error."""
        subgrid = Subgrid(name="test", lat=(-23.0, -20.0), lon=(-50.0, -47.0))
        reader = InputData(_storage(tmp_path))

        with pytest.raises(ObjectNotFoundError):
            reader.for_subgrid(subgrid, SLOTS[:4])


@pytest.mark.unit
class TestReadersDataFlow:
    """Test data flow through readers."""

    def test_subgrid_data_has_time_column(self, tmp_path: Path) -> None:
        """Test that SubgridInputData adds time column."""
        subgrid = Subgrid(name="test", lat=(-23.0, -20.0), lon=(-50.0, -47.0))
        time = datetime(2024, 8, 1, 0, 0)
        _write_frame(
            tmp_path,
            time,
            pl.DataFrame(
                {
                    "latitude": [-22.0],
                    "longitude": [-49.0],
                    "cod": [5.0],
                }
            ),
        )

        data = SubgridInputData.from_storage(subgrid, time, _storage(tmp_path))

        assert "time" in data.cod.columns
        assert data.cod["time"][0] == time

    def test_input_data_sorts_correctly(self, tmp_path: Path) -> None:
        """Test that InputData sorts by time, lat, lon."""
        subgrid = Subgrid(name="test", lat=(-23.0, -20.0), lon=(-50.0, -47.0))
        base_time = datetime(2024, 8, 1, 1, 0)
        slots = [base_time - timedelta(minutes=10 * (3 - i)) for i in range(3)]

        for time in slots:
            _write_frame(
                tmp_path,
                time,
                pl.DataFrame(
                    {
                        "latitude": [-21.0, -22.0, -20.5],
                        "longitude": [-48.0, -49.0, -48.5],
                        "cod": [1.0, 2.0, 3.0],
                    }
                ),
            )

        result = InputData(_storage(tmp_path)).for_subgrid(subgrid, slots)

        assert all(result.time[:-1] <= result.time[1:])
