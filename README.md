# Zehnder ComfoConnect PRO integration for Home Assistant core

The `comfoconnect_pro` integration for [Home Assistant core](https://github.com/home-assistant/core), staged here until it is submitted. It connects a Zehnder ComfoAir Q or Flex ventilation unit through the ComfoConnect PRO gateway, over Modbus TCP or Modbus RTU, using the device library [comfoconnect-pro-modbus](https://github.com/AlCalzone/comfoconnect-pro-modbus).

The layout mirrors core's, so the files copy straight across:

```text
homeassistant/components/comfoconnect_pro/   the integration
tests/components/comfoconnect_pro/           its tests and snapshots
docs/comfoconnect_pro.markdown               the page for home-assistant.io
```

## What it does

- A config flow with a menu for Modbus TCP (host, port, unit ID) or Modbus RTU (serial port, baud rate, parity, unit ID). It derives the stop bits from the parity, as the gateway does, and checks that the gateway reaches a ventilation unit before it creates the entry.
- One coordinator that polls the status, the measurements and the settings every 30 seconds.
- A fan with the four ventilation presets as speeds and the unit's auto mode as a preset.
- Sensors for airflow, five temperatures, five humidities, the filter life and the five alarm slots. CO₂ zone sensors are added once a zone reports a level.
- Binary sensors for the error, filter, standby and ComfoHood flags.
- Switches for boost, away and ComfoCool. Selects for the temperature profile and its mode. Numbers for the external setpoint and the boost duration. A button that resets the alarms.
- Diagnostics with the raw register dump. The host and serial port are redacted.

It takes its Modbus unit from core's `modbus` integration with `async_get_unit`, so it shares the connection with any other integration that talks to the same gateway or serial port.

The gateway has no serial number over Modbus. The config entry has no unique ID. Duplicates are refused by their link settings, and entities and the device are keyed by the config entry ID.

## Trying it in a core checkout

```bash
script/install-into-core.sh ../core
```

The script copies the integration and its tests into the checkout and adds it to `.strict-typing`. When the checkout has a `.venv`, it also regenerates the translations, `CODEOWNERS`, the generated config flow list, `mypy.ini` and `requirements_all.txt`.

Until `comfoconnect-pro-modbus` is on PyPI, install it from git into core's venv:

```bash
uv pip install --python ../core/.venv/bin/python "comfoconnect-pro-modbus @ git+https://github.com/AlCalzone/comfoconnect-pro-modbus@main"
```

Then run the tests from the core checkout:

```bash
.venv/bin/python -m pytest tests/components/comfoconnect_pro
```

CI does the same against core's `dev` branch on every push and once a week.

## Before submitting

- Publish `comfoconnect-pro-modbus` 0.1.0 to PyPI. The manifest pins it.
- Add the brand to [home-assistant/brands](https://github.com/home-assistant/brands). Core's `comfoconnect` integration is Zehnder too, so a `zehnder` brand that groups both fits. Until then hassfest fails the `brands` rule of the Bronze tier, which every new integration has to reach.
- Open the documentation pull request on home-assistant.io with `docs/comfoconnect_pro.markdown`.
- Test against a real gateway. The register map comes from the gateway's installation manual, document revision 140, and has only been tested against the mock. The fan's auto mode handling and the CO₂ zones in particular rest on readings of the manual that need checking.
