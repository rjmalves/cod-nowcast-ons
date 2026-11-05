"""The forecast must beat persistence on the regression fixture.

The definition is pre-registered in ``tests/fixtures/goes_cod/README.md``,
section "Definição da persistência". The score is the RMSE of
``nwp_core.metrics.skill`` over one valid-pixel mask that both forecasts
share, for each lead and as the mean over the leads.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
from nwp_core.metrics.skill import rmse

from tests.fixtures.goes_cod.criteria import L, P, nominal_slot
from tests.fixtures.goes_cod.materialize import SOURCE, load_source


def test_model_beats_persistence_on_the_regression_fixture(
    regression_cod_parquet: Path,
) -> None:
    latitude, longitude, frames = load_source(SOURCE)
    slots = [nominal_slot(f.name).replace(tzinfo=None) for f in frames]

    table = pl.read_parquet(regression_cod_parquet)
    assert np.array_equal(table["latitude"].unique().sort(), latitude)
    assert np.array_equal(table["longitude"].unique().sort(), longitude)
    assert (
        table["data_hora_previsao"].unique().sort().to_list()
        == slots[P : P + L]
    )

    newest = frames[P - 1].cod
    persistence = np.where(np.isfinite(newest), newest, 0.0)

    lines: list[str] = []
    model_scores: list[float] = []
    persistence_scores: list[float] = []
    for k in range(1, L + 1):
        target = frames[P + k - 1].cod
        model = (
            table.filter(pl.col("data_hora_previsao") == slots[P + k - 1])
            .sort("latitude", "longitude")["valor"]
            .to_numpy()
            .reshape(target.shape)
        )
        mask = (
            np.isfinite(target) & np.isfinite(model) & np.isfinite(persistence)
        )
        valid = int(mask.sum())
        assert valid > 0, f"lead {k}: the shared valid-pixel mask is empty"
        m_k = rmse(model[mask], target[mask])
        p_k = rmse(persistence[mask], target[mask])
        model_scores.append(m_k)
        persistence_scores.append(p_k)
        lines.append(
            f"lead {k} valid {valid} "
            f"model_rmse {m_k:.6f} persistence_rmse {p_k:.6f}"
        )

    model_mean = float(np.mean(model_scores))
    persistence_mean = float(np.mean(persistence_scores))
    lines.append(
        f"mean model_rmse {model_mean:.6f} "
        f"persistence_rmse {persistence_mean:.6f}"
    )
    report = "\n".join(lines)
    print(report)

    assert model_mean < persistence_mean, report
