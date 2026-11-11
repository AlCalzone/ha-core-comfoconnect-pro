"""Support for the Zehnder ComfoConnect PRO ventilation fan."""

from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import VentilationPreset

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
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
    # The preset mode and percentage a write just set, shown until the next
    # poll, since a refresh right after a write may wait for the coordinator's
    # cooldown
    _optimistic: tuple[str | None, int | None] | None = None

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Show what the unit reports again."""
        self._optimistic = None
        super()._handle_coordinator_update()

    @property
    @override
    def percentage(self) -> int | None:
        """Return the speed in effect, as a percentage, or None while away."""
        if self._optimistic is not None:
            return self._optimistic[1]
        return self._reported_percentage()

    @property
    @override
    def preset_mode(self) -> str | None:
        """Return boost or away while one runs, else auto while the unit picks."""
        if self._optimistic is not None:
            return self._optimistic[0]
        controls = self.coordinator.device.controls
        if controls.boost:
            return PRESET_BOOST
        if controls.away_function:
            return PRESET_AWAY
        return PRESET_AUTO if controls.auto_mode else None

    def _reported_percentage(self) -> int | None:
        """Return the speed the unit last reported.

        The unit moves the preset to high for a boost and to away for the away
        function only seconds after the coil turns on, so the coils decide.
        """
        controls = self.coordinator.device.controls
        if controls.boost:
            return 100
        if controls.away_function:
            return None
        preset = controls.ventilation_preset
        if preset not in SPEEDS:
            return None
        return ordered_list_item_to_percentage(SPEEDS, preset)

    @callback
    def _async_set_optimistic(
        self, preset_mode: str | None, percentage: int | None
    ) -> None:
        """Show what a write set until the next poll."""
        self._optimistic = (preset_mode, percentage)
        self.async_write_ha_state()

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
            self._async_set_optimistic(
                None, ordered_list_item_to_percentage(SPEEDS, preset)
            )

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
                # A boost runs the fans at the high speed
                self._async_set_optimistic(PRESET_BOOST, 100)
                return
            await controls.async_write_boost(False)
            if preset_mode == PRESET_AWAY:
                await controls.async_write_away_function(True)
                # Away has no speed of its own
                self._async_set_optimistic(PRESET_AWAY, None)
                return
            await controls.async_write_away_function(False)
            await controls.async_write_auto_mode(True)
            # Auto mode picks its own speed, which the next poll shows. The
            # one reported during a boost or away is not it.
            ending_mode = controls.boost or controls.away_function
            self._async_set_optimistic(
                PRESET_AUTO, None if ending_mode else self._reported_percentage()
            )

        await self._async_write(_set_preset())
