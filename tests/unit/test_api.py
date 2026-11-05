from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from nwp_core.errors import RunNotReadyError
from nwp_core.layout import cycle_token
from nwp_core.run import ItemReport, ItemStatus
from nwp_core.storage import StorageLocation

from cod_nowcast_ons import NowcastConfig, Subgrid, nowcast
from cod_nowcast_ons._config import SLOT
from tests.fixtures.goes_cod.criteria import P, nominal_slot
from tests.fixtures.goes_cod.materialize import (
    SOURCE,
    load_source,
    materialize,
)

_LATITUDE, _LONGITUDE, _FRAMES = load_source(SOURCE)
SLOTS = [nominal_slot(frame.name) for frame in _FRAMES]
FIXTURE = Subgrid(
    name="FIXTURE",
    lat=(float(_LATITUDE[0]), float(_LATITUDE[-1])),
    lon=(float(_LONGITUDE[0]), float(_LONGITUDE[-1])),
)


@pytest.fixture(scope="module")
def frames_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("frames")
    materialize(SOURCE, root)
    return root


def _config(
    root: Path,
    out: Path,
    base: datetime,
    *,
    num_past: int,
    staleness: timedelta = SLOT,
) -> NowcastConfig:
    return NowcastConfig(
        base_datetime=base,
        input=StorageLocation(uri=str(root)),
        output=StorageLocation(uri=str(out)),
        num_past_samples=num_past,
        num_future_samples=3,
        max_input_staleness=staleness,
        subgrids=(FIXTURE,),
    )


def _late_config(frames_root: Path, tmp_path: Path) -> NowcastConfig:
    return _config(
        frames_root,
        tmp_path / "out",
        SLOTS[-1] + 2 * SLOT,
        num_past=2,
        staleness=timedelta(minutes=20),
    )


def _issue_times(out: Path) -> list[datetime]:
    return (
        pl.read_parquet(out / "cod.parquet")["data_hora_rodada"]
        .unique()
        .to_list()
    )


def test_nowcast_succeeds_on_the_fixture_frames(
    frames_root: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    config = _config(frames_root, out, SLOTS[P], num_past=P)

    outcome = nowcast(config)

    assert outcome.exit_code == 0
    assert [(item.item_id, item.reason) for item in outcome.items] == [
        (cycle_token(SLOTS[P]), None)
    ]
    assert _issue_times(out) == [SLOTS[P].replace(tzinfo=None)]


def test_empty_root_is_not_ready(tmp_path: Path) -> None:
    root = tmp_path / "input"
    root.mkdir()
    config = _config(root, tmp_path / "out", SLOTS[P], num_past=P)

    with pytest.raises(RunNotReadyError) as excinfo:
        nowcast(config)

    outcome = excinfo.value.outcome
    (item,) = outcome.items
    assert outcome.exit_code == 4
    assert item.status is ItemStatus.NOT_READY
    assert item.reason == "input_not_ready"
    assert item.error_type == "InputNotReadyError"
    assert item.error_message is not None
    assert str(root) not in item.error_message


def test_late_frames_report_stale_input(
    frames_root: Path, tmp_path: Path
) -> None:
    outcome = nowcast(_late_config(frames_root, tmp_path))

    (item,) = outcome.items
    assert item.reason == "stale_input"
    assert _issue_times(tmp_path / "out") == [
        (SLOTS[-1] + SLOT).replace(tzinfo=None)
    ]


def test_issue_time_is_logged(
    frames_root: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        nowcast(_late_config(frames_root, tmp_path))

    (issued,) = (
        vars(record)
        for record in caplog.records
        if getattr(record, "event", None) == "nowcast.issued"
    )
    assert issued["issue_time"] == cycle_token(SLOTS[-1] + SLOT)
    assert issued["frames_used"] == 2


def test_stale_input_is_an_unregistered_success_reason() -> None:
    assert ItemReport.succeeded("stale_input").status is ItemStatus.SUCCEEDED
