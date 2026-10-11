"""Tests for the Zehnder ComfoConnect PRO integration."""

from comfoconnect_pro_modbus.model import address
from modbus_connection.mock import MockModbusUnit

from homeassistant.components.comfoconnect_pro.const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_UNIT_ID,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE

MOCK_TCP_INPUT = {
    CONF_HOST: "192.168.1.100",
    CONF_PORT: 502,
    CONF_UNIT_ID: 1,
}
MOCK_ENTRY_DATA = {CONF_TYPE: TYPE_TCP, **MOCK_TCP_INPUT}

MOCK_SERIAL_INPUT = {
    CONF_DEVICE: "/dev/ttyUSB0",
    CONF_BAUDRATE: "19200",
    CONF_PARITY: "even",
    CONF_UNIT_ID: 1,
}
MOCK_SERIAL_ENTRY_DATA = {
    CONF_TYPE: TYPE_SERIAL,
    **MOCK_SERIAL_INPUT,
    CONF_BAUDRATE: 19200,
}

# Keys are the manual's addresses; ``seed`` shifts them to protocol addresses.
DISCRETE = {0x0001: True, 0x0002: False, 0x0003: False, 0x0004: False}
INPUT = {
    0x0001: 0,  # connected
    0x0002: 79,  # filter warning
    0x0007: 175,
    0x0008: 215,
    0x0009: 218,
    0x000A: 52,
    0x000B: -35 & 0xFFFF,
    0x000C: 192,
    0x000D: 48,
    0x000E: 47,
    0x000F: 81,
    0x0010: 90,
    0x0011: 33,
    0x0012: 640,  # CO₂ zone 1
    0x0014: 812,  # CO₂ zone 3
    0x001A: 23,
}
HOLDING = {0x0001: 2, 0x0002: 0, 0x0003: 0, 0x0004: 220, 0x0005: 1800}
COIL = {0x0006: True, 0x0007: False, 0x0008: False, 0x0009: True}


def seed(
    unit: MockModbusUnit,
    *,
    discrete: dict[int, bool] | None = None,
    input_registers: dict[int, int] | None = None,
    holding: dict[int, int] | None = None,
    coil: dict[int, bool] | None = None,
) -> None:
    """Load values, given by the manual's addresses, into the mock."""
    for number, bit in (discrete or {}).items():
        unit.discrete[address(number)] = bit
    for number, word in (input_registers or {}).items():
        unit.input[address(number)] = word
    for number, word in (holding or {}).items():
        unit.holding[address(number)] = word
    for number, bit in (coil or {}).items():
        unit.coil[address(number)] = bit


def seed_gateway(unit: MockModbusUnit) -> None:
    """Seed a gateway reaching a ComfoAir Q with two CO₂ sensors."""
    seed(unit, discrete=DISCRETE, input_registers=INPUT, holding=HOLDING, coil=COIL)
