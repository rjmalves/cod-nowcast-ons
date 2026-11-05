from __future__ import annotations

import subprocess
import sys

from cod_nowcast_ons import __version__

ENTRY = "from cod_nowcast_ons.cli import main; main()"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", ENTRY, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_prints_tool_and_version() -> None:
    result = _run("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"cod-nowcast-ons {__version__}\n"


def test_nowcast_help_lists_config() -> None:
    result = _run("nowcast", "--help")

    assert result.returncode == 0, result.stderr
    assert "--config" in result.stdout
    assert "Local TOML file with the tool configuration." in result.stdout
