"""Tests for the Zehnder ComfoConnect PRO config flow."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, _patch, patch

from modbus_connection import (
    GatewayPathUnavailableError,
    ModbusSerialParams,
    ModbusTcpParams,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

from homeassistant import config_entries
from homeassistant.components.comfoconnect_pro.config_flow import (
    STEP_RECONFIGURE_SERIAL,
    STEP_RECONFIGURE_TCP,
)
from homeassistant.components.comfoconnect_pro.const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_UNIT_ID,
    DEFAULT_NAME,
    DOMAIN,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from . import (
    INPUT,
    MOCK_ENTRY_DATA,
    MOCK_SERIAL_ENTRY_DATA,
    MOCK_SERIAL_INPUT,
    MOCK_TCP_INPUT,
    seed,
    seed_gateway,
)

from tests.common import MockConfigEntry, get_schema_suggested_value


def _patch_temporary_unit(connection: MockModbusConnection) -> _patch[AsyncMock]:
    """Stand in for async_get_temporary_unit, handing out a unit on connection."""

    @asynccontextmanager
    async def _get_temporary_unit(
        hass: HomeAssistant,
        params: ModbusSerialParams | ModbusTcpParams,
        unit_id: int,
    ) -> AsyncIterator[MockModbusUnit]:
        yield connection.for_unit(unit_id)

    return patch(
        "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
        side_effect=_get_temporary_unit,
    )


class _RaisingTemporaryUnit:
    """Stand in for a temporary-unit context whose __aenter__ raises."""

    def __init__(self, error: Exception) -> None:
        """Initialize with the error to raise on entry."""
        self._error = error

    async def __aenter__(self) -> None:
        raise self._error

    async def __aexit__(self, *args: object) -> None:
        """No cleanup: entry never succeeded."""


def _gateway() -> MockModbusConnection:
    """A connection to a gateway that reaches its ventilation unit."""
    connection = MockModbusConnection()
    seed_gateway(connection.for_unit(1))
    return connection


async def _start_flow(hass: HomeAssistant, connection_type: str) -> str:
    """Open the flow, pick a connection type, and return the flow ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == [TYPE_TCP, TYPE_SERIAL]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": connection_type}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == connection_type
    assert result["errors"] == {}

    return result["flow_id"]


