"""Cut and screen the candidate windows of the GOES COD regression fixture.

The operator supplies full-grid ``GOES_COD_BR`` frames in a local directory
outside the repository. ``read_cut`` keeps the ``EXTENT`` box of one frame.
``python -m tests.fixtures.goes_cod.cut screen SRC_DIR`` screens the
candidate windows with ``criteria.screen_window``, in ascending start time,
and stops at the first one that passes.

``convert SRC_DIR START`` screens the window at ``START`` again and writes
its frames to the text source ``materialize.SOURCE``. ``verify SRC_DIR``
checks that text against the source files, by file sha256, exact table
equality, bit equality and canonical digest.

Only file names that match the product key are ever read, and no output
names the directory. The module imports only the standard library, numpy,
polars and its sibling fixture modules, and it runs no model.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

import numpy as np
import numpy.typing as npt
import polars as pl
from polars.testing import assert_frame_equal

from tests.fixtures.goes_cod.criteria import (
    STEP,
    WINDOW,
    Screen,
    nominal_slot,
    screen_window,
)
from tests.fixtures.goes_cod.materialize import (
    COLUMNS,
    GRID,
    SCHEMA,
    SOURCE,
    Frame,
    canonical_digest,
    dump_source,
    frame_table,
    load_source,
    recorded_digests,
)

PRODUCT: Final = "GOES_COD_BR"
EXTENT: Final = ((-23.0, -20.0), (-50.0, -47.0))
FULL_GRID: Final = 1251
FULL_EXTENT: Final = ((-40.0, 10.0), (-80.0, -30.0))

_PRODUCT_KEY: Final = re.compile(rf"{PRODUCT}_\d{{8}}-\d{{4}}\.parquet")
_USAGE: Final = (
    "usage: python -m tests.fixtures.goes_cod.cut screen SRC_DIR\n"
    "       python -m tests.fixtures.goes_cod.cut convert SRC_DIR START\n"
    "       python -m tests.fixtures.goes_cod.cut verify SRC_DIR"
)
_TABLE_HEADER: Final = (
    "| start | contiguous | finite counts | shifts | translation | passed |"
)
_TABLE_SEPARATOR: Final = "| --- | --- | --- | --- | --- | --- |"
_START_FORMAT: Final = "%Y-%m-%dT%H:%MZ"

Coordinates = npt.NDArray[np.float64]
Grid = npt.NDArray[np.float32]


class _Box(NamedTuple):
    """The ``read_cut`` result of one cached frame, with its file name."""

    name: str
    latitude: Coordinates
    longitude: Coordinates
    time: datetime
    grid: Grid


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
    """Run ``python -m tests.fixtures.goes_cod.cut`` with a subcommand.

    The subcommands are ``screen SRC_DIR``, ``convert SRC_DIR START`` and
    ``verify SRC_DIR``.

    Returns:
        0 when the subcommand succeeds and 1 when it fails: no candidate
        passes, the ``START`` window does not pass, or a frame does not
        verify. 2, after the usage lines on stderr, when the arguments are
        wrong, ``SRC_DIR`` is not a directory, ``START`` is not in
        ``%Y-%m-%dT%H:%MZ`` or, for ``screen``, no file name in ``SRC_DIR``
        matches the product key.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) == 2 and args[0] == "screen":
        return _screen(Path(args[1]))
    if len(args) == 3 and args[0] == "convert":
        return _convert(Path(args[1]), args[2])
    if len(args) == 2 and args[0] == "verify":
        return _verify(Path(args[1]))
    return _usage(
        "expected screen SRC_DIR, convert SRC_DIR START or verify SRC_DIR"
    )


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
            cache[slot] = _Box(path.name, *read_cut(path))
        box = cache[slot]
        if first is None:
            first = box
        elif not (
            np.array_equal(box.latitude, first.latitude)
            and np.array_equal(box.longitude, first.longitude)
        ):
            raise ValueError(
                f"{first.name} and {box.name} have different coordinates"
            )
        slots.append(slot)
        grids.append(box.grid)
    return screen_window(slots, grids)


