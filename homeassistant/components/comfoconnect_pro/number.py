"""Support for Zehnder ComfoConnect PRO numbers."""

from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import (
    BOOST_TIME_MAX,
    EXTERNAL_SETPOINT_MAX,
    EXTERNAL_SETPOINT_MIN,
    TemperatureProfileMode,
)

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProNumberDescription(
    NumberEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO number."""

    component: str = "controls"


EXTERNAL_SETPOINT = ComfoConnectProNumberDescription(
    key="external_setpoint",
    translation_key="external_setpoint",
    entity_category=EntityCategory.CONFIG,
    device_class=NumberDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    native_min_value=EXTERNAL_SETPOINT_MIN,
    native_max_value=EXTERNAL_SETPOINT_MAX,
    native_step=0.1,
    mode=NumberMode.BOX,
)

BOOST_DURATION = ComfoConnectProNumberDescription(
    key="boost_duration",
    translation_key="boost_duration",
    entity_category=EntityCategory.CONFIG,
    device_class=NumberDeviceClass.DURATION,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    native_min_value=0,
    native_max_value=BOOST_TIME_MAX,
    native_step=1,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO number platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ComfoConnectProExternalSetpointNumber(coordinator, EXTERNAL_SETPOINT),
            ComfoConnectProBoostDurationNumber(coordinator, BOOST_DURATION),
        ]
    )


class ComfoConnectProExternalSetpointNumber(ComfoConnectProEntity, NumberEntity):
    """The comfort temperature the unit follows in the external setpoint mode.

    The gateway reads back the comfort temperature in effect, which is the
    external setpoint only in that mode, so the number is unavailable in the
    other modes.
    """

    entity_description: ComfoConnectProNumberDescription

    @property
    @override
    def available(self) -> bool:
        """Whether the unit is in the external setpoint mode."""
        return (
            super().available
            and self.coordinator.device.controls.temperature_profile_mode
            is TemperatureProfileMode.EXTERNAL_SETPOINT
        )

    @property
    @override
    def native_value(self) -> float | None:
        """Return the external setpoint."""
        return self.coordinator.device.controls.comfort_temperature

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the external setpoint to the gateway."""
        await self._async_write(
            self.coordinator.device.controls.async_write_external_setpoint(value)
        )


class ComfoConnectProBoostDurationNumber(ComfoConnectProEntity, RestoreNumber):
    """How long a boost started from Home Assistant lasts.

    The gateway reads back the time left on a boost, not its length, so the
    number keeps the length itself, and the Boost switch writes it before each
    boost.
    """

    entity_description: ComfoConnectProNumberDescription

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the boost duration."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and (
            last.native_value is not None
        ):
            self.coordinator.config_entry.runtime_data.boost_duration = int(
                last.native_value
            )

    @property
    @override
    def native_value(self) -> int:
        """Return the boost duration."""
        return self.coordinator.config_entry.runtime_data.boost_duration

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the boost duration to the gateway, then keep it."""
        await self._async_write(
            self.coordinator.device.controls.async_write_boost_time(value)
        )
        self.coordinator.config_entry.runtime_data.boost_duration = int(value)
        self.async_write_ha_state()
