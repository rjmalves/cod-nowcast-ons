from __future__ import annotations

import shutil
import socket
from datetime import UTC
from pathlib import Path
from typing import NoReturn

import polars as pl
import pytest
from nwp_core.errors import ObjectNotFoundError, RunFailedError
from nwp_core.run import ItemStatus
from nwp_core.storage import StorageLocation, open_storage
from PIL import Image

from cod_nowcast_ons import NowcastConfig, nowcast
from cod_nowcast_ons._config import Postprocessing, Shapefile, Subgrid
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData
from cod_nowcast_ons._output import write_inference_results
from tests.fixtures.goes_cod.criteria import nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source

_, _, _FRAMES = load_source(SOURCE)
SLOTS = [nominal_slot(frame.name).replace(tzinfo=None) for frame in _FRAMES]


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _reader(root: Path) -> InputData:
    return InputData(open_storage(StorageLocation(uri=str(root))))


def _plot_config(
    layout_root: Path, output: Path, shapefile: Shapefile | None
) -> NowcastConfig:
    return NowcastConfig(
        base_datetime=SLOTS[4].replace(tzinfo=UTC),
        input=StorageLocation(uri=str(layout_root)),
        output=StorageLocation(uri=str(output)),
        num_past_samples=4,
        num_future_samples=2,
        subgrids=(
            Subgrid(name="TEST", lat=(-23.0, -20.0), lon=(-50.0, -47.0)),
        ),
        postprocessing=Postprocessing(plots=True, shapefile=shapefile),
    )


@pytest.fixture
def offline_maps(
    monkeypatch: pytest.MonkeyPatch, generated_shapefile: Path
) -> None:
    def refuse(*args: object, **kwargs: object) -> NoReturn:
        msg = "network access is disabled"
        raise OSError(msg)

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(
        "cartopy.io.shapereader.natural_earth",
        lambda **_: str(generated_shapefile),
    )
    monkeypatch.setattr("cartopy.feature._NATURAL_EARTH_GEOM_CACHE", {})


@pytest.mark.integration
class TestFullPipeline:
    """Test the complete nowcasting pipeline from input to output."""

    def test_end_to_end_inference(
        self, layout_root: Path, temp_output_dir: Path
    ) -> None:
        """Test complete inference pipeline with test data."""
        result = predict_subgrids(
            _reader(layout_root),
            [
                Subgrid(
                    name="TEST",
                    lat=(-23.0, -20.0),
                    lon=(-50.0, -47.0),
                )
            ],
            slots=SLOTS[:4],
            num_future_samples=3,
        )

        # Verify result structure
        assert result is not None
        assert "TEST" in result.subgrid_results

        subgrid_result = result.subgrid_results["TEST"]
        assert subgrid_result.cod is not None
        assert subgrid_result.motion_field is not None

        # Verify forecast dimensions
        assert subgrid_result.cod.time.size == 3
        assert subgrid_result.motion_field.shape[0] == 2  # U, V

        # Write results
        write_inference_results(
            result,
            open_storage(StorageLocation(uri=str(temp_output_dir))),
            SLOTS[4],
        )

        # Verify output file exists
        output_file = temp_output_dir / "cod.parquet"
        assert output_file.exists()

        # Verify output content
        df = pl.read_parquet(output_file)
        assert len(df) > 0
        assert "data_hora_rodada" in df.columns
        assert "data_hora_previsao" in df.columns
        assert "latitude" in df.columns
        assert "longitude" in df.columns
        assert "valor" in df.columns

    def test_pipeline_with_multiple_subgrids(
        self, layout_root: Path, temp_output_dir: Path
    ) -> None:
        """Test pipeline with multiple geographic subgrids."""
        result = predict_subgrids(
            _reader(layout_root),
            [
                Subgrid(
                    name="REGION1",
                    lat=(-23.0, -21.5),
                    lon=(-50.0, -48.5),
                ),
                Subgrid(
                    name="REGION2",
                    lat=(-21.5, -20.0),
                    lon=(-48.5, -47.0),
                ),
            ],
            slots=SLOTS[:4],
            num_future_samples=2,
        )

        # Verify both subgrids processed
        assert "REGION1" in result.subgrid_results
        assert "REGION2" in result.subgrid_results

        # Write and verify
        write_inference_results(
            result,
            open_storage(StorageLocation(uri=str(temp_output_dir))),
            SLOTS[4],
        )
        output_file = temp_output_dir / "cod.parquet"
        assert output_file.exists()

        df = pl.read_parquet(output_file)
        # Should have data from both regions
        assert len(df) > 0

    @pytest.mark.plotting
    @pytest.mark.usefixtures("offline_maps")
    @pytest.mark.parametrize(
        "with_shapefile",
        [True, False],
        ids=["with-shapefile", "coastlines-only"],
    )
    def test_nowcast_writes_plots_offline(
        self,
        layout_root: Path,
        temp_output_dir: Path,
        generated_shapefile: Path,
        with_shapefile: bool,
    ) -> None:
        shapefile = (
            Shapefile(
                key="test_shapes.shp",
                location=StorageLocation(uri=str(generated_shapefile.parent)),
            )
            if with_shapefile
            else None
        )

        outcome = nowcast(_plot_config(layout_root, temp_output_dir, shapefile))

        assert outcome.exit_code == 0
        plots = temp_output_dir / "plots"
        (item,) = outcome.items
        written = [temp_output_dir / "cod.parquet", *plots.iterdir()]
        assert item.artifacts_written == 1 + (2 + 1)
        assert item.bytes_written == sum(
            path.stat().st_size for path in written
        )
        assert sorted(path.name for path in plots.iterdir()) == [
            "TEST_0000.png",
            "TEST_0001.png",
            "TEST_forecast.gif",
        ]
        for name in ("TEST_0000.png", "TEST_0001.png"):
            assert (plots / name).read_bytes().startswith(PNG_SIGNATURE)
        gif = plots / "TEST_forecast.gif"
        assert gif.read_bytes().startswith(b"GIF89a")
        with Image.open(gif) as image:
            assert image.n_frames == 2
        for path in plots.iterdir():
            assert path.stat().st_mode & 0o777 == 0o600

    @pytest.mark.plotting
    @pytest.mark.usefixtures("offline_maps")
    def test_missing_shapefile_part_fails_the_item(
        self,
        layout_root: Path,
        temp_output_dir: Path,
        generated_shapefile: Path,
        tmp_path: Path,
    ) -> None:
        shapes = tmp_path / "shapes"
        shapes.mkdir()
        for suffix in (".shp", ".shx"):
            shutil.copy(generated_shapefile.with_suffix(suffix), shapes)
        shapefile = Shapefile(
            key="test_shapes.shp", location=StorageLocation(uri=str(shapes))
        )

        with pytest.raises(RunFailedError) as excinfo:
            nowcast(_plot_config(layout_root, temp_output_dir, shapefile))

        (item,) = excinfo.value.outcome.items
        assert item.status is ItemStatus.FAILED
        assert item.error_type == "ObjectNotFoundError"
        assert (temp_output_dir / "cod.parquet").exists()
        assert not (temp_output_dir / "plots").exists()


