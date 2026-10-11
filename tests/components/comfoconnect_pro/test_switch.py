"""Tests for the Zehnder ComfoConnect PRO switch platform."""

from comfoconnect_pro_modbus.model import address
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

pytestmark = pytest.mark.parametrize("platforms", [[Platform.SWITCH]])


async def test_switches(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every switch and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("entity_id", "coil"),
    [
        pytest.param("switch.comfoair_boost", 0x0007, id="boost"),
        pytest.param("switch.comfoair_away", 0x0008, id="away"),
        pytest.param("switch.comfoair_comfocool", 0x0009, id="comfocool"),
    ],
)
async def test_turn_on_and_off(
    hass: HomeAssistant, mock_unit: MockModbusUnit, entity_id: str, coil: int
) -> None:
    """Test each switch writes its coil and the state follows."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    for service in (SERVICE_TURN_ON, SERVICE_TURN_OFF):
        await hass.services.async_call(
            SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    assert writes == [
        WriteEvent("coil", address(coil), [True], 0x05),
        WriteEvent("coil", address(coil), [False], 0x05),
    ]


@pytest.mark.usefixtures("init_integration")
async def test_write_failure(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Test a refused write surfaces as an error."""
    mock_unit.fail_write(address(0x0007), ModbusTimeoutError(), register_type="coil")

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.comfoair_boost"},
            blocking=True,
        )

    assert exc_info.value.translation_key == "write_failed"
