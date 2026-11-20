"""Buttons for the Husdata H66."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import H66ConfigEntry
from .entity import H66Entity

PARALLEL_UPDATES = 1

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="alarm_reset", translation_key="alarm_reset"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        H66Button(coordinator, d)
        for d in BUTTONS
        if d.key in coordinator.registers and coordinator.registers[d.key].writable
    )


class H66Button(H66Entity, ButtonEntity):
    """Resets a heat pump alarm; the heat pump turns off for 10 seconds."""

    async def async_press(self) -> None:
        """Reset the alarm."""
        await self.coordinator.async_reset_alarm()
