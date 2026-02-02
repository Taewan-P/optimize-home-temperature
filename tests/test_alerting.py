"""Tests for alerting module with multi-channel support."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.alerting import Alert, Alerting, AlertSeverity, AlertType


@pytest.fixture
def alerting_config():
    """Configuration for alerting system."""
    return {
        "ha_url": "http://localhost:8123",
        "ha_token": "test_token",
        "discord_webhook_url": "https://discord.com/api/webhooks/test/webhook",
        "dedup_window_minutes": 30,
    }


@pytest.fixture
def alerting(alerting_config):
    """Create alerting instance with mocked HTTP client."""
    return Alerting(
        ha_url=alerting_config["ha_url"],
        ha_token=alerting_config["ha_token"],
        discord_webhook_url=alerting_config["discord_webhook_url"],
        dedup_window_minutes=alerting_config["dedup_window_minutes"],
    )


@pytest.mark.asyncio
async def test_critical_alert_both_channels(alerting):
    """Test that CRITICAL alerts are sent to both push and Discord."""
    # Mock both channels
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.TEMP_OUT_OF_BOUNDS,
        message="Temperature outside 24-27°C range",
    )

    result = await alerting.send_alert(alert)

    # Both channels should be called
    assert alerting._send_ha_push.called
    assert alerting._send_discord.called
    assert result["status"] == "sent"
    assert "push" in result["channels"]
    assert "discord" in result["channels"]


@pytest.mark.asyncio
async def test_warning_alert_push_only(alerting):
    """Test that WARNING alerts only go to push, not Discord."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.WARNING,
        alert_type=AlertType.TIER_BOUNDARY,
        message="Approaching tier boundary",
    )

    result = await alerting.send_alert(alert)

    # Only push should be called
    assert alerting._send_ha_push.called
    assert not alerting._send_discord.called
    assert result["status"] == "sent"
    assert "push" in result["channels"]
    assert "discord" not in result["channels"]


@pytest.mark.asyncio
async def test_info_alert_push_only(alerting):
    """Test that INFO alerts only go to push, not Discord."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.INFO,
        alert_type=AlertType.STATE_CHANGE,
        message="Heater state changed to ON",
    )

    result = await alerting.send_alert(alert)

    # Only push should be called
    assert alerting._send_ha_push.called
    assert not alerting._send_discord.called
    assert result["status"] == "sent"


@pytest.mark.asyncio
async def test_deduplication_within_window(alerting):
    """Test that duplicate alerts within 30min window are suppressed."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.SENSOR_FAILURE,
        message="Sensor failure detected",
    )

    # First alert should be sent
    result1 = await alerting.send_alert(alert)
    assert result1["status"] == "sent"
    assert alerting._send_ha_push.call_count == 1

    # Second identical alert within 30min should be deduplicated
    result2 = await alerting.send_alert(alert)
    assert result2["status"] == "deduplicated"
    assert alerting._send_ha_push.call_count == 1  # No additional call


@pytest.mark.asyncio
async def test_deduplication_after_window_expires(alerting):
    """Test that alerts are sent again after dedup window expires."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.API_UNREACHABLE,
        message="HA API unreachable",
    )

    # First alert
    result1 = await alerting.send_alert(alert)
    assert result1["status"] == "sent"

    # Manually expire the dedup window
    alert_key = f"{alert.alert_type.value}_{alert.message}"
    alerting._last_alert_time[alert_key] = datetime.now() - timedelta(minutes=31)

    # Second alert should be sent (window expired)
    result2 = await alerting.send_alert(alert)
    assert result2["status"] == "sent"
    assert alerting._send_ha_push.call_count == 2


@pytest.mark.asyncio
async def test_discord_failure_doesnt_block_push(alerting):
    """Test that Discord failure doesn't prevent push notification."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(side_effect=Exception("Discord API error"))

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.TEMP_OUT_OF_BOUNDS,
        message="Temperature critical",
    )

    # Should still succeed despite Discord failure
    result = await alerting.send_alert(alert)
    assert result["status"] == "sent"
    assert "push" in result["channels"]
    # Discord should be attempted but failed gracefully
    assert alerting._send_discord.called


@pytest.mark.asyncio
async def test_push_failure_doesnt_block_discord(alerting):
    """Test that push failure doesn't prevent Discord notification."""
    alerting._send_ha_push = AsyncMock(side_effect=Exception("HA API error"))
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.SENSOR_FAILURE,
        message="Sensor failure",
    )

    result = await alerting.send_alert(alert)
    assert result["status"] == "sent"
    assert "discord" in result["channels"]
    assert alerting._send_ha_push.called


