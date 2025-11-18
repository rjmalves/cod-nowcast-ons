import os
from typing import Tuple

import cartopy
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib import colors, rcParams
from PIL import Image


def _cod_colormap_and_norm() -> Tuple[colors.Colormap, colors.BoundaryNorm]:
    color_list = (
        np.array([
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
        ])
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


def render_cod_forecast_frame(
    cod_forecast: xr.DataArray,
    motion_field: np.ndarray,
    step: int,
    figsize_pixels: tuple = (720, 720),
    image_output_dir: str = "steps",
    shapefile_path: str = "data/shapes/BR_UF_2022.shp",
) -> str:
    """Render a single COD forecast frame and save it to disk.

    Args:
        cod_forecast: 3D DataArray with dims (latitude, longitude, time).
        motion_field: 2xHxW motion field (U,V) from pysteps.
        step: Frame index (time dimension index) to render.
        image_output_dir: Directory where the frame image will be saved.
        shapefile_path: Path to the shapefile for borders/outlines.

    Returns:
        The saved filename for the rendered frame.
    """
    os.makedirs(image_output_dir, exist_ok=True)

    cmap, norm = _cod_colormap_and_norm()

    shapefile = list(shpreader.Reader(shapefile_path).geometries())

    plt.cla()
    plt.close()
    plt.figure(figsize=[p / rcParams["figure.dpi"] for p in figsize_pixels])
    ax = plt.axes(projection=ccrs.PlateCarree())

    minlon = cod_forecast.longitude.min().item()
    maxlon = cod_forecast.longitude.max().item()
    minlat = cod_forecast.latitude.min().item()
    maxlat = cod_forecast.latitude.max().item()

    grid_lat, grid_lon = np.mgrid[
        minlat : maxlat : complex(cod_forecast.latitude.values.shape[0] + 1),
        minlon : maxlon : complex(cod_forecast.longitude.values.shape[0] + 1),
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

    plt.colorbar(
        img, label="COD", orientation="horizontal", pad=0.03, fraction=0.05
    )

    skip = (slice(None, None, 20), slice(None, None, 20))
    U = motion_field[0, :, :][skip]
    V = motion_field[1, :, :][skip].copy()
    x_grid = grid_lon[skip]
    y_grid = grid_lat[skip]
    plt.quiver(x_grid, y_grid, U, V, width=0.0015, zorder=20)

    ax.add_geometries(
        shapefile,
        ccrs.PlateCarree(),
        edgecolor="black",
        facecolor="none",
        linewidth=0.3,
        zorder=30,
    )

    ax.coastlines(resolution="10m", color="black", linewidth=0.8, zorder=30)
    ax.add_feature(
        cartopy.feature.BORDERS, edgecolor="black", linewidth=0.5, zorder=30
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

    filename = f"{image_output_dir}/{step}.png"
    plt.savefig(filename, bbox_inches="tight", pad_inches=0)
    plt.close()
    return filename


def generate_cod_forecast_gif(
    cod_forecast: xr.DataArray,
    motion_field: np.ndarray,
    figsize_pixels: tuple = (720, 720),
    output_gif_filename: str = "forecast.gif",
    frame_interval_ms: int = 300,
    repeat_delay_ms: int = 700,
    image_output_dir: str = "steps",
    keep_frames: bool = False,
) -> None:
    """Generate an animated GIF from COD forecast and motion field.

    This renders frame images using render_cod_forecast_frame and then composes
    them into an animated GIF.
    """
    raw = np.array(cod_forecast).transpose((2, 0, 1))
    n_leadtimes = raw.shape[0]

    os.makedirs(image_output_dir, exist_ok=True)
    filenames = []
    for step in range(n_leadtimes):
        filenames.append(
            render_cod_forecast_frame(
                cod_forecast,
                motion_field,
                step,
                figsize_pixels=figsize_pixels,
                image_output_dir=image_output_dir,
            )
        )

    images = [Image.open(fname) for fname in filenames]

    fig, ax = plt.subplots()
    fig.set_size_inches(*[p / rcParams["figure.dpi"] for p in figsize_pixels])
    ax.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    im = ax.imshow(images[0], animated=True)

    def update(i):
        im.set_array(images[i])
        return (im,)

    animation_fig = animation.FuncAnimation(
        fig,
        update,
        frames=len(images),
        interval=frame_interval_ms,
        blit=True,
        repeat_delay=repeat_delay_ms,
    )
    animation_fig.save(output_gif_filename)

    if not keep_frames:
        for fname in filenames:
            os.remove(fname)
