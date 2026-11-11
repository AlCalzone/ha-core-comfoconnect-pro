"""Support for Zehnder ComfoConnect PRO binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import ComfoConnectPro

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProBinarySensorDescription(
    BinarySensorEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO binary sensor."""

    value_fn: Callable[[ComfoConnectPro], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[ComfoConnectProBinarySensorDescription, ...] = (
    ComfoConnectProBinarySensorDescription(
        key="error",
        translation_key="error",
        component="status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.status.error_flag,
    ),
    ComfoConnectProBinarySensorDescription(
        key="filter_dirty",
        translation_key="filter_dirty",
        component="status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda device: device.status.filter_dirty,
    ),
    ComfoConnectProBinarySensorDescription(
        key="standby",
        translation_key="standby",
        component="status",
        value_fn=lambda device: device.status.standby,
    ),
    ComfoConnectProBinarySensorDescription(
        key="comfohood",
        translation_key="comfohood",
        component="status",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda device: device.status.comfohood,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO binary sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ComfoConnectProBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class ComfoConnectProBinarySensor(ComfoConnectProEntity, BinarySensorEntity):
    """Defines a ComfoConnect PRO binary sensor."""

    entity_description: ComfoConnectProBinarySensorDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        return self.entity_description.value_fn(self.coordinator.device)
