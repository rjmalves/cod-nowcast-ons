"""Unit tests of the GOES COD regression fixture criteria.

Every scene is synthetic: Gaussian blobs on a 76 x 76 float32 grid, moved by
a whole number of cells per frame with ``np.roll``. None reads fixture data.
"""

from __future__ import annotations

import math
import warnings
from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt
import pytest

from tests.fixtures.goes_cod import criteria as c

GRID = 76
START = datetime(2025, 1, 3, 12, 0, tzinfo=UTC)
# (row, column, sigma, height) of three blobs, at least 10 cells from the
# edges at the start and after every step of the scenes below.
BLOBS = ((12, 12, 3.0, 100.0), (18, 24, 2.5, 70.0), (24, 16, 3.5, 85.0))

Grid = npt.NDArray[np.float32]


def _blobs() -> Grid:
    rows, columns = np.mgrid[0:GRID, 0:GRID]
    field = np.zeros((GRID, GRID))
    for row, column, sigma, height in BLOBS:
        distance = (rows - row) ** 2 + (columns - column) ** 2
        field += height * np.exp(-distance / (2 * sigma**2))
    return field.astype(np.float32)


def _keep_top(grid: Grid, count: int) -> Grid:
    """Keep the ``count`` highest pixels finite and set the rest to NaN."""
    order = np.argsort(-grid.ravel(), kind="stable")
    keep = np.zeros(grid.size, dtype=bool)
    keep[order[:count]] = True
    return np.where(keep.reshape(grid.shape), grid, np.float32(np.nan))


def _line(dy: int, dx: int, count: int = c.WINDOW) -> list[tuple[int, int]]:
    return [(k * dy, k * dx) for k in range(count)]


def _window(
    offsets: list[tuple[int, int]], keep: int | None = None
) -> list[Grid]:
    base = _blobs() if keep is None else _keep_top(_blobs(), keep)
    return [np.roll(base, offset, axis=(0, 1)) for offset in offsets]


def _slots(
    gap_before: int | None = None, count: int = c.WINDOW
) -> list[datetime]:
    slots = [START + k * c.STEP for k in range(count)]
    if gap_before is not None:
        slots[gap_before:] = [slot + c.STEP for slot in slots[gap_before:]]
    return slots


def _directions(screen: c.Screen) -> list[tuple[int, int]]:
    return [(dy, dx) for dy, dx, _ in screen.shifts]


def test_nominal_slot_parses_the_product_key() -> None:
    slot = c.nominal_slot("GOES_COD_BR_20250103-1250.parquet")

    assert slot == datetime(2025, 1, 3, 12, 50, tzinfo=UTC)
    assert slot.tzinfo is UTC
    for key in (
        "GOES_COD_BR_20250103-1250.csv",
        "GOES_COD_BR_20250103-125.parquet",
        "GOES_COD_BR_20250103-1250.parquet.bak",
        "goes_processed/GOES_COD_BR_20250103-1250.parquet",
        "GOES_COD_BR_20251301-1250.parquet",
        "",
    ):
        with pytest.raises(ValueError):
            c.nominal_slot(key)


def test_translating_scene_passes() -> None:
    slots = _slots()
    screen = c.screen_window(slots, _window(_line(1, 1)))

    assert screen.start == slots[0]
    assert screen.contiguous
    assert screen.finite_counts == (GRID * GRID,) * c.L
    assert _directions(screen) == [(1, 1)] * 4
    assert screen.translation
    assert screen.passed


def test_stationary_scene_fails_translation() -> None:
    screen = c.screen_window(_slots(), _window(_line(0, 0)))

    assert screen.contiguous
    assert _directions(screen) == [(0, 0)] * 4
    assert not screen.translation
    assert not screen.passed


def test_gap_fails_contiguity() -> None:
    slots = _slots(gap_before=3)
    assert slots[3] - slots[2] == 2 * c.STEP

    screen = c.screen_window(slots, _window(_line(1, 1)))

    assert screen.start == slots[0]
    assert not screen.contiguous
    assert screen.finite_counts == ()
    assert screen.shifts == ()
    assert not screen.translation
    assert not screen.passed

    for count in (c.WINDOW - 1, c.WINDOW + 1):
        run = _slots(count=count)
        assert all(
            later - earlier == c.STEP for earlier, later in zip(run, run[1:])
        )

        screen = c.screen_window(run, _window(_line(1, 1, count)))

        assert screen.start == run[0]
        assert not screen.contiguous
        assert screen.finite_counts == ()
        assert screen.shifts == ()
        assert not screen.translation
        assert not screen.passed


def test_499_finite_pixels_fail_the_sample_size() -> None:
    grids = _window(_line(1, 1))
    grids[c.P + 1] = _keep_top(grids[c.P + 1], 499)

    screen = c.screen_window(_slots(), grids)

    assert screen.finite_counts[1] == 499
    assert screen.translation
    assert not screen.passed


def test_500_finite_pixels_pass() -> None:
    grids = _window(_line(1, 1))
    grids[c.P + 1] = _keep_top(grids[c.P + 1], 500)

    screen = c.screen_window(_slots(), grids)

    assert screen.finite_counts[1] == 500
    assert screen.translation
    assert screen.passed


def test_translating_scene_over_a_mostly_nan_background_passes() -> None:
    grids = _window(_line(1, 1), keep=600)

    screen = c.screen_window(_slots(), grids)

    assert all(np.isnan(grid).mean() >= 0.85 for grid in grids)
    assert all(count >= c.MIN_FINITE for count in screen.finite_counts)
    assert _directions(screen) == [(1, 1)] * 4
    assert screen.passed


def test_shift_of_four_cells_passes() -> None:
    screen = c.screen_window(_slots(), _window(_line(4, 0)))

    assert _directions(screen) == [(4, 0)] * 4
    assert screen.passed


def test_shift_at_the_window_edge_fails() -> None:
    screen = c.screen_window(_slots(), _window(_line(5, 0)))

    assert _directions(screen) == [(5, 0)] * 4
    assert not screen.translation
    assert not screen.passed


def test_all_nan_pair_ties_to_the_zero_shift() -> None:
    nan = np.full((GRID, GRID), np.nan, dtype=np.float32)

    assert c.best_shift(nan, nan) == (0, 0, -math.inf)


def test_opposite_directions_fail() -> None:
    offsets = [(0, 0), (1, 1), (2, 2), (1, 1), (0, 0)]

    screen = c.screen_window(_slots(), _window(offsets))

    assert _directions(screen) == [(1, 1), (1, 1), (-1, -1), (-1, -1)]
    assert not screen.translation
    assert not screen.passed

    perpendicular = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]

    screen = c.screen_window(_slots(), _window(perpendicular))

    assert _directions(screen) == [(1, 0), (1, 0), (0, 1), (0, 1)]
    assert not screen.translation
    assert not screen.passed


def test_constant_frame_fails_translation_without_raising() -> None:
    grids = _window(_line(1, 1))
    grids[0] = np.zeros((GRID, GRID), dtype=np.float32)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        screen = c.screen_window(_slots(), grids)

    assert screen.shifts[0] == (0, 0, -math.inf)
    assert not screen.translation
    assert not screen.passed
