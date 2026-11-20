"""The Husdata H66 integration."""

from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType
from husdata_h66 import REGO600_REGISTERS, HusdataH66, Register
from modbus_connection import ModbusTcpParams

from .const import (
    CONF_CONTROLLER,
    CONF_FIRMWARE,
    CONF_REGISTERS,
    CONF_UNIT_ID,
    DOMAIN,
    LOGGER,
)
from .coordinator import H66ConfigEntry, H66Coordinator
from .web import H66WebError, async_fetch_info, registers_from_data, registers_to_data

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Entities replaced by another platform: (old platform, register key).
_REPLACED_ENTITIES = (("number", "electric_heater_max_power"),)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    return True


@callback
def _async_remove_replaced_entities(hass: HomeAssistant, entry: H66ConfigEntry) -> None:
    """Drop entities that moved to another platform, so they don't linger."""
    registry = er.async_get(hass)
    device_key = entry.unique_id or entry.entry_id
    for platform, key in _REPLACED_ENTITIES:
        entity_id = registry.async_get_entity_id(
            platform, DOMAIN, f"{device_key}_{key}"
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


async def _async_register_map(
    hass: HomeAssistant, entry: H66ConfigEntry
) -> tuple[list[Register], str | None, str | None, str | None]:
    """Read the register map from the H66, falling back to the stored one.

    The addresses can move after an H66 firmware update, so the map stored
    when the gateway was added is only used when the web page can't be read.
    A changed map is saved to the entry.
    """
    try:
        info = await async_fetch_info(hass, entry.data[CONF_HOST])
    except H66WebError as err:
        LOGGER.warning(
            "Using the stored register map, since the H66 web page could not be read: %s",
            err,
        )
        stored = entry.data.get(CONF_REGISTERS)
        registers = (
            registers_from_data(stored, entry.data.get(CONF_CONTROLLER))
            if stored
            else list(REGO600_REGISTERS)
        )
        return (
            registers,
            entry.data.get(CONF_FIRMWARE),
            entry.data.get(CONF_CONTROLLER),
            None,
        )

    data = {
        **entry.data,
        CONF_REGISTERS: registers_to_data(info.registers),
        CONF_FIRMWARE: info.firmware,
        CONF_CONTROLLER: info.controller,
    }
    if data != entry.data:
        if entry.data.get(CONF_REGISTERS) not in (None, data[CONF_REGISTERS]):
            LOGGER.info("The H66 register map has changed; using the new one")
        hass.config_entries.async_update_entry(entry, data=data)
    return info.registers, info.firmware, info.controller, info.mac


async def async_setup_entry(hass: HomeAssistant, entry: H66ConfigEntry) -> bool:
    """Set up an H66 gateway from a config entry."""
    registers, firmware, controller, mac = await _async_register_map(hass, entry)
    try:
        unit = async_get_unit(
            hass,
            entry,
            ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]),
            entry.data[CONF_UNIT_ID],
        )
    except HomeAssistantError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="connection_in_use",
            translation_placeholders={"error": str(err)},
        ) from err

    coordinator = H66Coordinator(
        hass,
        entry,
        HusdataH66(unit, registers),
        firmware=firmware,
        controller=controller,
        mac=mac,
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_remove_replaced_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: H66ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
