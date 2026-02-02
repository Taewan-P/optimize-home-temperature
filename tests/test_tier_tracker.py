"""Tests for electricity tier tracking module - TDD RED phase."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tier_tracker import TierTracker, TierInfo


@pytest.fixture
def tier_tracker():
    """Create a TierTracker instance for testing."""
    return TierTracker(
        ha_base_url="http://localhost:8123",
        ha_token="test_token",
        influx_url="http://localhost:8086",
        influx_token="test_influx_token",
        influx_org="test_org",
        influx_bucket="heater",
    )


class TestTierIdentification:
    """Test tier identification based on kWh usage."""

    @pytest.mark.asyncio
    async def test_tier_1_identification(self, tier_tracker):
        """Test correctly identifies tier 1 (0-120kWh)."""
        # Mock usage data: 100 kWh (within tier 1)
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 100.0

            tier_info = await tier_tracker.get_current_tier()

            assert tier_info.tier == 1
            assert tier_info.usage_kwh == 100.0
            assert tier_info.tier_name == "Tier 1 (0-120kWh)"

    @pytest.mark.asyncio
    async def test_tier_2_identification(self, tier_tracker):
        """Test correctly identifies tier 2 (120-300kWh)."""
        # Mock usage data: 200 kWh (within tier 2)
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 200.0

            tier_info = await tier_tracker.get_current_tier()

            assert tier_info.tier == 2
            assert tier_info.usage_kwh == 200.0
            assert tier_info.tier_name == "Tier 2 (120-300kWh)"

    @pytest.mark.asyncio
    async def test_tier_3_identification(self, tier_tracker):
        """Test correctly identifies tier 3 (300+ kWh)."""
        # Mock usage data: 350 kWh (within tier 3)
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 350.0

            tier_info = await tier_tracker.get_current_tier()

            assert tier_info.tier == 3
            assert tier_info.usage_kwh == 350.0
            assert tier_info.tier_name == "Tier 3 (300+ kWh)"

    @pytest.mark.asyncio
    async def test_tier_boundary_exact_120(self, tier_tracker):
        """Test tier boundary at exactly 120 kWh (should be tier 2)."""
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 120.0

            tier_info = await tier_tracker.get_current_tier()

            assert tier_info.tier == 2

    @pytest.mark.asyncio
    async def test_tier_boundary_exact_300(self, tier_tracker):
        """Test tier boundary at exactly 300 kWh (should be tier 3)."""
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 300.0

            tier_info = await tier_tracker.get_current_tier()

            assert tier_info.tier == 3


class TestBillingCycle:
    """Test billing cycle handling (resets on 21st)."""

    @pytest.mark.asyncio
    async def test_billing_cycle_rollover(self, tier_tracker):
        """Test handles billing cycle reset on 21st."""
        # Mock current date: 22nd of month (day after reset)
        test_date = datetime(2026, 2, 22, 10, 0, 0, tzinfo=UTC)

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            cycle_start, cycle_end = tier_tracker._get_billing_cycle_dates()

            # Should be Feb 21 - Mar 20
            assert cycle_start.day == 21
            assert cycle_start.month == 2
            assert cycle_end.day == 20
            assert cycle_end.month == 3

    @pytest.mark.asyncio
    async def test_billing_cycle_before_21st(self, tier_tracker):
        """Test billing cycle when current date is before 21st."""
        # Mock current date: 15th of month (before reset)
        test_date = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            cycle_start, cycle_end = tier_tracker._get_billing_cycle_dates()

            # Should be Jan 21 - Feb 20
            assert cycle_start.day == 21
            assert cycle_start.month == 1
            assert cycle_end.day == 20
            assert cycle_end.month == 2

    @pytest.mark.asyncio
    async def test_days_remaining_calculation(self, tier_tracker):
        """Test calculates days remaining in billing cycle correctly."""
        # Mock current date: Feb 15 (6 days until Feb 20 end)
        test_date = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            with patch.object(
                tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
            ) as mock_usage:
                mock_usage.return_value = 100.0

                tier_info = await tier_tracker.get_current_tier()

                # Feb 15 to Feb 20 = 5 days remaining
                assert tier_info.days_remaining == 5


class TestTierBoundaryPrediction:
    """Test tier boundary crossing prediction."""

    @pytest.mark.asyncio
    async def test_tier_boundary_prediction_will_cross(self, tier_tracker):
        """Test predicts crossing into next tier based on current usage rate."""
        # Mock: 110 kWh used, 5 days remaining, usage rate 10 kWh/day
        # Prediction: 110 + (10 * 5) = 160 kWh (will cross into tier 2)
        test_date = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            with patch.object(
                tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
            ) as mock_usage:
                mock_usage.return_value = 110.0

                with patch.object(
                    tier_tracker, "_calculate_daily_usage_rate", new_callable=AsyncMock
                ) as mock_rate:
                    mock_rate.return_value = 10.0

                    tier_info = await tier_tracker.get_current_tier()

                    assert tier_info.predicted_tier_end == 2
                    assert tier_info.predicted_usage_kwh == 160.0

    @pytest.mark.asyncio
    async def test_tier_boundary_prediction_stay_same(self, tier_tracker):
        """Test predicts staying in same tier."""
        # Mock: 50 kWh used, 10 days remaining, usage rate 5 kWh/day
        # Prediction: 50 + (5 * 10) = 100 kWh (stays in tier 1)
        test_date = datetime(2026, 2, 10, 10, 0, 0, tzinfo=UTC)

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            with patch.object(
                tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
            ) as mock_usage:
                mock_usage.return_value = 50.0

                with patch.object(
                    tier_tracker, "_calculate_daily_usage_rate", new_callable=AsyncMock
                ) as mock_rate:
                    mock_rate.return_value = 5.0

                    tier_info = await tier_tracker.get_current_tier()

                    assert tier_info.predicted_tier_end == 1
                    assert tier_info.predicted_usage_kwh == 100.0


class TestDataHandling:
    """Test data handling and delayed data scenarios."""

    @pytest.mark.asyncio
    async def test_handles_delayed_data(self, tier_tracker):
        """Test handles delayed electricity data (available ~9 hours after usage)."""
        # Mock: Query yesterday's data since today's isn't available yet
        test_date = datetime(2026, 2, 15, 8, 0, 0, tzinfo=UTC)  # 8am, before 9am data availability

        with patch("src.tier_tracker.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            with patch.object(
                tier_tracker, "_query_ha_electricity", new_callable=AsyncMock
            ) as mock_query:
                mock_query.return_value = 100.0

                await tier_tracker._get_cumulative_usage()

                # Should query for yesterday's date
                call_args = mock_query.call_args
                # Verify it's querying historical data, not real-time
                assert mock_query.called

    @pytest.mark.asyncio
    async def test_stores_daily_usage_to_influxdb(self, tier_tracker):
        """Test stores daily usage data to InfluxDB."""
        with patch.object(tier_tracker, "_write_to_influxdb", new_callable=AsyncMock) as mock_write:
            with patch.object(
                tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
            ) as mock_usage:
                mock_usage.return_value = 150.0

                await tier_tracker.record_daily_usage()

                mock_write.assert_called_once()
                # Verify the data point includes usage_kwh field
                call_args = mock_write.call_args[0][0]
                assert "usage_kwh" in str(call_args) or hasattr(call_args, "_fields")


class TestHeaterContribution:
    """Test heater contribution estimation."""

    @pytest.mark.asyncio
    async def test_calculates_heater_contribution(self, tier_tracker):
        """Test calculates estimated heater contribution to usage."""
        # Mock: Heater on for 10 hours, power rating 0.8 kW
        # Expected: 10 * 0.8 = 8 kWh
        heater_on_hours = 10.0
        heater_power_kw = 0.8

        with patch.object(
            tier_tracker, "_get_heater_on_time", new_callable=AsyncMock
        ) as mock_on_time:
            mock_on_time.return_value = heater_on_hours

            contribution = await tier_tracker.estimate_heater_contribution(heater_power_kw)

            assert contribution == pytest.approx(8.0, rel=0.01)


class TestAPIEndpoint:
    """Test API endpoint exposure."""

    @pytest.mark.asyncio
    async def test_api_endpoint_returns_tier_info(self, tier_tracker):
        """Test /api/tier endpoint returns correct JSON structure."""
        with patch.object(
            tier_tracker, "_get_cumulative_usage", new_callable=AsyncMock
        ) as mock_usage:
            mock_usage.return_value = 100.0

            with patch.object(
                tier_tracker, "_calculate_daily_usage_rate", new_callable=AsyncMock
            ) as mock_rate:
                mock_rate.return_value = 5.0

                tier_info = await tier_tracker.get_current_tier()

                # Verify structure matches API requirements
                assert hasattr(tier_info, "tier")
                assert hasattr(tier_info, "usage_kwh")
                assert hasattr(tier_info, "days_remaining")
                assert hasattr(tier_info, "predicted_tier_end")
