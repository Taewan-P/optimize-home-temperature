"""Heater controller with state machine and hysteresis logic."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from src.alerting import Alert, AlertSeverity, AlertType, Alerting
from src.ha_client import HaApiError, HaClient

logger = logging.getLogger(__name__)


class ControllerState(Enum):
    IDLE = "IDLE"
    HEATING = "HEATING"
    COOLDOWN = "COOLDOWN"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    FAILURE = "FAILURE"


class Controller:
    MAX_VERIFICATION_RETRIES = 3

    def __init__(
        self,
        ha_client: HaClient,
        alerting: Alerting,
        heater_entity_id: str,
        temp_sensor_id: str,
        on_temp: float,
        off_temp: float,
        min_cycle_time: int,
        sensor_stale_timeout: int,
        manual_override_timeout: int,
    ):
        self._ha_client = ha_client
        self._alerting = alerting
        self._heater_entity_id = heater_entity_id
        self._temp_sensor_id = temp_sensor_id
        self._on_temp = on_temp
        self._off_temp = off_temp
        self._min_cycle_time = min_cycle_time
        self._sensor_stale_timeout = sensor_stale_timeout
        self._manual_override_timeout = manual_override_timeout

        self.state = ControllerState.IDLE
        self.last_state_change = datetime.now()
        self.last_temperature: Optional[float] = None
        self.last_temp_timestamp: Optional[datetime] = None
        self.last_decision: Optional[str] = None
        self.last_decision_timestamp: Optional[datetime] = None

    async def run_control_cycle(self) -> None:
        try:
            current_temp = await self._ha_client.get_temperature(self._temp_sensor_id)
            self.last_temperature = current_temp
            self.last_temp_timestamp = datetime.now()

            heater_state_data = await self._ha_client.get_heater_state(self._heater_entity_id)

            if self._is_data_stale(heater_state_data):
                await self._enter_failure_state("Sensor data is stale (>5min old)")
                return

            await self._evaluate_state_machine(current_temp, heater_state_data)

        except HaApiError as e:
            await self._enter_failure_state(f"Home Assistant API error: {e}")
        except Exception as e:
            await self._enter_failure_state(f"Unexpected error: {e}")
            logger.exception("Unexpected error in control cycle")

    def _is_data_stale(self, heater_state_data: dict) -> bool:
        last_updated_str = heater_state_data.get("last_updated")
        if not last_updated_str:
            return True

        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=None)
                now = datetime.now()
            else:
                from datetime import timezone

                now = datetime.now(timezone.utc)

            age = (now - last_updated).total_seconds()
            return age > self._sensor_stale_timeout
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse last_updated timestamp: {e}")
            return True

    async def _evaluate_state_machine(self, current_temp: float, heater_state_data: dict) -> None:
        current_heater_state = heater_state_data.get("state", "unknown")
        time_in_current_state = (datetime.now() - self.last_state_change).total_seconds()

        if self.state == ControllerState.IDLE:
            await self._handle_idle_state(current_temp, current_heater_state)
        elif self.state == ControllerState.HEATING:
            await self._handle_heating_state(current_temp, current_heater_state)
        elif self.state == ControllerState.COOLDOWN:
            await self._handle_cooldown_state(current_temp, time_in_current_state)
        elif self.state == ControllerState.MANUAL_OVERRIDE:
            await self._handle_manual_override_state(time_in_current_state)
        elif self.state == ControllerState.FAILURE:
            pass

    async def _handle_idle_state(self, current_temp: float, current_heater_state: str) -> None:
        if current_temp < self._on_temp:
            decision = f"Temperature {current_temp}°C < {self._on_temp}°C threshold → turn ON"
            logger.info(decision)
            self.last_decision = decision
            self.last_decision_timestamp = datetime.now()

            success = await self._turn_on_with_retry()
            if success:
                await self._transition_to_state(ControllerState.HEATING)
            else:
                await self._enter_failure_state("Failed to turn on heater after retries")

    async def _handle_heating_state(self, current_temp: float, current_heater_state: str) -> None:
        if current_temp >= self._off_temp:
            decision = f"Temperature {current_temp}°C >= {self._off_temp}°C threshold → turn OFF"
            logger.info(decision)
            self.last_decision = decision
            self.last_decision_timestamp = datetime.now()

            success = await self._turn_off_with_retry()
            if success:
                await self._transition_to_state(ControllerState.COOLDOWN)
            else:
                await self._enter_failure_state("Failed to turn off heater after retries")

    async def _handle_cooldown_state(
        self, current_temp: float, time_in_current_state: float
    ) -> None:
        if time_in_current_state >= self._min_cycle_time:
            if current_temp < self._on_temp:
                decision = f"COOLDOWN complete ({time_in_current_state:.0f}s), temp {current_temp}°C < {self._on_temp}°C → turn ON"
                logger.info(decision)
                self.last_decision = decision
                self.last_decision_timestamp = datetime.now()

                success = await self._turn_on_with_retry()
                if success:
                    await self._transition_to_state(ControllerState.HEATING)
                else:
                    await self._enter_failure_state("Failed to turn on heater after retries")
            else:
                decision = f"COOLDOWN complete ({time_in_current_state:.0f}s), temp {current_temp}°C >= {self._on_temp}°C → IDLE"
                logger.info(decision)
                self.last_decision = decision
                self.last_decision_timestamp = datetime.now()
                await self._transition_to_state(ControllerState.IDLE)
        else:
            remaining = self._min_cycle_time - time_in_current_state
            if current_temp < self._on_temp:
                decision = f"COOLDOWN in progress ({remaining:.0f}s remaining), temp {current_temp}°C < {self._on_temp}°C → wait"
                logger.info(decision)
                self.last_decision = decision
                self.last_decision_timestamp = datetime.now()

    async def _handle_manual_override_state(self, time_in_current_state: float) -> None:
        if time_in_current_state >= self._manual_override_timeout:
            decision = (
                f"Manual override timeout ({time_in_current_state:.0f}s) → resume automatic control"
            )
            logger.info(decision)
            self.last_decision = decision
            self.last_decision_timestamp = datetime.now()
            await self._transition_to_state(ControllerState.IDLE)
        else:
            remaining = self._manual_override_timeout - time_in_current_state
            decision = f"Manual override active ({remaining:.0f}s remaining) → no action"
            logger.debug(decision)

    async def _turn_on_with_retry(self) -> bool:
        for attempt in range(self.MAX_VERIFICATION_RETRIES):
            try:
                success = await self._ha_client.turn_on(self._heater_entity_id)
                if success:
                    logger.info(f"Heater turned ON successfully (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(f"Heater turn ON verification failed (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"Error turning on heater (attempt {attempt + 1}): {e}")

            if attempt < self.MAX_VERIFICATION_RETRIES - 1:
                await asyncio.sleep(2)

        return False

    async def _turn_off_with_retry(self) -> bool:
        for attempt in range(self.MAX_VERIFICATION_RETRIES):
            try:
                success = await self._ha_client.turn_off(self._heater_entity_id)
                if success:
                    logger.info(f"Heater turned OFF successfully (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(f"Heater turn OFF verification failed (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"Error turning off heater (attempt {attempt + 1}): {e}")

            if attempt < self.MAX_VERIFICATION_RETRIES - 1:
                await asyncio.sleep(2)

        return False

    async def _transition_to_state(self, new_state: ControllerState) -> None:
        old_state = self.state
        self.state = new_state
        self.last_state_change = datetime.now()
        logger.info(f"State transition: {old_state.value} → {new_state.value}")

    async def _enter_failure_state(self, reason: str) -> None:
        logger.error(f"Entering FAILURE state: {reason}")
        await self._transition_to_state(ControllerState.FAILURE)

        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.SENSOR_FAILURE,
            message=f"Heater controller entered FAILURE state: {reason}",
        )
        await self._alerting.send_alert(alert)

        self.last_decision = f"FAILURE: {reason}"
        self.last_decision_timestamp = datetime.now()

    def get_health(self) -> dict:
        time_since_state_change = (datetime.now() - self.last_state_change).total_seconds()

        return {
            "state": self.state.value,
            "last_temperature": self.last_temperature,
            "last_temp_timestamp": self.last_temp_timestamp.isoformat()
            if self.last_temp_timestamp
            else None,
            "last_decision": self.last_decision,
            "last_decision_timestamp": self.last_decision_timestamp.isoformat()
            if self.last_decision_timestamp
            else None,
            "time_since_state_change": time_since_state_change,
            "last_state_change": self.last_state_change.isoformat(),
        }


__all__ = ["Controller", "ControllerState"]
