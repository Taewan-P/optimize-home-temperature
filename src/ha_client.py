"""Home Assistant REST API client with retry logic and WebSocket support."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aiohttp
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


class HaApiError(Exception):
    """Exception raised for Home Assistant API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:
        if self.status_code:
            return f"{self.message} (HTTP {self.status_code})"
        return self.message


class StateChangeSubscription:
    """Context manager for WebSocket state change subscriptions."""

    def __init__(self, ws: ClientConnection, entity_id: str):
        self._ws = ws
        self._entity_id = entity_id
        self._event_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def get_event(self) -> dict:
        """Get the next state change event."""
        return await self._event_queue.get()

    async def _process_messages(self) -> None:
        """Process incoming WebSocket messages."""
        async for message in self._ws:
            data = json.loads(message)
            if data.get("type") == "event":
                event = data.get("event", {})
                event_data = event.get("data", {})
                if event_data.get("entity_id") == self._entity_id:
                    await self._event_queue.put(event_data)


class HaClient:
    """Async Home Assistant REST API client with retry logic and WebSocket support."""

    RETRY_DELAYS = [1, 2, 4]
    MAX_RETRIES = 3

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    @classmethod
    def from_env(cls) -> HaClient:
        """Create client from HA_URL and HA_TOKEN environment variables."""
        base_url = os.environ["HA_URL"]
        token = os.environ["HA_TOKEN"]
        return cls(base_url=base_url, token=token)

    async def __aenter__(self) -> HaClient:
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session:
            await self._session.close()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
    ) -> dict:
        """Make HTTP request to Home Assistant API with retry logic."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(
                    "[%s] %s %s (attempt %d/%d)",
                    datetime.now().isoformat(),
                    method.upper(),
                    url,
                    attempt + 1,
                    self.MAX_RETRIES,
                )

                if self._session is None:
                    raise HaApiError(
                        "Client session not initialized. Use async context manager."
                    )

                response = await self._execute_request(method, url, headers, data)
                return await self._handle_response(response)

            except HaApiError:
                raise
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "Request failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                        str(e),
                    )
                    await asyncio.sleep(delay)

        raise HaApiError(
            f"Request failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    async def _execute_request(
        self,
        method: str,
        url: str,
        headers: dict,
        data: Optional[dict],
    ) -> Any:
        if method.lower() == "get":
            return await self._session.get(url, headers=headers)
        elif method.lower() == "post":
            return await self._session.post(url, headers=headers, json=data)
        else:
            raise HaApiError(f"Unsupported HTTP method: {method}")

    async def _handle_response(self, response: aiohttp.ClientResponse) -> dict:
        """Handle HTTP response and raise on errors."""
        if response.status == 401:
            text = await response.text()
            raise HaApiError(f"Unauthorized: {text}", status_code=401)
        if response.status == 404:
            raise HaApiError("Entity not found", status_code=404)
        if response.status >= 400:
            text = await response.text()
            raise HaApiError(f"API error: {text}", status_code=response.status)

        try:
            return await response.json()
        except aiohttp.ContentTypeError:
            return {"state": await response.text()}

    async def _call_service(
        self,
        domain: str,
        service: str,
        **service_data: Any,
    ) -> bool:
        """Call a Home Assistant service."""
        endpoint = f"/api/services/{domain}/{service}"
        await self._make_request("post", endpoint, data=service_data)
        return True

    async def _verify_state(
        self,
        entity_id: str,
        expected_state: str,
        timeout: float = 5.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Verify entity reached expected state within timeout."""
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            state_data = await self.get_state(entity_id)
            if state_data.get("state") == expected_state:
                return True
            await asyncio.sleep(poll_interval)

        return False

    async def get_state(self, entity_id: str) -> dict:
        """Get current state of an entity."""
        endpoint = f"/api/states/{entity_id}"
        return await self._make_request("get", endpoint)

    async def turn_on(self, entity_id: str) -> bool:
        """Turn on a climate entity."""
        await self._call_service("climate", "turn_on", entity_id=entity_id)
        return await self._verify_state(entity_id, "heat")

    async def turn_off(self, entity_id: str) -> bool:
        """Turn off a climate entity."""
        await self._call_service("climate", "turn_off", entity_id=entity_id)
        return await self._verify_state(entity_id, "off")

    async def set_hvac_mode(self, entity_id: str, hvac_mode: str) -> bool:
        """Set HVAC mode for a climate entity."""
        await self._call_service(
            "climate", "set_hvac_mode", entity_id=entity_id, hvac_mode=hvac_mode
        )
        return await self._verify_state(entity_id, hvac_mode)

    async def get_temperature(self, entity_id: str) -> float:
        """Read temperature from a sensor entity."""
        state_data = await self.get_state(entity_id)
        return float(state_data["state"])

    async def get_humidity(self, entity_id: str) -> float:
        """Read humidity from a sensor entity."""
        state_data = await self.get_state(entity_id)
        return float(state_data["state"])

    async def get_heater_state(self, entity_id: str) -> dict:
        """Get full state of a heater/climate entity."""
        return await self.get_state(entity_id)

    async def get_weather(self, entity_id: str) -> dict:
        """Get weather data from a weather entity."""
        return await self.get_state(entity_id)

    @asynccontextmanager
    async def subscribe_state_changes(
        self, entity_id: str
    ) -> AsyncIterator[StateChangeSubscription]:
        """Subscribe to state changes for an entity via WebSocket."""
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"

        async with websockets.connect(ws_url) as ws:
            auth_required = await ws.recv()
            auth_data = json.loads(auth_required)

            if auth_data.get("type") != "auth_required":
                raise HaApiError("Unexpected WebSocket response during auth")

            await ws.send(json.dumps({"type": "auth", "access_token": self.token}))

            auth_result = await ws.recv()
            auth_result_data = json.loads(auth_result)

            if auth_result_data.get("type") == "auth_invalid":
                raise HaApiError("WebSocket authentication failed")

            subscribe_msg = {
                "id": 1,
                "type": "subscribe_events",
                "event_type": "state_changed",
            }
            await ws.send(json.dumps(subscribe_msg))

            sub_result = await ws.recv()
            sub_result_data = json.loads(sub_result)

            if not sub_result_data.get("success", False):
                raise HaApiError("Failed to subscribe to state changes")

            subscription = StateChangeSubscription(ws, entity_id)
            asyncio.create_task(subscription._process_messages())

            yield subscription


__all__ = ["HaClient", "HaApiError", "StateChangeSubscription"]
