"""Materialize the GOES COD regression frames from their TOML text source.

``frames.toml``, next to this module, holds every frame of the regression
fixture as text. ``materialize`` turns it back into goes.cod_frames 1.0
parquet files under a gold layout root, after it checks each table against
its recorded canonical digest. ``dump_source`` writes that text.

Run ``python materialize.py ROOT`` to materialize ``SOURCE`` under the
existing layout root ``ROOT``. The module imports only the standard library,
numpy and polars, so it also runs inside the built image.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import polars as pl

SOURCE: Final[Path] = Path(__file__).with_name("frames.toml")
FRAMES_PREFIX: Final = "goes_processed"
COLUMNS: Final = ("time", "latitude", "longitude", "cod")
GRID: Final = 76
SCHEMA: Final = pl.Schema(
    {
        "time": pl.Datetime("us", "UTC"),
        "latitude": pl.Float64(),
        "longitude": pl.Float64(),
        "cod": pl.Float32(),
    }
)

_HEADER: Final = (
    "# Generated file: do not edit by hand. "
    "Provenance: README.md in this directory.\n"
    "# materialize.py recomputes every sha256 before it writes a frame.\n"
)
_ARROW_TYPES: Final = {
    "time": "timestamp[us, tz=UTC]",
    "latitude": "double",
    "longitude": "double",
    "cod": "float",
}
_BUFFER_DTYPES: Final = {
    "time": "<i8",
    "latitude": "<f8",
    "longitude": "<f8",
    "cod": "<f4",
}
# The only float32 NaN bit patterns that ``nan`` and ``-nan`` carry through
# tomllib's float64 and back.
_NAN_BITS: Final = 0x7FC00000
_NEGATIVE_NAN_BITS: Final = 0xFFC00000
_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(frozen=True)
class Frame:
    """One GOES COD frame of the text source.

    Attributes:
        name: The file name ``GOES_COD_BR_%Y%m%d-%H%M.parquet``.
        time: The aware UTC scan time.
        source_sha256: The sha256 of the source parquet file, 64 lowercase
            hex characters.
        cod: The ``(GRID, GRID)`` grid. Row ``i`` is ``latitude[i]`` and
            column ``j`` is ``longitude[j]``.
    """

    name: str
    time: datetime
    source_sha256: str
    cod: npt.NDArray[np.float32]


def frame_table(
    latitude: npt.NDArray[np.float64],
    longitude: npt.NDArray[np.float64],
    frame: Frame,
) -> pl.DataFrame:
    """Build the goes.cod_frames table of a frame with exactly ``SCHEMA``.

    The rows are in C order: latitude ascending, then longitude ascending.
    """
    rows = latitude.size * longitude.size
    return pl.DataFrame(
        [
            pl.Series("time", [frame.time] * rows, dtype=SCHEMA["time"]),
            pl.Series(
                "latitude",
                np.repeat(latitude, longitude.size),
                dtype=SCHEMA["latitude"],
            ),
            pl.Series(
                "longitude",
                np.tile(longitude, latitude.size),
                dtype=SCHEMA["longitude"],
            ),
            pl.Series("cod", frame.cod.reshape(-1), dtype=SCHEMA["cod"]),
        ]
    )


def canonical_digest(table: pl.DataFrame) -> str:
    """Return the canonical column digest of a frame table.

    For each column in ``COLUMNS`` order, the sha256 is fed the column name,
    a NUL byte, the Arrow type string, a NUL byte and the little-endian
    buffer of the values: ``time`` as int64 microseconds since the epoch,
    the coordinates as float64 and ``cod`` as float32. Parquet bytes are
    never hashed, so the digest depends on the values alone.

    Raises:
        ValueError: If a column of ``COLUMNS`` is missing or its dtype
            differs from ``SCHEMA``. The message names the first one.
    """
    for name in COLUMNS:
        actual = table.schema.get(name)
        if actual is None or actual != SCHEMA[name]:
            raise ValueError(
                f"column {name!r} has dtype {actual}, expected {SCHEMA[name]}"
            )
    digest = hashlib.sha256()
    for name in COLUMNS:
        column = table[name]
        if name == "time":
            column = column.dt.epoch("us")
        buffer = np.ascontiguousarray(
            column.to_numpy(), dtype=_BUFFER_DTYPES[name]
        )
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_ARROW_TYPES[name].encode("utf-8"))
        digest.update(b"\0")
        digest.update(buffer.tobytes())
    return digest.hexdigest()


def dump_source(
    latitude: npt.NDArray[np.float64],
    longitude: npt.NDArray[np.float64],
    frames: Sequence[Frame],
) -> str:
    """Return the TOML 1.0 text source of a grid and its frames.

    Each frame's ``sha256`` is the canonical digest of its ``frame_table``,
    computed here. ``cod`` values are written as ``repr`` of the float32
    value, and NaN as ``nan`` or ``-nan``, so the text is exact bit for bit.

    Raises:
        ValueError: If a coordinate array is not ``GRID`` strictly ascending
            values, if a grid is not ``(GRID, GRID)``, or if a ``cod`` NaN
            has float32 bits other than ``0x7fc00000`` and ``0xffc00000``.
    """
    _check_coordinate("latitude", latitude)
    _check_coordinate("longitude", longitude)
    parts = [
        _HEADER,
        f"latitude = {_float_array(latitude)}\n",
        f"longitude = {_float_array(longitude)}\n",
    ]
    for frame in frames:
        rows = _cod_rows(frame)
        sha256 = canonical_digest(frame_table(latitude, longitude, frame))
        parts.append(
            "\n[[frames]]\n"
            f"name = {json.dumps(frame.name)}\n"
            f"time = {frame.time.strftime(_TIME_FORMAT)}\n"
            f"source_sha256 = {json.dumps(frame.source_sha256)}\n"
            f'sha256 = "{sha256}"\n'
            f"cod = [\n{rows}]\n"
        )
    return "".join(parts)


def load_source(
    source: Path,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], list[Frame]]:
    """Read a text source into its coordinates and frames.

    ``cod`` is parsed as float64 and then cast to float32, which restores
    each float32 value, ``-0.0`` and both NaN patterns bit for bit.

    Raises:
        ValueError: If a coordinate array is not ``GRID`` long or a grid is
            not ``(GRID, GRID)``.
    """
    document = _read(source)
    latitude = _coordinate(document, "latitude")
    longitude = _coordinate(document, "longitude")
    frames = [
        Frame(
            name=entry["name"],
            time=entry["time"],
            source_sha256=entry["source_sha256"],
            cod=_grid(entry["name"], entry["cod"]).astype(np.float32),
        )
        for entry in document.get("frames", [])
    ]
    return latitude, longitude, frames


def recorded_digests(source: Path) -> dict[str, str]:
    """Map each frame ``name`` of a text source to its recorded ``sha256``."""
    return {
        entry["name"]: entry["sha256"]
        for entry in _read(source).get("frames", [])
    }


def frame_objects(source: Path) -> list[tuple[str, bytes]]:
    """Return the ``(layout key, parquet bytes)`` of each frame, in order.

    The layout key is ``f"{FRAMES_PREFIX}/{name}"``, the goes.cod_frames 1.0
    key under a gold layout root.

    Raises:
        ValueError: ``digest mismatch for {name}`` when a table's canonical
            digest differs from its recorded ``sha256``.
    """
    latitude, longitude, frames = load_source(source)
    recorded = recorded_digests(source)
    objects = []
    for frame in frames:
        table = frame_table(latitude, longitude, frame)
        if canonical_digest(table) != recorded[frame.name]:
            raise ValueError(f"digest mismatch for {frame.name}")
        buffer = io.BytesIO()
        table.write_parquet(buffer)
        objects.append((f"{FRAMES_PREFIX}/{frame.name}", buffer.getvalue()))
    return objects


def materialize(source: Path, root: Path) -> list[Path]:
    """Write every frame of a text source under the layout root ``root``.

    ``root`` must exist. Every digest is checked before anything is written.

    Returns:
        The written paths, ``root / FRAMES_PREFIX / key``, in source order.
    """
    objects = frame_objects(source)
    (root / FRAMES_PREFIX).mkdir(exist_ok=True)
    paths = []
    for key, data in objects:
        path = root / key
        path.write_bytes(data)
        paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``python materialize.py ROOT``: materialize ``SOURCE`` at ROOT."""
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1:
        print("usage: python materialize.py ROOT", file=sys.stderr)
        return 2
    materialize(SOURCE, Path(args[0]))
    return 0


