"""Tests for the Zehnder ComfoConnect PRO number platform."""

from comfoconnect_pro_modbus.model import address
from modbus_connection import IllegalDataValueError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

pytestmark = pytest.mark.parametrize("platforms", [[Platform.NUMBER]])

BOOST_TIME = "number.comfoair_boost_duration"


async def test_numbers(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every number and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("entity_id", "value", "register", "word"),
    [
        pytest.param(
            "number.comfoair_external_setpoint", 23.5, 0x0004, 235, id="setpoint"
        ),
        pytest.param(BOOST_TIME, 600, 0x0005, 600, id="boost"),
        pytest.param(BOOST_TIME, 86400, 0x0005, 65535, id="boost_day"),
    ],
)
async def test_set_value(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    entity_id: str,
    value: float,
    register: int,
    word: int,
) -> None:
    """Test setting a value writes its register."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )

    assert writes == [WriteEvent("holding", address(register), [word], 0x06)]


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(70000, id="between_limits"),
        pytest.param(90.5, id="fraction"),
    ],
)
async def test_invalid_boost_time_is_refused(
    hass: HomeAssistant, mock_unit: MockModbusUnit, value: float
) -> None:
    """Test a boost time the register cannot hold is refused, not rounded."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: BOOST_TIME, ATTR_VALUE: value},
            blocking=True,
        )

    assert exc_info.value.translation_key == "invalid_value"
    assert writes == []


@pytest.mark.usefixtures("init_integration")
async def test_refused_setpoint_write(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a setpoint write the gateway refuses surfaces as an error."""
    mock_unit.fail_write(address(0x0004), IllegalDataValueError())

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.comfoair_external_setpoint", ATTR_VALUE: 21},
            blocking=True,
        )

    assert exc_info.value.translation_key == "write_failed"
