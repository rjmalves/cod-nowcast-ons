from __future__ import annotations

import io
import posixpath
from datetime import datetime
from typing import Final

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from nwp_core.storage import Storage

from cod_nowcast_ons._config import Shapefile
from cod_nowcast_ons._forecast import InferenceResult
from cod_nowcast_ons._plots import generate_cod_forecast_gif
from cod_nowcast_ons._storage import StorageFactory

COD_PARQUET: Final = "cod.parquet"

SCHEMA: Final = pa.schema(
    [
        pa.field("data_hora_rodada", pa.timestamp("us"), nullable=False),
        pa.field("data_hora_previsao", pa.timestamp("us"), nullable=False),
        pa.field("latitude", pa.float64(), nullable=False),
        pa.field("longitude", pa.float64(), nullable=False),
        pa.field("valor", pa.float32(), nullable=True),
    ]
)


def shapefile_path(shapefile: Shapefile | None) -> str | None:
    if shapefile is None:
        return None
    return posixpath.join(shapefile.location.uri, shapefile.key)


def write_inference_results(
    result: InferenceResult, outputs: Storage, issue_time: datetime
) -> None:
    """Replace ``cod.parquet`` in ``outputs`` with every subgrid forecast.

    The columns, types and nullability are ``SCHEMA``, in that order. Rows
    follow the subgrids in order, then latitude, longitude and lead time. NaN
    values are written as nulls. ``issue_time`` is naive UTC.
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
    outputs.write(COD_PARQUET, buffer.getvalue(), mode="replace")


def write_cloud_motion_plots(
    result: InferenceResult,
    output: str,
    shapefile_path: str | None,
) -> None:
    storage = StorageFactory.get_storage(output)

    for subgrid_name, subgrid_result in result.subgrid_results.items():
        output_dir = storage.join_path(output, "plots")
        storage.makedirs(output_dir)

        generate_cod_forecast_gif(
            subgrid_result.cod,
            subgrid_result.motion_field,
            image_output_dir=output_dir,
            output_gif_filename=storage.join_path(
                output_dir, f"{subgrid_name}_forecast.gif"
            ),
            image_prefix=subgrid_name,
            keep_frames=True,
            shapefile_path=shapefile_path,
            storage=storage,
        )
