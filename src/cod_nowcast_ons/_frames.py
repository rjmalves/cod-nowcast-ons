import posixpath
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import polars as pl
import xarray as xr
from nwp_core.storage import StorageLocation

from cod_nowcast_ons._config import Subgrid
from cod_nowcast_ons._storage import StorageFactory

FRAMES_PREFIX: Final = "goes_processed"


def frames_folder(location: StorageLocation) -> str:
    return posixpath.join(location.uri, FRAMES_PREFIX)


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
    def from_parquet(
        cls, config: Subgrid, time: datetime, directory: str
    ) -> "SubgridInputData":
        storage = StorageFactory.get_storage(directory)

        filepath = storage.join_path(directory, cls.goes_input_filename(time))

        df = (
            storage.read_parquet(filepath)
            .filter(
                (pl.col("latitude") >= config.lat[0])
                & (pl.col("latitude") <= config.lat[1])
                & (pl.col("longitude") >= config.lon[0])
                & (pl.col("longitude") <= config.lon[1])
            )
            .collect()
        )
        df = df.with_columns(
            [
                pl.lit(time).alias("time").cast(pl.Datetime),
            ]
        )
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

    def __init__(self, path: str):
        self.path = path

    def for_subgrid(
        self,
        subgrid: Subgrid,
        num_past_samples: int,
        base_datetime: datetime,
    ) -> xr.DataArray:
        goes_times = [
            base_datetime - timedelta(minutes=10 * i)
            for i in reversed(range(1, num_past_samples + 1))
        ]
        cod_dfs = []
        for time in goes_times:
            subgrid_data = SubgridInputData.from_parquet(
                subgrid, time, self.path
            )
            cod_dfs.append(subgrid_data.cod)
        cod_df: pl.DataFrame = pl.concat(cod_dfs).sort(self.INDEX_COLS)
        cod_pd_df = cod_df.to_pandas().set_index(self.INDEX_COLS)
        cod_xr = cod_pd_df.to_xarray()["cod"]
        return cod_xr
