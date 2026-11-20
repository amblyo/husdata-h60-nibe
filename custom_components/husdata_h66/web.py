"""Read the H66 home page: register map, firmware, controller and MAC address.

The H66 serves no identity or register list over Modbus, and its register
addresses can move after a firmware update or when custom registers are
added. Its home page lists all of that, so the integration reads it when a
gateway is added and every time the config entry is set up.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from husdata_h66 import (
    Register,
    make_register,
    parse_controller,
    parse_firmware_version,
    parse_registers,
)

from .nibe import apply_nibe

# The H60/H66 shows two IDs for some variables ("2D02 / 0136", the second one
# as an edit link); the first one is the one the register map uses.
_DUAL_ID = re.compile(
    r"(?:&nbsp;?|\s)*/(?:&nbsp;?|\s)*"
    r"(?:<a[^>]*>\s*)?(?:<span[^>]*>\s*)?[0-9A-Fa-f]{4}(?:\s*</span>)?(?:\s*</a>)?",
    re.I,
)
# Interface cable line on the H60 page, e.g. "NIBE Styr2002, Firmware: 502301".
_CABLE = re.compile(r"Interface cable\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>", re.I)


def _normalise(page: str) -> str:
    """Make the H60/H66 home page parseable.

    The H60 page never closes its table rows, and shows some IDs twice.
    """
    page = re.sub(r"<tr\b", "</tr><tr", page, flags=re.I)
    page = re.sub(r"</table>", "</tr></table>", page, flags=re.I)
    # Only touch the ID cell: a dual ID is followed by "</td>" directly.
    return re.sub(
        r"(<td[^>]*>\s*(?:&nbsp;?\s*)?(?:<a[^>]*>\s*<span[^>]*>\s*)?"
        r"[0-9A-Fa-f]{4}(?:\s*</span>\s*</a>)?)" + _DUAL_ID.pattern + r"(\s*</td>)",
        r"\1\2",
        page,
        flags=re.I,
    )


# A custom register row: "<ID> / <register>" followed by the Modbus address.
_CUSTOM_ROW = re.compile(
    r"[0-9A-Fa-f]{4}(?:&nbsp;?|\s)*/(?:&nbsp;?|\s)*"
    r"(?:<a[^>]*>\s*)?(?:<span[^>]*>\s*)?([0-9A-Fa-f]{4})(?:\s*</span>)?(?:\s*</a>)?"
    r"\s*</td>\s*<td[^>]*>\s*(\d+)",
    re.I,
)


def _custom_codes(page: str) -> dict[int, str]:
    """Return the Husdata register code of each custom register, by address.

    The ID the H60 gives a custom register depends on the order they were
    added, but the register code (``0215``) is what identifies it.
    """
    return {int(address): code.upper() for code, address in _CUSTOM_ROW.findall(page)}


_MAC = re.compile(r"Mac Address\s*</td>\s*<td[^>]*>\s*([0-9A-Fa-f:.-]{12,17})", re.I)
_TIMEOUT = aiohttp.ClientTimeout(total=10)


class H66WebError(Exception):
    """The H66 home page could not be read or parsed."""


@dataclass(frozen=True, slots=True)
class H66Info:
    """What the H66 home page tells about the gateway."""

    registers: list[Register]
    firmware: str | None
    controller: str | None
    mac: str | None


def parse_mac(page: str) -> str | None:
    """Return the gateway's MAC address in Home Assistant's format, if present."""
    match = _MAC.search(page)
    return format_mac(match.group(1)) if match else None


def parse_info(page: str) -> H66Info:
    """Parse the H66 home page.

    Raises ``H66WebError`` if the page has no parameter table.
    """
    try:
        registers = parse_registers(_normalise(page))
    except ValueError as err:
        raise H66WebError(str(err)) from err
    cable = _CABLE.search(page)
    # "NIBE Styr2002, Firmware: 502301" -> "NIBE Styr2002"
    controller = parse_controller(page) or (
        cable.group(1).split(",")[0].strip() if cable else None
    )
    return H66Info(
        registers=apply_nibe(registers, controller, _custom_codes(page)),
        firmware=parse_firmware_version(page),
        controller=controller,
        mac=parse_mac(page),
    )


async def async_fetch_info(hass: HomeAssistant, host: str) -> H66Info:
    """Fetch and parse the H66 home page.

    Raises ``H66WebError`` if the page cannot be read or has no parameter table.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(f"http://{host}/", timeout=_TIMEOUT) as response:
            response.raise_for_status()
            raw = await response.read()
        # The H60 sends Swedish names (ä, ö) as ISO-8859-1 without saying so.
        try:
            page = raw.decode("utf-8")
        except UnicodeDecodeError:
            page = raw.decode("latin-1")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise H66WebError(f"cannot read http://{host}/: {err}") from err
    return parse_info(page)


def registers_to_data(registers: list[Register]) -> list[list[Any]]:
    """Serialise a register map for a config entry."""
    return [[r.variable_id, r.address, r.name, r.writable] for r in registers]


def registers_from_data(
    data: list[list[Any]], controller: str | None = None
) -> list[Register]:
    """Rebuild a register map stored by ``registers_to_data``."""
    return apply_nibe(
        [
            make_register(variable_id, address, name, writable=writable)
            for variable_id, address, name, writable in data
        ],
        controller,
    )
