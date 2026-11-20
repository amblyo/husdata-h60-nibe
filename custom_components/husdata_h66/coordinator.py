"""Data update coordinator for the Husdata H66."""

from __future__ import annotations

from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from husdata_h66 import HusdataH66, Register
from modbus_connection import ModbusError

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER

type H66ConfigEntry = ConfigEntry[H66Coordinator]

# The H66 applies a write only after a while (seen with the room setpoint: up
# to ~25 s before its web page and Modbus register show it), and it can drop a
# write that follows shortly after another one. So: read back after
# WRITE_SETTLE, keep showing the written value until a read matches it, and if
# that hasn't happened within WRITE_HOLD, write it once more; if the retry
# isn't confirmed within another WRITE_HOLD either, log it and show what the
# H66 reports.
WRITE_SETTLE = timedelta(seconds=10)
WRITE_HOLD = timedelta(seconds=60)


@dataclass(slots=True)
class PendingWrite:
    """A written value the H66 hasn't reported back yet."""

    value: Any
    deadline: datetime
    retried: bool = False


class H66Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all H66 registers; data is the values keyed by register key."""

    config_entry: H66ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: H66ConfigEntry,
        device: HusdataH66,
        *,
        firmware: str | None,
        controller: str | None,
        mac: str | None,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.device = device
        self.firmware = firmware
        self.controller = controller
        self.mac = mac
        self._pending_writes: dict[str, PendingWrite] = {}
        self._unsub_read_back: CALLBACK_TYPE | None = None

    @property
    def device_key(self) -> str:
        """Stable identifier of the gateway (the config entry unique id)."""
        return self.config_entry.unique_id or self.config_entry.entry_id

    @property
    def registers(self) -> dict[str, Register]:
        """The register map, keyed by register key."""
        return self.device.registers

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            report = await self.device.async_update()
        except ModbusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if not report.complete:
            error = "; ".join(str(err) for err in report.failed.values())
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": error},
            )
        return self._with_pending_writes(self.device.values, read=True)

    def _with_pending_writes(
        self, values: dict[str, Any], *, read: bool = False
    ) -> dict[str, Any]:
        """Keep recently written values until the H66 reports them.

        Until a read (``read=True``) returns the written value, the written
        value is shown instead of the H66's. When WRITE_HOLD runs out first,
        the value is written once more; when the retry runs out too, the
        H66's value wins and a warning is logged.
        """
        now = dt_util.utcnow()
        for key, pending in list(self._pending_writes.items()):
            if values.get(key) == pending.value:
                del self._pending_writes[key]
            elif not read or now < pending.deadline:
                values[key] = pending.value
            elif not pending.retried:
                LOGGER.warning(
                    "The H66 hasn't applied %s = %s within %s s (it reports %s); "
                    "writing it again",
                    key,
                    pending.value,
                    int(WRITE_HOLD.total_seconds()),
                    values.get(key),
                )
                pending.retried = True
                pending.deadline = now + WRITE_HOLD
                values[key] = pending.value
                self.config_entry.async_create_background_task(
                    self.hass,
                    self._async_retry_write(key, pending.value),
                    f"husdata_h66 retry {key}",
                )
            else:
                LOGGER.warning(
                    "The H66 didn't apply %s = %s, also after a retry; it reports %s",
                    key,
                    pending.value,
                    values.get(key),
                )
                del self._pending_writes[key]
        return values

    async def _async_retry_write(self, key: str, value: Any) -> None:
        """Write a value the H66 didn't apply once more."""
        try:
            await self.device.async_set(key, value)
        except (ModbusError, ValueError) as err:
            LOGGER.warning("Retrying %s = %s failed: %s", key, value, err)
            self._pending_writes.pop(key, None)
            return
        self._schedule_read_back()

    async def async_set(self, key: str, value: float | bool) -> None:
        """Write a setting, show it at once, and read it back a bit later."""
        await self._async_write(self.device.async_set(key, value))
        if self.registers[key].write_only:
            # Nothing to confirm: the H66 can't read the value back.
            return
        self._pending_writes[key] = PendingWrite(value, dt_util.utcnow() + WRITE_HOLD)
        if self.data is not None:
            self.async_set_updated_data(self._with_pending_writes(dict(self.data)))

    async def async_reset_alarm(self) -> None:
        """Reset an alarm: the heat pump turns off for 10 seconds."""
        await self._async_write(self.device.async_reset_alarm())

    async def _async_write(self, write: Coroutine[Any, Any, None]) -> None:
        """Run a write, translating errors, and schedule a read-back."""
        try:
            await write
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        self._schedule_read_back()

    @callback
    def _schedule_read_back(self) -> None:
        """Read everything once the H66 has had time to update its registers."""
        if self._unsub_read_back is not None:
            self._unsub_read_back()

        @callback
        def _read_back(_now: datetime) -> None:
            self._unsub_read_back = None
            self.config_entry.async_create_background_task(
                self.hass, self.async_refresh(), "husdata_h66 read-back"
            )

        self._unsub_read_back = async_call_later(self.hass, WRITE_SETTLE, _read_back)

    async def async_shutdown(self) -> None:
        """Cancel a pending read-back."""
        if self._unsub_read_back is not None:
            self._unsub_read_back()
            self._unsub_read_back = None
        await super().async_shutdown()
