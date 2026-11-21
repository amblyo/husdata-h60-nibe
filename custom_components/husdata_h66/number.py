"""Number entities for the Husdata H66 settings."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import H66ConfigEntry, H66Coordinator
from .entity import H66Entity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class H66NumberEntityDescription(NumberEntityDescription):
    """A setting; min, max and step default to the register's own limits."""


def _temperature(key: str, **kwargs) -> H66NumberEntityDescription:
    return H66NumberEntityDescription(
        key=key,
        translation_key=key,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        **kwargs,
    )


NUMBERS: tuple[H66NumberEntityDescription, ...] = (
    H66NumberEntityDescription(
        key="heat_curve",
        translation_key="heat_curve",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    _temperature("heat_curve_parallel", entity_category=EntityCategory.CONFIG),
    _temperature("hot_water_stop_temperature", entity_category=EntityCategory.CONFIG),
    _temperature("hot_water_difference", entity_category=EntityCategory.CONFIG),
    H66NumberEntityDescription(
        key="heat_curve_2",
        translation_key="heat_curve_2",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    _temperature("heat_curve_parallel_2", entity_category=EntityCategory.CONFIG),
    _temperature(
        "hot_water_start_temperature", entity_category=EntityCategory.CONFIG
    ),
    H66NumberEntityDescription(
        key="extra_hot_water",
        translation_key="extra_hot_water",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        # The H66 changes it in whole hours.
        native_step=60,
        mode=NumberMode.BOX,
    ),
    _temperature("summer_mode", native_step=1),
    H66NumberEntityDescription(
        key="holiday_mode",
        translation_key="holiday_mode",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        native_step=1,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        H66Number(coordinator, d)
        for d in NUMBERS
        if d.key in coordinator.registers and coordinator.registers[d.key].writable
    )


class H66Number(H66Entity, NumberEntity):
    """A numeric H66 setting."""

    entity_description: H66NumberEntityDescription

    def __init__(
        self, coordinator: H66Coordinator, description: H66NumberEntityDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, description)
        register = self.register
        if register.minimum is not None:
            self._attr_native_min_value = register.minimum
        if register.maximum is not None:
            self._attr_native_max_value = register.maximum
        if description.native_step is None and register.step:
            self._attr_native_step = register.step

    @property
    def native_value(self) -> float | None:
        """Return the current setting."""
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        """Write the setting."""
        if self.register.step == 1:
            value = int(value)
        await self.coordinator.async_set(self.entity_description.key, value)
