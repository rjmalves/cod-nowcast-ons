from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import polars as pl
import xarray as xr
from nwp_core.storage import Storage

from cod_nowcast_ons._config import Subgrid

FRAMES_PREFIX: Final = "goes_processed"


def frame_key(slot: datetime) -> str:
    return f"{FRAMES_PREFIX}/{SubgridInputData.goes_input_filename(slot)}"


@dataclass
class SubgridInputData:
    name: str
    latitude_range: tuple[float, float]
    longitude_range: tuple[float, float]
    time: datetime
    cod: pl.DataFrame

    @classmethod
    def goes_input_filename(cls, time: datetime) -> str:
        return f"GOES_COD_BR_{time.strftime('%Y%m%d-%H%M')}.parquet"

    @classmethod
    def from_storage(
        cls, config: Subgrid, time: datetime, storage: Storage
    ) -> SubgridInputData:
        with storage.open_read(frame_key(time)) as stream:
            frame = pl.read_parquet(stream)

        df = frame.filter(
            (pl.col("latitude") >= config.lat[0])
            & (pl.col("latitude") <= config.lat[1])
            & (pl.col("longitude") >= config.lon[0])
            & (pl.col("longitude") <= config.lon[1])
        )
        df = df.with_columns(pl.lit(time).alias("time").cast(pl.Datetime))
        return cls(
            name=config.name,
            latitude_range=config.lat,
            longitude_range=config.lon,
            time=time,
            cod=df,
        )


class InputData:
    INDEX_COLS = [
        "time",
        "latitude",
        "longitude",
    ]

    def __init__(self, storage: Storage):
        self.storage = storage

    def for_subgrid(
        self, subgrid: Subgrid, slots: Sequence[datetime]
    ) -> xr.DataArray:
        cod_dfs = [
            SubgridInputData.from_storage(subgrid, slot, self.storage).cod
            for slot in slots
        ]
        cod_df = pl.concat(cod_dfs).sort(self.INDEX_COLS)
        cod_pd_df = cod_df.to_pandas().set_index(self.INDEX_COLS)
        return cod_pd_df.to_xarray()["cod"]
