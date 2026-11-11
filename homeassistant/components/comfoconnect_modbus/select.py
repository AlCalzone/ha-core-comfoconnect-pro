"""Support for Zehnder ComfoConnect PRO selects."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import override

from comfoconnect_pro_modbus import Controls, TemperatureProfile, TemperatureProfileMode

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1


def _enum_options(enum_type: type[IntEnum]) -> list[str]:
    """The select options a device enum maps to."""
    return [member.name.lower() for member in enum_type]


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProSelectDescription(
    SelectEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO select, backed by a register of ``Controls``."""

    component: str = "controls"
    value_fn: Callable[[Controls], IntEnum | None]
    write_fn: Callable[[Controls, str], Awaitable[None]]


SELECT_DESCRIPTIONS: tuple[ComfoConnectProSelectDescription, ...] = (
    ComfoConnectProSelectDescription(
        key="temperature_profile",
        translation_key="temperature_profile",
        entity_category=EntityCategory.CONFIG,
        options=_enum_options(TemperatureProfile),
        value_fn=lambda controls: controls.temperature_profile,
        write_fn=lambda controls, option: controls.async_write_temperature_profile(
            TemperatureProfile[option.upper()]
        ),
    ),
    ComfoConnectProSelectDescription(
        key="temperature_profile_mode",
        translation_key="temperature_profile_mode",
        entity_category=EntityCategory.CONFIG,
        options=_enum_options(TemperatureProfileMode),
        value_fn=lambda controls: controls.temperature_profile_mode,
        write_fn=lambda controls, option: controls.async_write_temperature_profile_mode(
            TemperatureProfileMode[option.upper()]
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO select platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ComfoConnectProSelect(coordinator, description)
        for description in SELECT_DESCRIPTIONS
    )


class ComfoConnectProSelect(ComfoConnectProEntity, SelectEntity):
    """Defines a ComfoConnect PRO select."""

    entity_description: ComfoConnectProSelectDescription

    @property
    @override
    def current_option(self) -> str | None:
        """Return the selected option."""
        value = self.entity_description.value_fn(self.coordinator.device.controls)
        return value.name.lower() if value is not None else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the gateway."""
        await self._async_write(
            self.entity_description.write_fn(self.coordinator.device.controls, option)
        )
