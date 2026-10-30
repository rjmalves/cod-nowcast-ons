from datetime import datetime
from pathlib import Path

import pytest

from app.internal.config import Config, PostprocessingConfig, SubgridConfig


class TestSubgridConfig:
    """Test SubgridConfig dataclass."""

    def test_parse_valid(self) -> None:
        """Test parsing valid subgrid dictionary."""
        data = {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
        config = SubgridConfig.parse(data)

        assert config.name == "SE"
        assert config.lat == [-23.0, -20.0]
        assert config.lon == [-50.0, -47.0]

    def test_direct_construction(self) -> None:
        """Test direct construction."""
        config = SubgridConfig(
            name="test", lat=[-10.0, -5.0], lon=[-60.0, -55.0]
        )
        assert config.name == "test"
        assert len(config.lat) == 2
        assert len(config.lon) == 2


class TestPostprocessingConfig:
    """Test PostprocessingConfig dataclass."""

    def test_parse_with_plots(self) -> None:
        """Test parsing with plots enabled."""
        config = PostprocessingConfig.parse({"plots": True})
        assert config.plots is True
        assert config.shapefile_path is None

    def test_parse_default(self) -> None:
        """Test parsing with missing plots key."""
        config = PostprocessingConfig.parse({})
        assert config.plots is False
        assert config.shapefile_path is None

    def test_parse_false(self) -> None:
        """Test parsing with plots explicitly false."""
        config = PostprocessingConfig.parse({"plots": False})
        assert config.plots is False

    def test_parse_with_shapefile(self) -> None:
        """Test parsing with shapefile_path."""
        config = PostprocessingConfig.parse(
            {
                "plots": True,
                "shapefile_path": "data/shapes/test.shp",
            }
        )
        assert config.plots is True
        assert config.shapefile_path == "data/shapes/test.shp"


class TestConfig:
    """Test main Config dataclass."""

    def test_parse_complete_config(self) -> None:
        """Test parsing a complete configuration."""
        data = {
            "mode": "inference",
            "input": "data/input",
            "output": "data/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ],
            "postprocessing": {"plots": True},
        }

        config = Config.parse(data)

        assert config.mode == "inference"
        assert config.input == "data/input"
        assert config.output == "data/output"
        assert isinstance(config.base_datetime, datetime)
        assert config.base_datetime.year == 2024
        assert config.num_past_samples == 6
        assert config.num_future_samples == 3
        assert len(config.subgrids) == 1
        assert config.subgrids[0].name == "SE"
        assert config.postprocessing.plots is True

    def test_parse_minimal_config(self) -> None:
        """Test parsing minimal configuration (no postprocessing)."""
        data = {
            "mode": "inference",
            "input": "data/input",
            "output": "data/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ],
        }

        config = Config.parse(data)
        assert config.postprocessing.plots is False

    def test_parse_multiple_subgrids(self) -> None:
        """Test parsing configuration with multiple subgrids."""
        data = {
            "mode": "inference",
            "input": "data/input",
            "output": "data/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]},
                {"name": "NE", "lat": [-18.0, -15.0], "lon": [-48.0, -45.0]},
            ],
        }

        config = Config.parse(data)
        assert len(config.subgrids) == 2
        assert config.subgrids[0].name == "SE"
        assert config.subgrids[1].name == "NE"

    def test_parse_s3_paths(self) -> None:
        """Test parsing configuration with S3 paths."""
        data = {
            "mode": "inference",
            "input": "s3://example-bucket/input",
            "output": "s3://example-bucket/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ],
        }

        config = Config.parse(data)
        assert config.input.startswith("s3://")
        assert config.output.startswith("s3://")

    def test_from_json(self, tmp_path: Path) -> None:
        """Test loading configuration from JSON file."""
        config_data = """{
            "mode": "inference",
            "input": "data/input",
            "output": "data/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ]
        }"""

        config_file = tmp_path / "config.jsonc"
        config_file.write_text(config_data)

        config = Config.from_json(str(config_file))
        assert config.mode == "inference"
        assert config.num_past_samples == 6

    def test_from_json_with_comments(self, tmp_path: Path) -> None:
        """Test loading JSON with comments (JSONC format)."""
        config_data = """{
            // This is a comment
            "mode": "inference",
            "input": "data/input",  // inline comment
            "output": "data/output",
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            /* Multi-line
               comment */
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ]
        }"""

        config_file = tmp_path / "config.jsonc"
        config_file.write_text(config_data)

        config = Config.from_json(str(config_file))
        assert config.mode == "inference"

    def test_invalid_datetime_format(self) -> None:
        """Test that invalid datetime raises error."""
        data = {
            "mode": "inference",
            "input": "data/input",
            "output": "data/output",
            "base_datetime": "invalid-datetime",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ],
        }

        with pytest.raises(ValueError):
            Config.parse(data)

    def test_missing_required_field(self) -> None:
        """Test that missing required field raises error."""
        data = {
            "mode": "inference",
            "input": "data/input",
            # Missing output
            "base_datetime": "2024-08-01T10:00:00",
            "num_past_samples": 6,
            "num_future_samples": 3,
            "subgrids": [
                {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
            ],
        }

        with pytest.raises(KeyError):
            Config.parse(data)


@pytest.mark.unit
def test_config_roundtrip(tmp_path: Path) -> None:
    """Test that config can be saved and loaded preserving values."""
    import json

    original_data = {
        "mode": "inference",
        "input": "data/input",
        "output": "data/output",
        "base_datetime": "2024-08-01T10:00:00",
        "num_past_samples": 6,
        "num_future_samples": 3,
        "subgrids": [
            {"name": "SE", "lat": [-23.0, -20.0], "lon": [-50.0, -47.0]}
        ],
        "postprocessing": {"plots": True},
    }

    # Save
    config_file = tmp_path / "config.json"
    with open(config_file, "w") as f:
        json.dump(original_data, f)

    # Load
    config = Config.from_json(str(config_file))

    # Verify
    assert config.mode == original_data["mode"]
    assert config.num_past_samples == original_data["num_past_samples"]
    assert config.postprocessing.plots is True
