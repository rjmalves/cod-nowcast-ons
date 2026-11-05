"""Shared regression config, adapter and session fixtures.

The constants below are the one regression config. They derive from the
committed text source and the pre-registered criteria, so no date or box is
written out here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cod_nowcast_ons._config import Config, PostprocessingConfig, SubgridConfig
from cod_nowcast_ons._forecast import InferenceManager
from cod_nowcast_ons._frames import InputData
from cod_nowcast_ons._output import write_inference_results
from tests.fixtures.goes_cod.criteria import L, P, nominal_slot
from tests.fixtures.goes_cod.materialize import (
    FRAMES_PREFIX,
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
    """Run the code under test on the frames under ``input_root``.

    This is the only call into the code under test, which epic 03 retargets
    to ``cod_nowcast_ons.nowcast``. ``input_root`` is the gold layout root,
    which the retargeted adapter passes to ``[input]`` unchanged. The frame
    reader reads the frames directly under its input, so this adapter appends
    ``goes_processed``.

    Returns:
        The path of the ``cod.parquet`` written under ``out_dir``.
    """
    name, lat, lon = SUBGRID
    config = Config(
        mode="inference",
        input=str(input_root / FRAMES_PREFIX),
        output=str(out_dir),
        base_datetime=BASE_DATETIME,
        num_past_samples=NUM_PAST,
        num_future_samples=NUM_FUTURE,
        subgrids=[SubgridConfig(name=name, lat=list(lat), lon=list(lon))],
        postprocessing=PostprocessingConfig(plots=False, shapefile_path=None),
    )
    result = InferenceManager(config, InputData(config.input)).predict()
    write_inference_results(config, result)
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
