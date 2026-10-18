"""Connection manager for one Globe e-bike.

The bike only accepts one BLE connection, has no pairing, and streams pages
51/52/53 at ~10 Hz once asked. We connect when an advertisement is seen, run the
same start-up sequence as the Globe app, and push throttled updates to entities.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later

from . import protocol
from .const import DOMAIN, PUBLISH_INTERVAL, RECONNECT_COOLDOWN

_LOGGER = logging.getLogger(__name__)


class GlobeDevice:
    """Owns the BLE connection and the latest decoded state."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.state = protocol.GlobeState()
        self.status: dict[str, Any] = {}
        self.info: dict[str, str] = {}
        self.connected = False

        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._last_disconnect = 0.0
        self._listeners: list[Callable[[], None]] = []
        self._new_field_listeners: list[Callable[[set[str]], None]] = []
        self._announced: set[str] = set()
        self._dirty = False
        self._flush_unsub: CALLBACK_TYPE | None = None
        self._unsub_adv: CALLBACK_TYPE | None = None
        self._stopping = False
        self._urgent = False

    # ---- listeners -------------------------------------------------------
    @callback
    def async_add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    @callback
    def async_add_new_field_listener(self, cb: Callable[[set[str]], None]) -> CALLBACK_TYPE:
        self._new_field_listeners.append(cb)
        return lambda: self._new_field_listeners.remove(cb)

    @callback
    def _publish(self, *_: Any) -> None:
        self._flush_unsub = None
        self._dirty = False
        new = self.state.supported - self._announced
        if new:
            self._announced |= new
            for cb in list(self._new_field_listeners):
                cb(new)
        for cb in list(self._listeners):
            cb()

    @callback
    def _schedule_publish(self, immediate: bool = False) -> None:
        if immediate:
            if self._flush_unsub:
                self._flush_unsub()
            self._publish()
            return
        self._dirty = True
        if self._flush_unsub is None:
            self._flush_unsub = async_call_later(self.hass, PUBLISH_INTERVAL, self._publish)

    # ---- lifecycle -------------------------------------------------------
    @callback
    def async_start(self) -> None:
        self._unsub_adv = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        if bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True):
            self._spawn_connect()

    async def async_stop(self) -> None:
        self._stopping = True
        if self._unsub_adv:
            self._unsub_adv()
        if self._flush_unsub:
            self._flush_unsub()
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    @callback
    def _on_advertisement(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        if self.connected or self._connect_lock.locked():
            return
        if time.monotonic() - self._last_disconnect < RECONNECT_COOLDOWN:
            return
        self._spawn_connect()

    @callback
    def _spawn_connect(self) -> None:
        self.hass.async_create_background_task(self._connect(), f"globe_ebike connect {self.address}")

    @callback
    def _on_disconnect(self, _client: BleakClient) -> None:
        _LOGGER.debug("%s disconnected", self.name)
        self.connected = False
        self._client = None
        self._last_disconnect = time.monotonic()
        self.status["awake"] = False
        self._schedule_publish(immediate=True)

    # ---- connection ------------------------------------------------------
    async def _connect(self) -> None:
        if self._stopping:
            return
        async with self._connect_lock:
            if self.connected:
                return
            ble_device: BLEDevice | None = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                return
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    disconnected_callback=self._on_disconnect,
                    max_attempts=3,
                )
                self._client = client
                await self._start_session(client)
            except (BleakError, TimeoutError, asyncio.TimeoutError) as err:
                _LOGGER.debug("%s: connect/setup failed: %s", self.name, err)
                self._last_disconnect = time.monotonic()
                if self._client and self._client.is_connected:
                    await self._client.disconnect()
                self._client = None
                return
            self.connected = True
            _LOGGER.info("%s connected (%s)", self.name, self.info)
            self._update_device_registry()
            self._schedule_publish(immediate=True)

    @callback
    def _update_device_registry(self) -> None:
        reg = dr.async_get(self.hass)
        if dev := reg.async_get_device(identifiers={(DOMAIN, self.address)}):
            reg.async_update_device(
                dev.id,
                model=self.info.get("model"),
                serial_number=self.info.get("serial"),
                sw_version=self.info.get("controller_sw") or self.info.get("sw_version"),
                hw_version=self.info.get("controller_hw") or self.info.get("hw_version"),
            )

    async def _write_cmd(self, client: BleakClient, data: bytes) -> None:
        char = client.services.get_characteristic(protocol.CHAR_CMD)
        await client.write_gatt_char(char, data, response="write" in char.properties)

    async def _start_session(self, client: BleakClient) -> None:
        for key, uuid in protocol.DIS_CHARS.items():
            try:
                raw = await client.read_gatt_char(uuid)
                text = raw.decode("ascii", errors="ignore").strip("\x00 \xff")
                if text:
                    self.info[key] = text
            except BleakError:
                pass

        try:  # bypass mode off (already the default), write-without-response
            await client.write_gatt_char(protocol.CHAR_BYPASS, protocol.cmd_bypass_off(), response=False)
        except BleakError as err:
            _LOGGER.debug("bypass-off write skipped: %s", err)

        await client.start_notify(protocol.CHAR_CMD, self._on_ack)
        await client.start_notify(protocol.CHAR_STATUS, self._on_status)
        self._on_status(None, await client.read_gatt_char(protocol.CHAR_STATUS))
        await self._write_cmd(client, protocol.cmd_mtu_page_mode(True))
        await client.start_notify(protocol.CHAR_DATA, self._on_data)
        await self._write_cmd(client, protocol.cmd_once_pages(protocol.INFO_PAGES))
        await asyncio.sleep(2)
        await self._write_cmd(client, protocol.cmd_once_pages(protocol.CONFIG_PAGES))
        await asyncio.sleep(1)
        await self._write_cmd(client, protocol.cmd_loop_pages())

    # ---- notifications ---------------------------------------------------
    @callback
    def _on_ack(self, _char: Any, data: bytearray) -> None:
        if len(data) == 3 and data[0] == 0x10 and data[2] != 1:
            _LOGGER.debug("%s: command 0x%02x returned status %d", self.name, data[1], data[2])

    @callback
    def _on_status(self, _char: Any, data: bytearray) -> None:
        new = protocol.parse_status(bytes(data))
        if new and new != {k: self.status.get(k) for k in new}:
            self.status.update(new)
            self._schedule_publish(immediate=True)

    @callback
    def _on_data(self, _char: Any, data: bytearray) -> None:
        changed = False
        for page, fields in protocol.parse_notification(bytes(data)):
            if 11 <= page <= 28:
                for key, val in fields.items():
                    if val:
                        self.info[key] = val
                continue
            if page == 55 and fields.get("light") is not None and fields["light"] != self.state.values.get("light"):
                self._urgent = True  # someone toggled the light / assist: show it now
            if page == 55 and fields.get("assist_mode") != self.state.values.get("assist_mode"):
                self._urgent = True
            changed |= self.state.update(fields)
        if changed:
            self._schedule_publish(immediate=self._urgent)
            self._urgent = False

    # ---- commands --------------------------------------------------------
    async def async_send(self, data: bytes) -> None:
        if not self._client or not self.connected:
            raise BleakError("bike not connected")
        # The bike pushes page 55 by itself when assist/light change (seen in capture),
        # so the new state comes back without re-requesting it.
        await self._write_cmd(self._client, data)
