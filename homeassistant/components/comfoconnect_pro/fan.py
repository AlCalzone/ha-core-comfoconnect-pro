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
PRESET_AWAY = "away"
PRESET_BOOST = "boost"
# The away preset belongs to the away function, which runs on top of the
# speeds, so the fan's speeds are the other three.
SPEEDS = [VentilationPreset.LOW, VentilationPreset.MEDIUM, VentilationPreset.HIGH]


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
    """The ventilation unit's fans: three speeds, auto mode, away and boost.

    The unit always ventilates, so the fan has no off state. Away and boost
    run on top of auto mode or a manual speed, which the unit returns to when
    they end.
    """

    entity_description: ComfoConnectProFanDescription
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    _attr_speed_count = len(SPEEDS)
    _attr_preset_modes = [PRESET_AUTO, PRESET_AWAY, PRESET_BOOST]

    @property
    @override
    def percentage(self) -> int | None:
        """Return the speed in effect, as a percentage, or None while away."""
        preset = self.coordinator.device.controls.ventilation_preset
        if preset not in SPEEDS:
            return None
        return ordered_list_item_to_percentage(SPEEDS, preset)

    @property
    @override
    def preset_mode(self) -> str | None:
        """Return boost or away while one runs, else auto while the unit picks."""
        controls = self.coordinator.device.controls
        if controls.boost:
            return PRESET_BOOST
        if controls.away_function:
            return PRESET_AWAY
        return PRESET_AUTO if controls.auto_mode else None

    @override
    async def async_set_percentage(self, percentage: int) -> None:
        """Leave auto mode, then switch to the preset closest to ``percentage``."""
        if percentage == 0:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cannot_turn_off"
            )
        controls = self.coordinator.device.controls
        preset = percentage_to_ordered_list_item(SPEEDS, percentage)

        async def _set_speed() -> None:
            # Write every mode off unconditionally, because the cached state
            # can be stale, and boost, away and auto mode would each override
            # the preset.
            await controls.async_write_boost(False)
            await controls.async_write_away_function(False)
            await controls.async_write_auto_mode(False)
            await controls.async_write_ventilation_preset(preset)

        await self._async_write(_set_speed())

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Hand the speed to auto mode, or start away or a boost."""
        runtime_data = self.coordinator.config_entry.runtime_data
        controls = runtime_data.device.controls

        async def _set_preset() -> None:
            if preset_mode == PRESET_BOOST:
                await controls.async_write_away_function(False)
                # The gateway reads back the time left on a boost, not its
                # length, and Zehnder's app writes a length of its own, so
                # write the chosen one before each boost.
                await controls.async_write_boost_time(runtime_data.boost_duration)
                await controls.async_write_boost(True)
                return
            await controls.async_write_boost(False)
            if preset_mode == PRESET_AWAY:
                await controls.async_write_away_function(True)
                return
            await controls.async_write_away_function(False)
            await controls.async_write_auto_mode(True)

        await self._async_write(_set_preset())
