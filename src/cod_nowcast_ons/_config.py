from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final, Self

from nwp_core.config import OPERATIONAL, ToolConfig, parse_duration
from nwp_core.storage import StorageLocation, StorageSettings
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

SLOT: Final = timedelta(minutes=10)
ENV_PREFIX: Final = "COD_NOWCAST_ONS"

_NAME = re.compile(r"[A-Za-z0-9._-]{1,255}", re.ASCII)
_NESTED = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def _check_name(value: str) -> str:
    if (
        _NAME.fullmatch(value) is None
        or value in {".", ".."}
        or value.startswith(".nwp-")
    ):
        msg = (
            "name must hold 1 to 255 characters of [A-Za-z0-9._-], and must"
            " not be '.', '..' or start with '.nwp-'"
        )
        raise ValueError(msg)
    return value


def _utc(value: object) -> object:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return value


def _on_grid(value: datetime) -> datetime:
    if (
        value.second
        or value.microsecond
        or timedelta(minutes=value.minute) % SLOT
    ):
        msg = "must fall on a 10-minute slot with zero seconds"
        raise ValueError(msg)
    return value


def _duration(value: object) -> object:
    return parse_duration(value) if isinstance(value, str) else value


def _staleness(value: timedelta) -> timedelta:
    if value < SLOT or value % SLOT != timedelta(0):
        msg = "must be a positive multiple of 10 minutes"
        raise ValueError(msg)
    return value


_Latitude = Annotated[float, Field(ge=-90.0, le=90.0, allow_inf_nan=False)]
_Longitude = Annotated[float, Field(ge=-180.0, le=180.0, allow_inf_nan=False)]


class Subgrid(BaseModel):
    model_config = _NESTED

    name: Annotated[
        str,
        AfterValidator(_check_name),
        Field(description="Subgrid name, one component of the output keys."),
    ]
    lat: Annotated[
        tuple[_Latitude, _Latitude],
        Field(
            description="South and north bounds in degrees within [-90, 90],"
            " south first."
        ),
    ]
    lon: Annotated[
        tuple[_Longitude, _Longitude],
        Field(
            description="West and east bounds in degrees within [-180, 180],"
            " west first."
        ),
    ]

    @model_validator(mode="after")
    def _ordered_bounds(self) -> Self:
        if not (self.lat[0] < self.lat[1] and self.lon[0] < self.lon[1]):
            msg = "lat and lon must each be increasing"
            raise ValueError(msg)
        return self


class Shapefile(BaseModel):
    model_config = _NESTED

    key: Annotated[
        str,
        Field(description="Object key of the .shp file under the location."),
    ]
    location: Annotated[
        StorageLocation,
        Field(description="Where the shapefile components are stored."),
    ]


class Postprocessing(BaseModel):
    model_config = _NESTED

    plots: Annotated[bool, Field(description="Render the forecast plots.")] = (
        False
    )
    shapefile: Annotated[
        Shapefile | None,
        Field(description="Extra borders for the plots; unset draws none."),
    ] = None


class NowcastConfig(ToolConfig):
    base_datetime: Annotated[
        datetime,
        OPERATIONAL,
        BeforeValidator(_utc),
        AfterValidator(_on_grid),
        Field(description="Forecast base instant, UTC on a 10-minute slot."),
    ]
    input: Annotated[
        StorageLocation,
        OPERATIONAL,
        Field(description="Where the GOES COD frames are read from."),
    ]
    output: Annotated[
        StorageLocation,
        OPERATIONAL,
        Field(description="Where the forecasts are written."),
    ]
    num_past_samples: Annotated[
        int, Field(ge=2, description="Past frames used to estimate motion.")
    ]
    num_future_samples: Annotated[
        int, Field(ge=1, description="Future frames to forecast.")
    ]
    max_input_staleness: Annotated[
        timedelta,
        OPERATIONAL,
        BeforeValidator(_duration),
        AfterValidator(_staleness),
        Field(
            description=(
                "ISO 8601 duration, a multiple of 10 minutes, the newest"
                " input frame may lag the base instant."
            )
        ),
    ] = SLOT
    min_input_frames: Annotated[
        int | None,
        OPERATIONAL,
        Field(
            description=(
                "Fewest input frames accepted; unset means num_past_samples."
            )
        ),
    ] = None
    subgrids: Annotated[
        tuple[Subgrid, ...],
        Field(min_length=1, description="Regions to forecast, unique names."),
    ]
    postprocessing: Annotated[
        Postprocessing, Field(description="Plot and shapefile options.")
    ] = Postprocessing()
    storage: Annotated[
        StorageSettings,
        OPERATIONAL,
        Field(description="Retry, timeout and pool settings of the storage."),
    ] = StorageSettings()

    @field_validator("min_input_frames")
    @classmethod
    def _frames_within_past(
        cls, value: int | None, info: ValidationInfo
    ) -> int | None:
        if value is None:
            return value
        past = info.data.get("num_past_samples")
        if value < 2 or (past is not None and value > past):
            msg = "must satisfy 2 <= value <= num_past_samples"
            raise ValueError(msg)
        return value

    @field_validator("subgrids")
    @classmethod
    def _unique_names(cls, value: tuple[Subgrid, ...]) -> tuple[Subgrid, ...]:
        names = [subgrid.name for subgrid in value]
        if len(names) != len(set(names)):
            msg = "subgrid names must be unique"
            raise ValueError(msg)
        return value
