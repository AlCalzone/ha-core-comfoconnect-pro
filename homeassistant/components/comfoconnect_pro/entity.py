"""Base entity for Zehnder ComfoConnect PRO gateways."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import InvalidValueError
from modbus_connection import ModbusError

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Send a write to the gateway, then refresh.

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
            await self.coordinator.async_request_refresh()
