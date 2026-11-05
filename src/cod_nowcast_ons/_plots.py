from __future__ import annotations

import io
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader
import numpy as np
import xarray as xr
from matplotlib import colors, rcParams
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from nwp_core.storage import Storage
from PIL import Image

_FIGSIZE_PIXELS: Final = (720, 720)
_FRAME_INTERVAL_MS: Final = 300


def _cod_colormap_and_norm() -> tuple[colors.Colormap, colors.BoundaryNorm]:
    color_list = (
        np.array(
            [
                (255, 255, 255),  # 0.0
                (245, 245, 255),  # 0.2
                (180, 180, 255),  # 0.5
                (120, 120, 255),  # 1.5
                (20, 20, 255),  # 2.5
                (0, 216, 195),  # 4.0
                (0, 150, 144),  # 6.0
                (0, 102, 102),  # 10
                (255, 255, 0),  # 15
                (255, 200, 0),  # 20
                (255, 150, 0),  # 30
                (255, 100, 0),  # 40
                (255, 0, 0),  # 50
                (200, 0, 0),  # 60
                (120, 0, 0),  # 75
                (40, 0, 0),  # > 100
            ]
        )
        / 255.0
    )

    clevs = [
        0.0,
        0.2,
        0.5,
        1.0,
        2.0,
        3,
        4,
        5,
        7.5,
        10,
        12.5,
        15,
        20,
        30,
        50,
        100,
        160,
    ]

    cmap = colors.LinearSegmentedColormap.from_list(
        "cmap", color_list, len(clevs) - 1
    )
    cmap.set_over("darkred", 1)
    norm = colors.BoundaryNorm(clevs, cmap.N)
    cmap.set_bad("grey", alpha=0.5)
    cmap.set_under("none")
    return cmap, norm


def read_shapes(storage: Storage, key: str) -> list[Any]:
    """Read the geometries of the shapefile stored under ``key``.

    The ``.shx`` and ``.dbf`` objects must sit beside the ``.shp`` object.
    Cartopy's reader only takes a file name, so the three objects are copied
    to a temporary folder first.

    Raises:
        ObjectNotFoundError: If one of the three objects is absent.
    """
    shp = PurePosixPath(key)
    parts = {
        ".shp": key,
        ".shx": str(shp.with_suffix(".shx")),
        ".dbf": str(shp.with_suffix(".dbf")),
    }
    with tempfile.TemporaryDirectory() as folder:
        for suffix, part in parts.items():
            with storage.open_read(part) as stream:
                Path(folder, f"shapes{suffix}").write_bytes(stream.read())
        reader = shpreader.Reader(str(Path(folder, "shapes.shp")))
        try:
            return list(reader.geometries())
        finally:
            reader.close()


def render_cod_forecast_frame(
    cod_forecast: xr.DataArray,
    motion_field: np.ndarray,
    step: int,
    *,
    shapes: Sequence[Any],
) -> bytes:
    """Render one COD forecast frame and return it as PNG bytes.

    Args:
        cod_forecast: 3D DataArray with dims (latitude, longitude, time).
        motion_field: 2xHxW motion field (U,V) from pysteps.
        step: Frame index (time dimension index) to render.
        shapes: Geometries drawn as extra outlines on top of Cartopy's
            coastlines and borders; empty draws none.
    """
    cmap, norm = _cod_colormap_and_norm()

    width, height = _FIGSIZE_PIXELS
    dpi = rcParams["figure.dpi"]
    fig = Figure(figsize=(width / dpi, height / dpi))
    FigureCanvasAgg(fig)
    ax: Any = fig.add_subplot(projection=ccrs.PlateCarree())

    minlon = cod_forecast.longitude.min().item()
    maxlon = cod_forecast.longitude.max().item()
    minlat = cod_forecast.latitude.min().item()
    maxlat = cod_forecast.latitude.max().item()

    grid_lat, grid_lon = np.mgrid[
        minlat : maxlat : complex(0, cod_forecast.latitude.values.shape[0] + 1),  # type: ignore[misc]  # numpy stubs reject a complex slice step
        minlon : maxlon : complex(
            0, cod_forecast.longitude.values.shape[0] + 1
        ),  # type: ignore[misc]  # numpy stubs reject a complex slice step
    ]

    ax.set_extent([minlon, maxlon, minlat, maxlat], ccrs.PlateCarree())

    img = ax.pcolormesh(
        grid_lon,
        grid_lat,
        np.squeeze(cod_forecast.isel(time=step).values),
        cmap=cmap,
        norm=norm,
        zorder=10,
    )

    fig.colorbar(
        img,
        ax=ax,
        label="COD",
        orientation="horizontal",
        pad=0.03,
        fraction=0.05,
    )

    skip = (slice(None, None, 20), slice(None, None, 20))
    U = motion_field[0, :, :][skip]
    V = motion_field[1, :, :][skip].copy()
    x_grid = grid_lon[skip]
    y_grid = grid_lat[skip]
    ax.quiver(x_grid, y_grid, U, V, width=0.0015, zorder=20)

    if shapes:
        ax.add_geometries(
            shapes,
            ccrs.PlateCarree(),
            edgecolor="black",
            facecolor="none",
            linewidth=0.3,
            zorder=30,
        )

    ax.coastlines(resolution="10m", color="black", linewidth=0.8, zorder=30)
    ax.add_feature(
        cfeature.BORDERS, edgecolor="black", linewidth=0.5, zorder=30
    )
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        color="black",
        alpha=1.0,
        linestyle="--",
        linewidth=0.4,
        xlocs=np.arange(-180, 180, 5),
        ylocs=np.arange(-90, 90, 5),
        draw_labels=True,
    )
    gl.top_labels = False
    gl.right_labels = False

    # Titles
    title_left = "Cloud Optical Depth - Forecast"
    title_right = cod_forecast.time.values[step].item().isoformat()
    ax.set_title(title_left, fontweight="bold", fontsize=10, loc="left")
    ax.set_title(title_right, fontsize=10, loc="right")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0)
    return buffer.getvalue()


def animate_frames(pngs: Sequence[bytes]) -> bytes:
    """Compose the PNG frames, in order, into GIF bytes."""
    frames = [np.asarray(Image.open(io.BytesIO(png))) for png in pngs]

    width, height = _FIGSIZE_PIXELS
    dpi = rcParams["figure.dpi"]
    fig = Figure(figsize=(width / dpi, height / dpi))
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    image = ax.imshow(frames[0], animated=True)

    def update(i: int) -> tuple[AxesImage]:
        image.set_array(frames[i])
        return (image,)

    animation = FuncAnimation(fig, update, frames=len(pngs))
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder, "forecast.gif")
        writer = PillowWriter(fps=1000 / _FRAME_INTERVAL_MS)  # type: ignore[arg-type]  # the stub types fps as int, a float keeps the frame interval exact
        animation.save(target, writer=writer)
        return target.read_bytes()
