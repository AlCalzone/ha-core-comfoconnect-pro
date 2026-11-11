"""Diagnostics support for Zehnder ComfoConnect PRO gateways."""

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_DEVICE, CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import ComfoConnectProConfigEntry

TO_REDACT = {CONF_DEVICE, CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ComfoConnectProConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    device = entry.runtime_data.device
    status = device.status
    raw = read_error = None
    try:
        raw = await device.async_read_raw()
    except ModbusError as err:
        read_error = type(err).__name__

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "connection_state": (
            None if status.connection_state is None else status.connection_state.name
        ),
        "active_alarms": [
            code.name if hasattr(code, "name") else code
            for code in status.active_alarms
        ],
        "co2_zones": sorted(device.sensors.co2_zones),
        "last_update_failed": sorted(entry.runtime_data.coordinator.data.failed),
        "read_error": read_error,
        "raw": raw,
    }
