"""Support for the Zehnder ComfoConnect PRO ventilation fan."""

from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import VentilationPreset

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import DOMAIN
from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1

PRESET_AUTO = "auto"
SPEEDS = list(VentilationPreset)


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProFanDescription(
    FanEntityDescription, ComfoConnectProEntityDescription
):
    """Describe the ComfoConnect PRO fan."""


VENTILATION = ComfoConnectProFanDescription(
    key="ventilation",
    translation_key="ventilation",
    name=None,
    component="controls",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO fan platform."""
    async_add_entities(
        [ComfoConnectProFan(entry.runtime_data.coordinator, VENTILATION)]
    )


class ComfoConnectProFan(ComfoConnectProEntity, FanEntity):
    """The ventilation unit's fans: a speed per preset, and auto mode.

    The unit always ventilates, so the fan has no off state.
    """

    entity_description: ComfoConnectProFanDescription
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    _attr_speed_count = len(SPEEDS)
    _attr_preset_modes = [PRESET_AUTO]

    @property
    @override
    def percentage(self) -> int | None:
        """Return the speed of the preset in effect, as a percentage."""
        preset = self.coordinator.device.controls.ventilation_preset
        if preset is None:
            return None
        return ordered_list_item_to_percentage(SPEEDS, preset)

    @property
    @override
    def preset_mode(self) -> str | None:
        """Return auto while the unit picks the speed itself."""
        return PRESET_AUTO if self.coordinator.device.controls.auto_mode else None

    @override
    async def async_set_percentage(self, percentage: int) -> None:
        """Switch to the preset closest to ``percentage`` and leave auto mode."""
        if percentage == 0:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cannot_turn_off"
            )
        controls = self.coordinator.device.controls
        preset = percentage_to_ordered_list_item(SPEEDS, percentage)
        await self._async_write(controls.async_write_ventilation_preset(preset))
        if controls.auto_mode:
            await self._async_write(controls.write("auto_mode", False))

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Hand the speed to the unit's auto mode."""
        await self._async_write(
            self.coordinator.device.controls.write("auto_mode", True)
        )
