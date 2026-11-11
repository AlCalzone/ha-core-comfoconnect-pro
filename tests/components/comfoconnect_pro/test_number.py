"""Tests for the Zehnder ComfoConnect PRO number platform."""

from comfoconnect_pro_modbus.model import address
from modbus_connection import IllegalDataValueError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import seed, setup_integration

pytestmark = pytest.mark.parametrize("platforms", [[Platform.NUMBER]])

BOOST_DURATION = "number.comfoair_boost_duration"
EXTERNAL_SETPOINT = "number.comfoair_external_setpoint"


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set a number through its service."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def _enter_external_setpoint_mode(
    init_integration: MockConfigEntry, mock_unit: MockModbusUnit
) -> None:
    """Switch the unit to the external setpoint mode and poll."""
    seed(mock_unit, holding={0x0003: 2})
    await init_integration.runtime_data.coordinator.async_refresh()


async def test_numbers(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every number and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_external_setpoint_unavailable_outside_its_mode(
    hass: HomeAssistant,
) -> None:
    """Test the external setpoint is unavailable while the unit is adaptive."""
    assert hass.states.get(EXTERNAL_SETPOINT).state == STATE_UNAVAILABLE


async def test_set_external_setpoint(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
) -> None:
    """Test the external setpoint shows and writes the comfort temperature."""
    await _enter_external_setpoint_mode(init_integration, mock_unit)
    assert hass.states.get(EXTERNAL_SETPOINT).state == "22.0"
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await _set_value(hass, EXTERNAL_SETPOINT, 23.5)

    assert writes == [WriteEvent("holding", address(0x0004), [235], 0x06)]
    assert hass.states.get(EXTERNAL_SETPOINT).state == "23.5"


async def test_refused_setpoint_write(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
) -> None:
    """Test a setpoint write the gateway refuses surfaces as an error."""
    await _enter_external_setpoint_mode(init_integration, mock_unit)
    mock_unit.fail_write(address(0x0004), IllegalDataValueError())

    with pytest.raises(HomeAssistantError) as exc_info:
        await _set_value(hass, EXTERNAL_SETPOINT, 21)

    assert exc_info.value.translation_key == "write_failed"


@pytest.mark.parametrize(
    ("value", "word"),
    [pytest.param(600, 600, id="minutes"), pytest.param(86400, 65535, id="day")],
)
async def test_set_boost_duration(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    value: int,
    word: int,
) -> None:
    """Test the boost duration is written and kept, as nothing reads it back."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await _set_value(hass, BOOST_DURATION, value)

    assert writes == [WriteEvent("holding", address(0x0005), [word], 0x06)]
    assert hass.states.get(BOOST_DURATION).state == str(value)
    assert init_integration.runtime_data.boost_duration == value


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(70000, id="between_limits"),
        pytest.param(90.5, id="fraction"),
    ],
)
async def test_invalid_boost_duration_is_refused(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    value: float,
) -> None:
    """Test a boost duration the register cannot hold is refused, not rounded."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    with pytest.raises(ServiceValidationError) as exc_info:
        await _set_value(hass, BOOST_DURATION, value)

    assert exc_info.value.translation_key == "invalid_value"
    assert writes == []
    assert hass.states.get(BOOST_DURATION).state == "1800"
    assert init_integration.runtime_data.boost_duration == 1800


@pytest.mark.usefixtures("mock_get_unit")
async def test_boost_duration_is_restored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    platforms: list[Platform],
) -> None:
    """Test the boost duration survives a restart."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(BOOST_DURATION, "900"),
                {
                    "native_max_value": 86400,
                    "native_min_value": 0,
                    "native_step": 1,
                    "native_unit_of_measurement": "s",
                    "native_value": 900,
                },
            ),
        ),
    )

    await setup_integration(hass, mock_config_entry, platforms)

    assert hass.states.get(BOOST_DURATION).state == "900"
    assert mock_config_entry.runtime_data.boost_duration == 900
