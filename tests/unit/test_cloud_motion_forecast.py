import numpy as np
import pytest
import xarray as xr

from app.services.cloud_motion_forecast import CloudMotionForecast


class TestCloudMotionForecast:
    """Test CloudMotionForecast service."""

    def test_initialization(self, sample_cod_dataarray: xr.DataArray) -> None:
        """Test CloudMotionForecast initialization."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        assert forecast.cod is sample_cod_dataarray
        assert forecast.TIME_STEP_MINUTES == 10
        assert forecast.MOTION_FIELD_METHOD == "LK"
        assert forecast.NOWCAST_METHOD == "extrapolation"

    def test_motion_field_shape(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that motion field has correct shape."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        cod_array = np.array(sample_cod_dataarray)

        motion = forecast._eval_motion_field(cod_array)

        # Motion field should be (2, height, width)
        assert motion.shape[0] == 2  # U and V components
        assert motion.shape[1] == cod_array.shape[1]  # height
        assert motion.shape[2] == cod_array.shape[2]  # width

    def test_prepares_forecasting_sample(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test sample preparation (last timestep, fill NaN)."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        cod_array = np.array(sample_cod_dataarray)

        # Add some NaN values
        cod_array[-1, 0, 0] = np.nan

        sample = forecast._prepares_forecasting_sample(cod_array)

        # Should be last time step
        assert sample.shape == (10, 10)

        # Should have no NaN (filled with 0)
        assert not np.any(np.isnan(sample))
        assert sample[0, 0] == 0.0

    def test_forecast_returns_xarray(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that forecast returns xarray DataArray."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=3)

        assert isinstance(result, xr.DataArray)
        assert "time" in result.dims
        assert "latitude" in result.dims
        assert "longitude" in result.dims

    def test_forecast_correct_dimensions(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test forecast output dimensions."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        n_leadtimes = 5
        result = forecast.forecast(n_leadtimes=n_leadtimes)

        # Should have correct number of time steps
        assert result.time.size == n_leadtimes

        # Spatial dimensions should match input
        assert result.latitude.size == sample_cod_dataarray.latitude.size
        assert result.longitude.size == sample_cod_dataarray.longitude.size

    def test_forecast_time_progression(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that forecast times are correctly spaced."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=3)

        # Get last input time
        last_input_time = sample_cod_dataarray.time.values[-1]

        # Check forecast times are 10 minutes apart
        times = result.time.values
        for i in range(len(times) - 1):
            diff = (times[i + 1] - times[i]) / np.timedelta64(1, "m")
            assert diff == 10.0

        # First forecast should be 10 minutes after last input
        first_forecast_time = times[0]
        diff_first = (first_forecast_time - last_input_time) / np.timedelta64(
            1, "m"
        )
        assert diff_first == 10.0

    def test_motion_field_stored(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that motion field is stored after forecast."""
        forecast = CloudMotionForecast(sample_cod_dataarray)

        # Before forecast
        assert not hasattr(forecast, "motion_field")

        forecast.forecast(n_leadtimes=3)

        # After forecast
        assert hasattr(forecast, "motion_field")
        assert isinstance(forecast.motion_field, np.ndarray)
        assert forecast.motion_field.shape[0] == 2  # U, V components

    def test_forecast_values_are_finite(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that forecast doesn't produce infinite values."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=3)

        # Allow NaN (for masked regions) but not inf
        values = result.values
        assert not np.any(np.isinf(values))

    @pytest.mark.slow
    def test_forecast_with_many_leadtimes(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test forecast with many lead times (slower)."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=12)  # 2 hours

        assert result.time.size == 12
        # Verify time span
        time_span = (result.time[-1] - result.time[0]) / np.timedelta64(1, "m")
        assert time_span == 110.0  # 11 * 10 minutes

    def test_forecast_coordinates_preserved(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test that spatial coordinates are preserved."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=3)

        # Latitude and longitude should match input
        np.testing.assert_array_equal(
            result.latitude.values, sample_cod_dataarray.latitude.values
        )
        np.testing.assert_array_equal(
            result.longitude.values, sample_cod_dataarray.longitude.values
        )

    def test_forecast_with_uniform_field(self) -> None:
        """Test forecast with uniform (no motion) field."""
        # Create uniform field (no gradients)
        times = np.arange(6)
        lats = np.linspace(-23, -20, 10)
        lons = np.linspace(-50, -47, 10)

        # Uniform value
        data = np.ones((6, 10, 10)) * 5.0

        cod = xr.DataArray(
            data,
            coords={"time": times, "latitude": lats, "longitude": lons},
            dims=["time", "latitude", "longitude"],
        )

        forecast = CloudMotionForecast(cod)
        result = forecast.forecast(n_leadtimes=3)

        # With uniform field, forecast should also be uniform
        # (no motion means persistence)
        assert result.shape == (10, 10, 3)


@pytest.mark.unit
class TestCloudMotionForecastEdgeCases:
    """Test edge cases for CloudMotionForecast."""

    def test_forecast_with_missing_data(self) -> None:
        """Test forecast with some missing data."""
        times = np.arange(6)
        lats = np.linspace(-23, -20, 10)
        lons = np.linspace(-50, -47, 10)

        data = np.random.gamma(2, 2, size=(6, 10, 10))
        # Add missing data
        data[:, 0:2, 0:2] = np.nan

        cod = xr.DataArray(
            data,
            coords={"time": times, "latitude": lats, "longitude": lons},
            dims=["time", "latitude", "longitude"],
        )

        forecast = CloudMotionForecast(cod)
        result = forecast.forecast(n_leadtimes=3)

        # Should complete without error
        assert result is not None
        assert result.time.size == 3

    def test_forecast_with_small_domain(self) -> None:
        """Test forecast with very small spatial domain."""
        times = np.arange(6)
        lats = np.linspace(-23, -22.5, 3)  # Only 3 points
        lons = np.linspace(-50, -49.5, 3)

        data = np.random.gamma(2, 2, size=(6, 3, 3))

        cod = xr.DataArray(
            data,
            coords={"time": times, "latitude": lats, "longitude": lons},
            dims=["time", "latitude", "longitude"],
        )

        forecast = CloudMotionForecast(cod)
        result = forecast.forecast(n_leadtimes=2)

        assert result.shape == (3, 3, 2)

    def test_forecast_single_leadtime(
        self, sample_cod_dataarray: xr.DataArray
    ) -> None:
        """Test forecast with just one lead time."""
        forecast = CloudMotionForecast(sample_cod_dataarray)
        result = forecast.forecast(n_leadtimes=1)

        assert result.time.size == 1
        assert isinstance(result, xr.DataArray)