def _convert(src_dir: Path, start_text: str) -> int:
    """Screen the window at ``start_text`` again and write it to ``SOURCE``.

    Each file is read once. The text is written only when the window
    passes and ``dump_source`` accepts every frame.

    Raises:
        ValueError: If ``read_cut`` rejects a frame, if two frames have
            different coordinates, or if ``dump_source`` rejects a ``cod``
            NaN payload. The message names the file.
    """
    if not src_dir.is_dir():
        return _usage("SRC_DIR is not a directory")
    try:
        start = datetime.strptime(start_text, _START_FORMAT)
    except ValueError:
        return _usage(f"START is not in {_START_FORMAT}")
    start = start.replace(tzinfo=UTC)
    paths = dict(candidates(src_dir)).get(start)
    cache: dict[datetime, _Box] = {}
    if paths is None or not _screen_window(start, paths, cache).passed:
        print(
            f"window {start.strftime(_START_FORMAT)} does not pass",
            file=sys.stderr,
        )
        return 1
    # A passing window is contiguous, so the cache holds all of its slots.
    boxes = [cache[start + k * STEP] for k in range(WINDOW)]
    frames = [
        Frame(
            name=box.name,
            time=box.time,
            source_sha256=_file_sha256(src_dir / box.name),
            cod=box.grid,
        )
        for box in boxes
    ]
    text = dump_source(boxes[0].latitude, boxes[0].longitude, frames)
    SOURCE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(frames)} frames")
    return 0


def _verify(src_dir: Path) -> int:
    """Check every frame of ``SOURCE`` against its file in ``src_dir``."""
    if not src_dir.is_dir():
        return _usage("SRC_DIR is not a directory")
    latitude, longitude, frames = load_source(SOURCE)
    recorded = recorded_digests(SOURCE)
    for frame in frames:
        failed = _failed_check(
            src_dir / frame.name,
            latitude,
            longitude,
            frame,
            recorded[frame.name],
        )
        if failed is not None:
            print(f"mismatch: {frame.name}: {failed}", file=sys.stderr)
            return 1
    print(f"{len(frames)} frames verified")
    return 0


def _failed_check(
    path: Path,
    latitude: Coordinates,
    longitude: Coordinates,
    frame: Frame,
    sha256: str,
) -> str | None:
    """Return the first check that ``frame`` fails against ``path``, if any.

    The checks run in order: the name is a product key and ``path`` exists,
    the file sha256 equals ``frame.source_sha256``, ``frame_table`` equals
    ``cut_table`` exactly, every column is equal bit for bit, and the
    canonical digest of the cut equals the recorded ``sha256``.
    """
    if not _PRODUCT_KEY.fullmatch(frame.name):
        return "not a product key"
    if not path.is_file():
        return "missing source file"
    if _file_sha256(path) != frame.source_sha256:
        return "source sha256"
    expected = frame_table(latitude, longitude, frame)
    actual = cut_table(path)
    try:
        assert_frame_equal(expected, actual, check_exact=True)
    except AssertionError:
        return "frame table"
    expected_bits, actual_bits = _bits(expected), _bits(actual)
    for name in COLUMNS:
        if not np.array_equal(expected_bits[name], actual_bits[name]):
            return f"{name} bits"
    if canonical_digest(actual) != sha256:
        return "canonical digest"
    return None


def _bits(table: pl.DataFrame) -> dict[str, npt.NDArray[np.integer]]:
    """Return each column of a frame table as integers, bit for bit.

    ``cod`` is viewed as uint32, so ``-0.0``, tiny negatives and every NaN
    pattern compare by their bits. The coordinates are viewed as uint64 and
    ``time`` is int64 microseconds since the epoch.
    """
    return {
        "time": table["time"].dt.epoch("us").to_numpy(),
        "latitude": _view(table["latitude"], np.float64, np.uint64),
        "longitude": _view(table["longitude"], np.float64, np.uint64),
        "cod": _view(table["cod"], np.float32, np.uint32),
    }


def _view(
    column: pl.Series,
    dtype: type[np.floating],
    bits: type[np.unsignedinteger],
) -> npt.NDArray[np.unsignedinteger]:
    return np.ascontiguousarray(column.to_numpy(), dtype=dtype).view(bits)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
