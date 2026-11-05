"""Importing the package has no process-wide side effect of its own."""

from __future__ import annotations

import json
import subprocess
import sys

from nwp_core._testing.cli import child_env

_IMPORT = "import cod_nowcast_ons, cod_nowcast_ons.cli"
_RECORD = f"""
import json, sys

before = set(sys.modules)
{_IMPORT}
print(json.dumps([
    name
    for name in sys.modules
    if name not in before and name.partition(".")[0] != "cod_nowcast_ons"
]))
"""
_COMPARE = f"""
import importlib, json, logging, os, sys, warnings


def state():
    return {{
        "filters": repr(warnings.filters),
        "environ": dict(os.environ),
        "handlers": repr(logging.root.handlers),
        "level": logging.root.level,
        "excepthook": repr(sys.excepthook),
    }}


for name in json.load(sys.stdin):
    if name not in sys.modules:
        importlib.import_module(name)
before = state()
{_IMPORT}
after = state()
print(json.dumps(sorted(key for key in before if before[key] != after[key])))
"""


def _child(code: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        env=child_env(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _recorded() -> list[str]:
    run = _child(_RECORD)
    assert run.returncode == 0, run.stderr
    names: list[str] = json.loads(run.stdout.splitlines()[-1])
    return names


def test_import_writes_nothing() -> None:
    run = _child(_IMPORT)

    assert run.returncode == 0, run.stderr
    assert run.stdout == ""
    assert run.stderr == ""


def test_import_loads_no_pysteps() -> None:
    loaded = [
        name
        for name in _recorded()
        if name == "pysteps" or name.startswith("pysteps.")
    ]

    assert loaded == []


def test_import_changes_no_process_state() -> None:
    run = _child(_COMPARE, json.dumps(_recorded()))

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.splitlines()[-1]) == []
