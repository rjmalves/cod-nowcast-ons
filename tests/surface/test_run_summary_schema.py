"""Schema snapshot of the nwp.run-summary/1 document (ADR-023).

Regenerate the snapshot with `NWP_UPDATE_SNAPSHOTS=1 uv run --no-sync pytest
tests/surface`, then review and commit it. The run still fails, so an update
is never silent.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nwp_core.metrics.run_summary import run_summary_schema

_RUN_SUMMARY_SCHEMA = (
    Path(__file__).resolve().parent / "run-summary.schema.json"
)

Snapshot = Callable[[Path, str], None]


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip(value)
            for key, value in node.items()
            if key not in ("title", "description")
        }
    if isinstance(node, list):
        return [_strip(value) for value in node]
    return node


def _normalized(schema: dict[str, Any]) -> str:
    return json.dumps(_strip(schema), sort_keys=True, indent=2) + "\n"


def test_run_summary_schema_matches_the_snapshot(
    assert_snapshot: Snapshot,
) -> None:
    assert_snapshot(_RUN_SUMMARY_SCHEMA, _normalized(run_summary_schema()))
