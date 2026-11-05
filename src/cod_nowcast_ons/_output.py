import posixpath
from datetime import datetime

import pandas as pd

from cod_nowcast_ons._config import Shapefile
from cod_nowcast_ons._forecast import InferenceResult
from cod_nowcast_ons._plots import generate_cod_forecast_gif
from cod_nowcast_ons._storage import StorageFactory


def shapefile_path(shapefile: Shapefile | None) -> str | None:
    if shapefile is None:
        return None
    return posixpath.join(shapefile.location.uri, shapefile.key)


def write_inference_results(
    result: InferenceResult, output: str, issue_time: datetime
) -> None:
    storage = StorageFactory.get_storage(output)
    storage.makedirs(output)

    dfs = []
    for _, subgrid_result in result.subgrid_results.items():
        df = subgrid_result.cod.to_dataframe(name="cod").reset_index()
        dfs.append(df)

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

    output_path = storage.join_path(output, "cod.parquet")
    storage.write_parquet(final_df, output_path)


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
