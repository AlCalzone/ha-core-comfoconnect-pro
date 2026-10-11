"""Tests for the Zehnder ComfoConnect PRO integration setup."""

from datetime import timedelta
from unittest.mock import MagicMock

from comfoconnect_pro_modbus.model import address
from freezegun.api import FrozenDateTimeFactory
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusSerialParams,
    ModbusTcpParams,
)
from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.comfoconnect_pro.const import DOMAIN, SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import INPUT, MOCK_SERIAL_ENTRY_DATA, seed

from tests.common import MockConfigEntry, async_fire_time_changed

_SCAN = timedelta(seconds=SCAN_INTERVAL)
AIRFLOW = "sensor.comfoair_airflow"


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Run the next poll."""
    freezer.tick(_SCAN)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Test the entry sets up over a unit from modbus and unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    mock_get_unit.assert_called_once_with(
        hass,
        init_integration,
        ModbusTcpParams(host="192.168.1.100", port=502),
        1,
    )

    await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize("platforms", [[]])
async def test_setup_over_serial(
    hass: HomeAssistant,
    mock_get_unit: MagicMock,
    platforms: list[Platform],
) -> None:
    """Test a serial entry asks for the line settings it stored."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.LOADED
    mock_get_unit.assert_called_once_with(
        hass,
        entry,
        ModbusSerialParams(
            device="/dev/ttyUSB0", baudrate=19200, parity="E", stopbits=1
        ),
        1,
    )


async def test_device_info(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the gateway lands in the device registry."""
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, init_integration.entry_id), init_integration.entry_id
    )
    assert device == snapshot


@pytest.mark.usefixtures("mock_get_unit")
async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test an unreachable gateway retries setup."""
    mock_unit.fail_requests(ModbusConnectionError())
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("mock_get_unit")
async def test_setup_retries_without_ventilation_unit(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a gateway that lost its ventilation unit retries setup."""
    seed(mock_unit, input_registers={0x0001: 50})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.reason == (
        "The ComfoConnect PRO does not reach a supported ventilation unit "
        "(connection state 50)"
    )


@pytest.mark.parametrize("platforms", [[Platform.SENSOR]])
async def test_failed_component_goes_unavailable(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test only the entities of a refused block go unavailable."""
    mock_unit.fail_read(
        address(0x0007), IllegalDataAddressError(), register_type="input"
    )
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.comfoair_active_error_1").state == (
        "filter_warning_flag"
    )

    mock_unit.fail_read(address(0x0007), None, register_type="input")
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == "175"


@pytest.mark.parametrize("platforms", [[Platform.SENSOR]])
async def test_dead_link_makes_everything_unavailable(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a dropped link marks the gateway unavailable until it answers."""
    mock_unit.fail_requests(ModbusConnectionError())
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == STATE_UNAVAILABLE

    mock_unit.fail_requests(None)
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == "175"


@pytest.mark.parametrize("platforms", [[Platform.SENSOR]])
async def test_every_component_failing_marks_the_poll_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a poll where no component answers fails as a whole."""
    error = IllegalDataAddressError()
    mock_unit.fail_read(address(0x0001), error, register_type="input")
    mock_unit.fail_read(address(0x0007), error, register_type="input")
    mock_unit.fail_read(address(0x0001), error, register_type="holding")
    await _tick(hass, freezer)

    assert not init_integration.runtime_data.coordinator.last_update_success
    assert hass.states.get(AIRFLOW).state == STATE_UNAVAILABLE


@pytest.mark.parametrize("platforms", [[Platform.SENSOR]])
async def test_lost_ventilation_unit_makes_everything_unavailable(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a gateway that loses its ventilation unit marks it unavailable."""
    seed(mock_unit, input_registers={0x0001: 7})
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == STATE_UNAVAILABLE

    seed(mock_unit, input_registers=INPUT)
    await _tick(hass, freezer)

    assert hass.states.get(AIRFLOW).state == "175"
