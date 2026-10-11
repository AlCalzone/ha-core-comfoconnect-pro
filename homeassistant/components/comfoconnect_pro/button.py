"""Support for Zehnder ComfoConnect PRO buttons."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProButtonDescription(
    ButtonEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO button."""


RESET_ERRORS = ComfoConnectProButtonDescription(
    key="reset_errors",
    translation_key="reset_errors",
    component="controls",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO button platform."""
    async_add_entities(
        [ComfoConnectProResetErrorsButton(entry.runtime_data.coordinator, RESET_ERRORS)]
    )


class ComfoConnectProResetErrorsButton(ComfoConnectProEntity, ButtonEntity):
    """Clears the ventilation unit's alarms."""

    entity_description: ComfoConnectProButtonDescription

    @override
    async def async_press(self) -> None:
        """Clear the alarms."""
        await self._async_write(self.coordinator.device.controls.async_reset_errors())
