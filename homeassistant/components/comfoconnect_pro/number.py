"""Support for Zehnder ComfoConnect PRO numbers."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import (
    BOOST_TIME_MAX,
    EXTERNAL_SETPOINT_MAX,
    EXTERNAL_SETPOINT_MIN,
    ComfoConnectPro,
)

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
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
    value_fn: Callable[[ComfoConnectPro], float | None]
    write_fn: Callable[[ComfoConnectPro, float], Awaitable[None]]


NUMBER_DESCRIPTIONS: tuple[ComfoConnectProNumberDescription, ...] = (
    ComfoConnectProNumberDescription(
        key="external_setpoint",
        translation_key="external_setpoint",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=EXTERNAL_SETPOINT_MIN,
        native_max_value=EXTERNAL_SETPOINT_MAX,
        native_step=0.1,
        mode=NumberMode.BOX,
        value_fn=lambda device: device.controls.external_setpoint,
        write_fn=lambda device, value: device.controls.async_write_external_setpoint(
            value
        ),
    ),
    ComfoConnectProNumberDescription(
        key="boost_time",
        translation_key="boost_time",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=0,
        native_max_value=BOOST_TIME_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda device: device.controls.boost_time,
        write_fn=lambda device, value: device.controls.async_write_boost_time(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO number platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ComfoConnectProNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    )


class ComfoConnectProNumber(ComfoConnectProEntity, NumberEntity):
    """Defines a ComfoConnect PRO number."""

    entity_description: ComfoConnectProNumberDescription

    @property
    @override
    def native_value(self) -> float | None:
        """Return the value of the number."""
        return self.entity_description.value_fn(self.coordinator.device)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the value to the gateway."""
        await self._async_write(
            self.entity_description.write_fn(self.coordinator.device, value)
        )
