"""Binary sensors for the Husdata H66."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import H66ConfigEntry
from .entity import H66Entity

PARALLEL_UPDATES = 0


def _running(key: str) -> BinarySensorEntityDescription:
    return BinarySensorEntityDescription(
        key=key, translation_key=key, device_class=BinarySensorDeviceClass.RUNNING
    )


BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    _running("compressor"),
    _running("add_heat_step_1"),
    _running("add_heat_step_2"),
    _running("pump_cold_circuit"),
    _running("pump_heat_circuit"),
    _running("pump_radiator"),
    # The switch valve: off when heating the radiators, on when making hot water.
    _running("switch_valve_1"),
    BinarySensorEntityDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        H66BinarySensor(coordinator, d)
        for d in BINARY_SENSORS
        if d.key in coordinator.registers
    )


class H66BinarySensor(H66Entity, BinarySensorEntity):
    """An H66 status variable."""

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        value = self.value
        return None if value is None else bool(value)
