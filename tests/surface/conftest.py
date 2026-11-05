"""Snapshot fixture of the surface tests.

The policy is nwp-core's docs/public-surface-policy.md.
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

_UPDATE = "NWP_UPDATE_SNAPSHOTS"


@pytest.fixture
def assert_snapshot() -> Callable[[Path, str], None]:
    """Return a check that `text` equals the committed snapshot `path`.

    A difference fails with a unified diff that names the file and the public
    surface policy of nwp-core. With `NWP_UPDATE_SNAPSHOTS=1` the file is
    rewritten and the test still fails, so an update is never silent.
    """

    def check(path: Path, text: str) -> None:
        committed = path.read_text(encoding="utf-8") if path.exists() else ""
        if text == committed:
            return
        if os.environ.get(_UPDATE) == "1":
            path.write_text(text, encoding="utf-8")
            pytest.fail(
                f"snapshot updated; review and commit: {path}", pytrace=False
            )
        diff = "".join(
            difflib.unified_diff(
                committed.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{path} (committed)",
                tofile=f"{path} (actual)",
            )
        )
        pytest.fail(
            f"{path} differs from the committed snapshot; a change to the"
            " public surface needs a version bump and a changelog entry,"
            " see nwp-core's docs/public-surface-policy.md\n" + diff,
            pytrace=False,
        )

    return check
