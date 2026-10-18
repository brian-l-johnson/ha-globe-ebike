"""Specialized Globe (Xplova / Acer MPS) BLE protocol.

Pure Python, no Home Assistant imports, so it can be unit tested on its own.
Reference: android-re-pipeline/findings/globe/PROTOCOL.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SERVICE_UUID = "00010000-452d-4269-6b65-58706c6f7661"
CHAR_DATA = "00010001-452d-4269-6b65-58706c6f7661"  # notify: 20-byte pages
CHAR_STATUS = "00010004-452d-4269-6b65-58706c6f7661"  # read/notify: 4-byte status
CHAR_CMD = "00010010-452d-4269-6b65-58706c6f7661"  # write + indicate
CHAR_BYPASS = "00010011-452d-4269-6b65-58706c6f7661"  # write without response

DIS_CHARS = {
    "model": "00002a24-0000-1000-8000-00805f9b34fb",
    "serial": "00002a25-0000-1000-8000-00805f9b34fb",
    "hw_version": "00002a27-0000-1000-8000-00805f9b34fb",
    "sw_version": "00002a28-0000-1000-8000-00805f9b34fb",
}

# Globe bikes advertise only flags + appearance (0x0480 cycling) + name "EH0x_nnnnn".
# The service UUID is in the scan response, which passive scanners never see.
NAME_PREFIX = "EH0"


def is_globe(name: str | None, service_uuids: list[str] | None) -> bool:
    if SERVICE_UUID in [u.lower() for u in (service_uuids or [])]:
        return True
    return bool(name) and name.startswith(NAME_PREFIX) and "_" in name


FRAME_LEN = 20

OP_MTU_PAGE_MODE = 0x3C
OP_ONCE_PAGE = 0x3D
OP_LOOP_PAGE = 0x3E
OP_BYPASS = 0x1E
OP_ASSIST = 0x01
OP_LIGHT = 0x07

LOOP_PAGES = (51, 52, 53)
INFO_PAGES = tuple(range(11, 29))
CONFIG_PAGES = (54, 55)

WALK_MODE = 255


def cmd_bypass_off() -> bytes:
    return bytes([OP_BYPASS, 0])


def cmd_mtu_page_mode(on: bool = True) -> bytes:
    return bytes([OP_MTU_PAGE_MODE, 1 if on else 0])


def _page_request(op: int, pages: tuple[int, ...] | list[int]) -> bytes:
    ids = list(pages)[:18]
    return bytes([op, *ids] + [0] * (18 - len(ids)))


def cmd_once_pages(pages) -> bytes:
    return _page_request(OP_ONCE_PAGE, pages)


def cmd_loop_pages(pages=LOOP_PAGES) -> bytes:
    return _page_request(OP_LOOP_PAGE, pages)


def cmd_assist(level: int) -> bytes:
    return bytes([OP_ASSIST, level & 0xFF])


def cmd_light(on: bool) -> bytes:
    return bytes([OP_LIGHT, 1 if on else 0, 0])


def _u(buf: bytes, off: int, size: int, signed: bool = False) -> int | None:
    """Little-endian int; all-0xFF (unsigned) means 'not supported'."""
    if off + size > len(buf):
        return None
    raw = buf[off : off + size]
    if not signed and raw == b"\xff" * size:
        return None
    val = int.from_bytes(raw, "little", signed=signed)
    if signed and val == -1:
        return None
    return val


def _scaled(val: int | None, div: float) -> float | None:
    return None if val is None else round(val / div, 3)


def _str(buf: bytes) -> str | None:
    s = buf[1:17].split(b"\xff")[0].decode("ascii", errors="ignore").strip("\x00 ")
    return s or None


_STRING_PAGES = {
    11: "motor_serial_1",
    12: "motor_serial_2",
    13: "motor_model",
    14: "motor_sw",
    15: "motor_hw",
    16: "controller_serial_1",
    17: "controller_serial_2",
    18: "controller_model",
    19: "controller_sw",
    20: "controller_hw",
    21: "battery_serial_1",
    22: "battery_serial_2",
    23: "battery_model",
    24: "battery_sw",
    25: "battery_hw",
    26: "motor_manufacturer",
    27: "controller_manufacturer",
    28: "battery_manufacturer",
}


def parse_frame(frame: bytes) -> dict[str, Any]:
    """Decode one 20-byte page into a dict of field -> value (None = unsupported)."""
    if len(frame) < FRAME_LEN:
        return {}
    page = frame[0]
    if page == 51:
        return {
            "battery_level": _u(frame, 1, 1),
            "speed": _scaled(_u(frame, 2, 2), 10),  # km/h
            "odometer": _scaled(_u(frame, 4, 4), 1000),  # km
            "trip_distance": _scaled(_u(frame, 8, 4), 1000),  # km
            "range": _u(frame, 12, 2),  # km
            "trip_time": _u(frame, 14, 4),  # s
        }
    if page == 52:
        current = _u(frame, 2, 2, signed=True)
        return {
            "battery_temperature": _u(frame, 1, 1),  # °C
            # Bike reports mA, negative = charging. Expose as A, positive = charging.
            "battery_current": None if current is None else round(-current / 1000, 3),
            "battery_voltage": _scaled(_u(frame, 4, 2), 1000),  # V
            "controller_temperature": _u(frame, 8, 1),
            "motor_temperature": _u(frame, 9, 1),
            "motor_rpm": _u(frame, 12, 2),
        }
    if page == 53:
        return {
            "torque": _scaled(_u(frame, 3, 2), 10),
            "rider_power": _u(frame, 7, 4),
        }
    if page == 54:
        return {
            "assist_levels": _u(frame, 1, 1),
            "wheel_circumference": _u(frame, 2, 2),  # mm
            "speed_limit": _scaled(_u(frame, 4, 2), 10),  # km/h
            "battery_health": _u(frame, 7, 1),
            "full_charge_capacity": _u(frame, 8, 2),
            "charge_cycles": _u(frame, 10, 2),
        }
    if page == 55:
        assist = _u(frame, 1, 1)
        return {
            "assist_mode": None if assist is None else ("walk" if assist == WALK_MODE else assist),
            "light": None if (v := _u(frame, 3, 1)) is None else v == 1,
            "error_code": (
                int.from_bytes(frame[8:12], "little")
                | (_u(frame, 12, 2) or 0)
                | (_u(frame, 14, 2) or 0)
                | (_u(frame, 16, 2) or 0)
            ),
            "controller_error": _u(frame, 12, 2),
            "battery_error": _u(frame, 14, 2),
            "motor_error": _u(frame, 16, 2),
        }
    if page in _STRING_PAGES:
        return {_STRING_PAGES[page]: _str(frame)}
    return {}


def parse_notification(data: bytes) -> list[tuple[int, dict[str, Any]]]:
    """A notification may hold several 20-byte frames back to back."""
    out = []
    for i in range(0, len(data) - len(data) % FRAME_LEN, FRAME_LEN):
        frame = bytes(data[i : i + FRAME_LEN])
        out.append((frame[0], parse_frame(frame)))
    return out


def parse_status(data: bytes) -> dict[str, Any]:
    if len(data) < 4:
        return {}
    return {
        "awake": data[0] != 0,
        "locked": data[1] == 1,
        "charging": data[2] == 1,
        "imperial_display": data[3] == 1,
    }


@dataclass
class GlobeState:
    """Latest known values. Unsupported fields stay out of `values`."""

    values: dict[str, Any] = field(default_factory=dict)
    supported: set[str] = field(default_factory=set)

    def update(self, fields: dict[str, Any]) -> bool:
        changed = False
        for key, val in fields.items():
            if val is None:
                continue
            self.supported.add(key)
            if self.values.get(key) != val:
                self.values[key] = val
                changed = True
        if "battery_current" in fields or "battery_voltage" in fields:
            cur, volt = self.values.get("battery_current"), self.values.get("battery_voltage")
            if cur is not None and volt is not None:
                power = round(max(cur, 0) * volt, 1)
                if self.values.get("charging_power") != power:
                    self.values["charging_power"] = power
                    self.supported.add("charging_power")
                    changed = True
        return changed
