"""Hildebrand Glow API client for the DCC (Data Communications Company) backend."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.glowmarkt.com/api/v0-1"
APPLICATION_ID = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"

# Resource classifiers
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

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self, username: str, password: str) -> str:
        """Authenticate and return the JWT token.

        Raises GlowAuthError on bad credentials or unexpected API responses.
        """
        url = f"{API_BASE}/auth"
        headers = {
            "Content-Type": "application/json",
            "applicationId": APPLICATION_ID,
        }
        payload = {"username": username, "password": password}

        try:
            async with self._session.post(url, headers=headers, json=payl
