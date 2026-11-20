# Husdata H60/H66 for Home Assistant (NIBE edition)

A Home Assistant custom integration for the Modbus TCP interface of the Husdata **H60** and **H66** gateways. It is a fork of
[jonnybergdahl/HomeAssistant_Husdata_H66_Modbus_Integration](https://github.com/jonnybergdahl/HomeAssistant_Husdata_H66_Modbus_Integration),
adapted for a **NIBE Fighter** (Styr2002 interface) and for the H60 home page. The Rego 600 support of the original is kept.

Tested with: NIBE Fighter F1130 (two heating circuits: radiators and floor heating), Husdata H60 firmware 240222, NIBE Styr2002 interface firmware 502301.

## What is different from the original

- The H60 home page never closes its table rows and shows some variable IDs twice (`2D02 / 0136`). The page is normalised before it is parsed. Without this the register map could not be read, and the integration fell back to the Rego 600 map.
- A **NIBE map** (`nibe.py`): keys, scales and limits for the NIBE variable IDs, with the limits the H60 page reports. It is used when the controller name contains NIBE/Fighter, or when a NIBE-only variable ID is present. Rego 600 is untouched.
- New entities: phase currents, an **estimated power** sensor, degree minutes, compressor starts, operating hours, the second heating circuit (floor heating), the operating mode (Summer, Spring/Autumn, Winter, Auto) and the extra hot water state.
- A temperature the gateway reports for a missing sensor (`-3276.8` or `1000`) is shown as unknown.
- Entity names are grouped as **Radiators**, **Floor heating** and **Hot water**.
- The domain is still `husdata_h66`, so an existing setup, its devices and entity IDs keep working.

## Installation

1. Copy `custom_components/husdata_h66` into `/config/custom_components/` (or add this repository to HACS as a custom repository of type *Integration*).
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Husdata H66**, enter the IP address of the gateway (no `http://`). Keep port `502` and unit ID `1`.

Modbus TCP must be turned on in the gateway (**Config → Modbus**, `MODBUS_PORT` 502). The gateway accepts only one Modbus client at a time.

## Entities for a NIBE F1130 with H60

| Group | Entities |
|---|---|
| Radiators | Heat curve, parallel offset (both settable), return temperature |
| Floor heating | Heat curve, parallel offset (both settable), forward temperature, setpoint (custom register `0215`) |
| Hot water | Start and stop temperature (settable), hot water temperature, hot water production, operating hours |
| Room | Room setpoint (settable), indoor temperature, room sensor influence |
| Heat pump | Compressor, brine pump, heat carrier pump, radiator pump, additional heat steps, hot gas, suction gas, liquid line, brine in/out |
| Power | Phase currents L1–L3, **estimated power** (see below) |
| Other | Operating mode, degree minutes, alarm, compressor starts, compressor/additional heat hours |

### Estimated power

The gateway reports the phase currents only. The estimate is `(L1 + L2 + L3) × 230 V × 0.9`. The power factor `0.9` is an assumption (constant `_POWER_FACTOR` in `sensor.py`); compare with a real meter if you need accuracy. To get energy, create a *Integral sensor* helper (Riemann sum) from the estimated power.

## Custom registers (advanced, H60)

The H60 can read extra variables as *custom registers* (**Home → Add custom register**). Findings on a Styr2002:

- Format: `0` + number of bytes + the variable number in hex. The variable number is the **"Modbus reg." column** of NIBE's RCU parameter list (`Returtemperatur 1` is reg 17 → `0211`).
- 1 byte: `01xx`. 2 bytes (signed int, temperatures): `02xx`. Never `00xx` – it gives `XE05 Illegal bytelen, 0` in the H60 log.
- Custom registers are **read-only on an H60** (writing is H66 only).
- A value of `1000` (or `10000` for the Number type) means the pump gave no value.
- Add them one at a time and check the H60 log (`/log`) for `XE05`.
- Verified on an F1130: `0211` (return 1), `0215` (calculated flow temperature, circuit 2), `021C` (outdoor).
- Not available on the same unit: `021B` (return temperature 2) answers `1000`, although the display shows a value.

## Known limits

- *Compressor starts* is a 16-bit register and wraps at 65 536 (the H60 page shows the full number).
- Settings are written to the heat pump over Modbus. Change one setting at a time and check the NIBE display.
- *Operating mode* is read only. The H60 reports the selected mode (Auto = 3), not the season Auto currently uses.

## Credits and license

Based on the work of [Jonny Bergdahl](https://github.com/jonnybergdahl) (integration and the [husdata-h66-modbus](https://pypi.org/project/husdata-h66-modbus/) library). MIT license, see `LICENSE`.
