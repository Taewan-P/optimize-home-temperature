from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.alerting import Alert, AlertSeverity, AlertType, Alerting
from src.controller import Controller, ControllerState
from src.data_collector import DataCollector


def _heater_state_payload(state: str = "off", last_updated: datetime | None = None) -> dict:
    timestamp = last_updated or datetime.now(timezone.utc)
    return {
        "state": state,
        "attributes": {"hvac_action": "off", "current_temperature": 24.0},
        "last_updated": timestamp.isoformat().replace("+00:00", "Z"),
    }


@pytest.mark.asyncio
async def test_control_loop_full_cycle(test_env, mock_ha_client):
    alerting = AsyncMock()
    controller = Controller(
        ha_client=mock_ha_client,
        alerting=alerting,
        heater_entity_id=test_env["HA_HEATER_CLIMATE_ID"],
        temp_sensor_id=test_env["HA_TEMP_SENSOR_ID"],
        on_temp=float(test_env["HEATER_ON_TEMP"]),
        off_temp=float(test_env["HEATER_OFF_TEMP"]),
        min_cycle_time=int(test_env["MIN_CYCLE_TIME_SECONDS"]),
        sensor_stale_timeout=int(test_env["SENSOR_STALE_TIMEOUT_SECONDS"]),
        manual_override_timeout=600,
    )

    mock_ha_client.get_temperature.return_value = 24.0
    mock_ha_client.get_heater_state.return_value = _heater_state_payload("off")

    await controller.run_control_cycle()

    mock_ha_client.turn_on.assert_awaited_once_with(test_env["HA_HEATER_CLIMATE_ID"])
    assert controller.state == ControllerState.HEATING

    mock_ha_client.get_temperature.return_value = 26.2
    mock_ha_client.get_heater_state.return_value = _heater_state_payload("heat")

    await controller.run_control_cycle()

    mock_ha_client.turn_off.assert_awaited_once_with(test_env["HA_HEATER_CLIMATE_ID"])
    assert controller.state == ControllerState.COOLDOWN


@pytest.mark.asyncio
async def test_hysteresis_deadband(test_env, mock_ha_client):
    alerting = AsyncMock()
    controller = Controller(
        ha_client=mock_ha_client,
        alerting=alerting,
        heater_entity_id=test_env["HA_HEATER_CLIMATE_ID"],
        temp_sensor_id=test_env["HA_TEMP_SENSOR_ID"],
        on_temp=float(test_env["HEATER_ON_TEMP"]),
        off_temp=float(test_env["HEATER_OFF_TEMP"]),
        min_cycle_time=int(test_env["MIN_CYCLE_TIME_SECONDS"]),
        sensor_stale_timeout=int(test_env["SENSOR_STALE_TIMEOUT_SECONDS"]),
        manual_override_timeout=600,
    )

    mock_ha_client.get_temperature.return_value = 25.4
    mock_ha_client.get_heater_state.return_value = _heater_state_payload("off")

    await controller.run_control_cycle()

    mock_ha_client.turn_on.assert_not_called()
    mock_ha_client.turn_off.assert_not_called()
    assert controller.state == ControllerState.IDLE


@pytest.mark.asyncio
async def test_data_collector_writes_to_influxdb(test_env, mock_ha_client, mock_influx_client):
    collector = DataCollector(
        ha_client=mock_ha_client,
        influx_url=test_env["INFLUX_URL"],
        influx_token=test_env["INFLUX_TOKEN"],
        influx_org=test_env["INFLUX_ORG"],
        influx_bucket=test_env["INFLUX_BUCKET"],
        temp_sensor_id=test_env["HA_TEMP_SENSOR_ID"],
        humidity_sensor_id=test_env["HA_HUMIDITY_SENSOR_ID"],
        heater_entity_id=test_env["HA_HEATER_CLIMATE_ID"],
        weather_entity_id=test_env["HA_WEATHER_ENTITY_ID"],
        electricity_sensor_id=test_env["HA_ELECTRICITY_SENSOR_ID"],
    )
    collector._write_api = mock_influx_client.write_api.return_value

    await collector.write_temperature(24.5, location="home")

    collector._write_api.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_controller_respects_minimum_cycle_time(test_env, mock_ha_client):
    alerting = AsyncMock()
    controller = Controller(
        ha_client=mock_ha_client,
        alerting=alerting,
        heater_entity_id=test_env["HA_HEATER_CLIMATE_ID"],
        temp_sensor_id=test_env["HA_TEMP_SENSOR_ID"],
        on_temp=float(test_env["HEATER_ON_TEMP"]),
        off_temp=float(test_env["HEATER_OFF_TEMP"]),
        min_cycle_time=int(test_env["MIN_CYCLE_TIME_SECONDS"]),
        sensor_stale_timeout=int(test_env["SENSOR_STALE_TIMEOUT_SECONDS"]),
        manual_override_timeout=600,
    )
    controller.state = ControllerState.COOLDOWN
    controller.last_state_change = datetime.now() - timedelta(seconds=30)

    mock_ha_client.get_temperature.return_value = 24.0
    mock_ha_client.get_heater_state.return_value = _heater_state_payload("off")

    await controller.run_control_cycle()

    mock_ha_client.turn_on.assert_not_called()
    assert controller.state == ControllerState.COOLDOWN


@pytest.mark.asyncio
async def test_stale_data_triggers_failure(test_env, mock_ha_client):
    alerting = AsyncMock()
    controller = Controller(
        ha_client=mock_ha_client,
        alerting=alerting,
        heater_entity_id=test_env["HA_HEATER_CLIMATE_ID"],
        temp_sensor_id=test_env["HA_TEMP_SENSOR_ID"],
        on_temp=float(test_env["HEATER_ON_TEMP"]),
        off_temp=float(test_env["HEATER_OFF_TEMP"]),
        min_cycle_time=int(test_env["MIN_CYCLE_TIME_SECONDS"]),
        sensor_stale_timeout=int(test_env["SENSOR_STALE_TIMEOUT_SECONDS"]),
        manual_override_timeout=600,
    )

    stale_time = datetime.now(timezone.utc) - timedelta(
        seconds=int(test_env["SENSOR_STALE_TIMEOUT_SECONDS"]) + 1
    )
    mock_ha_client.get_temperature.return_value = 24.0
    mock_ha_client.get_heater_state.return_value = _heater_state_payload(
        "off", last_updated=stale_time
    )

    await controller.run_control_cycle()

    assert controller.state == ControllerState.FAILURE
    alerting.send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_alerting_multi_channel(test_env):
    alerting = Alerting(
        ha_url=test_env["HA_URL"],
        ha_token=test_env["HA_TOKEN"],
        discord_webhook_url=test_env["DISCORD_WEBHOOK_URL"],
        dedup_window_minutes=30,
    )
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.SENSOR_FAILURE,
        message="Integration test alert",
    )

    result = await alerting.send_alert(alert)

    assert result["status"] == "sent"
    assert set(result["channels"]) == {"push", "discord"}
    alerting._send_ha_push.assert_awaited_once()
    alerting._send_discord.assert_awaited_once()
