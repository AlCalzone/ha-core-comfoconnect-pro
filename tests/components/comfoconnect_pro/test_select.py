"""Tests for the Zehnder ComfoConnect PRO select platform."""

from comfoconnect_pro_modbus import address
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

pytestmark = pytest.mark.parametrize("platforms", [[Platform.SELECT]])


async def test_selects(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every select and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("entity_id", "option", "register", "value"),
    [
        pytest.param(
            "select.comfoair_temperature_profile", "warm", 0x0002, 2, id="profile"
        ),
        pytest.param(
            "select.comfoair_temperature_profile_mode",
            "external_setpoint",
            0x0003,
            2,
            id="mode",
        ),
    ],
)
async def test_select_option(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    entity_id: str,
    option: str,
    register: int,
    value: int,
) -> None:
    """Test choosing an option writes its register and the state follows."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )

    assert writes == [WriteEvent("holding", address(register), [value], 0x06)]
    assert hass.states.get(entity_id).state == option
