"""Support for Zehnder ComfoConnect PRO switches."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from comfoconnect_pro_modbus import Controls

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProSwitchDescription(
    SwitchEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO switch, backed by a coil of ``Controls``."""

    component: str = "controls"
    value_fn: Callable[[Controls], bool | None]
    write_fn: Callable[[Controls, bool], Awaitable[None]]


SWITCH_DESCRIPTIONS: tuple[ComfoConnectProSwitchDescription, ...] = (
    ComfoConnectProSwitchDescription(
        key="boost",
        translation_key="boost",
        value_fn=lambda controls: controls.boost,
        write_fn=lambda controls, on: controls.async_write_boost(on),
    ),
    ComfoConnectProSwitchDescription(
        key="away",
        translation_key="away",
        value_fn=lambda controls: controls.away_function,
        write_fn=lambda controls, on: controls.async_write_away_function(on),
    ),
    ComfoConnectProSwitchDescription(
        key="comfocool",
        translation_key="comfocool",
        value_fn=lambda controls: controls.comfocool,
        write_fn=lambda controls, on: controls.async_write_comfocool(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO switch platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ComfoConnectProSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )


class ComfoConnectProSwitch(ComfoConnectProEntity, SwitchEntity):
    """Defines a ComfoConnect PRO switch."""

    entity_description: ComfoConnectProSwitchDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the state of the switch."""
        return self.entity_description.value_fn(self.coordinator.device.controls)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_write(
            self.entity_description.write_fn(self.coordinator.device.controls, True)
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_write(
            self.entity_description.write_fn(self.coordinator.device.controls, False)
        )
