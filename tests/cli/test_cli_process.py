"""The process contract of the ``cod-nowcast-ons`` command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from nwp_core._testing.cli import child_env, run_tool

from cod_nowcast_ons import __version__
from tests.fixtures.goes_cod.criteria import P, nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source

_EXE = Path(sys.executable).with_name("cod-nowcast-ons")
_BANNER = "Pysteps configuration file found at"
_LATITUDE, _LONGITUDE, _FRAMES = load_source(SOURCE)
_SLOTS = [nominal_slot(frame.name) for frame in _FRAMES]


def _config(path: Path, input_root: Path, output_root: Path) -> Path:
    path.write_text(
        f'base_datetime = "{_SLOTS[P].isoformat()}"\n'
        f"num_past_samples = {P}\n"
        "num_future_samples = 3\n"
        f'[input]\nuri = "{input_root}"\n'
        f'[output]\nuri = "{output_root}"\n'
        "[[subgrids]]\n"
        'name = "FIXTURE"\n'
        f"lat = [{_LATITUDE[0]}, {_LATITUDE[-1]}]\n"
        f"lon = [{_LONGITUDE[0]}, {_LONGITUDE[-1]}]\n",
        encoding="utf-8",
    )
    return path


def _fatal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event["event"] == "run.fatal"]


def test_version_prints_tool_and_version() -> None:
    run = run_tool([str(_EXE), "--version"], env=child_env())

    assert run.code == 0
    assert run.stdout == f"cod-nowcast-ons {__version__}\n"


def test_group_help_lists_the_nowcast_command() -> None:
    run = run_tool([str(_EXE), "--help"], env=child_env())

    assert run.code == 0
    assert "Run one nowcast at base_datetime." in run.stdout
    assert _BANNER not in run.stdout


def test_nowcast_help_lists_config() -> None:
    run = run_tool([str(_EXE), "nowcast", "--help"], env=child_env())

    assert run.code == 0
    assert "--config" in run.stdout
    assert "Local TOML file with the tool configuration." in run.stdout
    assert _BANNER not in run.stdout


def test_bare_group_is_a_usage_error() -> None:
    run = run_tool([str(_EXE)], env=child_env())

    assert run.code == 2
    assert run.stdout == ""
    assert [e["error_type"] for e in _fatal(run.events)] == [
        "NoArgsIsHelpError"
    ]


def test_run_prints_only_the_summary(layout_root: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    output_root.mkdir()
    config = _config(tmp_path / "config.toml", layout_root, output_root)

    run = run_tool(
        [str(_EXE), "nowcast", "--config", str(config)],
        env=child_env({"NWP_LOG_LEVEL": "DEBUG"}),
    )

    summary = run.summary
    assert summary is not None
    assert run.code == 0
    assert summary.exit_code == 0
    assert summary.counts.succeeded == 1
    assert _BANNER not in run.stdout
    imports = [e for e in run.events if e["event"] == "pysteps.import"]
    assert len(imports) == 1
    assert _BANNER in imports[0]["stdout"]


def test_empty_input_root_is_not_ready(tmp_path: Path) -> None:
    input_root = tmp_path / "in"
    input_root.mkdir()
    output_root = tmp_path / "out"
    output_root.mkdir()
    config = _config(tmp_path / "config.toml", input_root, output_root)

    run = run_tool(
        [str(_EXE), "nowcast", "--config", str(config)], env=child_env()
    )

    summary = run.summary
    assert summary is not None
    assert run.code == 4
    assert summary.counts.not_ready == 1
    assert summary.items[0].reason == "input_not_ready"


def test_invalid_config_is_a_config_error(
    layout_root: Path, tmp_path: Path
) -> None:
    output_root = tmp_path / "out"
    output_root.mkdir()
    config = _config(tmp_path / "config.toml", layout_root, output_root)

    run = run_tool(
        [str(_EXE), "nowcast", "--config", str(config)],
        env=child_env({"COD_NOWCAST_ONS_NUM_PAST_SAMPLES": "1"}),
    )

    assert run.code == 2
    assert run.stdout == ""
    assert [e["error_type"] for e in _fatal(run.events)] == ["ConfigError"]


def test_missing_output_root_is_run_fatal(
    layout_root: Path, tmp_path: Path
) -> None:
    config = _config(
        tmp_path / "config.toml", layout_root, tmp_path / "missing"
    )

    run = run_tool(
        [str(_EXE), "nowcast", "--config", str(config)], env=child_env()
    )

    summary = run.summary
    assert summary is not None
    assert summary.fatal_error is not None
    assert run.code == 2
    assert summary.exit_code == 2
    assert summary.fatal_error.type == "LocationUnusableError"
    assert len(_fatal(run.events)) == 1


def test_unreadable_frames_fail_the_item(
    layout_root: Path, tmp_path: Path
) -> None:
    for frame in (layout_root / "goes_processed").iterdir():
        frame.write_bytes(b"not a parquet file")
    output_root = tmp_path / "out"
    output_root.mkdir()
    config = _config(tmp_path / "config.toml", layout_root, output_root)

    run = run_tool(
        [str(_EXE), "nowcast", "--config", str(config)], env=child_env()
    )

    summary = run.summary
    assert summary is not None
    assert run.code == 3
    assert summary.counts.failed == 1
