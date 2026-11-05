from __future__ import annotations

import subprocess
import sys

SCRIPT = """
import logging
import sys
import warnings

from cod_nowcast_ons._forecast import load_pysteps

assert not [m for m in sys.modules if m.split(".")[0] == "pysteps"]
filters = list(warnings.filters)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(event)s"))
handler.setLevel(logging.DEBUG)
logger = logging.getLogger("cod_nowcast_ons._forecast")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
first = load_pysteps()
second = load_pysteps()
assert first is second
assert warnings.filters == filters
"""


def test_pysteps_loads_lazily_and_quietly() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "pysteps.import" in result.stderr.splitlines()
