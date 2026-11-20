"""Base entity for the Husdata H66."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from husdata_h66 import Register

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import H66Coordinator


def device_info(coordinator: H66Coordinator) -> DeviceInfo:
    """Device info for the gateway and the heat pump behind it."""
    info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.device_key)},
        name=coordinator.config_entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL,
        sw_version=coordinator.firmware,
        configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}/",
    )
    if coordinator.controller:
        info["hw_version"] = coordinator.controller
    if coordinator.mac:
        info["connections"] = {(CONNECTION_NETWORK_MAC, coordinator.mac)}
    return info


class H66Entity(CoordinatorEntity[H66Coordinator]):
    """An entity backed by one H66 register."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: H66Coordinator, description: EntityDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_key}_{description.key}"
        self._attr_device_info = device_info(coordinator)

    @property
    def register(self) -> Register:
        """The register this entity reads."""
        return self.coordinator.registers[self.entity_description.key]

    @property
    def value(self) -> Any:
        """The register's value from the last poll."""
        return self.coordinator.data.get(self.entity_description.key)
