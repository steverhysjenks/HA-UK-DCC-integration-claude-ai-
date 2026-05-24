"""Hildebrand Glow API client for the DCC (Data Communications Company) backend."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.glowmarkt.com/api/v0-1"
APPLICATION_ID = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"

CLASSIFIER_ELEC_CONSUMPTION = "electricity.consumption"
CLASSIFIER_ELEC_COST = "electricity.consumption.cost"
CLASSIFIER_GAS_CONSUMPTION = "gas.consumption"
CLASSIFIER_GAS_COST = "gas.consumption.cost"
CLASSIFIER_ELEC_EXPORT = "electricity.export"

KNOWN_CLASSIFIERS = {
    CLASSIFIER_ELEC_CONSUMPTION,
    CLASSIFIER_ELEC_COST,
    CLASSIFIER_GAS_CONSUMPTION,
    CLASSIFIER_GAS_COST,
    CLASSIFIER_ELEC_EXPORT,
}


class GlowAuthError(Exception):
    """Raised when authentication with the Glow API fails."""


class GlowApiError(Exception):
    """Raised when the Glow API returns an unexpected response."""


class GlowApiClient:
    """Async HTTP client for the Hildebrand Glow (Glowmarkt) API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    async def authenticate(self, username: str, password: str) -> str:
        """Authenticate and return the JWT token."""
        url = f"{API_BASE}/auth"
        headers = {
            "Content-Type": "application/json",
            "applicationId": APPLICATION_ID,
        }
        payload = {"username": username, "password": password}

        try:
            async with self._session.post(
                url, headers=headers, json=payload
            ) as resp:
                if resp.status == 401:
                    raise GlowAuthError("Invalid username or password")
                if resp.status != 200:
                    text = await resp.text()
                    raise GlowAuthError(
                        f"Unexpected auth response {resp.status}: {text}"
                    )
                data: dict[str, Any] = await resp.json()
        except aiohttp.ClientError as err:
            raise GlowAuthError(
                f"Network error during authentication: {err}"
            ) from err

        if not data.get("valid"):
            raise GlowAuthError("Authentication rejected by Glow API")

        token: str = data["token"]
        exp: int = data.get("exp", 0)
        self._token = token
        self._token_expiry = (
            datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        )
        _LOGGER.debug(
            "Glow API authenticated successfully, token expires %s",
            self._token_expiry,
        )
        return token

    def is_token_valid(self) -> bool:
        """Return True if the cached token is still usable."""
        if not self._token or not self._token_expiry:
            return False
        return (
            datetime.now(tz=timezone.utc)
            < self._token_expiry - timedelta(minutes=30)
        )

    def set_token(self, token: str, expiry: datetime | None = None) -> None:
        """Inject an existing token restored from config entry data."""
        self._token = token
        self._token_expiry = expiry

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            raise GlowApiError("No token available; authenticate first")
        return {
            "Content-Type": "application/json",
            "token": self._token,
            "applicationId": APPLICATION_ID,
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{API_BASE}{path}"
        try:
            async with self._session.get(
                url, headers=self._auth_headers(), params=params
            ) as resp:
                if resp.status == 401:
                    raise GlowAuthError("Token rejected; re-authentication required")
                if resp.status != 200:
                    text = await resp.text()
                    raise GlowApiError(
                        f"GET {path} returned {resp.status}: {text}"
                    )
                return await resp.json()
        except aiohttp.ClientError as err:
            raise GlowApiError(
                f"Network error calling {path}: {err}"
            ) from err

    async def get_virtual_entities(self) -> list[dict[str, Any]]:
        """Return all virtual entities for the authenticated user."""
        return await self._get("/virtualentity")

    async def get_virtual_entity_resources(
        self, ve_id: str
    ) -> list[dict[str, Any]]:
        """Return resources for a specific virtual entity."""
        data = await self._get(f"/virtualentity/{ve_id}/resources")
        return data.get("resources", [])

    async def get_resource_readings(
        self,
        resource_id: str,
        from_dt: datetime,
        to_dt: datetime,
        period: str = "P1D",
        function: str = "sum",
    ) -> list[list[float]]:
        """Retrieve time-series readings for a resource."""
        utc_offset = (
            int(from_dt.utcoffset().total_seconds() / 60)
            if from_dt.utcoffset()
            else 0
        )
        params = {
            "from": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "period": period,
            "offset": str(-utc_offset),
            "function": function,
        }
        data = await self._get(
            f"/resource/{resource_id}/readings", params=params
        )
        if data.get("status") != "OK":
            _LOGGER.warning(
                "Readings for %s returned status: %s",
                resource_id,
                data.get("status"),
            )
        return data.get("data", [])

    async def get_resource_current(
        self, resource_id: str
    ) -> list[float] | None:
        """Return the latest reading for a resource."""
        data = await self._get(f"/resource/{resource_id}/current")
        readings: list = data.get("data", [])
        if readings:
            return readings[0]
        return None

    async def get_tariff(self, resource_id: str) -> dict[str, Any]:
        """Return the current tariff for a resource."""
        return await self._get(f"/resource/{resource_id}/tariff")

async def get_today_usage(
    self, resource_id: str, local_tz: timezone | None = None
) -> float | None:
    """Return today's total usage/cost for a resource."""
    # Use the provided timezone, but default to BST/GMT via a fixed
    # UTC+1 offset in summer. Callers should pass hass.config.time_zone.
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/London") if local_tz is None else local_tz

    now = datetime.now(tz=tz)
    if now.hour < 1 or (now.hour == 1 and now.minute < 30):
        start = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    end = start.replace(hour=23, minute=59, second=59)

    try:
        readings = await self.get_resource_readings(
            resource_id, start, end, period="P1D", function="sum"
        )
        if readings:
            return readings[-1][1]
    except GlowAuthError:
        raise
    except GlowApiError as err:
        _LOGGER.debug(
            "Could not fetch today's usage for %s: %s", resource_id, err
        )
    return None
