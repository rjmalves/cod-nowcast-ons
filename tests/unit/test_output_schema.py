from __future__ import annotations

import itertools
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
import xarray as xr
from nwp_core.contracts import registry
from nwp_core.errors import LocationUnusableError
from nwp_core.storage import StorageLocation, open_storage

from cod_nowcast_ons._forecast import InferenceResult, SubgridResult
from cod_nowcast_ons._output import SCHEMA, write_inference_results

ISSUE = datetime(2024, 2, 7, 0, 20)
LEADS = [ISSUE + timedelta(minutes=10), ISSUE + timedelta(minutes=20)]


def _subgrid(
    latitude: list[float], longitude: list[float], values: np.ndarray
) -> SubgridResult:
    cod = xr.DataArray(
        values.astype(np.float32),
        dims=("latitude", "longitude", "time"),
        coords={
            "latitude": latitude,
            "longitude": longitude,
            "time": np.array(LEADS, dtype="datetime64[us]"),
        },
    )
    return SubgridResult(
        cod=cod,
        motion_field=np.zeros((2, len(latitude), len(longitude))),
    )


A_LATITUDE = [-23.0, -22.0]
A_LONGITUDE = [-50.0, -49.0, -48.0]
B_LATITUDE = [-21.0]
B_LONGITUDE = [-47.0]


def _result() -> InferenceResult:
    a_values = np.arange(12, dtype=np.float32).reshape(2, 3, 2)
    a_values[0, 1, 1] = np.nan
    return InferenceResult(
        subgrid_results={
            "A": _subgrid(A_LATITUDE, A_LONGITUDE, a_values),
            "B": _subgrid(B_LATITUDE, B_LONGITUDE, np.array([[[20.0, 21.0]]])),
        }
    )


def _write(root: Path, issue_time: datetime = ISSUE) -> None:
    write_inference_results(
        _result(), open_storage(StorageLocation(uri=str(root))), issue_time
    )


def _triples(schema: pa.Schema) -> list[tuple[str, str, bool]]:
    return [(f.name, str(f.type), f.nullable) for f in schema]


def test_schema_equals_the_cod_run_contract() -> None:
    contract = registry().get("cod_nowcast.cod_run", "1.0")

    assert _triples(SCHEMA) == [
        (c.name, c.arrow_type, c.nullable) for c in contract.columns
    ]


def test_written_object_reads_back_with_the_schema(tmp_path: Path) -> None:
    _write(tmp_path)

    table = pq.read_table(tmp_path / "cod.parquet")

    assert _triples(table.schema) == _triples(SCHEMA)
    assert table["valor"].to_pylist() == [
        0.0,
        1.0,
        2.0,
        None,
        4.0,
        5.0,
        6.0,
        7.0,
        8.0,
        9.0,
        10.0,
        11.0,
        20.0,
        21.0,
    ]
    assert table["data_hora_rodada"].to_pylist() == [ISSUE] * 14
    cells = [
        *itertools.product(A_LATITUDE, A_LONGITUDE, LEADS),
        *itertools.product(B_LATITUDE, B_LONGITUDE, LEADS),
    ]
    assert table["latitude"].to_pylist() == [lat for lat, _, _ in cells]
    assert table["longitude"].to_pylist() == [lon for _, lon, _ in cells]
    assert table["data_hora_previsao"].to_pylist() == [
        lead for _, _, lead in cells
    ]


def test_local_object_is_owner_only(tmp_path: Path) -> None:
    _write(tmp_path)

    assert stat.S_IMODE(os.stat(tmp_path / "cod.parquet").st_mode) == 0o600


def test_second_write_replaces_the_object(tmp_path: Path) -> None:
    later = ISSUE + timedelta(minutes=10)
    _write(tmp_path)

    _write(tmp_path, later)

    table = pq.read_table(tmp_path / "cod.parquet")
    assert set(table["data_hora_rodada"].to_pylist()) == {later}


def test_missing_output_root_is_unusable(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(LocationUnusableError):
        _write(missing)

    assert not missing.exists()
