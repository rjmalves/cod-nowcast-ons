from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import click
from nwp_core.cli import CliRun, common_options, run_cli
from nwp_core.config import load_config, secret_values
from nwp_core.logging import register_secrets
from nwp_core.run import RunOutcome

from cod_nowcast_ons import __version__, nowcast
from cod_nowcast_ons._api import TOOL
from cod_nowcast_ons._config import ENV_PREFIX, NowcastConfig

__all__ = ["cli", "main"]


@click.group("cod-nowcast-ons", no_args_is_help=True)
def cli() -> None:
    """Cloud optical depth nowcasts from GOES frames."""


@cli.command("nowcast")
@common_options
@click.pass_obj
def nowcast_command(run: CliRun, *, config: Path | None) -> RunOutcome:
    """Run one nowcast at base_datetime."""
    cfg = load_config(NowcastConfig, env_prefix=ENV_PREFIX, config_file=config)
    register_secrets(secret_values(cfg))
    return nowcast(cfg, run_id=run.run_id, started_at=run.anchor)


def main() -> NoReturn:
    run_cli(cli, tool=TOOL, version=__version__)