@pytest.mark.parametrize(
    ("connection_type", "user_input", "expected_params", "expected_data"),
    [
        pytest.param(
            TYPE_TCP,
            {**MOCK_TCP_INPUT, CONF_PORT: 1502},
            ModbusTcpParams(host="192.168.1.100", port=1502),
            {**MOCK_ENTRY_DATA, CONF_PORT: 1502},
            id="tcp",
        ),
        pytest.param(
            TYPE_SERIAL,
            MOCK_SERIAL_INPUT,
            ModbusSerialParams(
                device="/dev/ttyUSB0", baudrate=19200, parity="E", stopbits=1
            ),
            MOCK_SERIAL_ENTRY_DATA,
            id="serial_even",
        ),
        pytest.param(
            TYPE_SERIAL,
            {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "115200", CONF_PARITY: "none"},
            ModbusSerialParams(
                device="/dev/ttyUSB0", baudrate=115200, parity="N", stopbits=2
            ),
            {**MOCK_SERIAL_ENTRY_DATA, CONF_BAUDRATE: 115200, CONF_PARITY: "none"},
            id="serial_no_parity",
        ),
    ],
)
async def test_user_step_success(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    connection_type: str,
    user_input: dict[str, Any],
    expected_params: ModbusSerialParams | ModbusTcpParams,
    expected_data: dict[str, Any],
) -> None:
    """Test each connection type probes the gateway and creates an entry."""
    flow_id = await _start_flow(hass, connection_type)

    with _patch_temporary_unit(_gateway()) as mock_temporary_unit:
        result = await hass.config_entries.flow.async_configure(flow_id, user_input)

    mock_temporary_unit.assert_called_once_with(hass, expected_params, 1)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_NAME
    assert result["data"] == expected_data
    assert result["result"].unique_id is None
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "error",
    [ModbusTimeoutError("timed out"), HomeAssistantError("in use")],
)
async def test_user_step_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, error: Exception
) -> None:
    """Test an unreachable gateway shows the error, then recovers."""
    flow_id = await _start_flow(hass, TYPE_TCP)

    with patch(
        "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
        return_value=_RaisingTemporaryUnit(error),
    ):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"] == {"error": str(error)}
    assert (
        get_schema_suggested_value(result["data_schema"].schema, CONF_HOST)
        == (MOCK_TCP_INPUT[CONF_HOST])
    )

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(("code", "state"), [(50, "50"), (7, "7")])
async def test_user_step_no_ventilation_unit(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, code: int, state: str
) -> None:
    """Test a gateway without a ventilation unit shows its connection state."""
    connection = _gateway()
    seed(connection.for_unit(1), input_registers={**INPUT, 0x0001: code})
    flow_id = await _start_flow(hass, TYPE_TCP)

    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_ventilation_unit"}
    assert result["description_placeholders"] == {"state": state}

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("data", "connection_type", "user_input"),
    [
        (MOCK_ENTRY_DATA, TYPE_TCP, MOCK_TCP_INPUT),
        (
            MOCK_SERIAL_ENTRY_DATA,
            TYPE_SERIAL,
            {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"},
        ),
    ],
)
async def test_user_step_already_configured(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    data: dict[str, Any],
    connection_type: str,
    user_input: dict[str, Any],
) -> None:
    """Test a link an entry already uses is refused before any probe."""
    MockConfigEntry(domain=DOMAIN, data=data).add_to_hass(hass)
    flow_id = await _start_flow(hass, connection_type)

    with _patch_temporary_unit(_gateway()) as mock_temporary_unit:
        result = await hass.config_entries.flow.async_configure(flow_id, user_input)

    mock_temporary_unit.assert_not_called()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "user_input",
    [
        pytest.param({**MOCK_TCP_INPUT, CONF_UNIT_ID: 2}, id="other_unit_id"),
        pytest.param({**MOCK_TCP_INPUT, CONF_HOST: " 192.168.1.100 "}, id="spaces"),
    ],
)
async def test_user_step_same_tcp_gateway_is_a_duplicate(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, user_input: dict[str, Any]
) -> None:
    """Test the unit ID and the host's spelling don't make a new TCP gateway."""
    MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA).add_to_hass(hass)
    flow_id = await _start_flow(hass, TYPE_TCP)

    result = await hass.config_entries.flow.async_configure(flow_id, user_input)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_step_normalizes_the_host(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test the host is stored stripped and in lowercase."""
    flow_id = await _start_flow(hass, TYPE_TCP)

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {**MOCK_TCP_INPUT, CONF_HOST: " Gateway.LOCAL "}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "gateway.local"


async def test_user_step_serial_other_unit_id_is_new(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a second unit ID on the same RS-485 bus is a second gateway."""
    MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA).add_to_hass(hass)
    flow_id = await _start_flow(hass, TYPE_SERIAL)

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {**MOCK_SERIAL_INPUT, CONF_UNIT_ID: 2}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def _start_reconfigure(
    hass: HomeAssistant, entry: MockConfigEntry, step_id: str
) -> ConfigFlowResult:
    """Open the reconfigure flow, pick ``step_id`` from its menu, and check it."""
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [STEP_RECONFIGURE_TCP, STEP_RECONFIGURE_SERIAL]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step_id
    return result


async def test_reconfigure_from_tcp_to_serial(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test an entry can move from the network to RS-485 and keeps its ID."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_SERIAL)
    assert get_schema_suggested_value(result["data_schema"].schema, CONF_DEVICE) is None
    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], MOCK_SERIAL_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == MOCK_SERIAL_ENTRY_DATA


@pytest.mark.parametrize(
    ("other", "step_id", "user_input"),
    [
        pytest.param(MOCK_ENTRY_DATA, STEP_RECONFIGURE_TCP, MOCK_TCP_INPUT, id="tcp"),
        pytest.param(
            MOCK_SERIAL_ENTRY_DATA,
            STEP_RECONFIGURE_SERIAL,
            MOCK_SERIAL_INPUT,
            id="serial",
        ),
    ],
)
async def test_reconfigure_onto_another_entrys_link(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    other: dict[str, Any],
    step_id: str,
    user_input: dict[str, Any],
) -> None:
    """Test an entry cannot move onto a gateway another entry already uses."""
    MockConfigEntry(domain=DOMAIN, data=other).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, data={**MOCK_ENTRY_DATA, CONF_HOST: "192.168.1.200"}
    )
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry, step_id)
    with _patch_temporary_unit(_gateway()) as mock_temporary_unit:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    mock_temporary_unit.assert_not_called()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.168.1.200"


