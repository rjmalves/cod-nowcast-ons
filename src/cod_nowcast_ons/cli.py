import argparse
import sys
from pathlib import Path
from traceback import print_exc

from cod_nowcast_ons import __version__
from cod_nowcast_ons._config import Config
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData
from cod_nowcast_ons._output import (
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
        type=str,
        default="config.jsonc",
        help="Path to configuration JSON file (default: config.json)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def load_config(config_path: str) -> Config:
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    return Config.from_json(config_path)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        reader = InputData(config.input)

        mode = config.mode

        if mode == "inference":
            print("Starting inference mode...")
            result = predict_subgrids(
                reader,
                config.subgrids,
                issue_time=config.base_datetime,
                num_frames=config.num_past_samples,
                num_future_samples=config.num_future_samples,
            )
            print("Inference completed successfully!")
            write_inference_results(result, config.output, config.base_datetime)
            if config.postprocessing.plots:
                write_cloud_motion_plots(
                    result, config.output, config.postprocessing.shapefile_path
                )
            print("Results written successfully!")
        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
