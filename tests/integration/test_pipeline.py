from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from nwp_core.errors import ObjectNotFoundError
from nwp_core.storage import StorageLocation, open_storage

from cod_nowcast_ons._config import Subgrid
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData
from cod_nowcast_ons._output import (
    write_cloud_motion_plots,
    write_inference_results,
)
from tests.fixtures.goes_cod.criteria import nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source

_, _, _FRAMES = load_source(SOURCE)
SLOTS = [nominal_slot(frame.name).replace(tzinfo=None) for frame in _FRAMES]


def _reader(root: Path) -> InputData:
    return InputData(open_storage(StorageLocation(uri=str(root))))


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
        write_inference_results(result, str(temp_output_dir), SLOTS[4])

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
        write_inference_results(result, str(temp_output_dir), SLOTS[4])
        output_file = temp_output_dir / "cod.parquet"
        assert output_file.exists()

        df = pl.read_parquet(output_file)
        # Should have data from both regions
        assert len(df) > 0

    @pytest.mark.plotting
    def test_pipeline_with_plots(
        self,
        layout_root: Path,
        temp_output_dir: Path,
        test_shapefile_path: Path,
    ) -> None:
        """Test pipeline with plot generation enabled."""
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
            num_future_samples=2,
        )

        # Write results and plots, with the test shapefile
        write_inference_results(result, str(temp_output_dir), SLOTS[4])
        write_cloud_motion_plots(
            result, str(temp_output_dir), str(test_shapefile_path)
        )

        # Verify plot directory created
        plots_dir = temp_output_dir / "plots"
        assert plots_dir.exists()

        # Verify GIF created
        gif_files = list(plots_dir.glob("*.gif"))
        assert len(gif_files) > 0

        # Verify frame images (if kept)
        png_files = list(plots_dir.glob("*.png"))
        assert len(png_files) > 0


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
        write_inference_results(result, str(temp_output_dir), SLOTS[4])

        elapsed = time.time() - start

        # For small test data, should complete quickly
        # Adjust threshold based on expected performance
        assert elapsed < 30.0, f"Pipeline took {elapsed:.1f}s (too slow)"