async def test_reconfigure_no_ventilation_unit(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a reconfigure onto a gateway without a unit shows the error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    entry.add_to_hass(hass)
    connection = _gateway()
    seed(connection.for_unit(1), input_registers={**INPUT, 0x0001: 50})

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_TCP)
    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_HOST: "192.168.1.101"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_ventilation_unit"}

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_HOST: "192.168.1.101"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_tcp(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a TCP entry can move to another host."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_TCP)
    assert get_schema_suggested_value(result["data_schema"].schema, CONF_HOST) == (
        "192.168.1.100"
    )
    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_HOST: "192.168.1.101"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {**MOCK_ENTRY_DATA, CONF_HOST: "192.168.1.101"}


async def test_reconfigure_serial(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a serial entry shows its baud rate as an option and can change it."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_SERIAL)
    assert (
        get_schema_suggested_value(result["data_schema"].schema, CONF_BAUDRATE)
        == "19200"
    )
    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "38400"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {**MOCK_SERIAL_ENTRY_DATA, CONF_BAUDRATE: 38400}


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a failed probe keeps the old data and shows the error."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_TCP)
    with patch(
        "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
        return_value=_RaisingTemporaryUnit(ModbusTimeoutError("timed out")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_HOST: "192.168.1.101"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data == MOCK_ENTRY_DATA

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_HOST: "192.168.1.101"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


@pytest.mark.usefixtures("mock_get_unit")
async def test_reconfigure_new_line_settings(
    hass: HomeAssistant, mock_connection: MockModbusConnection
) -> None:
    """Test new line settings take the entry off the port before probing."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    states: list[ConfigEntryState] = []

    @asynccontextmanager
    async def _probe_watching_the_entry(
        hass: HomeAssistant,
        params: ModbusSerialParams | ModbusTcpParams,
        unit_id: int,
    ) -> AsyncIterator[MockModbusUnit]:
        states.append(entry.state)
        yield mock_connection.for_unit(unit_id)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_SERIAL)
    with patch(
        "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
        side_effect=_probe_watching_the_entry,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"}
        )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert states == [ConfigEntryState.NOT_LOADED]
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_get_unit")
async def test_reconfigure_new_line_settings_failing(
    hass: HomeAssistant, mock_connection: MockModbusConnection
) -> None:
    """Test a failed probe on new line settings sets the entry back up."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_SERIAL)
    with patch(
        "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
        return_value=_RaisingTemporaryUnit(ModbusTimeoutError("timed out")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"}
        )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data == MOCK_SERIAL_ENTRY_DATA
    assert entry.state is ConfigEntryState.LOADED

    with _patch_temporary_unit(mock_connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"}
        )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_user_step_no_path_to_unit(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a gateway that refuses the state read for lack of a unit says so."""
    connection = _gateway()
    connection.for_unit(1).fail_read(
        0, GatewayPathUnavailableError(), register_type="input"
    )
    flow_id = await _start_flow(hass, TYPE_TCP)

    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_path_to_unit"}

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(flow_id, MOCK_TCP_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_step_keeps_an_ipv6_scope_id(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test only the address part of an IPv6 host is folded to lowercase."""
    flow_id = await _start_flow(hass, TYPE_TCP)

    with _patch_temporary_unit(_gateway()):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {**MOCK_TCP_INPUT, CONF_HOST: "FE80::1%Eth0"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "fe80::1%Eth0"


@pytest.mark.usefixtures("mock_get_unit")
async def test_reconfigure_unexpected_probe_error_sets_the_entry_back_up(
    hass: HomeAssistant,
) -> None:
    """Test an unexpected probe error on new line settings restores the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_SERIAL_ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    result = await _start_reconfigure(hass, entry, STEP_RECONFIGURE_SERIAL)
    with (
        patch(
            "homeassistant.components.comfoconnect_pro.config_flow.async_get_temporary_unit",
            return_value=_RaisingTemporaryUnit(RuntimeError("boom")),
        ),
        pytest.raises(RuntimeError),
    ):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_BAUDRATE: "9600"}
        )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.data == MOCK_SERIAL_ENTRY_DATA
    assert entry.state is ConfigEntryState.LOADED
