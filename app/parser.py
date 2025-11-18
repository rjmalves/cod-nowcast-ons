import argparse


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
    return parser
