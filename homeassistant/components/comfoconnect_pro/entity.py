"""Base entity for Zehnder ComfoConnect PRO gateways."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import override

from comfoconnect_pro_modbus import InvalidValueError
from modbus_connection import ModbusError

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, WRITE_SETTLE_TIME
from .coordinator import ComfoConnectProDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProEntityDescription(EntityDescription):
    """Describe a ComfoConnect PRO entity."""

    # `component` names the attribute of ComfoConnectPro that holds the data.
    component: str


class ComfoConnectProEntity(CoordinatorEntity[ComfoConnectProDataUpdateCoordinator]):
    """Defines a base ComfoConnect PRO entity."""

    _attr_has_entity_name = True
    entity_description: ComfoConnectProEntityDescription
    _unsub_refresh: Callable[[], None] | None = None

    def __init__(
        self,
        coordinator: ComfoConnectProDataUpdateCoordinator,
        entity_description: ComfoConnectProEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )
        self._attr_device_info = coordinator.device_info

    @property
    @override
    def available(self) -> bool:
        """Whether this entity's component answered the most recent poll."""
        if not super().available:
            return False
        return self.entity_description.component not in self.coordinator.data.failed

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Cancel a pending refresh."""
        await super().async_will_remove_from_hass()
        if self._unsub_refresh is not None:
            self._unsub_refresh()
            self._unsub_refresh = None

    @callback
    def _async_schedule_refresh(self) -> None:
        """Refresh once the unit shows the write.

        A refresh right after a write reads the unit's state from before it.
        """
        if self._unsub_refresh is not None:
            self._unsub_refresh()

        async def _async_refresh(_now: datetime) -> None:
            self._unsub_refresh = None
            await self.coordinator.async_request_refresh()

        self._unsub_refresh = async_call_later(
            self.hass, WRITE_SETTLE_TIME, _async_refresh
        )

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Send a write to the gateway, then refresh once the unit shows it.

        The refresh runs after a failed write too, because part of a write
        sequence may have reached the gateway.
        """
        try:
            await write
        except InvalidValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
            ) from err
        finally:
            self._async_schedule_refresh()
