from __future__ import annotations

import importlib.metadata
import logging
from datetime import datetime
from functools import partial
from typing import Any, Final

from nwp_core.layout import cycle_token
from nwp_core.logging import log_event
from nwp_core.run import ItemReport, RunContext, RunOutcome, run_items
from nwp_core.storage import Storage, open_storage

from cod_nowcast_ons._config import NowcastConfig
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData, frame_key
from cod_nowcast_ons._guard import select_frames
from cod_nowcast_ons._output import (
    write_cloud_motion_plots,
    write_inference_results,
)
from cod_nowcast_ons._plots import read_shapes

TOOL: Final = "cod-nowcast-ons"

_LOG = logging.getLogger(__name__)


def nowcast(
    config: NowcastConfig,
    *,
    run_id: str | None = None,
    started_at: datetime | None = None,
) -> RunOutcome:
    """Run one nowcast for ``config.base_datetime`` and return its outcome.

    ``started_at`` is an aware datetime. The item is NOT_READY when the input
    guard finds too few frames.

    Raises:
        LocationUnusableError: If a storage location is unusable, such as a
            missing local output root (exit 2).
        RunNotReadyError: If the input frames are not ready (exit 4).
        RunFailedError: If the forecast or a writer fails (exit 3).
    """
    context = RunContext.create(
        TOOL,
        importlib.metadata.version(TOOL),
        config=config,
        run_id=run_id,
        started_at=started_at,
    )
    inputs = open_storage(config.input, config.storage)
    outputs = open_storage(config.output, config.storage)
    shapefile = config.postprocessing.shapefile
    shapes = (
        open_storage(shapefile.location, config.storage)
        if config.postprocessing.plots and shapefile is not None
        else None
    )
    outcome = run_items(
        [config.base_datetime],
        partial(_nowcast_item, config, inputs, outputs, shapes),
        context=context,
        item_id=cycle_token,
    )
    return outcome.raise_for_status()


def _shapes(config: NowcastConfig, storage: Storage | None) -> list[Any]:
    shapefile = config.postprocessing.shapefile
    if storage is None or shapefile is None:
        return []
    return read_shapes(storage, shapefile.key)


def _nowcast_item(
    config: NowcastConfig,
    inputs: Storage,
    outputs: Storage,
    shapes: Storage | None,
    base: datetime,
) -> ItemReport:
    selection = select_frames(
        base,
        max_staleness=config.max_input_staleness,
        num_past=config.num_past_samples,
        min_frames=(
            config.num_past_samples
            if config.min_input_frames is None
            else config.min_input_frames
        ),
        present=lambda slot: inputs.stat(frame_key(slot)) is not None,
    )
    issue = selection.issue_time
    log_event(
        _LOG,
        logging.INFO,
        "nowcast.issued",
        base_datetime=cycle_token(base),
        issue_time=cycle_token(issue),
        newest_frame=cycle_token(selection.slots[-1]),
        frames_used=len(selection.slots),
    )
    naive = issue.replace(tzinfo=None)
    result = predict_subgrids(
        InputData(inputs),
        config.subgrids,
        slots=tuple(slot.replace(tzinfo=None) for slot in selection.slots),
        num_future_samples=config.num_future_samples,
    )
    receipts = [write_inference_results(result, outputs, naive)]
    if config.postprocessing.plots:
        receipts += write_cloud_motion_plots(
            result, outputs, _shapes(config, shapes)
        )
    return ItemReport.succeeded(
        "stale_input" if issue < base else None,
        bytes_written=sum(receipt.size for receipt in receipts),
        artifacts_written=len(receipts),
    )
