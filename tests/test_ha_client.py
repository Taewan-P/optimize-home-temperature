"""Tests for Home Assistant client module - TDD RED phase."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.ha_client import HaApiError, HaClient


@pytest.fixture
def mock_response():
    """Create a mock aiohttp response."""
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value={"state": "heat", "attributes": {}})
    return response


@pytest.fixture
def ha_client():
    """Create a HaClient instance for testing."""
    return HaClient(base_url="http://localhost:8123", token="test_token_12345")


def create_mock_response(status=200, json_data=None, text_data=""):
    """Helper to create properly mocked aiohttp response."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data or {})
    mock_resp.text = AsyncMock(return_value=text_data)
    return mock_resp


class TestHaClientInitialization:
    """Test HaClient initialization and configuration."""

    def test_client_initialization(self):
        """Test client initializes with correct parameters."""
        client = HaClient(base_url="http://192.168.1.100:8123", token="my_long_lived_token")
        assert client.base_url == "http://192.168.1.100:8123"
        assert client.token == "my_long_lived_token"

    def test_client_from_env_variables(self):
        """Test client can be created from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "HA_URL": "http://homeassistant.local:8123",
                "HA_TOKEN": "env_token_value",
            },
        ):
            client = HaClient.from_env()
            assert client.base_url == "http://homeassistant.local:8123"
            assert client.token == "env_token_value"


class TestClimateControl:
    """Test climate control (turn_on, turn_off, set_hvac_mode)."""

    @pytest.mark.asyncio
    async def test_turn_on_success(self, ha_client):
        """Test successful turn_on command returns True."""
        with patch.object(ha_client, "_call_service", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = True
            with patch.object(ha_client, "_verify_state", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = True

                result = await ha_client.turn_on("climate.living_room_heater")

                assert result is True
                mock_call.assert_called_once_with(
                    "climate", "turn_on", entity_id="climate.living_room_heater"
                )
                mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_success(self, ha_client):
        """Test successful turn_off command returns True."""
        with patch.object(ha_client, "_call_service", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = True
            with patch.object(ha_client, "_verify_state", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = True

                result = await ha_client.turn_off("climate.living_room_heater")

                assert result is True
                mock_call.assert_called_once_with(
                    "climate", "turn_off", entity_id="climate.living_room_heater"
                )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat(self, ha_client):
        """Test setting HVAC mode to heat."""
        with patch.object(ha_client, "_call_service", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = True
            with patch.object(ha_client, "_verify_state", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = True

                result = await ha_client.set_hvac_mode("climate.heater", "heat")

                assert result is True
                mock_call.assert_called_once_with(
                    "climate",
                    "set_hvac_mode",
                    entity_id="climate.heater",
                    hvac_mode="heat",
                )


class TestRetryLogic:
    """Test exponential backoff retry logic."""

    @pytest.mark.asyncio
    async def test_request_retries_on_connection_error(self, ha_client):
        """Test failed command after 3 retries raises HaApiError."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientError("Connection failed")

        mock_session = AsyncMock()
        mock_session.get = mock_get

        ha_client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(HaApiError) as exc_info:
                await ha_client.get_state("climate.heater")

        assert "Connection failed" in str(exc_info.value) or "3 attempts" in str(exc_info.value)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_delays_exponential_backoff(self, ha_client):
        """Test retry uses exponential backoff delays (1s, 2s, 4s)."""
        delays = []

        async def track_sleep(delay):
            delays.append(delay)

        async def mock_get(*args, **kwargs):
            raise aiohttp.ClientError("Temporary failure")

        mock_session = AsyncMock()
        mock_session.get = mock_get
        ha_client._session = mock_session

        with patch("src.ha_client.asyncio.sleep", side_effect=track_sleep):
            with pytest.raises(HaApiError):
                await ha_client.get_state("climate.heater")

        assert delays == [1, 2]

    @pytest.mark.asyncio
    async def test_successful_after_retry(self, ha_client):
        """Test command succeeds after initial failures."""
        call_count = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise aiohttp.ClientError("Temporary failure")
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"state": "heat"})
            return mock_resp

        mock_session = AsyncMock()
        mock_session.get = failing_then_success
        ha_client._session = mock_session

        with patch("src.ha_client.asyncio.sleep", new_callable=AsyncMock):
            result = await ha_client.get_state("climate.heater")

        assert result["state"] == "heat"
        assert call_count == 3


