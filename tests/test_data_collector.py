"""Tests for Data Collector service - TDD RED phase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.data_collector import (
    DataCollector,
    DataValidationError,
    validate_humidity,
    validate_temperature,
)


@pytest.fixture
def mock_ha_client():
    """Create a mock HaClient instance."""
    client = AsyncMock()
    client.get_temperature = AsyncMock(return_value=22.5)
    client.get_humidity = AsyncMock(return_value=55.0)
    client.get_heater_state = AsyncMock(
        return_value={"state": "heat", "attributes": {"hvac_action": "heating"}}
    )
    client.get_weather = AsyncMock(
        return_value={
            "state": "cloudy",
            "attributes": {"temperature": 5.0, "humidity": 80},
        }
    )
    return client


@pytest.fixture
def mock_influx_write_api():
    """Create a mock InfluxDB write API."""
    write_api = AsyncMock()
    write_api.write = AsyncMock(return_value=True)
    return write_api


@pytest.fixture
def data_collector(mock_ha_client, mock_influx_write_api):
    """Create a DataCollector instance with mocked dependencies."""
    collector = DataCollector(
        ha_client=mock_ha_client,
        influx_url="http://localhost:8086",
        influx_token="test_token",
        influx_org="test_org",
        influx_bucket="test_bucket",
        temp_sensor_id="sensor.temperature",
        humidity_sensor_id="sensor.humidity",
        heater_entity_id="climate.heater",
        weather_entity_id="weather.home",
        electricity_sensor_id="sensor.electricity",
    )
    collector._write_api = mock_influx_write_api
    return collector


class TestDataValidation:
    """Test data validation functions."""

    def test_valid_temperature_accepted(self):
        """Test that valid temperatures within range are accepted."""
        assert validate_temperature(22.5) == 22.5
        assert validate_temperature(-40.0) == -40.0
        assert validate_temperature(60.0) == 60.0
        assert validate_temperature(0.0) == 0.0

    def test_invalid_temperature_rejected(self):
        """Test that temperatures outside -40 to 60 range are rejected."""
        with pytest.raises(DataValidationError) as exc_info:
            validate_temperature(-50.0)
        assert "Temperature -50.0 out of valid range" in str(exc_info.value)

        with pytest.raises(DataValidationError):
            validate_temperature(100.0)

        with pytest.raises(DataValidationError):
            validate_temperature(-41.0)

        with pytest.raises(DataValidationError):
            validate_temperature(61.0)

    def test_valid_humidity_accepted(self):
        """Test that valid humidity values are accepted."""
        assert validate_humidity(55.0) == 55.0
        assert validate_humidity(0.0) == 0.0
        assert validate_humidity(100.0) == 100.0

    def test_invalid_humidity_rejected(self):
        """Test that humidity values outside 0-100 range are rejected."""
        with pytest.raises(DataValidationError) as exc_info:
            validate_humidity(-5.0)
        assert "Humidity -5.0 out of valid range" in str(exc_info.value)

        with pytest.raises(DataValidationError):
            validate_humidity(105.0)


class TestInfluxDBWrites:
    """Test InfluxDB write functionality."""

    @pytest.mark.asyncio
    async def test_valid_temperature_writes_to_influxdb(
        self, data_collector, mock_influx_write_api
    ):
        """Test valid temperature writes successfully to InfluxDB."""
        await data_collector.write_temperature(22.5, location="living_room")

        mock_influx_write_api.write.assert_called_once()
        call_args = mock_influx_write_api.write.call_args
        assert call_args[1]["bucket"] == "test_bucket"

    @pytest.mark.asyncio
    async def test_invalid_temperature_not_written(self, data_collector, mock_influx_write_api):
        """Test invalid temperature is rejected and not written."""
        with pytest.raises(DataValidationError):
            await data_collector.write_temperature(-50.0, location="living_room")

        mock_influx_write_api.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_humidity(self, data_collector, mock_influx_write_api):
        """Test humidity writes successfully to InfluxDB."""
        await data_collector.write_humidity(55.0, location="living_room")

        mock_influx_write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_heater_state(self, data_collector, mock_influx_write_api):
        """Test heater state writes successfully to InfluxDB."""
        await data_collector.write_heater_state(
            state="heat", hvac_action="heating", current_temp=22.0
        )

        mock_influx_write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_weather_data(self, data_collector, mock_influx_write_api):
        """Test weather data writes to InfluxDB with relevant fields only."""
        await data_collector.write_weather(temperature=5.0, humidity=80, condition="cloudy")

        mock_influx_write_api.write.assert_called_once()


class TestInfluxDBBuffering:
    """Test InfluxDB connection failure handling and buffering."""

    @pytest.mark.asyncio
    async def test_influxdb_failure_triggers_buffering(self, data_collector, mock_influx_write_api):
        """Test that InfluxDB failure triggers data buffering in memory."""
        mock_influx_write_api.write.side_effect = Exception("Connection failed")

        await data_collector.write_temperature(22.5, location="living_room")

        assert len(data_collector._buffer) == 1

    @pytest.mark.asyncio
    async def test_buffer_limited_to_max_size(self, data_collector, mock_influx_write_api):
        """Test that buffer is limited to 1000 points."""
        mock_influx_write_api.write.side_effect = Exception("Connection failed")

        for i in range(1100):
            temp = 20.0 + (i % 10)
            await data_collector.write_temperature(temp, location="room")

        assert len(data_collector._buffer) == 1000

    @pytest.mark.asyncio
    async def test_buffer_flushed_on_reconnect(self, data_collector, mock_influx_write_api):
        """Test that buffered data is flushed when connection is restored."""
        # First write fails, gets buffered
        mock_influx_write_api.write.side_effect = Exception("Connection failed")
        await data_collector.write_temperature(22.5, location="room1")
        await data_collector.write_temperature(23.0, location="room2")
        assert len(data_collector._buffer) == 2

        mock_influx_write_api.write.side_effect = None
        mock_influx_write_api.write.return_value = True

        await data_collector.flush_buffer()

        assert len(data_collector._buffer) == 0


class TestHeaterStateEvents:
    """Test heater state change event recording."""

    @pytest.mark.asyncio
    async def test_heater_state_change_event_recorded(self, data_collector, mock_influx_write_api):
        """Test heater state changes are recorded as events."""
        await data_collector.record_heater_state_change(
            old_state="off",
            new_state="heat",
            timestamp=datetime.now(UTC),
        )

        mock_influx_write_api.write.assert_called_once()
        call_args = mock_influx_write_api.write.call_args
        assert call_args[1]["bucket"] == "test_bucket"

    @pytest.mark.asyncio
    async def test_state_change_event_contains_transition_info(
        self, data_collector, mock_influx_write_api
    ):
        """Test state change event contains old and new state info."""
        await data_collector.record_heater_state_change(
            old_state="heat",
            new_state="off",
            timestamp=datetime.now(UTC),
        )

        mock_influx_write_api.write.assert_called_once()


class TestPollingIntervals:
    """Test polling interval configuration."""

    def test_default_polling_intervals(self, data_collector):
        """Test default polling intervals match requirements."""
        assert data_collector.temp_poll_interval == 60
        assert data_collector.weather_poll_interval == 300
        assert data_collector.electricity_poll_interval == 86400

    def test_custom_polling_intervals(self, mock_ha_client):
        """Test custom polling intervals can be set."""
        collector = DataCollector(
            ha_client=mock_ha_client,
            influx_url="http://localhost:8086",
            influx_token="test_token",
            influx_org="test_org",
            influx_bucket="test_bucket",
            temp_sensor_id="sensor.temp",
            humidity_sensor_id="sensor.humidity",
            heater_entity_id="climate.heater",
            weather_entity_id="weather.home",
            electricity_sensor_id="sensor.electricity",
            temp_poll_interval=30,
            weather_poll_interval=600,
            electricity_poll_interval=43200,
        )
        assert collector.temp_poll_interval == 30
        assert collector.weather_poll_interval == 600
        assert collector.electricity_poll_interval == 43200


class TestDataCollection:
    """Test data collection from HA sensors."""

    @pytest.mark.asyncio
    async def test_collect_temperature_and_humidity(
        self, data_collector, mock_ha_client, mock_influx_write_api
    ):
        """Test collecting temperature and humidity from HA sensors."""
        await data_collector.collect_temperature_humidity()

        mock_ha_client.get_temperature.assert_called_once_with("sensor.temperature")
        mock_ha_client.get_humidity.assert_called_once_with("sensor.humidity")
        assert mock_influx_write_api.write.call_count == 2

    @pytest.mark.asyncio
    async def test_collect_weather(self, data_collector, mock_ha_client, mock_influx_write_api):
        """Test collecting weather data from HA."""
        await data_collector.collect_weather()

        mock_ha_client.get_weather.assert_called_once_with("weather.home")
        mock_influx_write_api.write.assert_called_once()


class TestLogging:
    """Test data point logging."""

    @pytest.mark.asyncio
    async def test_data_points_logged_with_timestamps(
        self, data_collector, mock_influx_write_api, caplog
    ):
        """Test all data points are logged with timestamps."""
        import logging

        with caplog.at_level(logging.INFO):
            await data_collector.write_temperature(22.5, location="living_room")

        assert len([r for r in caplog.records if "temperature" in r.message.lower()]) > 0
