import argparse
import sys
from pathlib import Path
from traceback import print_exc

from nwp_core.config import load_config

from cod_nowcast_ons import __version__, nowcast
from cod_nowcast_ons._config import ENV_PREFIX, NowcastConfig

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
        nowcast(
            load_config(
                NowcastConfig, env_prefix=ENV_PREFIX, config_file=args.config
            )
        )
    except Exception as e:
        print(f"Error: {e}")
        print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
