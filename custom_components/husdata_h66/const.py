"""Constants for the Husdata H60/H66 integration."""

from __future__ import annotations

import logging
from typing import Final

# The domain stays "husdata_h66" so that existing config entries, devices and
# entity IDs keep working for people who installed the original integration.
DOMAIN: Final = "husdata_h66"
LOGGER = logging.getLogger(__package__)

MANUFACTURER: Final = "Husdata"
MODEL: Final = "H60/H66"

CONF_UNIT_ID: Final = "unit_id"
CONF_REGISTERS: Final = "registers"
CONF_FIRMWARE: Final = "firmware"
CONF_CONTROLLER: Final = "controller"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300
