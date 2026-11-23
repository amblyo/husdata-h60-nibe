"""Sensors for the Husdata H66."""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from husdata_h66 import ALARM_CODES, VariableKind

from .binary_sensor import BINARY_SENSORS
from .button import BUTTONS
from .const import DOMAIN
from .coordinator import H66ConfigEntry, H66Coordinator
from .entity import H66Entity
from .nibe import NIBE_HIDDEN, is_nibe
from .number import NUMBERS
from .select import SELECTS
from .switch import SWITCHES

PARALLEL_UPDATES = 0

# NIBE operating mode, as Husdata numbers it (variable 2201).
OPERATING_MODES: dict[int, str] = {
    0: "summer",
    1: "spring_autumn",
    2: "winter",
    3: "auto",
}

# NIBE extra hot water (menu 20): off, or on for 3, 6, 12 or 24 hours.
EXTRA_HOT_WATER: dict[int, str] = {
    0: "off",
    1: "3h",
    2: "6h",
    4: "12h",
    8: "24h",
}


def _temperature(key: str, **kwargs) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        **kwargs,
    )


def _hours(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


SENSORS: tuple[SensorEntityDescription, ...] = (
    _temperature("radiator_return"),
    _temperature("radiator_forward"),
    _temperature("heat_carrier_return"),
    _temperature("heat_carrier_forward"),
    _temperature("brine_in"),
    _temperature("brine_out"),
    _temperature("outdoor"),
    _temperature("indoor"),
    _temperature("hot_water_top"),
    _temperature("hot_water_mid"),
    _temperature("hot_gas"),
    _temperature("heating_setpoint"),
    _temperature("hot_water_setpoint"),
    _temperature("heating_setpoint_2"),
    _temperature("radiator_forward_2"),
    _temperature("radiator_return_2"),
    _temperature("suction_gas"),
    _temperature("liquid_line"),
    _temperature("pool_temperature", entity_registry_enabled_default=False),
    SensorEntityDescription(
        key="add_heat_status",
        translation_key="add_heat_status",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="alarm_code",
        translation_key="alarm_code",
        device_class=SensorDeviceClass.ENUM,
        options=[f"alarm_{code}" for code in ALARM_CODES],
        # The last alarm that triggered, not an active one ("Alarm" is that).
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _hours("compressor_hours_heating"),
    _hours("compressor_hours_hot_water"),
    _hours("aux_heater_hours_heating"),
    _hours("aux_heater_hours_hot_water"),
    SensorEntityDescription(
        key="power_consumption",
        translation_key="power_consumption",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="accumulated_consumption",
        translation_key="accumulated_consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        # Restarts at 0 when the H66 boots.
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    *(
        SensorEntityDescription(
            key=f"current_l{phase}",
            translation_key=f"current_l{phase}",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        )
        for phase in (1, 2, 3)
    ),
    SensorEntityDescription(
        key="heat_curve",
        translation_key="heat_curve",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="heat_curve_parallel",
        translation_key="heat_curve_parallel",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="heat_curve_2",
        translation_key="heat_curve_2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="heat_curve_parallel_2",
        translation_key="heat_curve_parallel_2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="hot_water_start_temperature",
        translation_key="hot_water_start_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="hot_water_stop_temperature",
        translation_key="hot_water_stop_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="degree_minutes",
        translation_key="degree_minutes",
        native_unit_of_measurement="GM",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="compressor_starts",
        translation_key="compressor_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="operating_mode",
        translation_key="operating_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(OPERATING_MODES.values()),
    ),
    SensorEntityDescription(
        key="extra_hot_water_mode",
        translation_key="extra_hot_water_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(EXTRA_HOT_WATER.values()),
    ),
    _hours("compressor_hours"),
    _hours("aux_heater_hours"),
    _hours("hot_water_hours"),
    SensorEntityDescription(
        key="room_sensor_influence",
        translation_key="room_sensor_influence",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

# Registers some other platform turns into an entity.
_OTHER_PLATFORMS = {
    d.key
    for group in (BINARY_SENSORS, BUTTONS, NUMBERS, SELECTS, SWITCHES)
    for d in group
}

# For registers this integration doesn't know, e.g. custom registers.
_GENERIC: dict[VariableKind, dict] = {
    VariableKind.TEMPERATURE: {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    VariableKind.PERCENT: {
        "native_unit_of_measurement": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    VariableKind.ENERGY: {
        "device_class": SensorDeviceClass.ENERGY,
        "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    VariableKind.HOURS: {
        "device_class": SensorDeviceClass.DURATION,
        "native_unit_of_measurement": UnitOfTime.HOURS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    VariableKind.MINUTES: {
        "device_class": SensorDeviceClass.DURATION,
        "native_unit_of_measurement": UnitOfTime.MINUTES,
    },
    VariableKind.POWER: {
        "device_class": SensorDeviceClass.POWER,
        "native_unit_of_measurement": UnitOfPower.WATT,
        "state_class": SensorStateClass.MEASUREMENT,
    },
}


def _generic_descriptions(coordinator: H66Coordinator) -> list[SensorEntityDescription]:
    known = {d.key for d in SENSORS} | _OTHER_PLATFORMS
    return [
        SensorEntityDescription(
            key=key, name=register.name, **_GENERIC.get(register.kind, {})
        )
        for key, register in coordinator.registers.items()
        if key not in known
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H66ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    descriptions = [d for d in SENSORS if d.key in coordinator.registers]
    if is_nibe(list(coordinator.registers.values()), coordinator.controller):
        # Drop the sensors a NIBE doesn't have, including any left over in the
        # entity registry from an earlier version.
        registry = er.async_get(hass)
        for key in NIBE_HIDDEN:
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{coordinator.device_key}_{key}"
            )
            if entity_id is not None:
                registry.async_remove(entity_id)
        descriptions = [d for d in descriptions if d.key not in NIBE_HIDDEN]
    descriptions += _generic_descriptions(coordinator)
    classes = {
        "alarm_code": H66LastAlarmSensor,
        "operating_mode": H66OperatingModeSensor,
        "extra_hot_water_mode": H66ExtraHotWaterSensor,
    }
    entities: list[SensorEntity] = [
        classes.get(d.key, H66Sensor)(coordinator, d) for d in descriptions
    ]
    entities.extend(
        H66DeltaSensor(coordinator, description, warm, cold)
        for description, warm, cold in DELTAS
        if warm in coordinator.registers and cold in coordinator.registers
    )
    if all(key in coordinator.registers for key in _PHASE_KEYS):
        entities.append(H66EstimatedPowerSensor(coordinator, ESTIMATED_POWER))
        entities.append(H66EstimatedEnergySensor(coordinator, ESTIMATED_ENERGY))
    async_add_entities(entities)


def _no_sensor(value: float | int | bool | None) -> bool:
    """A temperature the H66 reports for a sensor that isn't connected.

    The Rego 600 gives -48.3 °C (read as None by the library); a NIBE gives
    the raw value 0x8000 (-3276.8 °C) or 1000 °C, depending on the register.
    """
    return value is None or value <= -300 or value >= 900


class H66Sensor(H66Entity, SensorEntity):
    """A read-only H66 value."""

    entity_description: SensorEntityDescription

    def __init__(
        self, coordinator: H66Coordinator, description: SensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description)
        if (
            description.device_class is SensorDeviceClass.TEMPERATURE
            and _no_sensor(coordinator.data.get(description.key))
        ):
            # The H66 reports -48.3 °C for a sensor that isn't connected.
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | int | None:
        """Return the value."""
        value = self.value
        if isinstance(value, bool):
            return int(value)
        if (
            self.entity_description.device_class is SensorDeviceClass.TEMPERATURE
            and _no_sensor(value)
        ):
            return None
        return value


# Power estimated from the three phase currents (NIBE "Load L1-L3").
_PHASE_KEYS = ("current_l1", "current_l2", "current_l3")
# Phase to neutral voltage, and the power factor assumed for the heat pump
# (compressor motor, pumps and a resistive electric heater). The H66/H60 only
# gives currents, so this is an estimate; adjust _POWER_FACTOR if you compare
# it with a real energy meter.
_PHASE_VOLTAGE = 230
_POWER_FACTOR = 0.9

ESTIMATED_POWER = SensorEntityDescription(
    key="estimated_power",
    translation_key="estimated_power",
    device_class=SensorDeviceClass.POWER,
    native_unit_of_measurement=UnitOfPower.WATT,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)


# Temperature differences: (description, warm side, cold side).
DELTAS: tuple[tuple[SensorEntityDescription, str, str], ...] = (
    (
        SensorEntityDescription(
            key="brine_delta",
            translation_key="brine_delta",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        "brine_in",
        "brine_out",
    ),
    (
        SensorEntityDescription(
            key="heat_carrier_delta",
            translation_key="heat_carrier_delta",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        "heat_carrier_forward",
        "radiator_return",
    ),
)


class H66DeltaSensor(H66Entity, SensorEntity):
    """Difference between two temperature registers (warm minus cold side)."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: H66Coordinator,
        description: SensorEntityDescription,
        warm_key: str,
        cold_key: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description)
        self._warm_key = warm_key
        self._cold_key = cold_key

    @property
    def native_value(self) -> float | None:
        """Return warm minus cold in degrees, or None if either is missing."""
        warm = self.coordinator.data.get(self._warm_key)
        cold = self.coordinator.data.get(self._cold_key)
        if _no_sensor(warm) or _no_sensor(cold):
            return None
        return round(warm - cold, 1)


ESTIMATED_ENERGY = SensorEntityDescription(
    key="estimated_energy",
    translation_key="estimated_energy",
    device_class=SensorDeviceClass.ENERGY,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    state_class=SensorStateClass.TOTAL_INCREASING,
    suggested_display_precision=2,
)

# Longest gap between two polls that still counts towards the energy total.
_MAX_GAP_SECONDS = 600


class H66EstimatedPowerSensor(H66Entity, SensorEntity):
    """Electrical power, estimated from the three phase currents."""

    entity_description: SensorEntityDescription

    @property
    def native_value(self) -> int | None:
        """Return the estimated power in watts."""
        amps = [self.coordinator.data.get(key) for key in _PHASE_KEYS]
        if any(value is None for value in amps):
            return None
        return round(sum(amps) * _PHASE_VOLTAGE * _POWER_FACTOR)


class H66EstimatedEnergySensor(H66Entity, RestoreSensor):
    """Energy in kWh: the estimated power integrated over time (trapezoid)."""

    entity_description: SensorEntityDescription

    def __init__(
        self, coordinator: H66Coordinator, description: SensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description)
        self._total_kwh = 0.0
        self._last_power: float | None = None
        self._last_time = None

    async def async_added_to_hass(self) -> None:
        """Restore the total from before a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None and (
            last.native_value is not None
        ):
            try:
                self._total_kwh = float(last.native_value)
            except (TypeError, ValueError):
                self._total_kwh = 0.0

    def _power(self) -> float | None:
        amps = [self.coordinator.data.get(key) for key in _PHASE_KEYS]
        if any(value is None for value in amps):
            return None
        return sum(amps) * _PHASE_VOLTAGE * _POWER_FACTOR

    @callback
    def _handle_coordinator_update(self) -> None:
        power = self._power()
        now = dt_util.utcnow()
        if power is not None:
            if self._last_power is not None and self._last_time is not None:
                seconds = (now - self._last_time).total_seconds()
                if 0 < seconds <= _MAX_GAP_SECONDS:
                    average_w = (self._last_power + power) / 2
                    self._total_kwh += average_w * seconds / 3_600_000
            self._last_power = power
            self._last_time = now
        else:
            self._last_power = None
            self._last_time = None
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        """Return the accumulated energy in kWh."""
        return round(self._total_kwh, 4)


class H66OperatingModeSensor(H66Sensor):
    """The NIBE operating mode: summer, spring/autumn, winter or auto."""

    _states = OPERATING_MODES

    @property
    def native_value(self) -> str | None:
        """Return the mode, or None for a number Husdata doesn't list."""
        value = self.value
        if value is None:
            return None
        return self._states.get(round(value))

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        """Expose the raw value, in case the number isn't a known mode."""
        return {"raw": self.value}


class H66ExtraHotWaterSensor(H66OperatingModeSensor):
    """Extra hot water: off, or on for 3, 6, 12 or 24 hours."""

    _states = EXTRA_HOT_WATER


class H66LastAlarmSensor(H66Sensor):
    """The last alarm that triggered, even if no alarm is active now."""

    @property
    def native_value(self) -> str | None:
        """Return the alarm, or None for a code Husdata doesn't list."""
        code = self.value
        return f"alarm_{code}" if code in ALARM_CODES else None

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        """Expose the raw alarm code."""
        return {"code": self.value}
