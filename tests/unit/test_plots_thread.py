from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = """
import json
import socket
import sys
import threading
from pathlib import Path

import cartopy.io.shapereader as shapereader
import numpy as np
import xarray as xr
from nwp_core.storage import StorageLocation, open_storage

from cod_nowcast_ons._plots import (
    animate_frames,
    read_shapes,
    render_cod_forecast_frame,
)


def refuse(*args, **kwargs):
    raise OSError("network access is disabled")


socket.socket.connect = refuse
shapereader.natural_earth = lambda **_: sys.argv[1]

shapefile = Path(sys.argv[1])
cod = xr.DataArray(
    np.linspace(0.0, 40.0, 20 * 20 * 2, dtype=np.float32).reshape(20, 20, 2),
    dims=("latitude", "longitude", "time"),
    coords={
        "latitude": np.linspace(-23.0, -20.0, 20),
        "longitude": np.linspace(-50.0, -47.0, 20),
        "time": np.array(
            ["2024-08-01T00:10", "2024-08-01T00:20"], dtype="datetime64[us]"
        ),
    },
)
motion = np.linspace(-1.0, 1.0, 2 * 20 * 20).reshape(2, 20, 20)
found = {}


def work():
    storage = open_storage(StorageLocation(uri=str(shapefile.parent)))
    shapes = read_shapes(storage, shapefile.name)
    pngs = [
        render_cod_forecast_frame(cod, motion, step, shapes=shapes)
        for step in range(2)
    ]
    found["png"] = pngs[0][:8].hex()
    found["gif"] = animate_frames(pngs)[:6].decode("ascii")


thread = threading.Thread(target=work)
thread.start()
thread.join()
print(
    json.dumps(
        {
            "gif": found["gif"],
            "png": found["png"],
            "pyplot": "matplotlib.pyplot" in sys.modules,
        }
    )
)
"""


def test_plots_render_on_a_worker_thread_without_pyplot(
    generated_shapefile: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", SCRIPT, str(generated_shapefile)],
        env={**os.environ, "MPLBACKEND": "TkAgg", "DISPLAY": ":0"},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "gif": "GIF89a",
        "png": "89504e470d0a1a0a",
        "pyplot": False,
    }
