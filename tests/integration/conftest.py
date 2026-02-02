import os
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="session")
def test_env():
    """Set up test environment variables."""
    os.environ.update(
        {
            "HA_URL": "http://test-ha:8123",
            "HA_TOKEN": "test_token",
            "INFLUX_URL": "http://test-influx:8086",
            "INFLUX_TOKEN": "test_influx_token",
            "INFLUX_ORG": "test_org",
            "INFLUX_BUCKET": "test_heater",
            "HA_TEMP_SENSOR_ID": "sensor.test_temperature",
            "HA_HUMIDITY_SENSOR_ID": "sensor.test_humidity",
            "HA_HEATER_CLIMATE_ID": "climate.test_heater",
            "HA_WEATHER_ENTITY_ID": "weather.test_home",
            "HA_ELECTRICITY_SENSOR_ID": "sensor.test_electricity",
            "HEATER_ON_TEMP": "25.0",
            "HEATER_OFF_TEMP": "26.0",
            "MIN_CYCLE_TIME_SECONDS": "180",
            "SENSOR_STALE_TIMEOUT_SECONDS": "300",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/test",
        }
    )
    return os.environ


@pytest.fixture
def mock_ha_client():
    """Create a mock Home Assistant client."""
    client = AsyncMock()
    client.get_temperature.return_value = 24.5
    client.get_humidity.return_value = 55.0
    client.get_heater_state.return_value = {"state": "off", "attributes": {}}
    client.turn_on.return_value = True
    client.turn_off.return_value = True
    return client


@pytest.fixture
def mock_influx_client():
    """Create a mock InfluxDB client."""
    client = AsyncMock()
    write_api = AsyncMock()
    write_api.write = AsyncMock(return_value=True)
    client.write_api.return_value = write_api
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client
