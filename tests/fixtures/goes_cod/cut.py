"""Cut and screen the candidate windows of the GOES COD regression fixture.

The operator supplies full-grid ``GOES_COD_BR`` frames in a local directory
outside the repository. ``read_cut`` keeps the ``EXTENT`` box of one frame.
``python -m tests.fixtures.goes_cod.cut screen SRC_DIR`` screens the
candidate windows with ``criteria.screen_window``, in ascending start time,
and stops at the first one that passes.

Only file names that match the product key are ever read, and no output
names the directory. The module imports only the standard library, numpy,
polars and its sibling fixture modules, and it runs no model.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import polars as pl

from tests.fixtures.goes_cod.criteria import (
    STEP,
    WINDOW,
    Screen,
    nominal_slot,
    screen_window,
)
from tests.fixtures.goes_cod.materialize import GRID, SCHEMA

PRODUCT: Final = "GOES_COD_BR"
EXTENT: Final = ((-23.0, -20.0), (-50.0, -47.0))
FULL_GRID: Final = 1251
FULL_EXTENT: Final = ((-40.0, 10.0), (-80.0, -30.0))

_PRODUCT_KEY: Final = re.compile(rf"{PRODUCT}_\d{{8}}-\d{{4}}\.parquet")
_USAGE: Final = "usage: python -m tests.fixtures.goes_cod.cut screen SRC_DIR"
_TABLE_HEADER: Final = (
    "| start | contiguous | finite counts | shifts | translation | passed |"
)
_TABLE_SEPARATOR: Final = "| --- | --- | --- | --- | --- | --- |"
_START_FORMAT: Final = "%Y-%m-%dT%H:%MZ"

Coordinates = npt.NDArray[np.float64]
Grid = npt.NDArray[np.float32]
# The file name, latitudes, longitudes and grid of one cached box.
_Box = tuple[str, Coordinates, Coordinates, Grid]


def cut_table(path: Path) -> pl.DataFrame:
    """Read a full-grid frame and return its rows inside ``EXTENT``.

    The rows kept have both coordinates inside ``EXTENT``, bounds included,
    and stay in file order.

    Raises:
        ValueError: If the schema differs from ``SCHEMA``, column order
            included, if the table is not ``FULL_GRID * FULL_GRID`` rows
            spanning ``FULL_EXTENT``, if ``cod`` holds a null, or if the box
            holds other than ``GRID * GRID`` rows. The message names
            ``path.name`` and the failed check.
    """
    table = pl.read_parquet(path)
    if list(table.schema.items()) != list(SCHEMA.items()):
        raise ValueError(
            f"{path.name}: schema is {dict(table.schema)}, "
            f"expected {dict(SCHEMA)}"
        )
    if table.height != FULL_GRID * FULL_GRID:
        raise ValueError(
            f"{path.name}: holds {table.height} rows, "
            f"expected {FULL_GRID * FULL_GRID}"
        )
    latitude = table["latitude"].to_numpy()
    longitude = table["longitude"].to_numpy()
    extent = (
        (float(latitude.min()), float(latitude.max())),
        (float(longitude.min()), float(longitude.max())),
    )
    if extent != FULL_EXTENT:
        raise ValueError(
            f"{path.name}: spans latitude and longitude {extent}, "
            f"expected {FULL_EXTENT}"
        )
    nulls = table["cod"].null_count()
    if nulls != 0:
        raise ValueError(f"{path.name}: cod holds {nulls} nulls, expected 0")
    (south, north), (west, east) = EXTENT
    box = table.filter(
        pl.col("latitude").is_between(south, north, closed="both")
        & pl.col("longitude").is_between(west, east, closed="both")
    )
    if box.height != GRID * GRID:
        raise ValueError(
            f"{path.name}: box {EXTENT} holds {box.height} rows, "
            f"expected {GRID * GRID}"
        )
    return box


def read_cut(path: Path) -> tuple[Coordinates, Coordinates, datetime, Grid]:
    """Read the ``EXTENT`` box of a full-grid frame as a grid.

    Returns:
        The ``GRID`` ascending latitudes and longitudes of the box, the
        aware scan time and the ``(GRID, GRID)`` float32 ``cod`` grid, whose
        row ``i`` is ``latitude[i]`` and column ``j`` is ``longitude[j]``.
        No ``cod`` value is changed.

    Raises:
        ValueError: If ``cut_table`` rejects the frame, if the box holds
            more than one scan time, if it does not have ``GRID`` distinct
            latitudes and longitudes, or if its rows are not in C order,
            latitude ascending and then longitude ascending. The message
            names ``path.name`` and the failed check.
    """
    table = cut_table(path)
    times = table["time"].unique()
    if times.len() != 1:
        raise ValueError(
            f"{path.name}: holds {times.len()} scan times, expected 1"
        )
    time: datetime = times.item()
    row_latitude = table["latitude"].to_numpy()
    row_longitude = table["longitude"].to_numpy()
    latitude = np.unique(row_latitude)
    longitude = np.unique(row_longitude)
    if latitude.size != GRID or longitude.size != GRID:
        raise ValueError(
            f"{path.name}: box has {latitude.size} latitudes and "
            f"{longitude.size} longitudes, expected {GRID} each"
        )
    if not (
        np.array_equal(row_latitude, np.repeat(latitude, GRID))
        and np.array_equal(row_longitude, np.tile(longitude, GRID))
    ):
        raise ValueError(
            f"{path.name}: box rows are not in C order, latitude ascending "
            "and then longitude ascending"
        )
    cod = np.array(table["cod"].to_numpy(), dtype=np.float32)
    return latitude, longitude, time, cod.reshape(GRID, GRID)


def candidates(src_dir: Path) -> list[tuple[datetime, list[Path | None]]]:
    """List the candidate windows of the frames in ``src_dir``.

    Only the names directly in ``src_dir`` that match the product key
    ``GOES_COD_BR_YYYYMMDD-HHMM.parquet`` are kept, and no file is opened.
    The nominal slot of each kept file starts a window of ``WINDOW`` slots,
    ``STEP`` apart.

    Returns:
        ``(start, paths)`` for each window in ascending start, where
        ``paths[k]`` is the kept file of slot ``start + k * STEP``, or
        ``None`` when there is none.
    """
    by_slot = {
        nominal_slot(path.name): path
        for path in src_dir.glob(f"{PRODUCT}_*.parquet")
        if _PRODUCT_KEY.fullmatch(path.name)
    }
    return [
        (start, [by_slot.get(start + k * STEP) for k in range(WINDOW)])
        for start in sorted(by_slot)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``python -m tests.fixtures.goes_cod.cut screen SRC_DIR``.

    Returns:
        0 when a candidate passes and 1 when none does. 2, after a usage
        line on stderr, when the arguments are wrong, ``SRC_DIR`` is not a
        directory or no file name in it matches the product key.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) == 2 and args[0] == "screen":
        return _screen(Path(args[1]))
    return _usage("expected the screen subcommand and one SRC_DIR")


def _screen(src_dir: Path) -> int:
    """Screen the windows of ``src_dir`` and print the Markdown table.

    The screen stops after the first window that passes. Each file is read
    once, and the cache holds at most ``WINDOW`` box grids, those of the
    current window's slots.

    Raises:
        ValueError: If ``read_cut`` rejects a frame, or if two frames of one
            window have different coordinates. The message names the files.
    """
    if not src_dir.is_dir():
        return _usage("SRC_DIR is not a directory")
    windows = candidates(src_dir)
    if not windows:
        return _usage(
            f"no file name in SRC_DIR matches {PRODUCT}_YYYYMMDD-HHMM.parquet"
        )
    print(_TABLE_HEADER)
    print(_TABLE_SEPARATOR)
    cache: dict[datetime, _Box] = {}
    for index, (start, paths) in enumerate(windows):
        screen = _screen_window(start, paths, cache)
        print(_row(screen))
        if screen.passed:
            print(f"not screened: {len(windows) - index - 1}")
            print(f"first passing: {start.strftime(_START_FORMAT)}")
            return 0
    print("not screened: 0")
    print("no candidate passes")
    return 1


def _screen_window(
    start: datetime, paths: Sequence[Path | None], cache: dict[datetime, _Box]
) -> Screen:
    for slot in [slot for slot in cache if slot < start]:
        del cache[slot]
    slots: list[datetime] = []
    grids: list[Grid] = []
    first: _Box | None = None
    for k, path in enumerate(paths):
        if path is None:
            continue
        slot = start + k * STEP
        if slot not in cache:
            latitude, longitude, _, grid = read_cut(path)
            cache[slot] = (path.name, latitude, longitude, grid)
        box = cache[slot]
        if first is None:
            first = box
        elif not (
            np.array_equal(box[1], first[1])
            and np.array_equal(box[2], first[2])
        ):
            raise ValueError(
                f"{first[0]} and {box[0]} have different coordinates"
            )
        slots.append(slot)
        grids.append(box[3])
    return screen_window(slots, grids)


def _row(screen: Screen) -> str:
    cells = (
        screen.start.strftime(_START_FORMAT),
        _yes_no(screen.contiguous),
        ", ".join(str(count) for count in screen.finite_counts),
        ", ".join(
            f"({dy},{dx}) {score:.3f}" for dy, dx, score in screen.shifts
        ),
        _yes_no(screen.translation),
        _yes_no(screen.passed),
    )
    return "| " + " | ".join(cells) + " |"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _usage(reason: str) -> int:
    print(_USAGE, file=sys.stderr)
    print(f"error: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
