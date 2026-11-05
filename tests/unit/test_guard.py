from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from nwp_core.errors import InputNotReadyError
from nwp_core.run import ItemStatus, item_status_for, reason_for

from cod_nowcast_ons._config import SLOT
from cod_nowcast_ons._guard import select_frames

B = datetime(2024, 2, 7, 0, 20, tzinfo=UTC)


def _back(*steps: int) -> set[datetime]:
    return {B - n * SLOT for n in steps}


def _no_frame_error() -> InputNotReadyError:
    with pytest.raises(InputNotReadyError) as excinfo:
        select_frames(
            B,
            max_staleness=timedelta(minutes=30),
            num_past=2,
            min_frames=2,
            present=set().__contains__,
        )
    return excinfo.value


def test_all_present_uses_the_newest_run() -> None:
    selection = select_frames(
        B,
        max_staleness=SLOT,
        num_past=3,
        min_frames=3,
        present=lambda _: True,
    )

    assert selection.slots == (B - 3 * SLOT, B - 2 * SLOT, B - SLOT)
    assert selection.issue_time == B


def test_late_frame_within_staleness_moves_the_issue_time() -> None:
    selection = select_frames(
        B,
        max_staleness=2 * SLOT,
        num_past=2,
        min_frames=2,
        present=lambda slot: slot != B - SLOT,
    )

    assert selection.slots == (B - 3 * SLOT, B - 2 * SLOT)
    assert selection.issue_time == B - SLOT


def test_no_frame_within_staleness_is_not_ready() -> None:
    error = _no_frame_error()

    assert "20240207T0010Z" in str(error)
    assert "20240206T2350Z" in str(error)


def test_short_run_is_not_ready() -> None:
    with pytest.raises(InputNotReadyError, match="2 contiguous input frames"):
        select_frames(
            B,
            max_staleness=3 * SLOT,
            num_past=4,
            min_frames=3,
            present=_back(1, 2).__contains__,
        )


def test_run_never_spans_a_gap() -> None:
    selection = select_frames(
        B,
        max_staleness=3 * SLOT,
        num_past=4,
        min_frames=2,
        present=_back(1, 2, 4).__contains__,
    )

    assert selection.slots == (B - 2 * SLOT, B - SLOT)


def test_run_is_capped_at_num_past() -> None:
    selection = select_frames(
        B,
        max_staleness=3 * SLOT,
        num_past=2,
        min_frames=2,
        present=lambda _: True,
    )

    assert len(selection.slots) == 2


def test_predicate_sees_aware_slots_before_base() -> None:
    reach, num_past = 3, 3
    seen: list[datetime] = []

    def present(slot: datetime) -> bool:
        seen.append(slot)
        return slot <= B - 2 * SLOT

    select_frames(
        B,
        max_staleness=reach * SLOT,
        num_past=num_past,
        min_frames=2,
        present=present,
    )

    assert 0 < len(seen) <= reach + num_past
    assert all(slot.tzinfo is UTC for slot in seen)
    assert all(slot < B and (B - slot) % SLOT == timedelta(0) for slot in seen)


def test_not_ready_maps_to_input_not_ready() -> None:
    error = _no_frame_error()

    assert item_status_for(error) is ItemStatus.NOT_READY
    assert reason_for(error) == "input_not_ready"
