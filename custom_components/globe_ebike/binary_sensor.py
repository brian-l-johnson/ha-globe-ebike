"""Binary sensors: connected, charging, lock, light."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GlobeConfigEntry
from .device import GlobeDevice
from .entity import GlobeEntity


@dataclass(frozen=True, kw_only=True)
class GlobeBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[GlobeDevice], bool | None]
    always_available: bool = False


BINARY: tuple[GlobeBinaryDescription, ...] = (
    GlobeBinaryDescription(
        key="connected", name="Connected", device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC, always_available=True,
        value_fn=lambda d: d.connected,
    ),
    GlobeBinaryDescription(
        key="charging", name="Charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.get("charging"),
    ),
    GlobeBinaryDescription(
        # HA lock class: on = unlocked
        key="motor_lock", name="Motor lock", device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda d: None if d.status.get("locked") is None else not d.status["locked"],
    ),
    GlobeBinaryDescription(
        key="light", name="Light", device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=lambda d: d.state.values.get("light"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GlobeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(GlobeBinarySensor(entry.runtime_data, d) for d in BINARY)


class GlobeBinarySensor(GlobeEntity, BinarySensorEntity):
    entity_description: GlobeBinaryDescription

    @property
    def available(self) -> bool:
        return self.entity_description.always_available or self.device.connected

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.device)
