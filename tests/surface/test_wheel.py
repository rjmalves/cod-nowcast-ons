"""The built wheel installs one top-level package."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_BUILD_TIMEOUT = 300


def test_wheel_has_one_top_level_package(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.fail(
            "uv is not on PATH; the wheel check builds with uv", pytrace=False
        )
    proc = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(tmp_path), str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    (wheel,) = tmp_path.glob("*.whl")
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    with zipfile.ZipFile(wheel) as archive:
        top_level = {name.split("/")[0] for name in archive.namelist()}
    assert top_level == {
        "cod_nowcast_ons",
        f"cod_nowcast_ons-{version}.dist-info",
    }
