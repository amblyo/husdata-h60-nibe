"""Switches for the Husdata H66 on/off settings."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import H66ConfigEntry, H66Coordinator
from .entity import H66Entity

PARALLEL_UPDATES = 1

SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="electric_heater_allowed",
        translation_key="electric_heater_allowed",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="external_control",
        translation_key="external_control",
        entity_category=EntityCategory.CONFIG,
        # Husdata warns it can behave unpredictably on a Rego 600.
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    entities: list[H66Switch] = []
    for description in SWITCHES:
        register = coordinator.registers.get(description.key)
        if register is None or not register.writable:
            continue
        cls = H66WriteOnlySwitch if register.write_only else H66Switch
        entities.append(cls(coordinator, description))
    async_add_entities(entities)


class H66Switch(H66Entity, SwitchEntity):
    """An on/off H66 setting."""

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self.coordinator.async_set(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self.coordinator.async_set(self.entity_description.key, False)


class H66WriteOnlySwitch(H66Switch, RestoreEntity):
    """An on/off setting the H66 can't read back; shows what was last set."""

    _attr_assumed_state = True

    def __init__(
        self, coordinator: H66Coordinator, description: SwitchEntityDescription
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, description)
        self._last_set: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last set state."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in (STATE_ON, STATE_OFF):
            self._last_set = state.state == STATE_ON

    @property
    def is_on(self) -> bool | None:
        """Return the last set state."""
        return self._last_set

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await super().async_turn_on(**kwargs)
        self._last_set = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await super().async_turn_off(**kwargs)
        self._last_set = False
        self.async_write_ha_state()
