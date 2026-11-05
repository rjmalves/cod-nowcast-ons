from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from nwp_core.config import content_parameters, load_config
from nwp_core.errors import ConfigError, exit_code_for
from nwp_core.storage import StorageSettings

from cod_nowcast_ons import NowcastConfig
from cod_nowcast_ons._config import ENV_PREFIX, SLOT

_EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.toml"
_VALID = """\
base_datetime = "2024-02-07T00:20:00Z"
num_past_samples = 3
num_future_samples = 3

[input]
uri = "{root}"

[output]
uri = "{root}"

[[subgrids]]
name = "FIXTURE"
lat = [-23.0, -20.0]
lon = [-50.0, -47.0]
"""


def _subgrids(*subgrids: dict[str, object]) -> str:
    return json.dumps(list(subgrids))


def _subgrid(**override: object) -> dict[str, object]:
    return {
        "name": "FIXTURE",
        "lat": [-23.0, -20.0],
        "lon": [-50.0, -47.0],
    } | override


def _load(
    tmp_path: Path,
    env: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
) -> NowcastConfig:
    config_file = tmp_path / "config.toml"
    config_file.write_text(_VALID.format(root=tmp_path))
    return load_config(
        NowcastConfig,
        env_prefix=ENV_PREFIX,
        config_file=config_file,
        env=env or {},
        cli=cli,
    )


def _assert_rejected(tmp_path: Path, env: dict[str, str], loc: str) -> None:
    with pytest.raises(ConfigError) as caught:
        _load(tmp_path, env)
    assert f"{loc}: " in str(caught.value)
    assert exit_code_for(caught.value) == 2


def test_example_config_loads() -> None:
    cfg = load_config(
        NowcastConfig,
        env_prefix=ENV_PREFIX,
        config_file=_EXAMPLE,
        env={},
    )

    assert [subgrid.name for subgrid in cfg.subgrids] == ["SE"]
    assert cfg.base_datetime == datetime(2024, 8, 1, 10, tzinfo=UTC)
    assert cfg.max_input_staleness == SLOT
    assert cfg.min_input_frames is None
    assert cfg.storage == StorageSettings()


@pytest.mark.parametrize(
    "text",
    [
        "2024-02-07T00:20:00Z",
        "2024-02-07T03:20:00+03:00",
        "2024-02-07T00:20:00",
    ],
)
def test_base_datetime_is_normalized_to_utc(tmp_path: Path, text: str) -> None:
    cfg = _load(tmp_path, {"COD_NOWCAST_ONS_BASE_DATETIME": text})

    assert cfg.base_datetime == datetime(2024, 2, 7, 0, 20, tzinfo=UTC)
    assert cfg.base_datetime.tzinfo is UTC


def test_sources_take_precedence(tmp_path: Path) -> None:
    future = {"COD_NOWCAST_ONS_NUM_FUTURE_SAMPLES": "4"}
    attempts = {"COD_NOWCAST_ONS_STORAGE__MAX_ATTEMPTS": "7"}

    assert _load(tmp_path).num_future_samples == 3
    assert _load(tmp_path, future).num_future_samples == 4
    cli: dict[str, object] = {"num_future_samples": 5}
    assert _load(tmp_path, future, cli).num_future_samples == 5
    assert _load(tmp_path, attempts).storage.max_attempts == 7


@pytest.mark.parametrize(
    ("env", "loc"),
    [
        pytest.param(
            {"COD_NOWCAST_ONS_MAX_INPUT_STALENESS": "PT5M"},
            "max_input_staleness",
            id="staleness-below-slot",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_MAX_INPUT_STALENESS": "PT15M"},
            "max_input_staleness",
            id="staleness-off-slot",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_MIN_INPUT_FRAMES": "1"},
            "min_input_frames",
            id="min-frames-below-two",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_MIN_INPUT_FRAMES": "4"},
            "min_input_frames",
            id="min-frames-above-past",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_BASE_DATETIME": "2024-02-07T00:25:00Z"},
            "base_datetime",
            id="base-off-slot",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_BASE_DATETIME": "2024-02-07T00:20:30Z"},
            "base_datetime",
            id="base-with-seconds",
        ),
    ],
)
def test_invalid_guard_value_is_a_config_error(
    tmp_path: Path, env: dict[str, str], loc: str
) -> None:
    _assert_rejected(tmp_path, env, loc)


@pytest.mark.parametrize(
    ("env", "loc"),
    [
        pytest.param(
            {"COD_NOWCAST_ONS_INPUT__URI": "relative/input"},
            "input.uri",
            id="relative-input",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_MODE": "inference"}, "mode", id="mode-key"
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_SUBGRIDS": _subgrids(_subgrid(), _subgrid())},
            "subgrids",
            id="duplicate-names",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_SUBGRIDS": _subgrids(_subgrid(name=".."))},
            "subgrids.0.name",
            id="name-dot-dot",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_SUBGRIDS": _subgrids(_subgrid(name=".nwp-x"))},
            "subgrids.0.name",
            id="name-reserved-prefix",
        ),
        pytest.param(
            {
                "COD_NOWCAST_ONS_SUBGRIDS": _subgrids(
                    _subgrid(lat=[-20.0, -23.0])
                )
            },
            "subgrids.0",
            id="reversed-lat",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_SUBGRIDS": "[]"}, "subgrids", id="no-subgrids"
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_NUM_PAST_SAMPLES": "1"},
            "num_past_samples",
            id="one-past-sample",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_NUM_FUTURE_SAMPLES": "0"},
            "num_future_samples",
            id="no-future-samples",
        ),
        pytest.param(
            {"COD_NOWCAST_ONS_MAX_INPUT_STALENESS": "P1M"},
            "max_input_staleness",
            id="calendar-unit-staleness",
        ),
    ],
)
def test_invalid_value_is_a_config_error(
    tmp_path: Path, env: dict[str, str], loc: str
) -> None:
    _assert_rejected(tmp_path, env, loc)


def test_operational_fields_select_no_content(tmp_path: Path) -> None:
    cfg = _load(tmp_path)

    assert content_parameters(
        cfg, ["num_past_samples", "num_future_samples"]
    ) == {"num_past_samples": 3, "num_future_samples": 3}
    for name in (
        "base_datetime",
        "input.uri",
        "output.uri",
        "max_input_staleness",
        "min_input_frames",
        "storage.max_attempts",
    ):
        with pytest.raises(ConfigError):
            content_parameters(cfg, [name])
