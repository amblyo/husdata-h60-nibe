"""Diagnostics for the Husdata H66."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_REGISTERS
from .coordinator import H66ConfigEntry

TO_REDACT = {CONF_HOST, "mac", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: H66ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = {k: v for k, v in entry.data.items() if k != CONF_REGISTERS}
    return {
        "entry": async_redact_data(
            {"data": data, "options": dict(entry.options)}, TO_REDACT
        ),
        "firmware": coordinator.firmware,
        "controller": coordinator.controller,
        "registers": [
            {
                "address": r.address,
                "space": r.space,
                "variable_id": r.variable_id,
                "key": r.key,
                "name": r.name,
                "value": coordinator.data.get(r.key),
            }
            for r in coordinator.registers.values()
        ],
    }
