"""Config flow for the Husdata H66."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from husdata_h66 import REGO600_REGISTERS, HusdataH66, Register
from modbus_connection import ModbusError, ModbusTcpParams
import voluptuous as vol

from .const import (
    CONF_CONTROLLER,
    CONF_FIRMWARE,
    CONF_REGISTERS,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODEL,
)
from .coordinator import H66ConfigEntry
from .web import H66Info, H66WebError, async_fetch_info, registers_to_data

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            vol.Coerce(int),
        ),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, max=255)
            ),
            vol.Coerce(int),
        ),
    }
)


class CannotConnect(Exception):
    """The H66 did not answer over Modbus."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What a successful probe found."""

    unique_id: str
    title: str
    data: dict[str, Any]


async def _async_probe(hass: HomeAssistant, user_input: dict[str, Any]) -> ProbeResult:
    """Read the H66 web page and poll every register once.

    Raises ``CannotConnect`` if the H66 doesn't answer over Modbus.
    """
    host = user_input[CONF_HOST].strip()
    port = user_input[CONF_PORT]
    unit_id = user_input[CONF_UNIT_ID]

    info: H66Info | None
    try:
        info = await async_fetch_info(hass, host)
    except H66WebError as err:
        # Modbus works without it; the default map fits a Rego 600.
        LOGGER.debug("H66 web page not available, using the default map: %s", err)
        info = None
    registers: list[Register] = info.registers if info else list(REGO600_REGISTERS)

    try:
        async with async_get_temporary_unit(
            hass, ModbusTcpParams(host=host, port=port), unit_id
        ) as unit:
            report = await HusdataH66(unit, registers).async_update()
    except (ModbusError, HomeAssistantError) as err:
        raise CannotConnect(str(err)) from err
    if not report.complete:
        raise CannotConnect("; ".join(str(e) for e in report.failed.values()))

    controller = info.controller if info else None
    return ProbeResult(
        # Without the web page there is no MAC; the address is the best there is.
        unique_id=info.mac if info and info.mac else f"{host}:{port}:{unit_id}",
        title=f"{MODEL} {controller}" if controller else f"Husdata {MODEL}",
        data={
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_UNIT_ID: unit_id,
            CONF_REGISTERS: registers_to_data(registers),
            CONF_FIRMWARE: info.firmware if info else None,
            CONF_CONTROLLER: controller,
        },
    )


class H66ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Husdata H66."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: H66ConfigEntry) -> H66OptionsFlow:
        """Return the options flow."""
        return H66OptionsFlow()

    async def _async_try_probe(
        self, user_input: dict[str, Any], errors: dict[str, str], placeholders: dict
    ) -> ProbeResult | None:
        try:
            return await _async_probe(self.hass, user_input)
        except CannotConnect as err:
            errors["base"] = "cannot_connect"
            placeholders["error"] = str(err)
        except Exception:
            LOGGER.exception("Unexpected error probing %s", user_input[CONF_HOST])
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up an H66 by host name or IP address."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}
        if user_input is not None and (
            result := await self._async_try_probe(user_input, errors, placeholders)
        ):
            await self.async_set_unique_id(result.unique_id)
            self._abort_if_unique_id_configured(updates=result.data)
            return self.async_create_entry(title=result.title, data=result.data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, port or unit ID of an existing H66."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}
        if user_input is not None and (
            result := await self._async_try_probe(user_input, errors, placeholders)
        ):
            await self.async_set_unique_id(result.unique_id)
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(entry, data_updates=result.data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or entry.data
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class H66OptionsFlow(OptionsFlowWithReload):
    """Options: polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_SCAN_INTERVAL,
                                max=MAX_SCAN_INTERVAL,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="s",
                            )
                        )
                    }
                ),
                {
                    CONF_SCAN_INTERVAL: self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    )
                },
            ),
        )
