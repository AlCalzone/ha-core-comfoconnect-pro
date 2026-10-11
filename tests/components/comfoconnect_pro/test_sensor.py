"""Tests for the Zehnder ComfoConnect PRO sensor platform."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.comfoconnect_pro.const import SCAN_INTERVAL
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import INPUT, seed

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

pytestmark = pytest.mark.parametrize("platforms", [[Platform.SENSOR]])


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every sensor and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_co2_zone_added_when_it_reports(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a CO₂ zone that starts reporting gets its sensor."""
    assert hass.states.get("sensor.comfoair_co2_zone_2") is None

    seed(mock_unit, input_registers={0x0013: 455})
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.comfoair_co2_zone_2").state == "455"


@pytest.mark.parametrize(
    ("code", "state"),
    [
        pytest.param(0, "none", id="empty"),
        pytest.param(36, STATE_UNKNOWN, id="unlisted"),
        pytest.param(101, "comfonet_err", id="listed"),
    ],
)
async def test_active_error_states(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    code: int,
    state: str,
) -> None:
    """Test an alarm slot shows none, a listed alarm, or unknown."""
    seed(mock_unit, input_registers={**INPUT, 0x0002: code})
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.comfoair_active_error_1").state == state
