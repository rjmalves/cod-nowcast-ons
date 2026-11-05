"""Shared regression config, adapter and session fixtures.

The constants below are the one regression config. They derive from the
committed text source and the pre-registered criteria, so no date or box is
written out here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nwp_core.storage import StorageLocation

from cod_nowcast_ons import NowcastConfig, Subgrid, nowcast
from tests.fixtures.goes_cod.criteria import L, P, nominal_slot
from tests.fixtures.goes_cod.materialize import (
    SOURCE,
    load_source,
    materialize,
)

_LATITUDE, _LONGITUDE, _FRAMES = load_source(SOURCE)

SLOTS = [nominal_slot(frame.name) for frame in _FRAMES]
BASE_DATETIME = SLOTS[P].replace(tzinfo=None)
NUM_PAST = P
NUM_FUTURE = L
SUBGRID = (
    "FIXTURE",
    (float(_LATITUDE[0]), float(_LATITUDE[-1])),
    (float(_LONGITUDE[0]), float(_LONGITUDE[-1])),
)


def run_regression(input_root: Path, out_dir: Path) -> Path:
    """Run ``cod_nowcast_ons.nowcast`` on the frames under ``input_root``.

    This is the only call into the code under test. ``input_root`` is the gold
    layout root, which this adapter passes to ``[input]`` unchanged. It creates
    ``out_dir`` when missing, so the run writes into a folder that exists.

    Returns:
        The path of the ``cod.parquet`` written under ``out_dir``.
    """
    name, lat, lon = SUBGRID
    out_dir.mkdir(parents=True, exist_ok=True)
    nowcast(
        NowcastConfig(
            base_datetime=SLOTS[P],
            input=StorageLocation(uri=str(input_root)),
            output=StorageLocation(uri=str(out_dir)),
            num_past_samples=NUM_PAST,
            num_future_samples=NUM_FUTURE,
            subgrids=(Subgrid(name=name, lat=lat, lon=lon),),
        )
    )
    return out_dir / "cod.parquet"


@pytest.fixture(scope="session")
def regression_frames(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Materialize the text source once and return the gold layout root."""
    root = tmp_path_factory.mktemp("frames")
    materialize(SOURCE, root)
    return root


@pytest.fixture(scope="session")
def regression_cod_parquet(
    regression_frames: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Run the code under test once per session and return its output."""
    return run_regression(regression_frames, tmp_path_factory.mktemp("cod"))


@pytest.fixture(scope="session")
def regression_config() -> dict[str, object]:
    """The regression constants as JSON-ready values."""
    name, lat, lon = SUBGRID
    return {
        "slots": [slot.isoformat() for slot in SLOTS],
        "base_datetime": BASE_DATETIME.isoformat(),
        "num_past": NUM_PAST,
        "num_future": NUM_FUTURE,
        "subgrid": [name, list(lat), list(lon)],
    }
