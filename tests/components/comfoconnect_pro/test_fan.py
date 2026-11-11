"""Tests for the Zehnder ComfoConnect PRO fan platform."""

from datetime import timedelta

from comfoconnect_pro_modbus.model import address
from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalDataValueError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import COIL, seed

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
    """Test a speed ends boost, away and auto mode, then writes its preset."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
        blocking=True,
    )

    assert writes == [
        WriteEvent("coil", address(0x0007), [False], 0x05),
        WriteEvent("coil", address(0x0008), [False], 0x05),
        WriteEvent("coil", address(0x0006), [False], 0x05),
        WriteEvent("holding", address(0x0001), [3], 0x06),
    ]


@pytest.mark.usefixtures("init_integration")
async def test_set_percentage_with_stale_auto_mode(
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    """Test a speed writes auto mode off even when the cache says it is off.

    The user may have turned auto mode on at the unit since the last poll.
    """
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
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 33},
        blocking=True,
    )

    assert writes == [
        WriteEvent("coil", address(0x0007), [False], 0x05),
        WriteEvent("coil", address(0x0008), [False], 0x05),
        WriteEvent("coil", address(0x0006), [False], 0x05),
        WriteEvent("holding", address(0x0001), [1], 0x06),
    ]
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 33


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


@pytest.mark.parametrize(
    ("preset_mode", "expected"),
    [
        pytest.param(
            "auto",
            [
                WriteEvent("coil", address(0x0007), [False], 0x05),
                WriteEvent("coil", address(0x0008), [False], 0x05),
                WriteEvent("coil", address(0x0006), [True], 0x05),
            ],
            id="auto",
        ),
        pytest.param(
            "away",
            [
                WriteEvent("coil", address(0x0007), [False], 0x05),
                WriteEvent("coil", address(0x0008), [True], 0x05),
            ],
            id="away",
        ),
        pytest.param(
            "boost",
            [
                WriteEvent("coil", address(0x0008), [False], 0x05),
                WriteEvent("holding", address(0x0005), [600], 0x06),
                WriteEvent("coil", address(0x0007), [True], 0x05),
            ],
            id="boost",
        ),
    ],
)
async def test_set_preset_mode(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    preset_mode: str,
    expected: list[WriteEvent],
) -> None:
    """Test each preset ends the others, leaving auto mode to auto alone.

    The boost writes its duration first, because the gateway keeps none.
    """
    init_integration.runtime_data.boost_duration = 600
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: preset_mode},
        blocking=True,
    )

    assert writes == expected


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("coil", "preset", "preset_mode", "percentage"),
    [
        pytest.param({0x0007: True}, 3, "boost", 100, id="boost"),
        pytest.param({0x0008: True}, 0, "away", None, id="away"),
        pytest.param({0x0006: True}, 2, "auto", 66, id="auto"),
        pytest.param({0x0006: False}, 1, None, 33, id="manual"),
    ],
)
async def test_state_follows_the_unit(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
    coil: dict[int, bool],
    preset: int,
    preset_mode: str | None,
    percentage: int | None,
) -> None:
    """Test boost and away show over auto mode, which stays on beneath them."""
    seed(mock_unit, coil={**COIL, **coil}, holding={0x0001: preset})
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] == preset_mode
    assert state.attributes[ATTR_PERCENTAGE] == percentage


@pytest.mark.usefixtures("init_integration")
async def test_half_applied_speed_change_refreshes(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test the state follows the unit when auto mode went off but the preset failed."""
    mock_unit.fail_write(address(0x0001), IllegalDataValueError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_SET_PERCENTAGE,
            {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
            blocking=True,
        )
    await hass.async_block_till_done()

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] is None
    assert state.attributes[ATTR_PERCENTAGE] == 66
