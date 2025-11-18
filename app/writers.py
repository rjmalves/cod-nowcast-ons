from os import makedirs
from os.path import join

import pandas as pd

from app.inference import InferenceResult
from app.internal.config import Config
from app.utils.plots import generate_cod_forecast_gif


def write_inference_results(config: Config, result: InferenceResult):
    output_dir = config.output
    makedirs(output_dir, exist_ok=True)
    dfs = []
    for _, subgrid_result in result.subgrid_results.items():
        df = subgrid_result.cod.to_dataframe(name="cod").reset_index()
        dfs.append(df)
    final_df = pd.concat(dfs, axis=0, ignore_index=True)
    output_path = join(output_dir, "cod.parquet")
    final_df.to_parquet(output_path)


def write_cloud_motion_plots(
    config: Config,
    result: InferenceResult,
):
    for subgrid_name, subgrid_result in result.subgrid_results.items():
        output_dir = join(config.output, "plots")
        makedirs(output_dir, exist_ok=True)
        generate_cod_forecast_gif(
            subgrid_result.cod,
            subgrid_result.motion_field,
            image_output_dir=output_dir,
            output_gif_filename=join(
                output_dir, f"{subgrid_name}_forecast.gif"
            ),
            keep_frames=True,
        )
