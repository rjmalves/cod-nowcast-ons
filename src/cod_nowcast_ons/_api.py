from __future__ import annotations

import importlib.metadata
import logging
from datetime import datetime
from functools import partial
from typing import Final

from nwp_core.layout import cycle_token
from nwp_core.logging import log_event
from nwp_core.run import ItemReport, RunContext, RunOutcome, run_items
from nwp_core.storage import Storage, open_storage

from cod_nowcast_ons._config import NowcastConfig
from cod_nowcast_ons._forecast import predict_subgrids
from cod_nowcast_ons._frames import InputData, frame_key, frames_folder
from cod_nowcast_ons._guard import select_frames
from cod_nowcast_ons._output import (
    shapefile_path,
    write_cloud_motion_plots,
    write_inference_results,
)

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
    storage = open_storage(config.input, config.storage)
    outcome = run_items(
        [config.base_datetime],
        partial(_nowcast_item, config, storage),
        context=context,
        item_id=cycle_token,
    )
    return outcome.raise_for_status()


def _nowcast_item(
    config: NowcastConfig, storage: Storage, base: datetime
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
        present=lambda slot: storage.stat(frame_key(slot)) is not None,
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
        InputData(frames_folder(config.input)),
        config.subgrids,
        issue_time=naive,
        num_frames=len(selection.slots),
        num_future_samples=config.num_future_samples,
    )
    write_inference_results(result, config.output.uri, naive)
    if config.postprocessing.plots:
        write_cloud_motion_plots(
            result,
            config.output.uri,
            shapefile_path(config.postprocessing.shapefile),
        )
    return ItemReport.succeeded("stale_input" if issue < base else None)
