"""Support for Zehnder ComfoConnect PRO sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from comfoconnect_pro_modbus import ALARM_SLOTS, AlarmCode, ComfoConnectPro

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import ComfoConnectProConfigEntry
from .entity import ComfoConnectProEntity, ComfoConnectProEntityDescription

PARALLEL_UPDATES = 0

NO_ALARM = "none"
ALARM_OPTIONS = [NO_ALARM, *(code.name.lower() for code in AlarmCode)]
AIR_STREAMS = ("room", "extract", "exhaust", "outdoor", "supply")


@dataclass(frozen=True, kw_only=True)
class ComfoConnectProSensorDescription(
    SensorEntityDescription, ComfoConnectProEntityDescription
):
    """Describe a ComfoConnect PRO sensor."""

    value_fn: Callable[[ComfoConnectPro], StateType]


def _attribute(component: str, name: str) -> Callable[[ComfoConnectPro], StateType]:
    """Read ``name`` of ``component``."""

    def _value(device: ComfoConnectPro) -> StateType:
        value: StateType = getattr(getattr(device, component), name)
        return value

    return _value


def _alarm(slot: int) -> Callable[[ComfoConnectPro], StateType]:
    """Read alarm slot ``slot`` as a sensor option."""

    def _value(device: ComfoConnectPro) -> StateType:
        code = device.status.active_error(slot)
        if code is None:
            return None
        if code == 0:
            return NO_ALARM
        # Map a code the manual does not list to None because it has no option.
        return code.name.lower() if isinstance(code, AlarmCode) else None

    return _value


SENSOR_DESCRIPTIONS: tuple[ComfoConnectProSensorDescription, ...] = (
    ComfoConnectProSensorDescription(
        key="airflow",
        translation_key="airflow",
        component="sensors",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_attribute("sensors", "airflow"),
    ),
    *(
        ComfoConnectProSensorDescription(
            key=f"{stream}_temperature",
            translation_key=f"{stream}_temperature",
            component="sensors",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=_attribute("sensors", f"{stream}_temperature"),
        )
        for stream in AIR_STREAMS
    ),
    *(
        ComfoConnectProSensorDescription(
            key=f"{stream}_humidity",
            translation_key=f"{stream}_humidity",
            component="sensors",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_attribute("sensors", f"{stream}_humidity"),
        )
        for stream in AIR_STREAMS
    ),
    ComfoConnectProSensorDescription(
        key="filter_days_remaining",
        translation_key="filter_days_remaining",
        component="sensors",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_attribute("sensors", "filter_days_remaining"),
    ),
    *(
        ComfoConnectProSensorDescription(
            key=f"active_error_{slot}",
            translation_key="active_error",
            translation_placeholders={"number": str(slot)},
            component="status",
            device_class=SensorDeviceClass.ENUM,
            options=ALARM_OPTIONS,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=slot == 1,
            value_fn=_alarm(slot),
        )
        for slot in range(1, ALARM_SLOTS + 1)
    ),
)


def co2_sensor(zone: int) -> ComfoConnectProSensorDescription:
    """The CO₂ sensor of ``zone``."""
    return ComfoConnectProSensorDescription(
        key=f"co2_zone_{zone}",
        translation_key="co2_zone",
        translation_placeholders={"number": str(zone)},
        component="sensors",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        # A zone whose sensor drops out reads 0, which is no measurement
        value_fn=lambda device: device.sensors.co2(zone) or None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ComfoConnectProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ComfoConnect PRO sensor platform."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    async_add_entities(
        ComfoConnectProSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )

    @callback
    def _async_add_co2_zones() -> None:
        """Add a CO₂ zone's sensor the first time the zone reports a level."""
        new = set(runtime_data.device.sensors.co2_zones) - runtime_data.wired_co2_zones
        if not new:
            return
        runtime_data.wired_co2_zones.update(new)
        async_add_entities(
            ComfoConnectProSensor(coordinator, co2_sensor(zone)) for zone in sorted(new)
        )

    _async_add_co2_zones()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_co2_zones))


class ComfoConnectProSensor(ComfoConnectProEntity, SensorEntity):
    """Defines a ComfoConnect PRO sensor."""

    entity_description: ComfoConnectProSensorDescription

    @property
    @override
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.device)
