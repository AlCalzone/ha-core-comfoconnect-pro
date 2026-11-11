"""Tests for the Zehnder ComfoConnect PRO binary sensor platform."""

import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.mark.parametrize("platforms", [[Platform.BINARY_SENSOR]])
async def test_binary_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test every binary sensor and its state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)
