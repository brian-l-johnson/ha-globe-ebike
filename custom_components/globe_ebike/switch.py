"""Light switch. The bike echoes the new state back on page 55, which confirms it."""

from __future__ import annotations

from typing import Any

from bleak.exc import BleakError

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GlobeConfigEntry
from .entity import GlobeEntity
from .protocol import cmd_light

LIGHT = SwitchEntityDescription(key="light", name="Light", icon="mdi:car-light-high")


async def async_setup_entry(
    hass: HomeAssistant, entry: GlobeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([GlobeLightSwitch(entry.runtime_data, LIGHT)])


class GlobeLightSwitch(GlobeEntity, SwitchEntity):
    @property
    def available(self) -> bool:
        return self.device.connected

    @property
    def is_on(self) -> bool | None:
        return self.device.state.values.get("light")

    async def _set(self, on: bool) -> None:
        try:
            await self.device.async_send(cmd_light(on))
        except BleakError as err:
            raise HomeAssistantError(f"Couldn't reach the bike: {err}") from err
        # Optimistic until the bike's page-55 echo arrives (normally < 1 s).
        self.device.state.values["light"] = on
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
