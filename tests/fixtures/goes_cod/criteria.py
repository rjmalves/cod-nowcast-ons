"""Selection criteria of the GOES COD regression fixture.

A candidate cut is a window of ``WINDOW`` frames. ``screen_window`` applies
three model-independent criteria to it:

1. The window holds ``WINDOW`` slots, each ``STEP`` after the one before.
2. Each of the ``L`` verifying frames has at least ``MIN_FINITE`` finite
   pixels.
3. The integer shift that maximizes the Pearson correlation of each pair of
   consecutive frames shows translation: it lies strictly inside the search
   window, is at least one cell, and points the same way in every pair.

The module imports only the standard library and numpy, and runs no model.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import numpy as np
import numpy.typing as npt

P: Final = 2
L: Final = 3
WINDOW: Final = P + L
STEP: Final = timedelta(minutes=10)
MIN_FINITE: Final = 500
MAX_SHIFT: Final = 5

_KEY: Final = re.compile(r"GOES_COD_BR_(\d{8}-\d{4})\.parquet")


@dataclass(frozen=True)
class Screen:
    """The result of ``screen_window`` for one window.

    Attributes:
        start: The first slot of the window.
        contiguous: Whether the window meets criterion 1.
        finite_counts: The finite pixel count of each verifying frame, or
            empty when the window is not contiguous.
        shifts: The ``(dy, dx, score)`` of each consecutive pair, or empty
            when the window is not contiguous.
        translation: Whether the window meets criterion 3.
        passed: Whether the window meets all three criteria.
    """

    start: datetime
    contiguous: bool
    finite_counts: tuple[int, ...]
    shifts: tuple[tuple[int, int, float], ...]
    translation: bool
    passed: bool


def nominal_slot(key: str) -> datetime:
    """Return the nominal slot of a product key as an aware UTC datetime.

    Raises:
        ValueError: If ``key`` is not ``GOES_COD_BR_%Y%m%d-%H%M.parquet``.
    """
    match = _KEY.fullmatch(key)
    if match is None:
        raise ValueError(f"not a GOES COD frame key: {key!r}")
    return datetime.strptime(match.group(1), "%Y%m%d-%H%M").replace(tzinfo=UTC)


def best_shift(
    a: npt.NDArray[np.float32], b: npt.NDArray[np.float32]
) -> tuple[int, int, float]:
    """Return the integer shift ``(dy, dx)`` that best maps ``a`` onto ``b``.

    The shifts searched have ``|dy|`` and ``|dx|`` at most ``MAX_SHIFT``. NaN
    is set to 0 in both frames. The score of a shift is the Pearson
    correlation of ``a[i, j]`` against ``b[i + dy, j + dx]`` over the
    non-wrapping overlap. An undefined score, from a zero-variance overlap,
    is ``-inf``, so it never wins and never raises. The highest score wins.
    Ties go to the smallest ``dy * dy + dx * dx``, then to the smallest
    ``(dy, dx)``.

    Returns:
        ``(dy, dx, score)`` of the best shift. The score is ``-inf`` when
        every score is undefined, and the shift is then ``(0, 0)``.
    """
    a = np.where(np.isnan(a), 0.0, a)
    b = np.where(np.isnan(b), 0.0, b)
    n = a.shape[0]
    ranked = []
    for dy in range(-MAX_SHIFT, MAX_SHIFT + 1):
        for dx in range(-MAX_SHIFT, MAX_SHIFT + 1):
            x = a[max(0, -dy) : min(n, n - dy), max(0, -dx) : min(n, n - dx)]
            y = b[max(0, dy) : min(n, n + dy), max(0, dx) : min(n, n + dx)]
            ranked.append((-_pearson(x, y), dy * dy + dx * dx, dy, dx))
    negative_score, _, dy, dx = min(ranked)
    return dy, dx, -negative_score


def screen_window(
    slots: Sequence[datetime], grids: Sequence[npt.NDArray[np.float32]]
) -> Screen:
    """Apply the three criteria to a window of frames.

    ``slots[k]`` is the nominal slot of ``grids[k]``. The verifying frames
    are ``grids[P:P + L]``. A window that is not contiguous gets empty
    counts and shifts. A window with an undefined score has the shift
    ``(0, 0, -inf)`` for that pair and fails criterion 3 without raising.

    Raises:
        ValueError: If ``slots`` is empty or its length differs from
            ``grids``.
    """
    if not slots or len(slots) != len(grids):
        raise ValueError(
            f"need as many slots as grids and at least one, "
            f"got {len(slots)} slots and {len(grids)} grids"
        )
    contiguous = len(slots) == WINDOW and all(
        later - earlier == STEP for earlier, later in zip(slots, slots[1:])
    )
    if not contiguous:
        return Screen(slots[0], False, (), (), False, False)
    finite_counts = tuple(int(np.isfinite(g).sum()) for g in grids[P : P + L])
    shifts = tuple(best_shift(a, b) for a, b in zip(grids, grids[1:]))
    translation = all(
        abs(dy) < MAX_SHIFT
        and abs(dx) < MAX_SHIFT
        and max(abs(dy), abs(dx)) >= 1
        and all(
            dy * other_dy + dx * other_dx > 0
            for k, (other_dy, other_dx, _) in enumerate(shifts)
            if k != i
        )
        for i, (dy, dx, _) in enumerate(shifts)
    )
    passed = translation and all(c >= MIN_FINITE for c in finite_counts)
    return Screen(slots[0], True, finite_counts, shifts, translation, passed)


def _pearson(x: npt.NDArray[np.float32], y: npt.NDArray[np.float32]) -> float:
    with np.errstate(divide="ignore", invalid="ignore"):
        score = float(np.corrcoef(x.ravel(), y.ravel())[0, 1])
    return score if math.isfinite(score) else -math.inf
