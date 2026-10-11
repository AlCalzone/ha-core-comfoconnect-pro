"""Config flow for Zehnder ComfoConnect PRO gateways."""

from collections.abc import Mapping
from typing import Any, override

from comfoconnect_pro_modbus import ComfoConnectPro, NoVentilationUnitError
from modbus_connection import ModbusError
import probatio

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)

from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_UNIT_ID,
    DEFAULT_BAUDRATE,
    DEFAULT_NAME,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    PARITIES,
    TYPE_SERIAL,
    TYPE_TCP,
)
from .helpers import create_modbus_params

STEP_RECONFIGURE_SERIAL = "reconfigure_serial"
STEP_RECONFIGURE_TCP = "reconfigure_tcp"

UNIT_ID_SELECTOR = probatio.All(
    NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)),
    probatio.Coerce(int),
)

STEP_TCP_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
    }
)

STEP_SERIAL_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE): SerialPortSelector(),
        probatio.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): probatio.All(
            SelectSelector(
                SelectSelectorConfig(
                    options=[str(baudrate) for baudrate in BAUDRATES],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_PARITY, default=DEFAULT_PARITY): SelectSelector(
            SelectSelectorConfig(
                options=list(PARITIES),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_PARITY,
            )
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
    }
)


def _link_identity(data: Mapping[str, Any]) -> dict[str, Any]:
    """The entry data that names the gateway's link, for duplicate checks."""
    if data[CONF_TYPE] == TYPE_SERIAL:
        keys: tuple[str, ...] = (CONF_TYPE, CONF_DEVICE, CONF_UNIT_ID)
    else:
        keys = (CONF_TYPE, CONF_HOST, CONF_PORT, CONF_UNIT_ID)
    return {key: data[key] for key in keys}


async def _async_probe(hass: HomeAssistant, data: Mapping[str, Any]) -> None:
    """Connect to the gateway and check it reaches a ventilation unit, or raise."""
    params = create_modbus_params(data)
    async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
        await ComfoConnectPro.async_detect(unit)


class ComfoConnectProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a ComfoConnect PRO config flow."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the gateway is reached."""
        return self.async_show_menu(
            step_id="user", menu_options=[TYPE_TCP, TYPE_SERIAL]
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway reached over the network."""
        return await self._async_step_link(TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway reached over RS-485."""
        return await self._async_step_link(
            TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def _async_step_link(
        self,
        connection_type: str,
        schema: probatio.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Ask for the link settings, then probe the gateway behind them."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TYPE: connection_type, **user_input}
            # The gateway has no serial number, so its link identifies it.
            self._async_abort_entries_match(_link_identity(data))
            errors, description_placeholders = await self._async_validate(data)
            if not errors:
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        return self.async_show_form(
            step_id=connection_type,
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updating an existing entry's connection details."""
        entry = self._get_reconfigure_entry()
        if entry.data[CONF_TYPE] == TYPE_SERIAL:
            return await self.async_step_reconfigure_serial()
        return await self.async_step_reconfigure_tcp()

    async def async_step_reconfigure_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updating a gateway reached over the network."""
        return await self._async_step_reconfigure_link(
            STEP_RECONFIGURE_TCP, TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input
        )

    async def async_step_reconfigure_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updating a gateway reached over RS-485."""
        return await self._async_step_reconfigure_link(
            STEP_RECONFIGURE_SERIAL, TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def _async_step_reconfigure_link(
        self,
        step_id: str,
        connection_type: str,
        schema: probatio.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Ask for the link settings, then probe the gateway behind them."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TYPE: connection_type, **user_input}

            # Release the entry's hold on the old link first, because the
            # shared connection refuses other settings for the same endpoint.
            relinking = False
            if entry.state in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY):
                current = create_modbus_params(entry.data)
                new = create_modbus_params(data)
                if new.endpoint == current.endpoint and new != current:
                    relinking = await self.hass.config_entries.async_unload(
                        entry.entry_id
                    )

            errors, description_placeholders = await self._async_validate(data)

            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
            if relinking:
                await self.hass.config_entries.async_setup(entry.entry_id)

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or _suggested(entry.data)
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def _async_validate(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Probe the gateway, returning the errors to show, if any."""
        try:
            await _async_probe(self.hass, data)
        except NoVentilationUnitError as err:
            state = "unknown" if err.state is None else str(err.state.value)
            return {"base": "no_ventilation_unit"}, {"state": state}
        except (ModbusError, HomeAssistantError) as err:
            return {"base": "cannot_connect"}, {"error": str(err)}
        return {}, {}


def _suggested(data: Mapping[str, Any]) -> dict[str, Any]:
    """Entry data as a form's suggested values, with the baud rate as its option."""
    suggested = dict(data)
    if CONF_BAUDRATE in suggested:
        suggested[CONF_BAUDRATE] = str(suggested[CONF_BAUDRATE])
    return suggested
