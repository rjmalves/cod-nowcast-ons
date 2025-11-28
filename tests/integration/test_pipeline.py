from datetime import datetime

import polars as pl
import pytest

from app.inference import InferenceManager
from app.internal.config import Config, PostprocessingConfig, SubgridConfig
from app.readers import InputData
from app.writers import write_cloud_motion_plots, write_inference_results


@pytest.mark.integration
class TestFullPipeline:
    """Test the complete nowcasting pipeline from input to output."""

    def test_end_to_end_inference(self, test_data_dir, temp_output_dir):
        """Test complete inference pipeline with test data."""
        # Check if we have test data
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if len(test_files) < 5:
            pytest.skip("Need at least 5 test files for full pipeline")

        # Get base time from last file
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        # Create config
        config = Config(
            mode="inference",
            input=str(test_data_dir),
            output=str(temp_output_dir),
            base_datetime=base_time,
            num_past_samples=4,
            num_future_samples=3,
            subgrids=[
                SubgridConfig(
                    name="TEST",
                    lat=[-23.0, -20.0],
                    lon=[-50.0, -47.0],
                )
            ],
            postprocessing=PostprocessingConfig(
                plots=False, shapefile_path=None
            ),
        )

        # Run pipeline
        reader = InputData(config.input)
        manager = InferenceManager(config, reader)
        result = manager.predict()

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
        write_inference_results(config, result)

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
        self, test_data_dir, temp_output_dir
    ):
        """Test pipeline with multiple geographic subgrids."""
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if len(test_files) < 5:
            pytest.skip("Need test data")

        # Setup
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        # Config with two subgrids
        config = Config(
            mode="inference",
            input=str(test_data_dir),
            output=str(temp_output_dir),
            base_datetime=base_time,
            num_past_samples=4,
            num_future_samples=2,
            subgrids=[
                SubgridConfig(
                    name="REGION1",
                    lat=[-23.0, -21.5],
                    lon=[-50.0, -48.5],
                ),
                SubgridConfig(
                    name="REGION2",
                    lat=[-21.5, -20.0],
                    lon=[-48.5, -47.0],
                ),
            ],
            postprocessing=PostprocessingConfig(
                plots=False, shapefile_path=None
            ),
        )

        # Run
        reader = InputData(config.input)
        manager = InferenceManager(config, reader)
        result = manager.predict()

        # Verify both subgrids processed
        assert "REGION1" in result.subgrid_results
        assert "REGION2" in result.subgrid_results

        # Write and verify
        write_inference_results(config, result)
        output_file = temp_output_dir / "cod.parquet"
        assert output_file.exists()

        df = pl.read_parquet(output_file)
        # Should have data from both regions
        assert len(df) > 0

    @pytest.mark.plotting
    def test_pipeline_with_plots(
        self, test_data_dir, temp_output_dir, test_shapefile_path
    ):
        """Test pipeline with plot generation enabled."""
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if len(test_files) < 5:
            pytest.skip("Need test data")

        # Setup
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        # Config with plots enabled and test shapefile
        config = Config(
            mode="inference",
            input=str(test_data_dir),
            output=str(temp_output_dir),
            base_datetime=base_time,
            num_past_samples=4,
            num_future_samples=2,
            subgrids=[
                SubgridConfig(
                    name="TEST",
                    lat=[-23.0, -20.0],
                    lon=[-50.0, -47.0],
                )
            ],
            postprocessing=PostprocessingConfig(
                plots=True, shapefile_path=str(test_shapefile_path)
            ),
        )

        # Run inference
        reader = InputData(config.input)
        manager = InferenceManager(config, reader)
        result = manager.predict()

        # Write results and plots
        write_inference_results(config, result)
        write_cloud_motion_plots(config, result)

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

    def test_missing_input_files(self, temp_output_dir):
        """Test that missing input files are handled gracefully."""
        config = Config(
            mode="inference",
            input="nonexistent_directory",
            output=str(temp_output_dir),
            base_datetime=datetime(2024, 8, 1, 1, 0),
            num_past_samples=6,
            num_future_samples=3,
            subgrids=[
                SubgridConfig(
                    name="TEST",
                    lat=[-23.0, -20.0],
                    lon=[-50.0, -47.0],
                )
            ],
            postprocessing=PostprocessingConfig(
                plots=False, shapefile_path=None
            ),
        )

        reader = InputData(config.input)
        manager = InferenceManager(config, reader)

        # Should raise error for missing files
        with pytest.raises(Exception) as _:
            manager.predict()

    def test_invalid_subgrid_bounds(self, test_data_dir, temp_output_dir):
        """Test with subgrid outside data bounds."""
        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if not test_files:
            pytest.skip("Need test data")

        # Setup
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        # Subgrid completely outside test data bounds
        config = Config(
            mode="inference",
            input=str(test_data_dir),
            output=str(temp_output_dir),
            base_datetime=base_time,
            num_past_samples=4,
            num_future_samples=2,
            subgrids=[
                SubgridConfig(
                    name="OUTSIDE",
                    lat=[10.0, 20.0],  # Outside test data
                    lon=[-10.0, -5.0],
                )
            ],
            postprocessing=PostprocessingConfig(
                plots=False, shapefile_path=None
            ),
        )

        reader = InputData(config.input)
        manager = InferenceManager(config, reader)

        # Should handle empty data gracefully or raise error
        with pytest.raises(Exception) as _:
            manager.predict()


@pytest.mark.integration
@pytest.mark.slow
class TestPipelinePerformance:
    """Performance tests for the pipeline."""

    def test_pipeline_completes_in_reasonable_time(
        self, test_data_dir, temp_output_dir
    ):
        """Test that pipeline completes within acceptable time."""
        import time

        test_files = list(test_data_dir.glob("GOES_COD_BR_*.parquet"))
        if len(test_files) < 5:
            pytest.skip("Need test data")

        # Setup
        last_file = sorted(test_files)[-1]
        time_str = last_file.stem.split("_")[-1]
        base_time = datetime.strptime(time_str, "%Y%m%d-%H%M")

        config = Config(
            mode="inference",
            input=str(test_data_dir),
            output=str(temp_output_dir),
            base_datetime=base_time,
            num_past_samples=4,
            num_future_samples=6,
            subgrids=[
                SubgridConfig(
                    name="TEST",
                    lat=[-23.0, -20.0],
                    lon=[-50.0, -47.0],
                )
            ],
            postprocessing=PostprocessingConfig(
                plots=False, shapefile_path=None
            ),
        )

        # Time the pipeline
        start = time.time()

        reader = InputData(config.input)
        manager = InferenceManager(config, reader)
        result = manager.predict()
        write_inference_results(config, result)

        elapsed = time.time() - start

        # For small test data, should complete quickly
        # Adjust threshold based on expected performance
        assert elapsed < 30.0, f"Pipeline took {elapsed:.1f}s (too slow)"
