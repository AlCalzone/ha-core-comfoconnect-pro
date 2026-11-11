"""Tests for the Zehnder ComfoConnect PRO switch platform."""

from comfoconnect_pro_modbus.model import address
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
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

pytestmark = pytest.mark.parametrize("platforms", [[Platform.SWITCH]])

COMFOCOOL = "switch.comfoair_comfocool"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_switches(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every switch and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_turn_on_and_off(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Test the ComfoCool switch writes its coil."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    for service in (SERVICE_TURN_ON, SERVICE_TURN_OFF):
        await hass.services.async_call(
            SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: COMFOCOOL}, blocking=True
        )

    assert writes == [
        WriteEvent("coil", address(0x0009), [True], 0x05),
        WriteEvent("coil", address(0x0009), [False], 0x05),
    ]


@pytest.mark.usefixtures("init_integration")
async def test_comfocool_disabled_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test ComfoCool starts disabled, since the gateway cannot tell it is fitted."""
    entry = entity_registry.async_get(COMFOCOOL)

    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(COMFOCOOL) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_write_failure(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Test a refused write surfaces as an error."""
    mock_unit.fail_write(address(0x0009), ModbusTimeoutError(), register_type="coil")

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: COMFOCOOL},
            blocking=True,
        )

    assert exc_info.value.translation_key == "write_failed"
