"""Tests for the Zehnder ComfoConnect PRO fan platform."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

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

from . import COIL, seed, wait_for_write_refresh

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
        # The unit moves the preset seconds after the coil turns on
        pytest.param({0x0007: True}, 2, "boost", 100, id="boost_starting"),
        pytest.param({0x0008: True}, 0, "away", None, id="away"),
        pytest.param({0x0008: True}, 2, "away", None, id="away_starting"),
        # and leaves it on away for seconds after the coil turns off
        pytest.param({0x0006: True}, 0, "auto", None, id="away_ending"),
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
    hass: HomeAssistant, mock_unit: MockModbusUnit, freezer: FrozenDateTimeFactory
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
    await wait_for_write_refresh(hass, freezer)

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] is None
    assert state.attributes[ATTR_PERCENTAGE] == 66


@pytest.mark.parametrize(
    ("service", "data", "preset_mode", "percentage"),
    [
        pytest.param(
            SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 33}, None, 33, id="speed"
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: "boost"},
            "boost",
            100,
            id="boost",
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "away"}, "away", None, id="away"
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "auto"}, "auto", 66, id="auto"
        ),
    ],
)
async def test_state_shows_a_write_until_the_next_poll(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    service: str,
    data: dict[str, Any],
    preset_mode: str | None,
    percentage: int | None,
) -> None:
    """Test the fan shows a write at once, then what the next poll reports.

    The refresh a write requests may wait for the coordinator's cooldown.
    """
    with patch.object(
        init_integration.runtime_data.coordinator,
        "async_request_refresh",
        AsyncMock(),
    ):
        await hass.services.async_call(
            FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True
        )

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] == preset_mode
    assert state.attributes[ATTR_PERCENTAGE] == percentage

    # Someone switches the unit back to auto mode before the next poll
    seed(mock_unit, coil=COIL, holding={0x0001: 2})
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] == "auto"
    assert state.attributes[ATTR_PERCENTAGE] == 66


@pytest.mark.parametrize("preset_mode", ["away", "boost"])
async def test_state_ignores_polls_before_the_unit_shows_a_write(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    preset_mode: str,
) -> None:
    """Test a poll that reads the unit before it applied a write keeps the write.

    The unit shows a change up to 2 seconds after the write is acknowledged.
    """
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: preset_mode},
        blocking=True,
    )

    # The unit has not applied the write yet
    seed(mock_unit, coil=COIL, holding={0x0001: 2})
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] == preset_mode

    # The refresh the write scheduled reads the unit once it settled
    await wait_for_write_refresh(hass, freezer)
    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] == "auto"


@pytest.mark.parametrize(
    ("service", "data", "preset"),
    [
        pytest.param(
            SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 100}, 3, id="manual_speed"
        ),
        pytest.param(SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "away"}, 0, id="away"),
        pytest.param(
            SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "boost"}, 3, id="boost"
        ),
    ],
)
async def test_auto_shows_the_speed_it_last_ran_at(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    service: str,
    data: dict[str, Any],
    preset: int,
) -> None:
    """Test choosing auto shows the speed auto mode ran at before.

    Auto mode returns to it, but the unit shows it only seconds after the
    write.
    """
    await hass.services.async_call(
        FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True
    )
    seed(mock_unit, holding={0x0001: preset})
    await wait_for_write_refresh(hass, freezer)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "auto"},
        blocking=True,
    )

    state = hass.states.get(FAN)
    assert state.attributes[ATTR_PRESET_MODE] == "auto"
    assert state.attributes[ATTR_PERCENTAGE] == 66


async def test_auto_ignores_polls_before_the_unit_shows_a_write(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a poll pairing auto mode with the old manual speed is not remembered."""
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: FAN, ATTR_PERCENTAGE: 100},
        blocking=True,
    )
    await wait_for_write_refresh(hass, freezer)
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "auto"},
        blocking=True,
    )
    # Auto mode is on, but the unit still shows the manual speed
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    for service, data in (
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 33}),
        (SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "auto"}),
    ):
        await hass.services.async_call(
            FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True
        )
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == 66
