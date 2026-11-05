from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from nwp_core.errors import InputNotReadyError
from nwp_core.layout import cycle_token

from cod_nowcast_ons._config import SLOT


@dataclass(frozen=True)
class FrameSelection:
    slots: tuple[datetime, ...]

    @property
    def issue_time(self) -> datetime:
        return self.slots[-1] + SLOT


def select_frames(
    base: datetime,
    *,
    max_staleness: timedelta,
    num_past: int,
    min_frames: int,
    present: Callable[[datetime], bool],
) -> FrameSelection:
    reach = max_staleness // SLOT
    candidates = (base - k * SLOT for k in range(1, reach + 1))
    newest = next((slot for slot in candidates if present(slot)), None)
    if newest is None:
        msg = (
            f"no input frame from {cycle_token(base - SLOT)} back to"
            f" {cycle_token(base - reach * SLOT)}"
        )
        raise InputNotReadyError(msg)
    run = [newest]
    while len(run) < num_past and present(previous := run[-1] - SLOT):
        run.append(previous)
    if len(run) < min_frames:
        msg = (
            f"{len(run)} contiguous input frames end at"
            f" {cycle_token(newest)}, {min_frames} needed"
        )
        raise InputNotReadyError(msg)
    return FrameSelection(tuple(reversed(run)))
