"""Golden regression of the forecast on the fixture cut.

``golden/cod_regression.json`` pins the values the code under test produces
on the committed frames. ``--update-golden`` rewrites it and fails, so a
regeneration is never mistaken for a pass.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from tests.fixtures.goes_cod.materialize import SOURCE

GOLDEN = Path(__file__).parent / "golden" / "cod_regression.json"

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = "tests/fixtures/goes_cod"
_DISTRIBUTIONS = (
    "numpy",
    "opencv-python-headless",
    "pysteps",
    "scipy",
    "polars",
    "pandas",
    "pyarrow",
    "xarray",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha(key: str, *args: str, first_line: bool = False) -> str:
    output = subprocess.run(
        ["git", *args], cwd=_ROOT, capture_output=True, text=True
    ).stdout
    lines = output.split()
    chosen = lines[:1] if first_line else lines
    if len(chosen) != 1 or not re.fullmatch(r"[0-9a-f]{40}", chosen[0]):
        raise RuntimeError(f"meta.{key}: expected exactly one SHA, got {lines}")
    return chosen[0]


def _meta() -> dict[str, object]:
    added = ("log", "--diff-filter=A", "--format=%H", "--")
    return {
        "format": 1,
        "code_commit": _git_sha("code_commit", "rev-parse", "HEAD"),
        "app_tree": _git_sha("app_tree", "rev-parse", "HEAD:app"),
        "criteria_commit": _git_sha(
            "criteria_commit", *added, f"{_FIXTURE_DIR}/criteria.py"
        ),
        "screen_commit": _git_sha(
            "screen_commit",
            "log",
            "--reverse",
            "--format=%H",
            "-S## Triagem",
            "--",
            f"{_FIXTURE_DIR}/README.md",
            first_line=True,
        ),
        "fixture_commit": _git_sha(
            "fixture_commit", *added, f"{_FIXTURE_DIR}/frames.toml"
        ),
        "fixture_sha256": _sha256(SOURCE),
        "uv_lock_sha256": _sha256(_ROOT / "uv.lock"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            name: importlib.metadata.version(name) for name in _DISTRIBUTIONS
        },
    }


def _document(
    table: pl.DataFrame,
    schema: list[list[str]],
    config: dict[str, object],
) -> dict[str, object]:
    return {
        "meta": _meta(),
        "config": config,
        "schema": schema,
        "rows": table.height,
        "data_hora_rodada": table["data_hora_rodada"][0].isoformat(),
        "data_hora_previsao": [
            lead.isoformat()
            for lead in table["data_hora_previsao"].unique().sort()
        ],
        "latitude": table["latitude"].unique().sort().to_list(),
        "longitude": table["longitude"].unique().sort().to_list(),
        "valor": [
            None if value is None else float(value)
            for value in table["valor"].to_list()
        ],
    }


def test_regression_output_matches_the_golden(
    regression_cod_parquet: Path,
    regression_config: dict[str, object],
    request: pytest.FixtureRequest,
) -> None:
    schema = [
        [field.name, str(field.type)]
        for field in pq.read_schema(regression_cod_parquet)
    ]
    table = pl.read_parquet(regression_cod_parquet)

    if request.config.getoption("--update-golden"):
        document = _document(table, schema, regression_config)
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(document, allow_nan=False, indent=1) + "\n",
            encoding="utf-8",
        )
        pytest.fail("golden updated; review and commit")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert golden["meta"]["fixture_sha256"] == _sha256(SOURCE), (
        "fixture_sha256: frames.toml differs from the one the golden "
        "was captured on"
    )
    assert schema == golden["schema"], f"schema: {schema} != {golden['schema']}"
    assert table.height == golden["rows"], (
        f"rows: {table.height} != {golden['rows']}"
    )
    rodada = [value.isoformat() for value in table["data_hora_rodada"].unique()]
    assert rodada == [golden["data_hora_rodada"]], (
        f"data_hora_rodada: {rodada} != [{golden['data_hora_rodada']!r}]"
    )

    lat = np.array(golden["latitude"], dtype=np.float64)
    lon = np.array(golden["longitude"], dtype=np.float64)
    lead = np.array(golden["data_hora_previsao"], dtype="datetime64[us]")
    expanded = {
        "latitude": np.repeat(lat, lon.size * lead.size),
        "longitude": np.tile(np.repeat(lon, lead.size), lat.size),
        "data_hora_previsao": np.tile(lead, lat.size * lon.size),
    }
    for name, expected in expanded.items():
        assert np.array_equal(table[name].to_numpy(), expected), (
            f"{name}: differs from the C-order expansion of the grid vectors"
        )

    valor = table["valor"]
    assert table.select(pl.col("valor").is_nan().sum()).item() == 0, (
        "valor: holds a NaN that is not null"
    )
    golden_null = np.array([value is None for value in golden["valor"]])
    assert np.array_equal(valor.is_null().to_numpy(), golden_null), (
        "valor: null mask differs"
    )
    actual = valor.drop_nulls().to_numpy().astype(np.float64)
    expected_valor = np.array(
        [value for value in golden["valor"] if value is not None],
        dtype=np.float64,
    )
    assert np.allclose(actual, expected_valor, rtol=1e-5, atol=1e-5), (
        "valor: differs beyond rtol=atol=1e-5, "
        f"max |diff| = {np.abs(actual - expected_valor).max():.3e}"
    )
