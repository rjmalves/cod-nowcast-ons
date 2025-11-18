from dataclasses import dataclass

import numpy as np
import xarray as xr

from app.internal.config import Config, SubgridConfig
from app.readers import InputData
from app.services.cloud_motion_forecast import CloudMotionForecast


@dataclass
class SubgridResult:
    cod: xr.DataArray
    motion_field: np.ndarray


@dataclass
class InferenceResult:
    subgrid_results: dict[str, SubgridResult]


class InferenceManager:
    def __init__(self, config: Config, reader: InputData):
        self.config = config
        self.reader = reader

    def _predict_for_subgrid(self, subgrid: SubgridConfig) -> SubgridResult:
        subgrid_data = self.reader.for_subgrid(
            subgrid, self.config.num_past_samples, self.config.base_datetime
        )
        steps = CloudMotionForecast(subgrid_data)
        cod = steps.forecast(self.config.num_future_samples)
        return SubgridResult(
            cod=cod,
            motion_field=steps.motion_field,
        )

    def predict(self) -> InferenceResult:
        results = {}
        for subgrid in self.config.subgrids:
            results[subgrid.name] = self._predict_for_subgrid(subgrid)
        return InferenceResult(subgrid_results=results)
