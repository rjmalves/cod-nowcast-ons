import argparse
import sys
from pathlib import Path
from traceback import print_exc

from nwp_core.config import load_config

from cod_nowcast_ons import __version__
from cod_nowcast_ons._config import ENV_PREFIX, NowcastConfig
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData, frames_folder
from cod_nowcast_ons._output import (
    shapefile_path,
    write_cloud_motion_plots,
    write_inference_results,
)

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cloud Optical Depth forecasts using GOES satellite images and pySTEPS"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Local TOML file with the tool configuration.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config(
            NowcastConfig, env_prefix=ENV_PREFIX, config_file=args.config
        )
        base = config.base_datetime.replace(tzinfo=None)
        print("Starting inference mode...")
        result = predict_subgrids(
            InputData(frames_folder(config.input)),
            config.subgrids,
            issue_time=base,
            num_frames=config.num_past_samples,
            num_future_samples=config.num_future_samples,
        )
        print("Inference completed successfully!")
        write_inference_results(result, config.output.uri, base)
        if config.postprocessing.plots:
            write_cloud_motion_plots(
                result,
                config.output.uri,
                shapefile_path(config.postprocessing.shapefile),
            )
        print("Results written successfully!")
    except Exception as e:
        print(f"Error: {e}")
        print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
