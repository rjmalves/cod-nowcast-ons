import sys
from pathlib import Path
from traceback import print_exc

from app.inference import InferenceManager
from app.internal.config import Config
from app.parser import build_parser
from app.readers import InputData
from app.writers import (
    write_cloud_motion_plots,
    write_inference_results,
)


def load_config(config_path: str) -> Config:
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    return Config.from_json(config_path)


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        reader = InputData(config.input)

        mode = config.mode

        if mode == "inference":
            print("Starting inference mode...")
            manager = InferenceManager(config, reader)
            result = manager.predict()
            print("Inference completed successfully!")
            write_inference_results(config, result)
            if config.postprocessing.plots:
                write_cloud_motion_plots(config, result)
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
