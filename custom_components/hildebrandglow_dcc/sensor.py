"""Sensor platform for the Hildebrand Glow (DCC) integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLASSIFIER_ELEC_CONSUMPTION,
    CLASSIFIER_ELEC_COST,
    CLASSIFIER_ELEC_EXPORT,
    CLASSIFIER_GAS_CONSUMPTION,
    CLASSIFIER_GAS_COST,
    CLASSIFIER_ICONS,
    CLASSIFIER_NAMES,
    DOMAIN,
)
from .coordinator import GlowUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlowSensorEntityDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with Glow-specific attributes."""

    classifier: str = ""


SENSOR_DESCRIPTIONS: dict[str, GlowSensorEntityDescription] = {
    CLASSIFIER_ELEC_CONSUMPTION: GlowSensorEntityDescription(
        key=CLASSIFIER_ELEC_CONSUMPTION,
        classifier=CLASSIFIER_ELEC_CONSUMPTION,
        name="Electricity Usage Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=CLASSIFIER_ICONS[CLASSIFIER_ELEC_CONSUMPTION],
    ),
    CLASSIFIER_ELEC_COST: GlowSensorEntityDescription(
        key=CLASSIFIER_ELEC_COST,
        classifier=CLASSIFIER_ELEC_COST,
        name="Electricity Cost Today",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=CLASSIFIER_ICONS[CLASSIFIER_ELEC_COST],
    ),
    CLASSIFIER_ELEC_EXPORT: GlowSensorEntityDescription(
        key=CLASSIFIER_ELEC_EXPORT,
        classifier=CLASSIFIER_ELEC_EXPORT,
        name="Electricity Export Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=CLASSIFIER_ICONS[CLASSIFIER_ELEC_EXPORT],
        entity_registry_enabled_default=False,  # disabled by default – less common
    ),
    CLASSIFIER_GAS_CONSUMPTION: GlowSensorEntityDescription(
        key=CLASSIFIER_GAS_CONSUMPTION,
        classifier=CLASSIFIER_GAS_CONSUMPTION,
        name="Gas Usage Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=CLASSIFIER_ICONS[CLASSIFIER_GAS_CONSUMPTION],
    ),
    CLASSIFIER_GAS_COST: GlowSensorEntityDescription(
        key=CLASSIFIER_GAS_COST,
        classifier=CLASSIFIER_GAS_COST,
        name="Gas Cost Today",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon=CLASSIFIER_ICONS[CLASSIFIER_GAS_COST],
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glow sensors from a config entry."""
    coordinator: GlowUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GlowSensor] = []
    for resource_id, resource in coordinator.data.resources.items():
        classifier: str = resource.get("classifier", "")
        description = SENSOR_DESCRIPTIONS.get(classifier)
        if description is None:
            _LOGGER.debug("Skipping unknown classifier: %s", classifier)
            continue
        entities.append(GlowSensor(coordinator, resource_id, description))

    async_add_entities(entities)


class GlowSensor(CoordinatorEntity[GlowUpdateCoordinator], SensorEntity):
    """A sensor representing one Glow resource (e.g. electricity consumption today)."""

    entity_description: GlowSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GlowUpdateCoordinator,
        resource_id: str,
        description: GlowSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._resource_id = resource_id

        resource = coordinator.data.resources[resource_id]
        ve_id: str = resource["ve_id"]
        ve_name: str = resource.get("ve_name", ve_id)

        self._attr_unique_id = f"{DOMAIN}_{resource_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ve_id)},
            name=ve_name,
            manufacturer="Hildebrand",
            model="DCC Smart Meter",
            entry_type=None,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> float | None:
        """Return the current sensor value."""
        return self.coordinator.data.usage.get(self._resource_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes with resource metadata."""
        resource = self.coordinator.data.resources.get(self._resource_id, {})
        return {
            "resource_id": self._resource_id,
            "classifier": resource.get("classifier"),
            "base_unit": resource.get("baseUnit"),
            "virtual_entity": resource.get("ve_name"),
        }
