"""NIBE (Fighter F1120/F1220/F1130/F1230 with RCU) adjustments to the H66 map.

The library only knows the Husdata variable IDs of a Rego 600. A NIBE behind
an H66 uses partly the same IDs (temperatures, pumps, compressor) and partly
other ones (currents, degree minutes, a second heating circuit, ...). Those
other IDs are given a key, a scale and limits here, so they get proper
entities instead of generic sensors.

Limits come from NIBE's "RCU Parameterlista F1230-F1130-F1120-F1220".
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from husdata_h66 import Register, VariableKind

_CONTROLLER = re.compile(r"nibe|fighter|f1[12][23]0", re.IGNORECASE)

# Variable IDs a Rego 600 doesn't have, but a NIBE does. Seeing one of them
# means NIBE even when the controller name on the H66 page says nothing.
_SIGNATURE = frozenset({"2201", "0212", "4101", "2A20", "8105"})

# variable ID -> fields of ``Register`` to replace.
_OVERRIDES: dict[str, dict[str, Any]] = {
    # Limits below are the ones the H60/H66 page shows ("Setting between").
    "0203": {"minimum": 13, "maximum": 29},
    # The page shows "3.00" for the room sensor influence (0-3), so 0.1.
    "2204": {"scale": 0.1, "minimum": 0, "maximum": 3},
    # Operating mode: 0 summer, 1 spring/autumn, 2 winter, 3 auto (Husdata).
    "2201": {"key": "operating_mode"},
    # Heating circuit 1: NIBE's curve goes to 15 in whole steps (Rego: 10).
    "2205": {"maximum": 15, "step": 1},
    "2207": {
        "key": "heat_curve_parallel",
        "minimum": -10,
        "maximum": 10,
        "step": 1,
    },
    # Heating circuit 2.
    "2222": {"key": "heat_curve_2", "minimum": 0, "maximum": 15, "step": 1},
    "2224": {
        "key": "heat_curve_parallel_2",
        "minimum": -10,
        "maximum": 10,
        "step": 1,
    },
    "0020": {"key": "radiator_forward_2"},
    "0D01": {"key": "radiator_return_2"},
    # Hot water: NIBE has an absolute start temperature, not a difference.
    "0208": {"minimum": 35, "maximum": 60, "step": 1},
    "0212": {
        "key": "hot_water_start_temperature",
        "minimum": 25,
        "maximum": 55,
        "step": 1,
    },
    # Refrigerant circuit and pool.
    "000C": {"key": "suction_gas"},
    "000D": {"key": "liquid_line"},
    "0011": {"key": "pool_temperature"},
    # Phase currents, 0.1 A.
    "4101": {"key": "current_l1", "scale": 0.1, "unit": "A"},
    "4102": {"key": "current_l2", "scale": 0.1, "unit": "A"},
    "4103": {"key": "current_l3", "scale": 0.1, "unit": "A"},
    # Degree minutes can be negative. Scale unverified: NIBE's own list has
    # factor 1, range -800..100.
    "8105": {"key": "degree_minutes", "kind": VariableKind.NUMBER, "scale": 1},
    # Alarm: a code that is 0 when there is none, so a status is enough.
    "2A20": {"key": "alarm", "kind": VariableKind.STATUS, "scale": 1},
    # Counters.
    "BC61": {"key": "compressor_starts"},
    "6C60": {"key": "compressor_hours"},
    "6C63": {"key": "aux_heater_hours"},
    "6C64": {"key": "hot_water_hours"},
}


# Sensors a NIBE F11xx/F12xx doesn't have (no tank top sensor, no pool).
NIBE_HIDDEN = frozenset({"hot_water_top", "pool_temperature"})


def is_nibe(registers: list[Register], controller: str | None) -> bool:
    """Whether the gateway sits on a NIBE."""
    if controller and _CONTROLLER.search(controller):
        return True
    return any(r.variable_id in _SIGNATURE for r in registers)


# Custom registers added on the H60 (Home > Add custom register), by register
# code. The ID the H60 gives them depends on the order they were added, so the
# code is what identifies them.
_CUSTOM_OVERRIDES: dict[str, dict[str, Any]] = {
    # Calculated flow temperature of heating circuit 2 (floor heating setpoint).
    "0215": {"key": "heating_setpoint_2"},
    # Extra hot water (read only on an H60).
    "0137": {"key": "extra_hot_water_mode"},
}


def apply_nibe(
    registers: list[Register],
    controller: str | None,
    custom_codes: dict[int, str] | None = None,
) -> list[Register]:
    """Give a NIBE's registers their keys, scales and limits; others unchanged.

    ``custom_codes`` maps a Modbus address to the register code of a custom
    register, as read from the H60 home page.
    """
    if not is_nibe(registers, controller):
        return registers
    codes = custom_codes or {}
    result = []
    for register in registers:
        fields = _OVERRIDES.get(register.variable_id)
        custom = _CUSTOM_OVERRIDES.get(codes.get(register.address, ""))
        if custom is not None:
            fields = custom
        result.append(replace(register, **fields) if fields else register)
    return result
