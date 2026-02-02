"""Tests for heater controller with state machine and hysteresis logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.controller import Controller, ControllerState


@pytest.fixture
def mock_ha_client():
    """Mock Home Assistant client."""
    client = AsyncMock()
    client.turn_on = AsyncMock(return_value=True)
    client.turn_off = AsyncMock(return_value=True)
    client.get_temperature = AsyncMock(return_value=25.5)
    client.get_heater_state = AsyncMock(
        return_value={"state": "off", "attributes": {"hvac_action": "off"}}
    )
    return client


@pytest.fixture
def mock_alerting():
    """Mock alerting system."""
    alerting = AsyncMock()
    alerting.send_alert = AsyncMock()
    return alerting


@pytest.fixture
def controller(mock_ha_client, mock_alerting):
    """Create controller instance with mocked dependencies."""
    return Controller(
        ha_client=mock_ha_client,
        alerting=mock_alerting,
        heater_entity_id="climate.heater",
        temp_sensor_id="sensor.temperature",
        on_temp=25.0,
        off_temp=26.0,
        min_cycle_time=180,
        sensor_stale_timeout=300,
        manual_override_timeout=1800,
    )


@pytest.mark.asyncio
async def test_heater_turns_on_below_threshold(controller, mock_ha_client):
    """Test heater turns ON when temperature drops below threshold."""
    # Temperature below ON threshold
    mock_ha_client.get_temperature.return_value = 24.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should turn heater on
    mock_ha_client.turn_on.assert_called_once_with("climate.heater")
    assert controller.state == ControllerState.HEATING


@pytest.mark.asyncio
async def test_heater_turns_off_above_threshold(controller, mock_ha_client):
    """Test heater turns OFF when temperature reaches OFF threshold."""
    # Set controller to HEATING state
    controller.state = ControllerState.HEATING
    controller.last_state_change = datetime.now() - timedelta(minutes=5)

    # Temperature above OFF threshold
    mock_ha_client.get_temperature.return_value = 26.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "heat",
        "attributes": {"hvac_action": "heating"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should turn heater off and enter COOLDOWN
    mock_ha_client.turn_off.assert_called_once_with("climate.heater")
    assert controller.state == ControllerState.COOLDOWN


@pytest.mark.asyncio
async def test_minimum_cycle_enforced(controller, mock_ha_client):
    """Test minimum 3-minute cycle is enforced during COOLDOWN."""
    # Set controller to COOLDOWN state (just turned off)
    controller.state = ControllerState.COOLDOWN
    controller.last_state_change = datetime.now() - timedelta(seconds=60)  # Only 1 minute ago

    # Temperature drops below ON threshold
    mock_ha_client.get_temperature.return_value = 24.0
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should NOT turn heater on (still in cooldown)
    mock_ha_client.turn_on.assert_not_called()
    assert controller.state == ControllerState.COOLDOWN


@pytest.mark.asyncio
async def test_cooldown_to_idle_after_3_minutes(controller, mock_ha_client):
    """Test transition from COOLDOWN to IDLE after 3 minutes."""
    # Set controller to COOLDOWN state (3+ minutes ago)
    controller.state = ControllerState.COOLDOWN
    controller.last_state_change = datetime.now() - timedelta(seconds=181)

    # Temperature above ON threshold (no action needed)
    mock_ha_client.get_temperature.return_value = 25.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should transition to IDLE
    assert controller.state == ControllerState.IDLE


@pytest.mark.asyncio
async def test_stale_data_triggers_failure(controller, mock_ha_client, mock_alerting):
    """Test entering FAILURE state when sensor data is stale (>5min old)."""
    # Return stale data timestamp
    stale_time = datetime.now() - timedelta(minutes=6)
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": stale_time.isoformat(),
    }

    await controller.run_control_cycle()

    # Should enter FAILURE state and send alert
    assert controller.state == ControllerState.FAILURE
    mock_alerting.send_alert.assert_called_once()


@pytest.mark.asyncio
async def test_manual_override_respected(controller, mock_ha_client):
    """Test system respects manual override and waits 30min before resuming."""
    # User manually turns on heater
    controller.state = ControllerState.MANUAL_OVERRIDE
    controller.last_state_change = datetime.now() - timedelta(minutes=10)

    # Temperature is in normal range
    mock_ha_client.get_temperature.return_value = 25.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "heat",
        "attributes": {"hvac_action": "heating"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should stay in MANUAL_OVERRIDE (not enough time elapsed)
    assert controller.state == ControllerState.MANUAL_OVERRIDE
    mock_ha_client.turn_off.assert_not_called()
    mock_ha_client.turn_on.assert_not_called()


@pytest.mark.asyncio
async def test_manual_override_timeout(controller, mock_ha_client):
    """Test automatic resumption after 30-minute manual override timeout."""
    # Manual override 30+ minutes ago
    controller.state = ControllerState.MANUAL_OVERRIDE
    controller.last_state_change = datetime.now() - timedelta(minutes=31)

    # Temperature is in normal range
    mock_ha_client.get_temperature.return_value = 25.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should transition to IDLE after timeout
    assert controller.state == ControllerState.IDLE


@pytest.mark.asyncio
async def test_state_verification_retry(controller, mock_ha_client):
    """Test retry logic when state verification fails."""
    # Temperature below ON threshold
    mock_ha_client.get_temperature.return_value = 24.5

    # First verification fails (heater didn't turn on)
    # Second verification succeeds
    mock_ha_client.turn_on.side_effect = [False, True]
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should retry turn_on
    assert mock_ha_client.turn_on.call_count == 2


@pytest.mark.asyncio
async def test_state_verification_max_retries_failure(controller, mock_ha_client, mock_alerting):
    """Test entering FAILURE state after max retries on verification failure."""
    # Temperature below ON threshold
    mock_ha_client.get_temperature.return_value = 24.5

    # All verification attempts fail
    mock_ha_client.turn_on.return_value = False
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should enter FAILURE state after max retries
    assert controller.state == ControllerState.FAILURE
    mock_alerting.send_alert.assert_called_once()


@pytest.mark.asyncio
async def test_hysteresis_prevents_oscillation(controller, mock_ha_client):
    """Test hysteresis deadband prevents rapid on/off cycling."""
    # Start in IDLE
    controller.state = ControllerState.IDLE

    # Temperature at 25.5°C (between ON=25.0 and OFF=26.0)
    mock_ha_client.get_temperature.return_value = 25.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Should remain in IDLE (within deadband)
    assert controller.state == ControllerState.IDLE
    mock_ha_client.turn_on.assert_not_called()


@pytest.mark.asyncio
async def test_health_endpoint_data(controller):
    """Test health endpoint returns correct state information."""
    controller.state = ControllerState.HEATING
    controller.last_temperature = 24.5
    controller.last_temp_timestamp = datetime.now()
    controller.last_decision = "Temperature 24.5°C < 25.0°C threshold → turn ON"
    controller.last_decision_timestamp = datetime.now()
    controller.last_state_change = datetime.now() - timedelta(minutes=2)

    health = controller.get_health()

    assert health["state"] == "HEATING"
    assert health["last_temperature"] == 24.5
    assert "last_temp_timestamp" in health
    assert "last_decision" in health
    assert "last_decision_timestamp" in health
    assert "time_since_state_change" in health


@pytest.mark.asyncio
async def test_api_unreachable_triggers_failure(controller, mock_ha_client, mock_alerting):
    """Test entering FAILURE state when HA API is unreachable."""
    # Simulate API failure
    mock_ha_client.get_temperature.side_effect = Exception("Connection refused")

    await controller.run_control_cycle()

    # Should enter FAILURE state
    assert controller.state == ControllerState.FAILURE
    mock_alerting.send_alert.assert_called_once()


@pytest.mark.asyncio
async def test_decision_logging(controller, mock_ha_client, caplog):
    """Test that control decisions are logged with reasoning."""
    import logging

    caplog.set_level(logging.INFO)

    # Temperature below ON threshold
    mock_ha_client.get_temperature.return_value = 24.5
    mock_ha_client.get_heater_state.return_value = {
        "state": "off",
        "attributes": {"hvac_action": "off"},
        "last_updated": datetime.now().isoformat(),
    }

    await controller.run_control_cycle()

    # Check that decision was logged
    assert any("24.5" in record.message for record in caplog.records)
    assert any(
        "turn ON" in record.message or "HEATING" in record.message for record in caplog.records
    )
