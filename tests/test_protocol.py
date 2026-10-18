"""Parser tests against frames captured from a real Globe Haul ST (2026-10-18)."""

import importlib.util
import pathlib
import sys

_p = pathlib.Path(__file__).parents[1] / "custom_components/globe_ebike/protocol.py"
_spec = importlib.util.spec_from_file_location("globe_protocol", _p)
protocol = importlib.util.module_from_spec(_spec)
sys.modules["globe_protocol"] = protocol
_spec.loader.exec_module(protocol)


def h(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", ""))


P51 = h("33 39 33 00 a0 f7 03 00 d0 dc 02 00 4c 00 29 00 00 00 00 ff")
P52_IDLE = h("34 16 00 00 7a bf ff ff ff ff ff ff 00 00 ff ff ff ff ff ff")
P52_CHARGING = h("34 16 f2 f4 2a c0 ff ff ff ff ff ff 00 00 ff ff ff ff ff ff")
P53 = h("35 ff ff 01 00 ff ff 4f 00 00 00 00 00 ff ff ff ff ff ff ff")
P54 = h("36 05 bb 08 fa 00 00 ff 10 27 ff ff ff ff ff ff ff ff ff ff")
P55 = h("37 03 ff 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ff ff")
P19 = h("13 30 32 2e 30 35 2e 73 30 20 20 20 20 20 20 20 20 ff ff ff")
P11 = h("0b 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 ff ff ff")


def test_page51():
    d = protocol.parse_frame(P51)
    assert d == {"battery_level": 57, "speed": 5.1, "odometer": 260.0,
                 "trip_distance": 187.6, "range": 76, "trip_time": 41}


def test_page52_idle_and_unsupported():
    d = protocol.parse_frame(P52_IDLE)
    assert d["battery_voltage"] == 49.018
    assert d["battery_temperature"] == 22
    assert d["battery_current"] == 0
    assert d["controller_temperature"] is None
    assert d["motor_temperature"] is None


def test_page52_charging_sign():
    d = protocol.parse_frame(P52_CHARGING)
    assert d["battery_current"] == 2.83  # positive = into the battery
    assert d["battery_voltage"] == 49.194


def test_page53_54_55():
    assert protocol.parse_frame(P53)["rider_power"] == 79
    d54 = protocol.parse_frame(P54)
    assert d54["assist_levels"] == 5 and d54["wheel_circumference"] == 2235
    assert d54["speed_limit"] == 25.0 and d54["battery_health"] is None
    d55 = protocol.parse_frame(P55)
    assert d55["assist_mode"] == 3 and d55["light"] is True and d55["error_code"] == 0


def test_strings():
    assert protocol.parse_frame(P19) == {"controller_sw": "02.05.s0"}
    assert protocol.parse_frame(P11) == {"motor_serial_1": None}


def test_concatenated_notification():
    frames = protocol.parse_notification(P51 + P52_CHARGING + P53)
    assert [p for p, _ in frames] == [51, 52, 53]


def test_status():
    assert protocol.parse_status(h("01 00 01 01")) == {
        "awake": True, "locked": False, "charging": True, "imperial_display": True}


def test_state_tracks_supported_and_power():
    s = protocol.GlobeState()
    assert s.update(protocol.parse_frame(P52_CHARGING))
    assert "motor_temperature" not in s.supported
    assert s.values["charging_power"] == round(2.83 * 49.194, 1)
    assert not s.update(protocol.parse_frame(P52_CHARGING))  # no change


def test_commands():
    assert protocol.cmd_loop_pages() == bytes([0x3E, 51, 52, 53] + [0] * 15)
    assert len(protocol.cmd_once_pages(protocol.INFO_PAGES)) == 19
    assert protocol.cmd_light(True) == bytes([7, 1, 0])
