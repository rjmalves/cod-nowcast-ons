"""Unit tests of the GOES COD frame text-source materializer.

Every test builds synthetic frames. None reads fixture data.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

from tests.fixtures.goes_cod import materialize as m

LATITUDE: npt.NDArray[np.float64] = np.round(
    -23.0 + 0.04 * np.arange(76), 2
).astype(np.float64)
LONGITUDE: npt.NDArray[np.float64] = np.round(
    -50.0 + 0.04 * np.arange(76), 2
).astype(np.float64)

NEGATIVE_ZERO_BITS = 0x80000000
TINY_NEGATIVE_BITS = int(np.array([-5e-13], np.float32).view(np.uint32)[0])
NEGATIVE_NAN_BITS = 0xFFC00000
NAN_BITS = 0x7FC00000


def _float32_from_bits(bits: int) -> np.float32:
    value: np.float32 = np.array([bits], np.uint32).view(np.float32)[0]
    return value


@pytest.fixture
def frames() -> list[m.Frame]:
    """Two synthetic frames, listed out of chronological order."""
    rng = np.random.default_rng(0)
    grids = rng.uniform(0.0, 120.0, size=(2, m.GRID, m.GRID)).astype(np.float32)
    grids[:, 0, :3] = np.nan
    grids[:, 40, 7] = np.nan
    grids[1, 5, 5] = -0.0
    grids[1, 6, 6] = np.float32(-5e-13)
    grids[1, 7, 7] = _float32_from_bits(NEGATIVE_NAN_BITS)
    return [
        m.Frame(
            name="GOES_COD_BR_20240801-0020.parquet",
            time=datetime(2024, 8, 1, 0, 20, 20, 774516, tzinfo=UTC),
            source_sha256="ab" * 32,
            cod=grids[0].copy(),
        ),
        m.Frame(
            name="GOES_COD_BR_20240801-0010.parquet",
            time=datetime(2024, 8, 1, 0, 10, 20, 123456, tzinfo=UTC),
            source_sha256="cd" * 32,
            cod=grids[1].copy(),
        ),
    ]


@pytest.fixture
def source(
    tmp_path_factory: pytest.TempPathFactory, frames: list[m.Frame]
) -> Path:
    """The dumped text source, outside the test's own ``tmp_path``."""
    path = tmp_path_factory.mktemp("source") / "frames.toml"
    path.write_text(
        m.dump_source(LATITUDE, LONGITUDE, frames), encoding="utf-8"
    )
    return path


def test_dump_then_load_round_trips_bitwise(
    frames: list[m.Frame], source: Path
) -> None:
    special = frames[1].cod.view(np.uint32)
    assert int(special[0, 0]) == NAN_BITS
    assert int(special[5, 5]) == NEGATIVE_ZERO_BITS
    assert int(special[6, 6]) == TINY_NEGATIVE_BITS
    assert int(special[7, 7]) == NEGATIVE_NAN_BITS
    text = source.read_text(encoding="utf-8")

    latitude, longitude, loaded = m.load_source(source)

    assert text.splitlines()[:2] == [
        "# Generated file: do not edit by hand. "
        "Provenance: README.md in this directory.",
        "# materialize.py recomputes every sha256 before it writes a frame.",
    ]
    assert "-nan" in text
    assert latitude.dtype == np.float64
    assert longitude.dtype == np.float64
    np.testing.assert_array_equal(
        latitude.view(np.uint64), LATITUDE.view(np.uint64)
    )
    np.testing.assert_array_equal(
        longitude.view(np.uint64), LONGITUDE.view(np.uint64)
    )
    assert [f.name for f in loaded] == [f.name for f in frames]
    assert [f.time for f in loaded] == [f.time for f in frames]
    assert [f.source_sha256 for f in loaded] == [
        f.source_sha256 for f in frames
    ]
    for before, after in zip(frames, loaded, strict=True):
        assert after.cod.dtype == np.float32
        np.testing.assert_array_equal(
            after.cod.view(np.uint32), before.cod.view(np.uint32)
        )
    assert m.dump_source(latitude, longitude, loaded) == text


