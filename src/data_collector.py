from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from datetime import UTC, datetime
from typing import Any, Optional

from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from src.ha_client import HaClient

logger = logging.getLogger(__name__)

MIN_VALID_TEMP = -40.0
MAX_VALID_TEMP = 60.0
MIN_VALID_HUMIDITY = 0.0
MAX_VALID_HUMIDITY = 100.0
MAX_BUFFER_SIZE = 1000

DEFAULT_TEMP_POLL_INTERVAL = 60
DEFAULT_WEATHER_POLL_INTERVAL = 300
DEFAULT_ELECTRICITY_POLL_INTERVAL = 86400


class DataValidationError(Exception):
    pass


def validate_temperature(value: float) -> float:
    if value < MIN_VALID_TEMP or value > MAX_VALID_TEMP:
        raise DataValidationError(
            f"Temperature {value} out of valid range [{MIN_VALID_TEMP}, {MAX_VALID_TEMP}]"
        )
    return value


def validate_humidity(value: float) -> float:
    if value < MIN_VALID_HUMIDITY or value > MAX_VALID_HUMIDITY:
        raise DataValidationError(
            f"Humidity {value} out of valid range [{MIN_VALID_HUMIDITY}, {MAX_VALID_HUMIDITY}]"
        )
    return value


class DataCollector:
    def __init__(
        self,
        ha_client: HaClient,
        influx_url: str,
        influx_token: str,
        influx_org: str,
        influx_bucket: str,
        temp_sensor_id: str,
        humidity_sensor_id: str,
        heater_entity_id: str,
        weather_entity_id: str,
        electricity_sensor_id: str,
        temp_poll_interval: int = DEFAULT_TEMP_POLL_INTERVAL,
        weather_poll_interval: int = DEFAULT_WEATHER_POLL_INTERVAL,
        electricity_poll_interval: int = DEFAULT_ELECTRICITY_POLL_INTERVAL,
    ):
        self._ha_client = ha_client
        self._influx_url = influx_url
        self._influx_token = influx_token
        self._influx_org = influx_org
        self._influx_bucket = influx_bucket

        self._temp_sensor_id = temp_sensor_id
        self._humidity_sensor_id = humidity_sensor_id
        self._heater_entity_id = heater_entity_id
        self._weather_entity_id = weather_entity_id
        self._electricity_sensor_id = electricity_sensor_id

        self.temp_poll_interval = temp_poll_interval
        self.weather_poll_interval = weather_poll_interval
        self.electricity_poll_interval = electricity_poll_interval

        self._buffer: deque = deque(maxlen=MAX_BUFFER_SIZE)
        self._influx_client: Optional[InfluxDBClientAsync] = None
        self._write_api: Optional[Any] = None
        self._running = False
        self._last_heater_state: Optional[str] = None

    @classmethod
    def from_env(cls, ha_client: HaClient) -> DataCollector:
        return cls(
            ha_client=ha_client,
            influx_url=os.environ["INFLUX_URL"],
            influx_token=os.environ["INFLUX_TOKEN"],
            influx_org=os.environ["INFLUX_ORG"],
            influx_bucket=os.environ["INFLUX_BUCKET"],
            temp_sensor_id=os.environ["HA_TEMP_SENSOR_ID"],
            humidity_sensor_id=os.environ["HA_HUMIDITY_SENSOR_ID"],
            heater_entity_id=os.environ["HA_HEATER_CLIMATE_ID"],
            weather_entity_id=os.environ["HA_WEATHER_ENTITY_ID"],
            electricity_sensor_id=os.environ["HA_ELECTRICITY_SENSOR_ID"],
            temp_poll_interval=int(
                os.environ.get("TEMP_POLL_INTERVAL_SECONDS", DEFAULT_TEMP_POLL_INTERVAL)
            ),
            weather_poll_interval=int(
                os.environ.get("WEATHER_POLL_INTERVAL_SECONDS", DEFAULT_WEATHER_POLL_INTERVAL)
            ),
            electricity_poll_interval=int(
                os.environ.get(
                    "ELECTRICITY_POLL_INTERVAL_SECONDS", DEFAULT_ELECTRICITY_POLL_INTERVAL
                )
            ),
        )

    async def __aenter__(self) -> DataCollector:
        self._influx_client = InfluxDBClientAsync(
            url=self._influx_url,
            token=self._influx_token,
            org=self._influx_org,
        )
        self._write_api = self._influx_client.write_api()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._influx_client:
            await self._influx_client.close()

    async def _write_point(self, point: Point) -> None:
        try:
            await self._write_api.write(bucket=self._influx_bucket, record=point)
            logger.info(
                "[%s] Wrote point: %s", datetime.now(UTC).isoformat(), point.to_line_protocol()
            )
        except Exception as e:
            logger.warning("InfluxDB write failed, buffering point: %s", str(e))
            self._buffer.append(point)

    async def write_temperature(self, value: float, location: str) -> None:
        validate_temperature(value)
        point = (
            Point("temperature")
            .tag("location", location)
            .field("value", value)
            .time(datetime.now(UTC))
        )
        await self._write_point(point)

    async def write_humidity(self, value: float, location: str) -> None:
        validate_humidity(value)
        point = (
            Point("humidity")
            .tag("location", location)
            .field("value", value)
            .time(datetime.now(UTC))
        )
        await self._write_point(point)

    async def write_heater_state(self, state: str, hvac_action: str, current_temp: float) -> None:
        point = (
            Point("heater_state")
            .tag("state", state)
            .field("hvac_action", hvac_action)
            .field("current_temp", current_temp)
            .time(datetime.now(UTC))
        )
        await self._write_point(point)

    async def write_weather(self, temperature: float, humidity: int, condition: str) -> None:
        point = (
            Point("weather")
            .tag("condition", condition)
            .field("temperature", temperature)
            .field("humidity", humidity)
            .time(datetime.now(UTC))
        )
        await self._write_point(point)

    async def write_electricity(self, usage: float) -> None:
        point = Point("electricity").field("usage", usage).time(datetime.now(UTC))
        await self._write_point(point)

    async def record_heater_state_change(
        self, old_state: str, new_state: str, timestamp: datetime
    ) -> None:
        point = (
            Point("heater_state_change")
            .tag("old_state", old_state)
            .tag("new_state", new_state)
            .field("transition", f"{old_state}->{new_state}")
            .time(timestamp)
        )
        await self._write_point(point)

    async def flush_buffer(self) -> None:
        if not self._buffer:
            return

        logger.info("Flushing %d buffered points", len(self._buffer))
        points_to_flush = list(self._buffer)
        self._buffer.clear()

        for point in points_to_flush:
            try:
                await self._write_api.write(bucket=self._influx_bucket, record=point)
            except Exception as e:
                logger.warning("Failed to flush buffered point: %s", str(e))
                self._buffer.append(point)

    async def collect_temperature_humidity(self) -> None:
        try:
            temp = await self._ha_client.get_temperature(self._temp_sensor_id)
            await self.write_temperature(temp, location="home")
        except DataValidationError as e:
            logger.warning("Invalid temperature reading: %s", str(e))
        except Exception as e:
            logger.error("Failed to collect temperature: %s", str(e))

        try:
            humidity = await self._ha_client.get_humidity(self._humidity_sensor_id)
            await self.write_humidity(humidity, location="home")
        except DataValidationError as e:
            logger.warning("Invalid humidity reading: %s", str(e))
        except Exception as e:
            logger.error("Failed to collect humidity: %s", str(e))

    async def collect_weather(self) -> None:
        try:
            weather = await self._ha_client.get_weather(self._weather_entity_id)
            attrs = weather.get("attributes", {})
            await self.write_weather(
                temperature=attrs.get("temperature", 0.0),
                humidity=attrs.get("humidity", 0),
                condition=weather.get("state", "unknown"),
            )
        except Exception as e:
            logger.error("Failed to collect weather: %s", str(e))

    async def collect_heater_state(self) -> None:
        try:
            state_data = await self._ha_client.get_heater_state(self._heater_entity_id)
            state = state_data.get("state", "unknown")
            attrs = state_data.get("attributes", {})

            await self.write_heater_state(
                state=state,
                hvac_action=attrs.get("hvac_action", "unknown"),
                current_temp=attrs.get("current_temperature", 0.0),
            )

            if self._last_heater_state is not None and self._last_heater_state != state:
                await self.record_heater_state_change(
                    old_state=self._last_heater_state,
                    new_state=state,
                    timestamp=datetime.now(UTC),
                )
            self._last_heater_state = state
        except Exception as e:
            logger.error("Failed to collect heater state: %s", str(e))

    async def collect_electricity(self) -> None:
        try:
            state_data = await self._ha_client.get_state(self._electricity_sensor_id)
            usage = float(state_data.get("state", 0))
            await self.write_electricity(usage)
        except Exception as e:
            logger.error("Failed to collect electricity: %s", str(e))

    async def _temp_humidity_loop(self) -> None:
        while self._running:
            await self.collect_temperature_humidity()
            await self.collect_heater_state()
            await asyncio.sleep(self.temp_poll_interval)

    async def _weather_loop(self) -> None:
        while self._running:
            await self.collect_weather()
            await asyncio.sleep(self.weather_poll_interval)

    async def _electricity_loop(self) -> None:
        while self._running:
            await self.collect_electricity()
            await asyncio.sleep(self.electricity_poll_interval)

    async def _buffer_flush_loop(self) -> None:
        while self._running:
            if self._buffer:
                await self.flush_buffer()
            await asyncio.sleep(60)

    async def start(self) -> None:
        self._running = True
        logger.info("Starting data collector service")

        asyncio.create_task(self._temp_humidity_loop())
        asyncio.create_task(self._weather_loop())
        asyncio.create_task(self._electricity_loop())
        asyncio.create_task(self._buffer_flush_loop())

    async def stop(self) -> None:
        logger.info("Stopping data collector service")
        self._running = False


__all__ = [
    "DataCollector",
    "DataValidationError",
    "validate_temperature",
    "validate_humidity",
]