def _read(source: Path) -> dict[str, Any]:
    with source.open("rb") as file:
        return tomllib.load(file)


def _coordinate(document: dict[str, Any], name: str) -> npt.NDArray[np.float64]:
    values = np.array(document[name], dtype=np.float64)
    if values.shape != (GRID,):
        raise ValueError(f"{name} has shape {values.shape}, expected {(GRID,)}")
    return values


def _grid(key: str, rows: Any) -> npt.NDArray[np.float64]:
    try:
        grid = np.array(rows, dtype=np.float64)
    except ValueError as error:
        raise ValueError(
            f"frame {key}: cod is not a {GRID} x {GRID} grid"
        ) from error
    if grid.shape != (GRID, GRID):
        raise ValueError(
            f"frame {key}: cod has shape {grid.shape}, expected {(GRID, GRID)}"
        )
    return grid


def _check_coordinate(name: str, values: npt.NDArray[np.float64]) -> None:
    if values.shape != (GRID,) or not bool(np.all(np.diff(values) > 0)):
        raise ValueError(f"{name} must hold {GRID} strictly ascending values")


def _float_array(values: npt.NDArray[np.float64]) -> str:
    return "[" + ", ".join(repr(float(value)) for value in values) + "]"


def _cod_rows(frame: Frame) -> str:
    cod = np.asarray(frame.cod, dtype=np.float32)
    if cod.shape != (GRID, GRID):
        raise ValueError(
            f"frame {frame.name}: cod has shape {cod.shape}, "
            f"expected {(GRID, GRID)}"
        )
    bits = cod.view(np.uint32)
    unknown = np.isnan(cod) & (bits != _NAN_BITS) & (bits != _NEGATIVE_NAN_BITS)
    if unknown.any():
        i, j = (int(index) for index in np.argwhere(unknown)[0])
        raise ValueError(
            f"frame {frame.name}: cod[{i}, {j}] is a NaN with float32 bits "
            f"0x{int(bits[i, j]):08x}, which is neither 0x7fc00000 nor "
            "0xffc00000"
        )
    lines = []
    for values, row_bits in zip(cod.tolist(), bits.tolist(), strict=True):
        cells = ", ".join(
            _cod_text(value, value_bits)
            for value, value_bits in zip(values, row_bits, strict=True)
        )
        lines.append(f"  [{cells}],\n")
    return "".join(lines)


def _cod_text(value: float, bits: int) -> str:
    if bits == _NAN_BITS:
        return "nan"
    if bits == _NEGATIVE_NAN_BITS:
        return "-nan"
    return repr(value)


if __name__ == "__main__":
    raise SystemExit(main())
