"""Storage backends and offline map stubs of the integration tests."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest
from nwp_core._testing.storage import isolate_aws_env, moto_location
from nwp_core.storage import StorageLocation


@dataclass(frozen=True)
class Backend:
    name: str
    input: StorageLocation
    output: StorageLocation


@pytest.fixture(params=["local", "moto"])
def storage_backend(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Backend]:
    if request.param == "local":
        store = tmp_path / "store"
        input_root = store / "input"
        output_root = store / "output"
        input_root.mkdir(parents=True)
        output_root.mkdir()
        yield Backend(
            name="local",
            input=StorageLocation(uri=str(input_root)),
            output=StorageLocation(uri=str(output_root)),
        )
        return
    isolate_aws_env(monkeypatch, tmp_path)
    with moto_location() as root:
        yield Backend(
            name="moto",
            input=StorageLocation(uri=f"{root.uri}/input"),
            output=StorageLocation(uri=f"{root.uri}/output"),
        )


@pytest.fixture
def offline_maps(
    monkeypatch: pytest.MonkeyPatch, generated_shapefile: Path
) -> None:
    def refuse(*args: object, **kwargs: object) -> NoReturn:
        msg = "network access is disabled"
        raise OSError(msg)

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(
        "cartopy.io.shapereader.natural_earth",
        lambda **_: str(generated_shapefile),
    )
    monkeypatch.setattr("cartopy.feature._NATURAL_EARTH_GEOM_CACHE", {})