@pytest.mark.integration
class TestPipelineErrorHandling:
    """Test error handling in the pipeline."""

    def test_missing_input_files(self, tmp_path: Path) -> None:
        """Test that missing input files are handled gracefully."""
        with pytest.raises(ObjectNotFoundError):
            predict_subgrids(
                _reader(tmp_path),
                [
                    Subgrid(
                        name="TEST",
                        lat=(-23.0, -20.0),
                        lon=(-50.0, -47.0),
                    )
                ],
                slots=SLOTS[:4],
                num_future_samples=3,
            )

    def test_invalid_subgrid_bounds(self, layout_root: Path) -> None:
        """Test with subgrid outside data bounds."""
        with pytest.raises(IndexError):
            predict_subgrids(
                _reader(layout_root),
                [
                    # Subgrid completely outside test data bounds
                    Subgrid(
                        name="OUTSIDE",
                        lat=(10.0, 20.0),  # Outside test data
                        lon=(-10.0, -5.0),
                    )
                ],
                slots=SLOTS[:4],
                num_future_samples=2,
            )


@pytest.mark.integration
@pytest.mark.slow
class TestPipelinePerformance:
    """Performance tests for the pipeline."""

    def test_pipeline_completes_in_reasonable_time(
        self, layout_root: Path, temp_output_dir: Path
    ) -> None:
        """Test that pipeline completes within acceptable time."""
        import time

        # Time the pipeline
        start = time.time()

        result = predict_subgrids(
            _reader(layout_root),
            [
                Subgrid(
                    name="TEST",
                    lat=(-23.0, -20.0),
                    lon=(-50.0, -47.0),
                )
            ],
            slots=SLOTS[:4],
            num_future_samples=6,
        )
        write_inference_results(
            result,
            open_storage(StorageLocation(uri=str(temp_output_dir))),
            SLOTS[4],
        )

        elapsed = time.time() - start

        # For small test data, should complete quickly
        # Adjust threshold based on expected performance
        assert elapsed < 30.0, f"Pipeline took {elapsed:.1f}s (too slow)"
