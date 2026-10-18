"""Specialized Globe e-bike (Xplova/Acer MPS drive) over Bluetooth."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback

from .const import CONF_SUPPORTED
from .device import GlobeDevice

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type GlobeConfigEntry = ConfigEntry[GlobeDevice]


async def async_setup_entry(hass: HomeAssistant, entry: GlobeConfigEntry) -> bool:
    device = GlobeDevice(hass, entry.data[CONF_ADDRESS], entry.data.get(CONF_NAME, entry.title))
    entry.runtime_data = device

    @callback
    def _remember_fields(new: set[str]) -> None:
        """Persist which fields this bike supports, so entities exist after a restart."""
        known = set(entry.data.get(CONF_SUPPORTED, []))
        if not new <= known:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_SUPPORTED: sorted(known | new)}
            )

    entry.async_on_unload(device.async_add_new_field_listener(_remember_fields))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    device.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GlobeConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok
