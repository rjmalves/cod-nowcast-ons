"""Snapshot of the CLI option and environment names.

Regenerate `cli-surface.json` with `NWP_UPDATE_SNAPSHOTS=1`, then review and
commit it. Help texts are not recorded.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import click
from nwp_core.config import env_var_names

from cod_nowcast_ons import NowcastConfig
from cod_nowcast_ons._config import ENV_PREFIX
from cod_nowcast_ons.cli import cli

_SNAPSHOT = Path(__file__).resolve().parent / "cli-surface.json"


def _options(command: click.Command) -> list[dict[str, object]]:
    options: list[dict[str, object]] = [
        {
            "names": sorted(
                name
                for name in (*param.opts, *param.secondary_opts)
                if name.startswith("--")
            ),
            "flag": param.is_flag,
            "choices": (
                list(param.type.choices)
                if isinstance(param.type, click.Choice)
                else None
            ),
        }
        for param in command.params
        if isinstance(param, click.Option)
    ]
    return sorted(options, key=lambda option: str(option["names"]))


def _surface() -> str:
    surface = {
        "commands": {
            name: _options(command)
            for name, command in sorted(cli.commands.items())
        },
        "group_options": _options(cli),
        "environment": {
            "config_file": f"{ENV_PREFIX}_CONFIG",
            "fields": env_var_names(NowcastConfig, ENV_PREFIX),
        },
    }
    return json.dumps(surface, sort_keys=True, indent=2) + "\n"


def test_cli_surface_matches_the_committed_snapshot(
    assert_snapshot: Callable[[Path, str], None],
) -> None:
    assert_snapshot(_SNAPSHOT, _surface())
