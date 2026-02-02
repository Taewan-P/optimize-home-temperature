"""Multi-channel alerting system with deduplication and acknowledgment."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertType(Enum):
    """Alert types."""

    TEMP_OUT_OF_BOUNDS = "temp_out_of_bounds"
    SENSOR_FAILURE = "sensor_failure"
    API_UNREACHABLE = "api_unreachable"
    TIER_BOUNDARY = "tier_boundary"
    STATE_CHANGE = "state_change"


@dataclass
class Alert:
    """Alert data structure."""

    severity: AlertSeverity
    alert_type: AlertType
    message: str
    custom_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


class Alerting:
    """Multi-channel alerting system with deduplication."""

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        discord_webhook_url: str,
        dedup_window_minutes: int = 30,
    ):
        """Initialize alerting system.

        Args:
            ha_url: Home Assistant base URL
            ha_token: Home Assistant long-lived access token
            discord_webhook_url: Discord webhook URL for alerts
            dedup_window_minutes: Deduplication window in minutes
        """
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.discord_webhook_url = discord_webhook_url
        self.dedup_window_minutes = dedup_window_minutes

        self._last_alert_time: Dict[str, datetime] = {}
        self.alert_log: List[Dict[str, Any]] = []
        self._acknowledged_alerts: set = set()

    async def send_alert(self, alert: Alert) -> Dict[str, Any]:
        """Send alert to appropriate channels with deduplication.

        Args:
            alert: Alert to send

        Returns:
            Dict with status, channels, and alert_id
        """
        alert_key = f"{alert.alert_type.value}_{alert.message}"
        if self._is_deduplicated(alert_key):
            logger.info(f"Alert deduplicated: {alert_key}")
            return {"status": "deduplicated", "alert_id": None}

        self._last_alert_time[alert_key] = datetime.now()
        alert_id = str(uuid.uuid4())
        channels_sent = []
        errors = []

        try:
            await self._send_ha_push(alert)
            channels_sent.append("push")
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            errors.append(("push", str(e)))

        if alert.severity == AlertSeverity.CRITICAL:
            try:
                await self._send_discord(alert)
                channels_sent.append("discord")
            except Exception as e:
                logger.error(f"Failed to send Discord notification: {e}")
                errors.append(("discord", str(e)))

        self._log_alert(alert, alert_id, channels_sent)

        if channels_sent:
            return {
                "status": "sent",
                "alert_id": alert_id,
                "channels": channels_sent,
                "errors": errors if errors else None,
            }
        else:
            return {
                "status": "failed",
                "alert_id": alert_id,
                "channels": [],
                "errors": errors,
            }

    async def _send_ha_push(self, alert: Alert) -> bool:
        """Send push notification via Home Assistant.

        Args:
            alert: Alert to send

        Returns:
            True if successful
        """
        url = f"{self.ha_url}/api/services/notify/mobile_app_notification"
        headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "service": "notify",
            "service_data": {
                "title": f"[{alert.severity.value.upper()}] {alert.alert_type.value}",
                "message": alert.message,
                "data": {
                    "alert_type": alert.alert_type.value,
                    "severity": alert.severity.value,
                    "timestamp": alert.timestamp.isoformat(),
                },
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status not in (200, 201):
                    raise Exception(f"HA push notification failed: {response.status}")
                return True

    async def _send_discord(self, alert: Alert) -> bool:
        """Send alert via Discord webhook.

        Args:
            alert: Alert to send

        Returns:
            True if successful
        """
        color_map = {
            AlertSeverity.CRITICAL: 0xFF0000,
            AlertSeverity.WARNING: 0xFFA500,
            AlertSeverity.INFO: 0x0000FF,
        }

        embed = {
            "title": f"{alert.severity.value.upper()}: {alert.alert_type.value}",
            "description": alert.message,
            "color": color_map.get(alert.severity, 0x808080),
            "timestamp": alert.timestamp.isoformat(),
            "fields": [],
        }

        if alert.custom_data:
            for key, value in alert.custom_data.items():
                embed["fields"].append({"name": key, "value": str(value), "inline": True})

        payload = {"embeds": [embed]}

        async with aiohttp.ClientSession() as session:
            async with session.post(self.discord_webhook_url, json=payload) as response:
                if response.status not in (200, 204):
                    raise Exception(f"Discord webhook failed: {response.status}")
                return True

    def _is_deduplicated(self, alert_key: str) -> bool:
        """Check if alert should be deduplicated.

        Args:
            alert_key: Unique key for the alert

        Returns:
            True if alert should be deduplicated
        """
        if alert_key not in self._last_alert_time:
            return False

        last_time = self._last_alert_time[alert_key]
        time_since_last = datetime.now() - last_time
        dedup_window = timedelta(minutes=self.dedup_window_minutes)

        return time_since_last < dedup_window

    def _log_alert(self, alert: Alert, alert_id: str, channels_sent: List[str]) -> None:
        """Log alert to internal log.

        Args:
            alert: Alert that was sent
            alert_id: Unique alert ID
            channels_sent: List of channels alert was sent to
        """
        log_entry = {
            "alert_id": alert_id,
            "timestamp": datetime.now().isoformat(),
            "severity": alert.severity.value,
            "type": alert.alert_type.value,
            "message": alert.message,
            "channels": channels_sent,
        }

        if alert.custom_data:
            log_entry["custom_data"] = alert.custom_data

        self.alert_log.append(log_entry)
        logger.info(f"Alert logged: {log_entry}")

    def acknowledge_alert(self, alert_id: str) -> Dict[str, str]:
        """Acknowledge an alert.

        Args:
            alert_id: ID of alert to acknowledge

        Returns:
            Dict with acknowledgment status
        """
        self._acknowledged_alerts.add(alert_id)
        logger.info(f"Alert acknowledged: {alert_id}")
        return {"status": "acknowledged", "alert_id": alert_id}

    def get_alert_history(
        self, limit: int = 100, severity: Optional[AlertSeverity] = None
    ) -> List[Dict[str, Any]]:
        """Get alert history.

        Args:
            limit: Maximum number of alerts to return
            severity: Filter by severity (optional)

        Returns:
            List of alert log entries
        """
        history = self.alert_log[-limit:]

        if severity:
            history = [entry for entry in history if entry["severity"] == severity.value]

        return history

    def clear_alert_log(self) -> None:
        """Clear alert log."""
        self.alert_log.clear()
        logger.info("Alert log cleared")
