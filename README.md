# cod-nowcast-ons

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![pySTEPS](https://img.shields.io/badge/pySTEPS-1.18.1+-green.svg)](https://pysteps.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Cloud Optical Depth nowcasting using GOES satellite imagery and optical flow-based extrapolation**

`cod-nowcast-ons` is a specialized nowcasting tool for Cloud Optical Depth (COD) derived from GOES satellite data. It provides short-term (up to ~1 hour) forecasts by applying optical flow motion detection and extrapolation techniques from the [pySTEPS](https://pysteps.readthedocs.io/) library to satellite-derived cloud properties.

## Table of Contents

- [Features](#features)
- [Quickstart](#quickstart)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Basic Usage](#basic-usage)
- [Methodology](#methodology)
  - [Overview](#overview)
  - [Motion Detection: Lucas-Kanade Optical Flow](#motion-detection-lucas-kanade-optical-flow)
  - [Nowcasting: Lagrangian Extrapolation](#nowcasting-lagrangian-extrapolation)
  - [Workflow Summary](#workflow-summary)
- [Configuration](#configuration)
  - [Configuration File Structure](#configuration-file-structure)
  - [Configuration Options](#configuration-options)
- [Outputs](#outputs)
  - [Forecast Data](#forecast-data)
  - [Visualizations](#visualizations)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
  - [Debug Tips](#debug-tips)
- [License](#license)

---

## Features

- **Optical Flow-Based Motion Detection**: Uses Lucas-Kanade (LK) method to estimate cloud motion vectors
- **Lagrangian Extrapolation**: Projects cloud fields forward in time based on detected motion
- **GOES Satellite Support**: Specifically designed for GOES-derived Cloud Optical Depth data
- **Subgrid Processing**: Configure multiple geographic regions of interest for parallel forecasting
- **S3 Storage Support**: Transparent read/write from Amazon S3 buckets with automatic backend selection
- **Automated Visualization**: Generate animated GIF forecasts with motion vectors overlaid
- **Flexible Output**: Export results as Parquet files for downstream analysis
- **Simple Configuration**: JSON-based configuration with sensible defaults

---

## Quickstart

### Prerequisites

- Python 3.11 or higher
- Linux-based system (tested on Ubuntu/Debian)
- GOES satellite COD data in Parquet format with columns: `latitude`, `longitude`, `cod` (Cloud Optical Depth)

### Installation

#### System-wide Installation (requires sudo)

```bash
git clone https://github.com/yourusername/cod-nowcast-ons.git
cd cod-nowcast-ons
sudo make install
```

#### User Installation (no sudo required)

```bash
git clone https://github.com/yourusername/cod-nowcast-ons.git
cd cod-nowcast-ons
make install-user
```

The installation will:

- Create a Python virtual environment
- Install all dependencies including pySTEPS, xarray, and visualization tools
- Create a CLI command `cod-nowcast-ons`

### Basic Usage

1. **Prepare your configuration file**:

```bash
cp config.example.jsonc config.jsonc
# Edit config.jsonc with your parameters
```

2. **Prepare input data**:

Place GOES COD Parquet files in your input directory (e.g., `data/input/`). Files should be named:

```
GOES_COD_BR_YYYYMMDD-HHMM.parquet
```

3. **Run the forecast**:

```bash
cod-nowcast-ons --config config.jsonc
```

4. **Check outputs**:

Results will be written to your configured output directory:

- `data/output/cod.parquet` - Forecast data
- `data/output/plots/*.gif` - Animated forecast visualizations (if enabled)

---

## Methodology

### Overview

`cod-nowcast-ons` implements a **deterministic Lagrangian nowcasting approach** for Cloud Optical Depth fields. The methodology is built on the [pySTEPS](https://pysteps.readthedocs.io/) framework and consists of two primary stages:

1. **Motion Field Estimation** using Lucas-Kanade optical flow
2. **Field Extrapolation** using Lagrangian advection

This approach is particularly suitable for short-term (0-60 minutes) forecasting where the assumption of field persistence and advection is reasonable.

### Motion Detection: Lucas-Kanade Optical Flow

The Lucas-Kanade (LK) method is an optical flow algorithm that estimates motion between consecutive images by assuming:

- **Brightness constancy**: Pixel intensities remain constant between frames
- **Small motion**: Displacement between frames is small
- **Spatial coherence**: Neighboring pixels belong to the same surface and have similar motion

**Implementation details**:

- **Input**: Historical COD fields (typically 6 time steps at 10-minute intervals = 50 minutes of history)
- **Method**: `pysteps.motion.LK` (Lucas-Kanade)
- **Output**: 2D motion field (U, V components) representing cloud motion in latitude/longitude space

The LK method computes motion vectors by solving:

$$
\nabla I \cdot \mathbf{v} + \frac{\partial I}{\partial t} = 0
$$

where $I$ is the image intensity (COD values), $\mathbf{v} = (u, v)$ is the velocity vector, and $\nabla I$ is the spatial gradient.

**Reference**: [pySTEPS LK Buffer Mask Example](https://pysteps.readthedocs.io/en/stable/auto_examples/LK_buffer_mask.html)

### Nowcasting: Lagrangian Extrapolation

Once the motion field is estimated, the forecast is generated using **semi-Lagrangian advection**:

$$
\text{COD}(x, y, t + \Delta t) \approx \text{COD}(x - u\Delta t, y - v\Delta t, t)
$$

where $(u, v)$ are the motion vectors at position $(x, y)$.

**Implementation details**:

- **Method**: `pysteps.nowcasts.extrapolation` (deterministic extrapolation)
- **Time step**: 10 minutes (configurable via `TIME_STEP_MINUTES`)
- **Lead times**: Configurable (default: 6 steps = 60 minutes ahead)
- **Interpolation**: Backward semi-Lagrangian scheme with bilinear interpolation

The extrapolation method applies the motion field to advect the last observed COD field forward in time, assuming the motion field remains constant over the forecast period.

**Reference**: [pySTEPS Extrapolation Nowcast Example](https://pysteps.readthedocs.io/en/stable/auto_examples/plot_extrapolation_nowcast.html)

### Workflow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Input Data Loading                                           │
│    - Read historical GOES COD Parquet files                     │
│    - Extract subgrid regions (latitude/longitude bounds)        │
│    - Convert to xarray.DataArray (time × lat × lon)             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Motion Field Estimation (Lucas-Kanade)                       │
│    - Apply LK optical flow to historical COD sequence           │
│    - Generate 2D velocity field (U, V components)               │
│    - Handle missing data and buffer zones                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Extrapolation Nowcast                                        │
│    - Use last observed COD field as initial condition           │
│    - Apply semi-Lagrangian advection with motion field          │
│    - Generate forecasts for N lead times (default: 6 × 10min)   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Output Generation                                            │
│    - Export forecast DataArray to Parquet (flattened)           │
│    - Generate visualization frames with motion vectors          │
│    - Compose animated GIF with forecast evolution               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Assumptions**:

- Cloud motion is approximately constant over the forecast period
- COD values are advected without transformation (no growth/decay modeling)
- Missing data regions remain missing in forecasts

**Limitations**:

- Forecast skill degrades beyond ~60 minutes due to motion field errors
- No ensemble uncertainty quantification (deterministic forecast only)
- Does not model cloud life cycle (formation, dissipation)

---

## Configuration

### Configuration File Structure

The application uses a JSON configuration file (with comments support via `pyjson5`). Create your config from the example:

```bash
cp config.example.jsonc config.jsonc
```

### Configuration Options

| Parameter              | Type    | Required | Default | Description                                                                                                                                         |
| ---------------------- | ------- | -------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mode`                 | string  | Yes      | -       | Application mode. Currently only `"inference"` is supported.                                                                                        |
| `input`                | string  | Yes      | -       | Path to directory containing input GOES COD Parquet files. Can be local path or S3 URI.                                                             |
| `output`               | string  | Yes      | -       | Path to directory where outputs will be written. Can be local path or S3 URI.                                                                       |
| `base_datetime`        | string  | Yes      | -       | ISO 8601 datetime string (e.g., `"2024-08-01T10:00:00"`) representing the forecast reference time. Historical data is read backward from this time. |
| `num_past_samples`     | integer | Yes      | -       | Number of historical time steps to use for motion estimation. Recommended: 6 (= 50 minutes with 10-min intervals).                                  |
| `num_future_samples`   | integer | Yes      | -       | Number of forecast lead times to generate. Each step is 10 minutes. Example: 6 = 60-minute forecast.                                                |
| `subgrids`             | array   | Yes      | -       | List of geographic subregions for processing. Each subgrid must have `name`, `lat`, and `lon`.                                                      |
| `subgrids[].name`      | string  | Yes      | -       | Identifier for the subgrid (e.g., `"SE"` for Southeast Brazil). Used in output filenames.                                                           |
| `subgrids[].lat`       | array   | Yes      | -       | Latitude bounds `[min_lat, max_lat]` in decimal degrees.                                                                                            |
| `subgrids[].lon`       | array   | Yes      | -       | Longitude bounds `[min_lon, max_lon]` in decimal degrees.                                                                                           |
| `postprocessing`       | object  | No       | `{}`    | Postprocessing options.                                                                                                                             |
| `postprocessing.plots` | boolean | No       | `false` | Whether to generate visualization plots (PNG frames + GIF animations).                                                                              |

**Example Configuration**:

```jsonc
{
  "mode": "inference",
  "input": "data/input",
  "output": "data/output",
  "base_datetime": "2024-08-01T10:00:00",
  "num_past_samples": 6,
  "num_future_samples": 6,
  "subgrids": [
    {
      "name": "SE",
      "lat": [-23.0, -2.0],
      "lon": [-53.0, -35.0]
    },
    {
      "name": "NE",
      "lat": [-18.0, -1.0],
      "lon": [-48.0, -34.0]
    }
  ],
  "postprocessing": {
    "plots": true
  }
}
```

**Input Data Requirements**:

- Files must be named: `GOES_COD_BR_YYYYMMDD-HHMM.parquet`
- Required columns: `latitude`, `longitude`, `cod`
- Data should be on a regular lat/lon grid
- Missing values should be NaN or null

---

## S3 Storage Support

`cod-nowcast-ons` includes transparent support for Amazon S3 storage, allowing you to read input data from and write output data to S3 buckets without code changes. The application automatically detects S3 URIs and uses the appropriate storage backend.

### Features

- **Transparent I/O**: Use S3 URIs just like local paths in your configuration
- **Mixed Storage**: Input from S3, output locally (or vice versa)
- **Full Feature Support**: All operations work with S3 (Parquet read/write, plot generation)
- **AWS Credentials**: Uses standard AWS credential chain (environment variables, AWS CLI, IAM roles)

### Configuration Examples

#### Local Filesystem (Traditional)

```jsonc
{
  "mode": "inference",
  "input": "data/input",
  "output": "data/output",
  "base_datetime": "2024-08-01T10:00:00",
  "num_past_samples": 6,
  "num_future_samples": 6,
  "subgrids": [
    {
      "name": "SE",
      "lat": [-23.0, -2.0],
      "lon": [-53.0, -35.0]
    }
  ]
}
```

#### S3 Input and Output

```jsonc
{
  "mode": "inference",
  "input": "s3://my-weather-bucket/goes-cod/input",
  "output": "s3://my-weather-bucket/goes-cod/output",
  "base_datetime": "2024-08-01T10:00:00",
  "num_past_samples": 6,
  "num_future_samples": 6,
  "subgrids": [
    {
      "name": "SE",
      "lat": [-23.0, -2.0],
      "lon": [-53.0, -35.0]
    }
  ]
}
```

#### Mixed: S3 Input, Local Output

```jsonc
{
  "mode": "inference",
  "input": "s3://my-weather-bucket/goes-cod/input",
  "output": "data/output",
  "base_datetime": "2024-08-01T10:00:00",
  "num_past_samples": 6,
  "num_future_samples": 6,
  "subgrids": [
    {
      "name": "SE",
      "lat": [-23.0, -2.0],
      "lon": [-53.0, -35.0]
    }
  ]
}
```

### AWS Authentication

The application uses standard AWS credential resolution order:

#### 1. Environment Variables

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

cod-nowcast-ons --config config.jsonc
```

#### 2. AWS CLI Configuration

```bash
aws configure
# Follow prompts to set:
#   AWS Access Key ID
#   AWS Secret Access Key
#   Default region name
#   Default output format

cod-nowcast-ons --config config.jsonc
```

#### 3. IAM Role (EC2/ECS/Lambda)

When running on AWS compute services with an attached IAM role, no credentials are needed:

```bash
# Running on EC2 instance with IAM role
cod-nowcast-ons --config config.jsonc
```

### Required S3 Permissions

Your AWS credentials or IAM role must have the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-weather-bucket/*",
        "arn:aws:s3:::my-weather-bucket"
      ]
    }
  ]
}
```

### S3 Data Organization

Organize your S3 bucket similar to local filesystem structure:

```
s3://my-weather-bucket/
├── goes-cod/
│   ├── input/
│   │   ├── GOES_COD_BR_20240801-0900.parquet
│   │   ├── GOES_COD_BR_20240801-0910.parquet
│   │   ├── GOES_COD_BR_20240801-0920.parquet
│   │   └── ...
│   └── output/
│       ├── cod.parquet
│       └── plots/
│           ├── SE_forecast.gif
│           ├── SE_0000.png
│           └── ...
```

### Performance Considerations

**S3 Read Optimization**:
- Uses `s3fs` and `pyarrow` for efficient Parquet streaming
- Leverages Polars' lazy evaluation with S3 storage options
- Automatic connection pooling and retry logic

**S3 Write Optimization**:
- Batch operations minimize API calls
- Temporary local buffering for image generation
- Parallel uploads for multi-subgrid outputs

**Cost Optimization**:
- Monitor S3 request costs (GET, PUT, LIST operations)
- Use S3 Lifecycle policies to archive old forecasts
- Consider S3 Intelligent-Tiering for infrequent access patterns

### Troubleshooting S3

**NoCredentialsError**:
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```
Solution: Configure AWS credentials using one of the methods above.

**AccessDenied**:
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the GetObject operation
```
Solution: Verify IAM permissions include required S3 actions.

**NoSuchBucket**:
```
botocore.exceptions.ClientError: An error occurred (NoSuchBucket) when calling the ListObjectsV2 operation
```
Solution: Check bucket name spelling and verify the bucket exists in your AWS account.

**Region Mismatch**:
```
botocore.exceptions.ClientError: An error occurred (301) when calling the ListObjectsV2 operation: Moved Permanently
```
Solution: Set `AWS_DEFAULT_REGION` to match your bucket's region.

---

## Outputs

### Forecast Data

**File**: `<output_dir>/cod.parquet`

A single Parquet file containing all forecast results concatenated across subgrids.

**Schema**:

| Column      | Type     | Description                          |
| ----------- | -------- | ------------------------------------ |
| `time`      | datetime | Forecast valid time (ISO 8601)       |
| `latitude`  | float    | Latitude in decimal degrees          |
| `longitude` | float    | Longitude in decimal degrees         |
| `cod`       | float    | Forecasted Cloud Optical Depth value |

**Example**:

```python
import pandas as pd

df = pd.read_parquet("data/output/cod.parquet")
print(df.head())

#                  time  latitude  longitude       cod
# 0 2024-08-01 10:10:00    -23.00     -53.00  12.34567
# 1 2024-08-01 10:10:00    -22.98     -53.00  11.98765
# 2 2024-08-01 10:10:00    -22.96     -53.00  13.45678
# ...
```

### Visualizations

**Directory**: `<output_dir>/plots/`

When `postprocessing.plots` is enabled, the following outputs are generated:

#### Individual Frames

**Files**: `<output_dir>/plots/<step>.png`

One PNG image per forecast time step, showing:

- COD field as colored contours (using a specialized colormap)
- Motion vectors as arrows (subsampled for clarity)
- Geographic boundaries (countries, states)
- Coordinate grid with lat/lon labels
- Timestamp and title

#### Animated GIF

**File**: `<output_dir>/plots/<subgrid_name>_forecast.gif`

An animated GIF combining all forecast frames in sequence. Useful for:

- Quick visual inspection of forecast evolution
- Presentations and reports
- Identifying motion patterns and forecast artifacts

**Animation parameters**:

- Frame interval: 300 ms
- Repeat delay: 700 ms
- Resolution: 720×720 pixels (configurable in code)

**Example visualization features**:

```
┌───────────────────────────────────────────────┐
│ Cloud Optical Depth - Forecast  2024-08-01T.. │
├───────────────────────────────────────────────┤
│                                               │
│         ↗  →  →  →  ↘                        │
│       ↗  [COD field contours]  ↘             │
│     ↑   with colormap + motion   ↓            │
│     ↑   vectors overlaid         ↓            │
│       ↖  ←  ←  ←  ↙                          │
│                                               │
├───────────────────────────────────────────────┤
│ [Colorbar: 0 ──────────── 100+ COD]           │
└───────────────────────────────────────────────┘
```

---

## Contributing

Contributions are welcome! Please follow these guidelines:

### Development Setup

1. Clone the repository:

```bash
git clone https://github.com/yourusername/cod-nowcast-ons.git
cd cod-nowcast-ons
```

2. Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install in development mode:

```bash
pip install -e .
```

### Code Style

- Follow PEP 8 conventions
- Use type hints for function signatures
- Maximum line length: 80 characters (configured in `pyproject.toml`)
- Run `ruff` for linting:

```bash
pip install ruff
ruff check .
```

### Testing

Currently, the project does not have automated tests. Contributions to add test coverage are highly appreciated!

Future testing priorities:

- Unit tests for motion estimation and extrapolation
- Integration tests with sample GOES data
- Validation against ground truth observations

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes with descriptive messages
4. Push to your fork and submit a pull request
5. Ensure all checks pass and provide a clear description

### Reporting Issues

When reporting bugs, please include:

- Python version (`python --version`)
- Operating system
- Full error traceback
- Configuration file (sanitized of sensitive paths)
- Sample input data (if possible)

---

## Troubleshooting

### Common Issues

#### 1. **FileNotFoundError: Input Parquet files not found**

**Symptom**:

```
FileNotFoundError: [Errno 2] No such file or directory: 'data/input/GOES_COD_BR_20240801-0950.parquet'
```

**Cause**: Missing historical GOES data files.

**Solution**:

- Ensure input files exist for all required time steps
- Check filename format: `GOES_COD_BR_YYYYMMDD-HHMM.parquet`
- Verify `base_datetime` and `num_past_samples` alignment with available data
- Example: If `base_datetime = "2024-08-01T10:00:00"` and `num_past_samples = 6`, you need files for:
  - 09:00, 09:10, 09:20, 09:30, 09:40, 09:50

#### 2. **ValueError: Motion field estimation failed**

**Symptom**:

```
ValueError: Not enough valid data for motion estimation
```

**Cause**: Excessive missing data (NaN values) in the input COD fields.

**Solution**:

- Check data quality: At least 30-40% of pixels should have valid COD values
- Verify subgrid bounds don't fall outside data coverage
- Consider using a larger spatial domain to include more valid data

#### 3. **MemoryError during processing**

**Symptom**:

```
MemoryError: Unable to allocate array
```

**Cause**: Large subgrid size or high spatial resolution.

**Solution**:

- Reduce subgrid extent (`lat` and `lon` ranges)
- Process subgrids sequentially rather than in parallel
- Increase system RAM or use a machine with more memory
- Consider downsampling input data if ultra-high resolution is not needed

#### 4. **No GIF output generated**

**Symptom**: Parquet output exists but no `*.gif` files in `plots/` directory.

**Cause**: `postprocessing.plots` is `false` or missing.

**Solution**:

```jsonc
{
  // ... other config ...
  "postprocessing": {
    "plots": true
  }
}
```

#### 5. **Import errors after installation**

**Symptom**:

```
ModuleNotFoundError: No module named 'pysteps'
```

**Cause**: Virtual environment not activated or installation incomplete.

**Solution**:

```bash
# Reinstall with force flag
sudo ./setup.sh --force
# OR for user installation
./setup.sh --user --force
```

### Debug Tips

#### Enable verbose logging

Modify `main.py` to add debug statements:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Inspect motion field

Add after motion estimation in `app/services/cloud_motion_forecast.py`:

```python
print(f"Motion field shape: {self.motion_field.shape}")
print(f"Motion field U range: {self.motion_field[0].min():.3f} to {self.motion_field[0].max():.3f}")
print(f"Motion field V range: {self.motion_field[1].min():.3f} to {self.motion_field[1].max():.3f}")
```

#### Validate input data

```python
import polars as pl

df = pl.read_parquet("data/input/GOES_COD_BR_20240801-0950.parquet")
print(df.describe())
print(f"Missing values: {df.null_count()}")
```

#### Check pySTEPS version

```bash
pip show pysteps
```

Ensure version ≥ 1.18.1.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

**Acknowledgments**:

- [pySTEPS](https://pysteps.readthedocs.io/) - Python framework for short-term ensemble prediction systems
- [GOES Satellite Program](https://www.goes.noaa.gov/) - Geostationary satellite imagery

**Citation**:

If you use this tool in your research, please cite:

```
@software{cod_nowcast_ons,
  title={cod-nowcast-ons: Cloud Optical Depth nowcasting using GOES satellite imagery and optical flow-based extrapolation},
  author={ Farias, William & Alves, Rogerio},
  year={2025},
  url={https://github.com/rjmalves/cod-nowcast-ons}
}
```
