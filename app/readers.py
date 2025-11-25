from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl
import xarray as xr

from app.internal.config import SubgridConfig
from app.storage import StorageFactory


@dataclass
class SubgridInputData:
    name: str
    latitude_range: list[float]
    longitude_range: list[float]
    time: datetime
    cod: pl.DataFrame

    @classmethod
    def goes_input_filename(cls, time: datetime) -> str:
        return f"GOES_COD_BR_{time.strftime('%Y%m%d-%H%M')}.parquet"

    @classmethod
    def from_parquet(
        cls, config: SubgridConfig, time: datetime, directory: str
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
        subgrid: SubgridConfig,
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
