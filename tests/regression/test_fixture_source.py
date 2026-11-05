"""Model-free regression tests of the committed GOES COD text source.

``frames.toml`` is the regression fixture. ``cut.py verify`` checked it
against the source files, which never enter the repository. These tests
carry that equality forward through the recorded canonical digests and
check the selection criteria on the committed frames. None reads a source
file or runs the model.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from tests.fixtures.goes_cod.criteria import (
    STEP,
    WINDOW,
    nominal_slot,
    screen_window,
)
from tests.fixtures.goes_cod.cut import EXTENT
from tests.fixtures.goes_cod.materialize import (
    GRID,
    SCHEMA,
    SOURCE,
    canonical_digest,
    load_source,
    materialize,
    recorded_digests,
)

# Half of the 0.04 degree cell.
HALF_CELL = 0.02


def test_source_is_one_contiguous_window() -> None:
    _, _, frames = load_source(SOURCE)

    slots = [nominal_slot(frame.name) for frame in frames]

    assert len(slots) == WINDOW
    assert [later - earlier for earlier, later in zip(slots, slots[1:])] == [
        STEP
    ] * (WINDOW - 1)


def test_materialized_frames_match_the_recorded_digests(
    tmp_path: Path,
) -> None:
    recorded = recorded_digests(SOURCE)

    paths = materialize(SOURCE, tmp_path)

    assert paths == [tmp_path / "goes_processed" / key for key in recorded]
    for key, sha256 in recorded.items():
        table = pl.read_parquet(tmp_path / "goes_processed" / key)
        assert table.schema == SCHEMA, key
        assert canonical_digest(table) == sha256, key


def test_committed_fixture_meets_the_criteria() -> None:
    _, _, frames = load_source(SOURCE)

    screen = screen_window(
        [nominal_slot(frame.name) for frame in frames],
        [frame.cod for frame in frames],
    )

    assert screen.passed, screen


def test_grid_lies_on_the_declared_extent() -> None:
    latitude, longitude, _ = load_source(SOURCE)

    for values, (low, high) in zip((latitude, longitude), EXTENT, strict=True):
        assert len(values) == GRID
        assert abs(float(values[0]) - low) <= HALF_CELL, values[0]
        assert abs(float(values[-1]) - high) <= HALF_CELL, values[-1]
