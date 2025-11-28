from dataclasses import dataclass
from datetime import datetime

import pyjson5


@dataclass
class SubgridConfig:
    name: str
    lat: list[float]
    lon: list[float]

    @classmethod
    def parse(cls, subgrid_dict: dict) -> "SubgridConfig":
        return cls(
            name=subgrid_dict["name"],
            lat=subgrid_dict["lat"],
            lon=subgrid_dict["lon"],
        )


@dataclass
class PostprocessingConfig:
    plots: bool
    shapefile_path: str | None

    @classmethod
    def parse(cls, config: dict) -> "PostprocessingConfig":
        return cls(
            plots=config.get("plots", False),
            shapefile_path=config.get("shapefile_path"),
        )


@dataclass
class Config:
    mode: str
    input: str
    output: str
    base_datetime: datetime
    num_past_samples: int
    num_future_samples: int
    subgrids: list[SubgridConfig]
    postprocessing: PostprocessingConfig

    @classmethod
    def parse(cls, config: dict) -> "Config":
        return cls(
            mode=config["mode"],
            input=config["input"],
            output=config["output"],
            base_datetime=datetime.fromisoformat(config["base_datetime"]),
            num_past_samples=config["num_past_samples"],
            num_future_samples=config["num_future_samples"],
            subgrids=[
                SubgridConfig.parse(subgrid) for subgrid in config["subgrids"]
            ],
            postprocessing=PostprocessingConfig.parse(
                config.get("postprocessing", {})
            ),
        )

    @classmethod
    def from_json(cls, json_path: str) -> "Config":
        with open(json_path) as f:
            config = pyjson5.decode(f.read())

        return cls.parse(config)
