from __future__ import annotations

import contextlib
import io
import logging
import threading
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import ModuleType

import numpy as np
import xarray as xr
from nwp_core.logging import log_event

from cod_nowcast_ons._config import Subgrid
from cod_nowcast_ons._frames import InputData

_LOG = logging.getLogger(__name__)
_PYSTEPS_LOCK = threading.Lock()
_PYSTEPS: tuple[ModuleType, ModuleType] | None = None


def load_pysteps() -> tuple[ModuleType, ModuleType]:
    """Return pysteps.motion and pysteps.nowcasts, importing them once."""
    global _PYSTEPS
    with _PYSTEPS_LOCK:
        if _PYSTEPS is None:
            buffer = io.StringIO()
            with warnings.catch_warnings(), contextlib.redirect_stdout(buffer):
                warnings.simplefilter("ignore", SyntaxWarning)
                from pysteps import motion, nowcasts
            log_event(
                _LOG, logging.DEBUG, "pysteps.import", stdout=buffer.getvalue()
            )
            _PYSTEPS = (motion, nowcasts)
        return _PYSTEPS


class CloudMotionForecast:
    TIME_STEP_MINUTES = 10
    MOTION_FIELD_METHOD = "LK"
    NOWCAST_METHOD = "extrapolation"

    def __init__(self, cod: xr.DataArray):
        self.cod = cod

    def _eval_motion_field(self, cod: np.ndarray) -> np.ndarray:
        motion, _ = load_pysteps()
        oflow_method = motion.get_method(self.MOTION_FIELD_METHOD)
        motion_field: np.ndarray = oflow_method(cod)
        return motion_field

    def _prepares_forecasting_sample(self, cod: np.ndarray) -> np.ndarray:
        last_sample = cod[-1, :, :]
        last_sample[~np.isfinite(last_sample)] = 0
        return last_sample

    def _forecast_with_motion_field(
        self,
        last_sample: np.ndarray,
        motion_field: np.ndarray,
        n_leadtimes: int,
    ) -> xr.DataArray:
        _, nowcasts = load_pysteps()
        extrapolate = nowcasts.get_method(self.NOWCAST_METHOD)
        cod_forecast = extrapolate(last_sample, motion_field, n_leadtimes)
        last_sample_time_step = self.cod.time.values[-1]
        # Casts to python datetime if is numpy datetime
        last_sample_time_step = (
            last_sample_time_step
            if isinstance(last_sample_time_step, datetime)
            else last_sample_time_step.astype("M8[ms]").astype(datetime)
        )
        times_cod_forecast = np.array(
            [
                last_sample_time_step
                + timedelta(minutes=self.TIME_STEP_MINUTES * (i + 1))
                for i in range(n_leadtimes)
            ],
            dtype="datetime64",
        )
        return xr.DataArray(
            np.transpose(cod_forecast, (1, 2, 0)),
            dims=("latitude", "longitude", "time"),
            coords={
                "latitude": self.cod.latitude.values,
                "longitude": self.cod.longitude.values,
                "time": times_cod_forecast,
            },
        )

    def forecast(self, n_leadtimes: int) -> xr.DataArray:
        cod = np.array(self.cod)
        self.motion_field = self._eval_motion_field(cod)
        last_sample = self._prepares_forecasting_sample(cod)
        self.cod_forecast = self._forecast_with_motion_field(
            last_sample, self.motion_field, n_leadtimes
        )
        return self.cod_forecast


@dataclass
class SubgridResult:
    cod: xr.DataArray
    motion_field: np.ndarray


@dataclass
class InferenceResult:
    subgrid_results: dict[str, SubgridResult]


def predict_subgrids(
    reader: InputData,
    subgrids: Sequence[Subgrid],
    *,
    slots: Sequence[datetime],
    num_future_samples: int,
) -> InferenceResult:
    """Forecast every subgrid from the frames at ``slots``.

    ``slots`` are naive UTC, oldest first, as the input guard selected them.
    """
    results = {}
    for subgrid in subgrids:
        subgrid_data = reader.for_subgrid(subgrid, slots)
        steps = CloudMotionForecast(subgrid_data)
        cod = steps.forecast(num_future_samples)
        results[subgrid.name] = SubgridResult(
            cod=cod, motion_field=steps.motion_field
        )
    return InferenceResult(subgrid_results=results)
