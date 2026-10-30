import argparse
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


def create_small_test_dataset(
    input_dir: Path,
    output_dir: Path,
    lat_range: tuple[float, float] = (-23.0, -20.0),
    lon_range: tuple[float, float] = (-50.0, -47.0),
    num_files: int = 8,
    base_datetime: datetime = datetime(2024, 8, 1, 0, 50),
) -> None:
    """
    Create small test datasets from full GOES COD parquet files.

    This extracts a small geographic subset to use as mock data in tests.
    The subset is small enough to commit to git but representative enough
    for testing the nowcasting pipeline.

    Args:
        input_dir: Directory containing full GOES COD parquet files
        output_dir: Directory to save test fixtures
        lat_range: (min_lat, max_lat) for subsetting
        lon_range: (min_lon, max_lon) for subsetting
        num_files: Number of time steps to include
        base_datetime: Starting datetime for test data
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating test dataset with {num_files} files...")
    print(f"Geographic bounds: lat {lat_range}, lon {lon_range}")

    total_rows = 0

    for i in range(num_files):
        # Calculate time for this file
        file_time = base_datetime - timedelta(minutes=10 * (num_files - 1 - i))

        # Source filename
        source_filename = (
            f"GOES_COD_BR_{file_time.strftime('%Y%m%d-%H%M')}.parquet"
        )
        source_path = input_dir / source_filename

        if not source_path.exists():
            print(f"Warning: {source_filename} not found, skipping...")
            continue

        # Read and filter
        df = pl.read_parquet(source_path)

        df_subset = df.filter(
            (pl.col("latitude") >= lat_range[0])
            & (pl.col("latitude") <= lat_range[1])
            & (pl.col("longitude") >= lon_range[0])
            & (pl.col("longitude") <= lon_range[1])
        )

        # Save subset
        output_filename = f"{source_filename}"
        output_path = output_dir / output_filename
        df_subset.write_parquet(output_path)

        rows = len(df_subset)
        total_rows += rows
        size_kb = output_path.stat().st_size / 1024

        print(f"  {output_filename}: {rows} rows, {size_kb:.1f} KB")

    print(f"\nTotal: {total_rows} rows across {num_files} files")
    print(f"Output directory: {output_dir}")
    print("\nTest data statistics:")

    # Show statistics from first file
    first_file = list(output_dir.glob("*.parquet"))[0]
    df_sample = pl.read_parquet(first_file)
    print(f"  Unique latitudes: {df_sample['latitude'].n_unique()}")
    print(f"  Unique longitudes: {df_sample['longitude'].n_unique()}")
    print(
        f"  COD range: [{df_sample['cod'].min():.2f}, {df_sample['cod'].max():.2f}]"  # type: ignore[str-bytes-safe]  # polars types Series.min/max as any literal; cod is Float
    )
    print(f"  COD mean: {df_sample['cod'].mean():.2f}")  # type: ignore[str-bytes-safe]  # polars types Series.mean as any literal; cod is Float
    print(f"  Missing values: {df_sample['cod'].null_count()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate test fixtures from GOES COD data"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/input"),
        help="Directory with full GOES COD parquet files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures/data"),
        help="Output directory for test fixtures",
    )
    parser.add_argument(
        "--lat-min",
        type=float,
        default=-23.0,
        help="Minimum latitude for subset",
    )
    parser.add_argument(
        "--lat-max",
        type=float,
        default=-20.0,
        help="Maximum latitude for subset",
    )
    parser.add_argument(
        "--lon-min",
        type=float,
        default=-50.0,
        help="Minimum longitude for subset",
    )
    parser.add_argument(
        "--lon-max",
        type=float,
        default=-47.0,
        help="Maximum longitude for subset",
    )
    parser.add_argument(
        "--num-files",
        type=int,
        default=8,
        help="Number of time step files to create",
    )

    args = parser.parse_args()

    create_small_test_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        lat_range=(args.lat_min, args.lat_max),
        lon_range=(args.lon_min, args.lon_max),
        num_files=args.num_files,
    )


if __name__ == "__main__":
    main()
