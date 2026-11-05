from __future__ import annotations

import io
from pathlib import Path

import polars as pl
import pytest
from nwp_core.storage import StorageLocation, open_storage

from cod_nowcast_ons import NowcastConfig, nowcast
from cod_nowcast_ons._config import Postprocessing, Subgrid
from tests.fixtures.goes_cod.criteria import P, nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source
from tests.integration.conftest import Backend

_LATITUDE, _LONGITUDE, _FRAMES = load_source(SOURCE)
_SLOTS = [nominal_slot(frame.name) for frame in _FRAMES]
_FIXTURE = Subgrid(
    name="FIXTURE",
    lat=(float(_LATITUDE[0]), float(_LATITUDE[-1])),
    lon=(float(_LONGITUDE[0]), float(_LONGITUDE[-1])),
)


def _upload(layout_root: Path, location: StorageLocation) -> None:
    storage = open_storage(location)
    for path in sorted((layout_root / "goes_processed").iterdir()):
        storage.write(f"goes_processed/{path.name}", path, mode="create")


def _config(backend: Backend, *, plots: bool) -> NowcastConfig:
    return NowcastConfig(
        base_datetime=_SLOTS[P],
        input=backend.input,
        output=backend.output,
        num_past_samples=P,
        num_future_samples=3,
        subgrids=(_FIXTURE,),
        postprocessing=Postprocessing(plots=plots),
    )


def test_nowcast_writes_the_parquet(
    storage_backend: Backend, layout_root: Path
) -> None:
    _upload(layout_root, storage_backend.input)

    outcome = nowcast(_config(storage_backend, plots=False))

    outputs = open_storage(storage_backend.output)
    info = outputs.stat("cod.parquet")
    (item,) = outcome.items
    assert outcome.exit_code == 0
    assert info is not None
    assert (item.artifacts_written, item.bytes_written) == (1, info.size)
    with outputs.open_read("cod.parquet") as stream:
        assert pl.read_parquet(io.BytesIO(stream.read())).height == 17328


@pytest.mark.usefixtures("offline_maps")
def test_nowcast_writes_the_plots(
    storage_backend: Backend, layout_root: Path
) -> None:
    _upload(layout_root, storage_backend.input)

    outcome = nowcast(_config(storage_backend, plots=True))

    outputs = open_storage(storage_backend.output)
    objects = {info.key: info.size for info in outputs.iter_prefix()}
    (item,) = outcome.items
    assert outcome.exit_code == 0
    assert sorted(objects) == [
        "cod.parquet",
        "plots/FIXTURE_0000.png",
        "plots/FIXTURE_0001.png",
        "plots/FIXTURE_0002.png",
        "plots/FIXTURE_forecast.gif",
    ]
    assert item.artifacts_written == 1 + (3 + 1)
    assert item.bytes_written == sum(objects.values())