class TestStateVerification:
    """Test state verification after commands."""

    @pytest.mark.asyncio
    async def test_state_verification_success(self, ha_client):
        """Test state verification confirms expected state."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"state": "heat", "attributes": {}}

            result = await ha_client._verify_state("climate.heater", expected_state="heat")

            assert result is True

    @pytest.mark.asyncio
    async def test_state_verification_detects_mismatch(self, ha_client):
        """Test state verification detects mismatch between expected and actual."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"state": "off", "attributes": {}}

            result = await ha_client._verify_state("climate.heater", expected_state="heat")

            assert result is False

    @pytest.mark.asyncio
    async def test_state_verification_timeout(self, ha_client):
        """Test state verification times out if state never changes."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"state": "off", "attributes": {}}

            with patch("src.ha_client.asyncio.sleep", new_callable=AsyncMock):
                result = await ha_client._verify_state(
                    "climate.heater",
                    expected_state="heat",
                    timeout=0.1,
                    poll_interval=0.05,
                )

            assert result is False


class TestSensorReading:
    """Test sensor reading functions."""

    @pytest.mark.asyncio
    async def test_sensor_reading_temperature(self, ha_client):
        """Test reading temperature sensor returns numeric value."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "state": "22.5",
                "attributes": {
                    "unit_of_measurement": "C",
                    "friendly_name": "Living Room Temperature",
                },
            }

            result = await ha_client.get_temperature("sensor.living_room_temp")

            assert result == 22.5
            mock_get.assert_called_once_with("sensor.living_room_temp")

    @pytest.mark.asyncio
    async def test_sensor_reading_humidity(self, ha_client):
        """Test reading humidity sensor returns numeric value."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "state": "65",
                "attributes": {"unit_of_measurement": "%"},
            }

            result = await ha_client.get_humidity("sensor.living_room_humidity")

            assert result == 65.0

    @pytest.mark.asyncio
    async def test_get_heater_state(self, ha_client):
        """Test getting heater current state."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "state": "heat",
                "attributes": {"hvac_action": "heating", "current_temperature": 20.5},
            }

            result = await ha_client.get_heater_state("climate.heater")

            assert result["state"] == "heat"
            assert result["attributes"]["hvac_action"] == "heating"

    @pytest.mark.asyncio
    async def test_get_weather(self, ha_client):
        """Test getting weather data."""
        with patch.object(ha_client, "get_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "state": "cloudy",
                "attributes": {"temperature": 5.0, "humidity": 80, "forecast": []},
            }

            result = await ha_client.get_weather("weather.home")

            assert result["state"] == "cloudy"
            assert result["attributes"]["temperature"] == 5.0


class TestWebSocketSubscription:
    """Test WebSocket subscription for real-time state monitoring."""

    @pytest.mark.asyncio
    async def test_websocket_subscribe_state_changes(self, ha_client):
        """Test subscribing to state changes via WebSocket."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "type": "result", "success": true}',
            ]
        )

        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_connect_cm):
            async with ha_client.subscribe_state_changes("climate.heater") as _:
                auth_call = mock_ws.send.call_args_list[0]
                assert "auth" in auth_call[0][0]
                assert ha_client.token in auth_call[0][0]

    @pytest.mark.asyncio
    async def test_websocket_receives_state_change_event(self, ha_client):
        """Test receiving state change events via WebSocket."""
        import json

        state_change_event = {
            "id": 1,
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "climate.heater",
                    "new_state": {"state": "heat"},
                    "old_state": {"state": "off"},
                },
            },
        }

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "type": "result", "success": true}',
                json.dumps(state_change_event),
            ]
        )

        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_connect_cm):
            async with ha_client.subscribe_state_changes("climate.heater") as subscription:
                assert subscription is not None


class TestAuthentication:
    """Test authentication handling."""

    @pytest.mark.asyncio
    async def test_auth_header_included_in_requests(self, ha_client):
        """Test Bearer token is included in request headers."""
        captured_headers = {}

        async def mock_get(url, headers=None, **kwargs):
            captured_headers.update(headers or {})
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"state": "on"})
            return mock_resp

        mock_session = AsyncMock()
        mock_session.get = mock_get
        ha_client._session = mock_session

        await ha_client.get_state("sensor.test")

        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer test_token_12345"

    @pytest.mark.asyncio
    async def test_auth_failure_raises_error(self, ha_client):
        """Test authentication failure raises HaApiError."""

        async def mock_get(url, headers=None, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status = 401
            mock_resp.text = AsyncMock(return_value="Unauthorized")
            return mock_resp

        mock_session = AsyncMock()
        mock_session.get = mock_get
        ha_client._session = mock_session

        with pytest.raises(HaApiError) as exc_info:
            await ha_client.get_state("sensor.test")

        assert "401" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)


class TestHaApiError:
    """Test custom exception class."""

    def test_exception_message(self):
        """Test HaApiError contains message."""
        error = HaApiError("API request failed")
        assert str(error) == "API request failed"

    def test_exception_with_status_code(self):
        """Test HaApiError can include status code."""
        error = HaApiError("Not found", status_code=404)
        assert error.status_code == 404
        assert "Not found" in str(error)


class TestContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self):
        """Test client properly cleans up resources."""
        client = HaClient(base_url="http://localhost:8123", token="test_token")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            async with client:
                pass

            mock_session.close.assert_called_once()
