"""DataUpdateCoordinator for the Hildebrand Glow (DCC) integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

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
        # resource_id -> float (today's usage/cost)
        self.usage: dict[str, float] = {}
        # resource_id -> full resource definition dict
        self.resources: dict[str, dict[str, Any]] = {}
        # ve_id -> virtual entity name
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
        # True only after a successful live authenticate() call this session.
        # Injecting a stored token via set_token() does NOT set this flag.
        self._have_live_token = False

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    async def _ensure_authenticated(self) -> None:
        """Ensure the API client has a usable token.

        Strategy:
        1. If we already performed a live authenticate() this session and the
           token is still valid, do nothing.
        2. If we have a stored token in the config entry that we haven't tried
           yet, inject it optimistically — the first API call will reveal
           whether it is still valid.
        3. Otherwise, perform a full username/password re-authentication.
        """
        if self._have_live_token and self._client.is_token_valid():
            _LOGGER.debug("Using existing live token")
            return

        stored_token = self.entry.data.get(CONF_TOKEN)
        if stored_token and not self._have_live_token:
            # Inject with no expiry; validity is confirmed on first API call
            self._client.set_token(stored_token)
            _LOGGER.debug(
                "Injected stored token from config entry; "
                "will validate on first API call"
            )
            return

        await self._do_authenticate()

    async def _do_authenticate(self) -> None:
        """Perform a full username/password authentication."""
        username = self.entry.data.get(CONF_USERNAME, "")
        _LOGGER.debug("Performing full authentication for %s", username)
        try:
            token = await self._client.authenticate(
                self.entry.data[CONF_USERNAME],
                self.entry.data[CONF_PASSWORD],
            )
        except GlowAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        self._have_live_token = True
        # Persist the refreshed token so it survives HA restarts
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_TOKEN: token},
        )
        _LOGGER.debug("Authentication successful, token persisted")

    async def _handle_auth_error(self) -> None:
        """Called when a 401 is received mid-session; forces a fresh login."""
        _LOGGER.warning(
            "Received 401 from Glow API — invalidating token and "
            "forcing re-authentication"
        )
        self._have_live_token = False
        await self._do_authenticate()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> GlowCoordinatorData:
        """Fetch fresh data from the Glow API."""
        await self._ensure_authenticated()

        # Use the HA-configured local timezone so BST/GMT offsets are correct
        try:
            from zoneinfo import ZoneInfo
            local_tz = ZoneInfo(self.hass.config.time_zone)
        except Exception:
            local_tz = None  # glow_api falls back to Europe/London

        result = GlowCoordinatorData()

        # ---- Step 1: get virtual entities --------------------------------
        try:
            entities = await self._client.get_virtual_entities()
        except GlowAuthError:
            await self._handle_auth_error()
            try:
                entities = await self._client.get_virtual_entities()
            except GlowAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
        except GlowApiError as err:
            raise UpdateFailed(
                f"Error fetching virtual entities: {err}"
            ) from err

        # ---- Step 2: iterate entities and their resources ----------------
        for entity in entities:
            ve_id: str = entity["veId"]
            ve_name: str = entity.get("name", ve_id)
            result.virtual_entities[ve_id] = ve_name

            try:
                resources = await self._client.get_virtual_entity_resources(
                    ve_id
                )
            except GlowAuthError:
                await self._handle_auth_error()
                try:
                    resources = (
                        await self._client.get_virtual_entity_resources(ve_id)
                    )
                except GlowApiError as err:
                    _LOGGER.warning(
                        "Could not fetch resources for %s after retry: %s",
                        ve_name,
                        err,
                    )
                    continue
            except GlowApiError as err:
                _LOGGER.warning(
                    "Could not fetch resources for %s: %s", ve_name, err
                )
                continue

            # ---- Step 3: fetch today's reading for each resource ---------
            for resource in resources:
                classifier: str = resource.get("classifier", "")
                if classifier not in INTERESTING_CLASSIFIERS:
                    continue

                resource_id: str = resource["resourceId"]
                result.resources[resource_id] = {
                    **resource,
                    "ve_id": ve_id,
                    "ve_name": ve_name,
                }

                try:
                    usage = await self._client.get_today_usage(
                        resource_id, local_tz=local_tz
                    )
                    if usage is not None:
                        # Convert pence -> GBP for cost classifiers
                        if "cost" in classifier:
                            usage = round(usage / 100, 4)
                        result.usage[resource_id] = usage
                        _LOGGER.debug(
                            "Resource %s (%s): today's value = %s",
                            resource_id,
                            classifier,
                            result.usage[resource_id],
                        )
                except GlowAuthError:
                    await self._handle_auth_error()
                    try:
                        usage = await self._client.get_today_usage(
                            resource_id, local_tz=local_tz
                        )
                        if usage is not None:
                            if "cost" in classifier:
                                usage = round(usage / 100, 4)
                            result.usage[resource_id] = usage
                    except GlowApiError as err:
                        _LOGGER.debug(
                            "Skipping usage for %s after retry: %s",
                            resource_id,
                            err,
                        )
                except GlowApiError as err:
                    _LOGGER.debug(
                        "Skipping today's data for resource %s (%s): %s",
                        resource_id,
                        classifier,
                        err,
                    )

        return result
