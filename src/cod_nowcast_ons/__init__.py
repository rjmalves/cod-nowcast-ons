"""
cod-nowcast-ons
====================

cod-nowcast-ons is a Cloud Motion Forecast tool developed by ONS
(Operador Nacional do Sistema Elétrico) for the Brazilian electric system.
It currently wraps the pySTEPS project and produces Cloud Optical
Density (COD) forecasts to be used for generating cloudy-sky irradiance
predictions through radiation transfer models.
"""

import importlib.metadata

from cod_nowcast_ons._api import nowcast
from cod_nowcast_ons._config import (
    NowcastConfig,
    Postprocessing,
    Shapefile,
    Subgrid,
)

__version__ = importlib.metadata.version("cod-nowcast-ons")
__all__ = [
    "NowcastConfig",
    "Postprocessing",
    "Shapefile",
    "Subgrid",
    "__version__",
    "nowcast",
]
