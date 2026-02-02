"""Electricity tier tracking module for billing cycle management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from src.ha_client import HaClient

logger = logging.getLogger(__name__)


@dataclass
class TierInfo:
    """Information about current electricity tier and usage."""

    tier: int
    tier_name: str
    usage_kwh: float
    days_remaining: int
    predicted_tier_end: int
    predicted_usage_kwh: float


class TierTracker:
    """Tracks electricity usage and tier boundaries for billing cycle."""

    TIER_BOUNDARIES = [120.0, 300.0]
    TIER_NAMES = [
        "Tier 1 (0-120kWh)",
        "Tier 2 (120-300kWh)",
        "Tier 3 (300+ kWh)",
    ]
    BILLING_CYCLE_START_DAY = 21

    def __init__(
        self,
        ha_base_url: str,
        ha_token: str,
        influx_url: str,
        influx_token: str,
        influx_org: str,
        influx_bucket: str,
    ):
        self.ha_base_url = ha_base_url
        self.ha_token = ha_token
        self.influx_url = influx_url
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket

    def _get_billing_cycle_dates(self) -> tuple[datetime, datetime]:
        """Calculate billing cycle start and end dates (21st to 20th)."""
        now = datetime.now(UTC)

        if now.day >= self.BILLING_CYCLE_START_DAY:
            cycle_start = datetime(now.year, now.month, self.BILLING_CYCLE_START_DAY, tzinfo=UTC)
            if now.month == 12:
                cycle_end = datetime(now.year + 1, 1, self.BILLING_CYCLE_START_DAY - 1, tzinfo=UTC)
            else:
                cycle_end = datetime(
                    now.year, now.month + 1, self.BILLING_CYCLE_START_DAY - 1, tzinfo=UTC
                )
        else:
            if now.month == 1:
                cycle_start = datetime(now.year - 1, 12, self.BILLING_CYCLE_START_DAY, tzinfo=UTC)
            else:
                cycle_start = datetime(
                    now.year, now.month - 1, self.BILLING_CYCLE_START_DAY, tzinfo=UTC
                )
            cycle_end = datetime(now.year, now.month, self.BILLING_CYCLE_START_DAY - 1, tzinfo=UTC)

        return cycle_start, cycle_end

    def _calculate_tier(self, usage_kwh: float) -> tuple[int, str]:
        """Calculate tier number and name based on usage."""
        if usage_kwh < self.TIER_BOUNDARIES[0]:
            return 1, self.TIER_NAMES[0]
        elif usage_kwh < self.TIER_BOUNDARIES[1]:
            return 2, self.TIER_NAMES[1]
        else:
            return 3, self.TIER_NAMES[2]

    async def _get_cumulative_usage(self) -> float:
        """Query cumulative electricity usage since billing cycle start."""
        cycle_start, _ = self._get_billing_cycle_dates()

        usage_kwh = await self._query_ha_electricity(cycle_start)
        return usage_kwh

    async def _query_ha_electricity(self, start_date: datetime) -> float:
        """Query Home Assistant for electricity usage data."""
        async with HaClient(self.ha_base_url, self.ha_token) as client:
            state = await client.get_state("sensor.electricity_usage")
            return float(state.get("state", 0.0))

    async def _calculate_daily_usage_rate(self) -> float:
        """Calculate average daily usage rate for prediction."""
        cycle_start, _ = self._get_billing_cycle_dates()
        now = datetime.now(UTC)

        days_elapsed = (now - cycle_start).days
        if days_elapsed == 0:
            days_elapsed = 1

        current_usage = await self._get_cumulative_usage()
        return current_usage / days_elapsed

    async def get_current_tier(self) -> TierInfo:
        """Get current tier information with prediction."""
        usage_kwh = await self._get_cumulative_usage()
        tier, tier_name = self._calculate_tier(usage_kwh)

        _, cycle_end = self._get_billing_cycle_dates()
        now = datetime.now(UTC)
        days_remaining = (cycle_end.date() - now.date()).days

        daily_rate = await self._calculate_daily_usage_rate()
        predicted_usage = usage_kwh + (daily_rate * days_remaining)
        predicted_tier, _ = self._calculate_tier(predicted_usage)

        return TierInfo(
            tier=tier,
            tier_name=tier_name,
            usage_kwh=usage_kwh,
            days_remaining=days_remaining,
            predicted_tier_end=predicted_tier,
            predicted_usage_kwh=predicted_usage,
        )

    async def record_daily_usage(self) -> None:
        """Record daily usage to InfluxDB."""
        usage_kwh = await self._get_cumulative_usage()
        point = Point("electricity").field("usage_kwh", usage_kwh).time(datetime.now(UTC))

        await self._write_to_influxdb(point)

    async def _write_to_influxdb(self, point: Point) -> None:
        """Write data point to InfluxDB."""
        async with InfluxDBClientAsync(
            url=self.influx_url,
            token=self.influx_token,
            org=self.influx_org,
        ) as client:
            write_api = client.write_api()
            await write_api.write(bucket=self.influx_bucket, record=point)

    async def estimate_heater_contribution(self, heater_power_kw: float) -> float:
        """Estimate heater contribution to electricity usage."""
        heater_on_hours = await self._get_heater_on_time()
        return heater_on_hours * heater_power_kw

    async def _get_heater_on_time(self) -> float:
        """Get total heater on-time in hours for current billing cycle."""
        cycle_start, _ = self._get_billing_cycle_dates()

        async with HaClient(self.ha_base_url, self.ha_token) as client:
            state = await client.get_heater_state("climate.heater")
            return 0.0


__all__ = ["TierTracker", "TierInfo"]
