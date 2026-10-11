"""Tests for the Zehnder ComfoConnect PRO fan platform."""

from datetime import timedelta

from comfoconnect_pro_modbus.model import address
from freezegun.api import FrozenDateTimeFactory
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.comfoconnect_pro.const import SCAN_INTERVAL
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import COIL, seed

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

pytestmark = pytest.mark.parametrize("platforms", [[Platform.FAN]])

FAN = "fan.comfoair"


async def test_fan(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the fan and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_set_percentage_leaves_auto_mode(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a speed writes its preset and turns auto mode off."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
        blocking=True,
    )

    assert writes == [
        WriteEvent("holding", address(0x0001), [3], 0x06),
        WriteEvent("coil", address(0x0006), [False], 0x05),
    ]


@pytest.mark.usefixtures("init_integration")
async def test_set_percentage_in_manual_mode(
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    """Test a speed in manual mode writes only its preset."""
    seed(mock_unit, coil={**COIL, 0x0006: False})
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] is None
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 25},
        blocking=True,
    )

    assert writes == [WriteEvent("holding", address(0x0001), [0], 0x06)]
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 25


@pytest.mark.usefixtures("init_integration")
async def test_set_percentage_zero_is_refused(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test the fan refuses to turn off."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_SET_PERCENTAGE,
            {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 0},
            blocking=True,
        )

    assert exc_info.value.translation_key == "cannot_turn_off"
    assert writes == []


@pytest.mark.usefixtures("init_integration")
async def test_set_preset_auto(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Test the auto preset turns auto mode on."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "auto"},
        blocking=True,
    )

    assert writes == [WriteEvent("coil", address(0x0006), [True], 0x05)]
