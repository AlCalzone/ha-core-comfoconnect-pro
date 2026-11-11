"""Tests for the Zehnder ComfoConnect PRO diagnostics."""

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.parametrize("platforms", [[]])


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test diagnostics hold the raw registers and redact the host."""
    assert (
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
        == snapshot
    )


async def test_diagnostics_read_error(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test diagnostics name a failed raw read instead of failing."""
    mock_unit.fail_requests(ModbusTimeoutError())

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert result["read_error"] == "ModbusTimeoutError"
    assert result["raw"] is None
