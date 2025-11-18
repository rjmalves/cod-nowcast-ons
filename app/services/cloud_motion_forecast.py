from datetime import timedelta

import numpy as np
import xarray as xr
from pysteps import motion, nowcasts


class CloudMotionForecast:
    TIME_STEP_MINUTES = 10
    MOTION_FIELD_METHOD = "LK"
    NOWCAST_METHOD = "extrapolation"

    def __init__(self, cod: xr.DataArray):
        self.cod = cod

    def _eval_motion_field(self, cod: np.ndarray) -> np.ndarray:
        oflow_method = motion.get_method(self.MOTION_FIELD_METHOD)
        return oflow_method(cod)

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
        extrapolate = nowcasts.get_method(self.NOWCAST_METHOD)
        cod_forecast = extrapolate(last_sample, motion_field, n_leadtimes)
        last_sample_time_step = self.cod.time.values[-1]
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
