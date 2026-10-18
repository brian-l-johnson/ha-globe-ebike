"""Sensors. Created for whichever fields this bike's controller actually reports."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GlobeConfigEntry
from .const import CONF_SUPPORTED
from .device import GlobeDevice
from .entity import GlobeEntity

M = SensorStateClass.MEASUREMENT


@dataclass(frozen=True, kw_only=True)
class GlobeSensorDescription(SensorEntityDescription):
    # Live values only mean something while connected (speed, current…). Others keep
    # their last value while the bike sleeps, which is what you want for battery % at home.
    live: bool = False


SENSORS: tuple[GlobeSensorDescription, ...] = (
    GlobeSensorDescription(key="battery_level", name="Battery", device_class=SensorDeviceClass.BATTERY,
                           native_unit_of_measurement=PERCENTAGE, state_class=M),
    GlobeSensorDescription(key="battery_voltage", name="Battery voltage", device_class=SensorDeviceClass.VOLTAGE,
                           native_unit_of_measurement=UnitOfElectricPotential.VOLT, state_class=M,
                           suggested_display_precision=2),
    GlobeSensorDescription(key="battery_current", name="Battery current", device_class=SensorDeviceClass.CURRENT,
                           native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, state_class=M,
                           suggested_display_precision=2, live=True),
    GlobeSensorDescription(key="charging_power", name="Charging power", device_class=SensorDeviceClass.POWER,
                           native_unit_of_measurement=UnitOfPower.WATT, state_class=M,
                           suggested_display_precision=0, live=True),
    GlobeSensorDescription(key="battery_temperature", name="Battery temperature",
                           device_class=SensorDeviceClass.TEMPERATURE,
                           native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=M),
    GlobeSensorDescription(key="range", name="Range", device_class=SensorDeviceClass.DISTANCE,
                           native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=M,
                           suggested_display_precision=0),
    GlobeSensorDescription(key="speed", name="Speed", device_class=SensorDeviceClass.SPEED,
                           native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR, state_class=M,
                           suggested_display_precision=1, live=True),
    GlobeSensorDescription(key="odometer", name="Odometer", device_class=SensorDeviceClass.DISTANCE,
                           native_unit_of_measurement=UnitOfLength.KILOMETERS,
                           state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=0),
    GlobeSensorDescription(key="trip_distance", name="Trip distance", device_class=SensorDeviceClass.DISTANCE,
                           native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=M,
                           suggested_display_precision=1),
    GlobeSensorDescription(key="trip_time", name="Trip time", device_class=SensorDeviceClass.DURATION,
                           native_unit_of_measurement=UnitOfTime.SECONDS, state_class=M,
                           suggested_unit_of_measurement=UnitOfTime.HOURS, suggested_display_precision=2),
    GlobeSensorDescription(key="rider_power", name="Rider power", device_class=SensorDeviceClass.POWER,
                           native_unit_of_measurement=UnitOfPower.WATT, state_class=M, live=True),
    GlobeSensorDescription(key="assist_mode", name="Assist level", icon="mdi:bicycle-electric"),
    GlobeSensorDescription(key="controller_temperature", name="Controller temperature",
                           device_class=SensorDeviceClass.TEMPERATURE,
                           native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=M, live=True),
    GlobeSensorDescription(key="motor_temperature", name="Motor temperature",
                           device_class=SensorDeviceClass.TEMPERATURE,
                           native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=M, live=True),
    GlobeSensorDescription(key="battery_health", name="Battery health", native_unit_of_measurement=PERCENTAGE,
                           state_class=M, entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:battery-heart"),
    GlobeSensorDescription(key="charge_cycles", name="Charge cycles", state_class=SensorStateClass.TOTAL_INCREASING,
                           entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:battery-sync"),
    GlobeSensorDescription(key="error_code", name="Error code", entity_category=EntityCategory.DIAGNOSTIC,
                           icon="mdi:alert-circle-outline"),
    GlobeSensorDescription(key="speed_limit", name="Assist speed limit", device_class=SensorDeviceClass.SPEED,
                           native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
                           entity_category=EntityCategory.DIAGNOSTIC),
    GlobeSensorDescription(key="wheel_circumference", name="Wheel circumference",
                           device_class=SensorDeviceClass.DISTANCE,
                           native_unit_of_measurement=UnitOfLength.MILLIMETERS,
                           entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False),
)
BY_KEY = {d.key: d for d in SENSORS}


async def async_setup_entry(
    hass: HomeAssistant, entry: GlobeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device = entry.runtime_data
    added: set[str] = set()

    @callback
    def _add(keys: set[str]) -> None:
        new = [GlobeSensor(device, BY_KEY[k]) for k in keys if k in BY_KEY and k not in added]
        added.update(e.entity_description.key for e in new)
        if new:
            async_add_entities(new)

    _add(set(entry.data.get(CONF_SUPPORTED, [])) | {"battery_level"})
    entry.async_on_unload(device.async_add_new_field_listener(_add))


class GlobeSensor(GlobeEntity, RestoreSensor):
    entity_description: GlobeSensorDescription

    def __init__(self, device: GlobeDevice, description: GlobeSensorDescription) -> None:
        super().__init__(device, description)
        self._restored = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self.entity_description.live and (last := await self.async_get_last_sensor_data()):
            self._restored = last.native_value

    @property
    def available(self) -> bool:
        if self.entity_description.live:
            return self.device.connected
        return self.native_value is not None

    @property
    def native_value(self):
        val = self.device.state.values.get(self.entity_description.key)
        return self._restored if val is None else val
