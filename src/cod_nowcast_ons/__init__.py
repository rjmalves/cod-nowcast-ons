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

__version__ = importlib.metadata.version("cod-nowcast-ons")
__all__ = ["__version__"]
