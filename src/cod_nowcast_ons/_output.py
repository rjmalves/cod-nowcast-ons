from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from nwp_core.storage import Storage, WriteReceipt

from cod_nowcast_ons._forecast import InferenceResult
from cod_nowcast_ons._plots import animate_frames, render_cod_forecast_frame

COD_PARQUET: Final = "cod.parquet"
PLOTS_PREFIX: Final = "plots"

SCHEMA: Final = pa.schema(
    [
        pa.field("data_hora_rodada", pa.timestamp("us"), nullable=False),
        pa.field("data_hora_previsao", pa.timestamp("us"), nullable=False),
        pa.field("latitude", pa.float64(), nullable=False),
        pa.field("longitude", pa.float64(), nullable=False),
        pa.field("valor", pa.float32(), nullable=True),
    ]
)


def write_inference_results(
    result: InferenceResult, outputs: Storage, issue_time: datetime
) -> WriteReceipt:
    """Replace ``cod.parquet`` in ``outputs`` with every subgrid forecast.

    The columns, types and nullability are ``SCHEMA``, in that order. Rows
    follow the subgrids in order, then latitude, longitude and lead time. NaN
    values are written as nulls. ``issue_time`` is naive UTC. Returns the
    receipt of the write.
    """
    dfs = [
        subgrid_result.cod.to_dataframe(name="cod").reset_index()
        for subgrid_result in result.subgrid_results.values()
    ]

    final_df = pd.concat(dfs, axis=0, ignore_index=True)
    final_df["data_hora_rodada"] = issue_time
    final_df = final_df.rename(
        columns={"time": "data_hora_previsao", "cod": "valor"}
    )
    final_df = final_df[
        [
            "data_hora_rodada",
            "data_hora_previsao",
            "latitude",
            "longitude",
            "valor",
        ]
    ]

    table = pa.Table.from_pandas(final_df, schema=SCHEMA, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return outputs.write(COD_PARQUET, buffer.getvalue(), mode="replace")


def write_cloud_motion_plots(
    result: InferenceResult, outputs: Storage, shapes: Sequence[Any]
) -> list[WriteReceipt]:
    """Replace the forecast plots of every subgrid in ``outputs``.

    Each subgrid gets one ``plots/<name>_NNNN.png`` per lead time and one
    ``plots/<name>_forecast.gif`` that animates them. ``shapes`` are extra
    outlines drawn on every frame. Returns the receipts in write order.
    """
    receipts: list[WriteReceipt] = []
    for name, subgrid_result in result.subgrid_results.items():
        pngs = []
        for step in range(subgrid_result.cod.sizes["time"]):
            png = render_cod_forecast_frame(
                subgrid_result.cod,
                subgrid_result.motion_field,
                step,
                shapes=shapes,
            )
            receipts.append(
                outputs.write(
                    f"{PLOTS_PREFIX}/{name}_{step:04d}.png",
                    png,
                    mode="replace",
                )
            )
            pngs.append(png)
        receipts.append(
            outputs.write(
                f"{PLOTS_PREFIX}/{name}_forecast.gif",
                animate_frames(pngs),
                mode="replace",
            )
        )
    return receipts
