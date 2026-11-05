"""Unit tests of the GOES COD candidate cut and screen.

Every frame is synthetic: a full 1251 x 1251 grid written to ``tmp_path``,
NaN outside the ``EXTENT`` box and a blob field inside it. None reads
supplied frames.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

from tests.fixtures.goes_cod import cut
from tests.fixtures.goes_cod.criteria import STEP, WINDOW
from tests.fixtures.goes_cod.materialize import GRID, SCHEMA

Grid = npt.NDArray[np.float32]

LATITUDE: npt.NDArray[np.float64] = np.round(
    -40.0 + 0.04 * np.arange(cut.FULL_GRID), 2
)
LONGITUDE: npt.NDArray[np.float64] = np.round(
    -80.0 + 0.04 * np.arange(cut.FULL_GRID), 2
)
(SOUTH, NORTH), (WEST, EAST) = cut.EXTENT
BOX_ROWS = np.flatnonzero((LATITUDE >= SOUTH) & (LATITUDE <= NORTH))
BOX_COLUMNS = np.flatnonzero((LONGITUDE >= WEST) & (LONGITUDE <= EAST))
START = datetime(2024, 2, 7, 12, 0, tzinfo=UTC)
SCAN_DELAY = timedelta(seconds=20.5)
# (row, column, sigma, height) of three blobs inside the box, at least 10
# cells from its edges after every move of the scenes below.
BLOBS = ((20, 20, 3.0, 100.0), (28, 34, 2.5, 70.0), (36, 24, 3.5, 85.0))
HEADER = (
    "| start | contiguous | finite counts | shifts | translation | passed |"
)
SEPARATOR = "| --- | --- | --- | --- | --- | --- |"


def _blobs(offset: int = 0) -> Grid:
    """The blob field with every blob moved by ``(offset, offset)`` cells."""
    rows, columns = np.mgrid[0:GRID, 0:GRID]
    field = np.zeros((GRID, GRID))
    for row, column, sigma, height in BLOBS:
        distance = (rows - row - offset) ** 2 + (columns - column - offset) ** 2
        field += height * np.exp(-distance / (2 * sigma**2))
    return field.astype(np.float32)


def _slot(k: int) -> datetime:
    return START + k * STEP


def _name(slot: datetime) -> str:
    return f"GOES_COD_BR_{slot:%Y%m%d-%H%M}.parquet"


def _text(slot: datetime) -> str:
    return f"{slot:%Y-%m-%dT%H:%M}Z"


def _table(slot: datetime, box: Grid) -> pl.DataFrame:
    """A full-grid frame in C order, with ``box`` inside ``EXTENT``."""
    cod = np.full((cut.FULL_GRID, cut.FULL_GRID), np.nan, dtype=np.float32)
    cod[np.ix_(BOX_ROWS, BOX_COLUMNS)] = box
    table = pl.DataFrame(
        {
            "latitude": np.repeat(LATITUDE, cut.FULL_GRID),
            "longitude": np.tile(LONGITUDE, cut.FULL_GRID),
            "cod": cod.reshape(-1),
        }
    ).select(
        pl.lit(slot + SCAN_DELAY, dtype=SCHEMA["time"]).alias("time"),
        "latitude",
        "longitude",
        "cod",
    )
    assert list(table.schema.items()) == list(SCHEMA.items())
    return table


def _write(directory: Path, slot: datetime, table: pl.DataFrame) -> Path:
    path = directory / _name(slot)
    table.write_parquet(path)
    return path


def _scene(directory: Path, boxes: list[Grid]) -> list[Path]:
    """Write ``boxes[k]`` as the frame of slot ``k``."""
    return [
        _write(directory, _slot(k), _table(_slot(k), box))
        for k, box in enumerate(boxes)
    ]


def test_read_cut_returns_the_76_by_76_box(tmp_path: Path) -> None:
    box = _blobs()
    box[5, 5] = -0.0
    box[6, 6] = np.float32(-5e-13)
    box[7, 7] = np.nan
    path = _write(tmp_path, START, _table(START, box))

    latitude, longitude, time, cod = cut.read_cut(path)

    assert latitude.shape == (GRID,)
    assert longitude.shape == (GRID,)
    assert (latitude[0], latitude[-1]) == (-23.0, -20.0)
    assert (longitude[0], longitude[-1]) == (-50.0, -47.0)
    np.testing.assert_array_equal(
        latitude.view(np.uint64), LATITUDE[BOX_ROWS].view(np.uint64)
    )
    np.testing.assert_array_equal(
        longitude.view(np.uint64), LONGITUDE[BOX_COLUMNS].view(np.uint64)
    )
    assert time == START + SCAN_DELAY
    assert time.utcoffset() == timedelta(0)
    assert cod.dtype == np.float32
    assert cod.shape == (GRID, GRID)
    bits = cod.view(np.uint32)
    assert int(bits[5, 5]) == 0x80000000
    assert int(bits[6, 6]) == int(
        np.array([-5e-13], np.float32).view(np.uint32)[0]
    )
    np.testing.assert_array_equal(bits, box.view(np.uint32))


def test_read_cut_rejects_rows_out_of_c_order(tmp_path: Path) -> None:
    table = _table(START, _blobs())
    first = int(BOX_ROWS[0]) * cut.FULL_GRID + int(BOX_COLUMNS[0])
    order = np.arange(table.height)
    order[[first, first + 1]] = order[[first + 1, first]]
    path = _write(tmp_path, START, table[order])

    with pytest.raises(ValueError, match="not in C order") as error:
        cut.read_cut(path)

    assert path.name in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_read_cut_rejects_a_frame_off_the_full_grid(tmp_path: Path) -> None:
    table = _table(START, _blobs())
    one_row_removed = _write(tmp_path, _slot(0), table.slice(1))
    one_null_cod = _write(
        tmp_path,
        _slot(1),
        table.with_columns(
            pl.when(pl.int_range(pl.len()) == 0)
            .then(None)
            .otherwise(pl.col("cod"))
            .alias("cod")
        ),
    )

    for path, check in ((one_row_removed, "rows"), (one_null_cod, "nulls")):
        with pytest.raises(ValueError, match=check) as error:
            cut.read_cut(path)
        assert path.name in str(error.value)
        assert str(tmp_path) not in str(error.value)


def test_candidates_follow_start_order_with_missing_slots_as_none(
    tmp_path: Path,
) -> None:
    paths = {k: tmp_path / _name(_slot(k)) for k in (6, 0, 3, 1)}
    for path in paths.values():
        path.touch()

    windows = cut.candidates(tmp_path)

    p0, p1, p3, p6 = paths[0], paths[1], paths[3], paths[6]
    assert windows == [
        (_slot(0), [p0, p1, None, p3, None]),
        (_slot(1), [p1, None, p3, None, None]),
        (_slot(3), [p3, None, None, p6, None]),
        (_slot(6), [p6, None, None, None, None]),
    ]
    assert all(len(window) == WINDOW for _, window in windows)


def test_candidates_ignore_files_outside_the_product_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "SENTINEL-not-a-frame-4f1c"
    (tmp_path / "notes.txt").write_text(sentinel, encoding="utf-8")
    (tmp_path / "other.parquet").write_bytes(b"not a parquet file")
    (tmp_path / f"{_name(_slot(1))}.bak").write_bytes(b"not a parquet file")
    (frame,) = _scene(tmp_path, [_blobs()])

    windows = cut.candidates(tmp_path)
    status = cut.main(["screen", str(tmp_path)])

    assert windows == [(_slot(0), [frame, None, None, None, None])]
    assert status == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    for absent in (sentinel, "notes.txt", "other.parquet", ".bak"):
        assert absent not in output


def test_screen_stops_at_the_first_pass_after_a_degenerate_window(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zeros = np.zeros((GRID, GRID), dtype=np.float32)
    paths = _scene(tmp_path, [zeros] + [_blobs(k) for k in range(1, 7)])
    read: list[str] = []
    read_cut = cut.read_cut

    def counting_read_cut(
        path: Path,
    ) -> tuple[
        npt.NDArray[np.float64], npt.NDArray[np.float64], datetime, Grid
    ]:
        read.append(path.name)
        return read_cut(path)

    monkeypatch.setattr(cut, "read_cut", counting_read_cut)

    status = cut.main(["screen", str(tmp_path)])

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert status == 0
    assert lines[:2] == [HEADER, SEPARATOR]
    assert lines[2] == (
        f"| {_text(_slot(0))} | yes | 5776, 5776, 5776 | "
        "(0,0) -inf, (1,1) 1.000, (1,1) 1.000, (1,1) 1.000 | no | no |"
    )
    assert lines[3] == (
        f"| {_text(_slot(1))} | yes | 5776, 5776, 5776 | "
        "(1,1) 1.000, (1,1) 1.000, (1,1) 1.000, (1,1) 1.000 | yes | yes |"
    )
    assert lines[4:] == ["not screened: 5", f"first passing: {_text(_slot(1))}"]
    assert read == [path.name for path in paths[:6]]
    assert str(tmp_path) not in captured.out + captured.err


def test_screen_exits_1_when_no_candidate_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _scene(tmp_path, [_blobs()] * WINDOW)

    status = cut.main(["screen", str(tmp_path)])

    lines = capsys.readouterr().out.splitlines()
    assert status == 1
    assert lines[:2] == [HEADER, SEPARATOR]
    assert lines[2] == (
        f"| {_text(_slot(0))} | yes | 5776, 5776, 5776 | "
        "(0,0) 1.000, (0,0) 1.000, (0,0) 1.000, (0,0) 1.000 | no | no |"
    )
    assert lines[3:-2] == [
        f"| {_text(_slot(k))} | no |  |  | no | no |" for k in range(1, WINDOW)
    ]
    assert lines[-2:] == ["not screened: 0", "no candidate passes"]


def test_screen_usage_errors_exit_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unmatched = tmp_path / "unmatched"
    unmatched.mkdir()
    (unmatched / "notes.txt").write_text("notes", encoding="utf-8")
    a_file = tmp_path / "a_file"
    a_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cut.py"])

    statuses = [
        cut.main(),
        cut.main([]),
        cut.main(["screen"]),
        cut.main(["scan", str(unmatched)]),
        cut.main(["screen", str(unmatched), "extra"]),
        cut.main(["screen", str(tmp_path / "missing")]),
        cut.main(["screen", str(a_file)]),
        cut.main(["screen", str(unmatched)]),
    ]

    captured = capsys.readouterr()
    assert statuses == [2] * 8
    assert captured.out == ""
    assert captured.err.count(
        "usage: python -m tests.fixtures.goes_cod.cut screen SRC_DIR\n"
    ) == len(statuses)
    assert str(tmp_path) not in captured.err
    assert "notes.txt" not in captured.err
