"""Tests for the ComfoConnect PRO on core's shared Modbus connections."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

from modbus_connection.mock import MockModbusConnection
import pytest

from homeassistant.components.comfoconnect_pro.config_flow import (
    STEP_RECONFIGURE_SERIAL,
)
from homeassistant.components.comfoconnect_pro.const import (
    CONF_BAUDRATE,
    CONF_UNIT_ID,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from . import MOCK_SERIAL_ENTRY_DATA, MOCK_SERIAL_INPUT, seed_gateway

from tests.common import MockConfigEntry


@pytest.fixture
def bus() -> MockModbusConnection:
    """One RS-485 bus with gateways on unit IDs 1 and 2."""
    connection = MockModbusConnection()
    seed_gateway(connection.for_unit(1))
    seed_gateway(connection.for_unit(2))
    return connection


@pytest.fixture
def connection_class(bus: MockModbusConnection) -> Generator[MagicMock]:
    """Stand in for the backend core's modbus helper opens connections with."""
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        return_value=bus,
    ) as connection_class:
        yield connection_class


async def _set_up_both(hass: HomeAssistant) -> tuple[MockConfigEntry, MockConfigEntry]:
    """Set up the gateways on unit IDs 1 and 2 of the same serial port."""
    first = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    second = MockConfigEntry(
        domain=DOMAIN, data={**MOCK_SERIAL_ENTRY_DATA, CONF_UNIT_ID: 2}
    )
    for entry in (first, second):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return first, second


async def test_two_gateways_share_one_serial_connection(
    hass: HomeAssistant, connection_class: MagicMock
) -> None:
    """Test two units on one bus load over a single connection."""
    first, second = await _set_up_both(hass)

    assert first.state is ConfigEntryState.LOADED
    assert second.state is ConfigEntryState.LOADED
    connection_class.assert_called_once()


@pytest.mark.usefixtures("connection_class")
async def test_relink_refused_while_another_entry_holds_the_port(
    hass: HomeAssistant,
) -> None:
    """Test new line settings fail while another entry holds the port.

    The entry is set back up on its old settings afterwards.
    """
    first, second = await _set_up_both(hass)

    result = await first.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": STEP_RECONFIGURE_SERIAL}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"}
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert "different link settings" in result["description_placeholders"]["error"]
    assert first.data == MOCK_SERIAL_ENTRY_DATA
    assert first.state is ConfigEntryState.LOADED
    assert second.state is ConfigEntryState.LOADED
