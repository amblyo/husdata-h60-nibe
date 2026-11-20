"""Selects for the Husdata H66 settings that take a fixed set of values."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import H66ConfigEntry, H66Coordinator
from .entity import H66Entity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class H66SelectEntityDescription(SelectEntityDescription):
    """A setting with named values."""

    values: dict[str, int]
    """Option name -> register value."""


SELECTS: tuple[H66SelectEntityDescription, ...] = (
    H66SelectEntityDescription(
        key="electric_heater_max_power",
        translation_key="electric_heater_max_power",
        entity_category=EntityCategory.CONFIG,
        # The H66 calls them steps 1, 2 and 4.
        values={"3_kw": 1, "6_kw": 2, "9_kw": 4},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        H66Select(coordinator, d)
        for d in SELECTS
        if d.key in coordinator.registers and coordinator.registers[d.key].writable
    )


class H66Select(H66Entity, SelectEntity):
    """A setting with named values."""

    entity_description: H66SelectEntityDescription

    def __init__(
        self, coordinator: H66Coordinator, description: H66SelectEntityDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, description)
        self._attr_options = list(description.values)

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        value = self.value
        for option, raw in self.entity_description.values.items():
            if raw == value:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the setting."""
        await self.coordinator.async_set(
            self.entity_description.key, self.entity_description.values[option]
        )
