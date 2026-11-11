"""Support for Zehnder ComfoConnect PRO switches."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ComfoConnectProConfigEntry, ComfoConnectProRuntimeData
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProSwitchDescription(
    SwitchEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO switch, backed by a coil of ``Controls``."""

    component: str = "controls"
    value_fn: Callable[[ComfoConnectProRuntimeData], bool | None]
    write_fn: Callable[[ComfoConnectProRuntimeData, bool], Awaitable[None]]


async def _write_boost(runtime_data: ComfoConnectProRuntimeData, on: bool) -> None:
    """Start a boost of the chosen duration, or stop it.

    The gateway reads back the time left on a boost, not its length, and
    Zehnder's app writes a length of its own, so write it before each boost.
    """
    controls = runtime_data.device.controls
    if on:
        await controls.async_write_boost_time(runtime_data.boost_duration)
    await controls.async_write_boost(on)


SWITCH_DESCRIPTIONS: tuple[ComfoConnectProSwitchDescription, ...] = (
    ComfoConnectProSwitchDescription(
        key="boost",
        translation_key="boost",
        value_fn=lambda data: data.device.controls.boost,
        write_fn=_write_boost,
    ),
    ComfoConnectProSwitchDescription(
        key="away",
        translation_key="away",
        value_fn=lambda data: data.device.controls.away_function,
        write_fn=lambda data, on: data.device.controls.async_write_away_function(on),
    ),
    ComfoConnectProSwitchDescription(
        key="comfocool",
        translation_key="comfocool",
        # The coil reads on without a ComfoCool fitted, and the gateway does not
        # tell whether one is
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.device.controls.comfocool,
        write_fn=lambda data, on: data.device.controls.async_write_comfocool(on),
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
        return self.entity_description.value_fn(
            self.coordinator.config_entry.runtime_data
        )

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_write(
            self.entity_description.write_fn(
                self.coordinator.config_entry.runtime_data, True
            )
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_write(
            self.entity_description.write_fn(
                self.coordinator.config_entry.runtime_data, False
            )
        )