def test_recorded_digest_is_the_canonical_digest(
    frames: list[m.Frame], source: Path
) -> None:
    recorded = m.recorded_digests(source)

    assert recorded == {
        frame.name: m.canonical_digest(
            m.frame_table(LATITUDE, LONGITUDE, frame)
        )
        for frame in frames
    }
    frame = frames[1]
    table = m.frame_table(LATITUDE, LONGITUDE, frame)
    assert table.schema == m.SCHEMA
    assert table.row(m.GRID + 2)[1:3] == (LATITUDE[1], LONGITUDE[2])
    epoch_us = (frame.time - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(
        microseconds=1
    )
    expected = hashlib.sha256()
    for name, arrow_type, values in (
        ("time", "timestamp[us, tz=UTC]", np.full(m.GRID**2, epoch_us, "<i8")),
        ("latitude", "double", np.repeat(LATITUDE, m.GRID).astype("<f8")),
        ("longitude", "double", np.tile(LONGITUDE, m.GRID).astype("<f8")),
        ("cod", "float", frame.cod.reshape(-1).astype("<f4")),
    ):
        expected.update(name.encode() + b"\0" + arrow_type.encode() + b"\0")
        expected.update(values.tobytes())
    assert recorded[frame.name] == expected.hexdigest()
    with pytest.raises(ValueError, match="'cod'"):
        m.canonical_digest(table.with_columns(pl.col("cod").cast(pl.Float64)))


def test_frame_objects_rejects_a_changed_digest(
    frames: list[m.Frame], source: Path, tmp_path: Path
) -> None:
    key = frames[1].name
    recorded = m.recorded_digests(source)[key]
    changed = tmp_path / "frames.toml"
    changed.write_text(
        source.read_text(encoding="utf-8").replace(recorded, "0" * 64),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match=f"digest mismatch for {re.escape(key)}"
    ):
        m.frame_objects(changed)


def test_load_source_rejects_a_wrong_grid_shape(
    frames: list[m.Frame], source: Path, tmp_path: Path
) -> None:
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    first_row = next(
        i for i, line in enumerate(lines) if line.startswith("  [")
    )
    missing_row = tmp_path / "missing_row.toml"
    missing_row.write_text(
        "".join(lines[:first_row] + lines[first_row + 1 :]), encoding="utf-8"
    )
    ragged = tmp_path / "ragged.toml"
    short_row = "  [" + lines[first_row].split(", ", 1)[1]
    ragged.write_text(
        "".join(lines[:first_row] + [short_row] + lines[first_row + 1 :]),
        encoding="utf-8",
    )
    short_latitude = tmp_path / "short_latitude.toml"
    short_latitude.write_text(
        "".join(
            "latitude = [" + line.split(", ", 1)[1]
            if line.startswith("latitude = ")
            else line
            for line in lines
        ),
        encoding="utf-8",
    )
    key = re.escape(frames[0].name)

    with pytest.raises(ValueError, match=rf"{key}: cod has shape \(75, 76\)"):
        m.load_source(missing_row)
    with pytest.raises(ValueError, match=rf"{key}: cod is not a 76 x 76 grid"):
        m.load_source(ragged)
    with pytest.raises(ValueError, match=r"latitude has shape \(75,\)"):
        m.load_source(short_latitude)


def test_dump_source_rejects_an_unknown_nan_payload(
    frames: list[m.Frame],
) -> None:
    cod = frames[0].cod.copy()
    cod[3, 4] = _float32_from_bits(0x7FC00001)
    assert int(cod.view(np.uint32)[3, 4]) == 0x7FC00001
    frame = dataclasses.replace(frames[0], cod=cod)

    with pytest.raises(
        ValueError, match=rf"{re.escape(frame.name)}: .*0x7fc00001"
    ):
        m.dump_source(LATITUDE, LONGITUDE, [frame])


def test_main_materializes_source_in_order(
    frames: list[m.Frame],
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path]] = []
    written: list[Path] = []
    materialize = m.materialize

    def record(source_path: Path, root: Path) -> list[Path]:
        calls.append((source_path, root))
        paths = materialize(source_path, root)
        written.extend(paths)
        return paths

    monkeypatch.setattr(m, "SOURCE", source)
    monkeypatch.setattr(m, "materialize", record)

    assert m.main([str(tmp_path)]) == 0

    assert calls == [(source, tmp_path)]
    assert written == [tmp_path / "goes_processed" / f.name for f in frames]
    assert list(tmp_path.iterdir()) == [tmp_path / "goes_processed"]
    assert sorted((tmp_path / "goes_processed").iterdir()) == sorted(written)
    recorded = m.recorded_digests(source)
    for frame, path in zip(frames, written, strict=True):
        table = pl.read_parquet(path)
        assert table.schema == m.SCHEMA
        assert m.canonical_digest(table) == recorded[frame.name]


def test_main_without_one_argument_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["materialize.py"])

    assert m.main() == 2
    assert m.main([]) == 2
    assert m.main(["first", "second"]) == 2
    assert capsys.readouterr().err.count("usage: python materialize.py") == 3
