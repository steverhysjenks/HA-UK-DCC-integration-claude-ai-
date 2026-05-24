"""DataUpdateCoordinator for the Hildebrand Glow (DCC) integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CLASSIFIER_ELEC_CONSUMPTION,
    CLASSIFIER_ELEC_COST,
    CLASSIFIER_ELEC_EXPORT,
    CLASSIFIER_GAS_CONSUMPTION,
    CLASSIFIER_GAS_COST,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .glow_api import GlowApiClient, GlowAuthError, GlowApiError

_LOGGER = logging.getLogger(__name__)

INTERESTING_CLASSIFIERS = {
    CLASSIFIER_ELEC_CONSUMPTION,
    CLASSIFIER_ELEC_COST,
    CLASSIFIER_ELEC_EXPORT,
    CLASSIFIER_GAS_CONSUMPTION,
    CLASSIFIER_GAS_COST,
}


class GlowCoordinatorData:
    """Holds all data fetched in a single coordinator refresh cycle."""

    def __init__(self) -> None:
        # resource_id → float (today's usage/cost)
        self.usage: dict[str, float] = {}
        # resource_id → full resource definition dict
        self.resources: dict[str, dict[str, Any]] = {}
        # ve_id → virtual entity name
        self.virtual_entities: dict[str, str] = {}


class GlowUpdateCoordinator(DataUpdateCoordinator[GlowCoordinatorData]):
    """Coordinator that fetches Glow data for all meters on the account."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        session = async_get_clientsession(hass)
        self._client = GlowApiClient(session)
        self._authenticated = False

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    async def _ensure_authenticated(self) -> None:
        """Authenticate (or re-authenticate) the API client."""
        if self._authenticated and self._client.is_token_valid():
            return

        # Try restoring a cached token first
        stored_token = self.entry.data.get(CONF_TOKEN)
        if stored_token and not self._authenticated:
            self._client.set_token(stored_token)
            if self._client.is_token_valid():
                self._authenticated = True
                return

        # Full re-auth
        try:
            token = await self._client.authenticate(
                self.entry.data[CONF_USERNAME],
                self.entry.data[CONF_PASSWORD],
            )
        except GlowAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        self._authenticated = True
        # Persist the new token so it survives HA restarts
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_TOKEN: token},
        )

    # ------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> GlowCoordinatorData:
        """Fetch fresh data from the Glow API."""
        await self._ensure_authenticated()

        result = GlowCoordinatorData()

        try:
            entities = await self._client.get_virtual_entities()
        except GlowAuthError as err:
            self._authenticated = False
            raise ConfigEntryAuthFailed(str(err)) from err
        except GlowApiError as err:
            raise UpdateFailed(f"Error fetching virtual entities: {err}") from err

        for entity in entities:
            ve_id: str = entity["veId"]
            ve_name: str = entity.get("name", ve_id)
            result.virtual_entities[ve_id] = ve_name

            try:
                resources = await self._client.get_virtual_entity_resources(ve_id)
            except GlowApiError as err:
                _LOGGER.warning("Could not fetch resources for %s: %s", ve_name, err)
                continue

            for resource in resources:
                classifier: str = resource.get("classifier", "")
                if classifier not in INTERESTING_CLASSIFIERS:
                    continue

                resource_id: str = resource["resourceId"]
                result.resources[resource_id] = {**resource, "ve_id": ve_id, "ve_name": ve_name}

                try:
                    usage = await self._client.get_today_usage(resource_id)
                    if usage is not None:
                        # pence → GBP conversion for cost classifiers
                        if "cost" in classifier:
                            usage = round(usage / 100, 4)
                        result.usage[resource_id] = usage
                except GlowApiError as err:
                    _LOGGER.debug(
                        "Skipping today's data for resource %s (%s): %s",
                        resource_id,
                        classifier,
                        err,
                    )

        return result
