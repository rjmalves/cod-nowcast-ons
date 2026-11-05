"""The nowcast must give identical tables on identical input.

pySTEPS's LK and extrapolation path has no RNG, so two runs in one process
must agree exactly, with no tolerance.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from tests.regression.conftest import run_regression


def test_nowcast_is_deterministic(
    regression_frames: Path, tmp_path: Path
) -> None:
    first = pl.read_parquet(
        run_regression(regression_frames, tmp_path / "first")
    )
    second = pl.read_parquet(
        run_regression(regression_frames, tmp_path / "second")
    )

    assert first.equals(second, null_equal=True)
    assert (first["valor"].is_finite() & (first["valor"] != 0)).any(), (
        "no finite non-zero valor: equal empty or all-zero tables"
    )
