"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN, MANUFACTURER
from .device import GlobeDevice


class GlobeEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: GlobeDevice, description: EntityDescription) -> None:
        self.device = device
        self.entity_description = description
        self._attr_unique_id = f"{device.address}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.device.info
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.address)},
            connections={(CONNECTION_BLUETOOTH, self.device.address)},
            name=self.device.name,
            manufacturer=MANUFACTURER,
            model=info.get("model", "Globe"),
            serial_number=info.get("serial"),
            sw_version=info.get("controller_sw") or info.get("sw_version"),
            hw_version=info.get("controller_hw") or info.get("hw_version"),
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()