@pytest.mark.asyncio
async def test_alert_logging(alerting):
    """Test that all alerts are logged with timestamps."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.TEMP_OUT_OF_BOUNDS,
        message="Temperature out of bounds",
    )

    await alerting.send_alert(alert)

    # Check that alert was logged
    assert len(alerting.alert_log) > 0
    logged_alert = alerting.alert_log[-1]
    assert logged_alert["severity"] == AlertSeverity.CRITICAL.value
    assert logged_alert["type"] == AlertType.TEMP_OUT_OF_BOUNDS.value
    assert logged_alert["message"] == "Temperature out of bounds"
    assert "timestamp" in logged_alert


@pytest.mark.asyncio
async def test_alert_acknowledgment(alerting):
    """Test alert acknowledgment mechanism."""
    alerting._send_ha_push = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.SENSOR_FAILURE,
        message="Sensor failure",
    )

    result = await alerting.send_alert(alert)
    alert_id = result.get("alert_id")

    # Acknowledge the alert
    ack_result = alerting.acknowledge_alert(alert_id)
    assert ack_result["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_ha_push_notification_payload(alerting):
    """Test that HA push notification has correct payload."""
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response

        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.TEMP_OUT_OF_BOUNDS,
            message="Temperature critical: 28°C",
        )

        await alerting._send_ha_push(alert)

        # Verify the call was made
        assert mock_post.called
        call_args = mock_post.call_args
        # Check URL contains notify service
        assert "notify" in str(call_args)


@pytest.mark.asyncio
async def test_discord_webhook_payload(alerting):
    """Test that Discord webhook has correct payload format."""
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__.return_value = mock_response

        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.API_UNREACHABLE,
            message="HA API unreachable",
        )

        await alerting._send_discord(alert)

        # Verify the call was made to Discord webhook
        assert mock_post.called
        call_args = mock_post.call_args
        assert alerting.discord_webhook_url in str(call_args)


@pytest.mark.asyncio
async def test_multiple_different_alerts_not_deduplicated(alerting):
    """Test that different alerts are not deduplicated."""
    alerting._send_ha_push = AsyncMock(return_value=True)
    alerting._send_discord = AsyncMock(return_value=True)

    alert1 = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.TEMP_OUT_OF_BOUNDS,
        message="Temperature too high",
    )

    alert2 = Alert(
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.SENSOR_FAILURE,
        message="Sensor failure",
    )

    # Both alerts should be sent (different types)
    result1 = await alerting.send_alert(alert1)
    result2 = await alerting.send_alert(alert2)

    assert result1["status"] == "sent"
    assert result2["status"] == "sent"
    assert alerting._send_ha_push.call_count == 2


@pytest.mark.asyncio
async def test_alert_with_custom_data(alerting):
    """Test alert with additional custom data."""
    alerting._send_ha_push = AsyncMock(return_value=True)

    alert = Alert(
        severity=AlertSeverity.WARNING,
        alert_type=AlertType.TIER_BOUNDARY,
        message="Approaching tier 2",
        custom_data={"current_usage": 115, "tier_limit": 120},
    )

    result = await alerting.send_alert(alert)
    assert result["status"] == "sent"

    # Check logged alert includes custom data
    logged_alert = alerting.alert_log[-1]
    assert logged_alert.get("custom_data") == {"current_usage": 115, "tier_limit": 120}


@pytest.mark.asyncio
async def test_alert_history_retrieval(alerting):
    """Test retrieving alert history."""
    alerting._send_ha_push = AsyncMock(return_value=True)

    # Send multiple alerts
    for i in range(3):
        alert = Alert(
            severity=AlertSeverity.INFO,
            alert_type=AlertType.STATE_CHANGE,
            message=f"State change {i}",
        )
        await alerting.send_alert(alert)

    # Retrieve history
    history = alerting.get_alert_history(limit=10)
    assert len(history) >= 3


@pytest.mark.asyncio
async def test_alert_severity_enum(alerting):
    """Test AlertSeverity enum values."""
    assert AlertSeverity.CRITICAL.value == "critical"
    assert AlertSeverity.WARNING.value == "warning"
    assert AlertSeverity.INFO.value == "info"


@pytest.mark.asyncio
async def test_alert_type_enum(alerting):
    """Test AlertType enum values."""
    assert AlertType.TEMP_OUT_OF_BOUNDS.value == "temp_out_of_bounds"
    assert AlertType.SENSOR_FAILURE.value == "sensor_failure"
    assert AlertType.API_UNREACHABLE.value == "api_unreachable"
    assert AlertType.TIER_BOUNDARY.value == "tier_boundary"
    assert AlertType.STATE_CHANGE.value == "state_change"
