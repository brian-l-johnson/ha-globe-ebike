"""Load the integration in a real HA core and feed it frames captured from the bike."""
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

DOMAIN = "globe_ebike"
ADDR = "AA:BB:CC:DD:EE:FF"
h = lambda s: bytearray.fromhex(s.replace(" ", ""))

P51 = h("33 39 33 00 a0 f7 03 00 d0 dc 02 00 4c 00 29 00 00 00 00 ff")
P52 = h("34 16 f2 f4 2a c0 ff ff ff ff ff ff 00 00 ff ff ff ff ff ff")
P53 = h("35 ff ff 01 00 ff ff 4f 00 00 00 00 00 ff ff ff ff ff ff ff")
P54 = h("36 05 bb 08 fa 00 00 ff 10 27 ff ff ff ff ff ff ff ff ff ff")
P55 = h("37 03 ff 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ff ff")


@pytest.fixture
def no_bt():
    import custom_components.globe_ebike.device  # noqa: F401  (so patch() can resolve it)
    with patch("custom_components.globe_ebike.device.GlobeDevice.async_start"), \
         patch("homeassistant.loader.Integration.dependencies", new=[]):
        yield


async def test_entities_from_frames(hass: HomeAssistant, enable_custom_integrations, no_bt) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, data={"address": ADDR, "name": "EH02_36839"},
                            title="EH02_36839")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    dev = entry.runtime_data
    dev.connected = True
    dev._on_status(None, h("01 00 01 01"))
    dev._on_data(None, P51 + P52 + P53)   # concatenated notification
    dev._on_data(None, P54)
    dev._on_data(None, P55)
    dev._publish()                        # skip the 5 s throttle
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all()}
    for eid, s in sorted(states.items()):
        print(eid, s.state, s.attributes.get("unit_of_measurement"))

    def st(suffix):
        return next(s for e, s in states.items() if e.endswith(suffix))

    assert st("sensor.eh02_36839_battery").state == "57"
    assert float(st("battery_voltage").state) == pytest.approx(49.194)
    assert float(st("battery_charge_current").state) == pytest.approx(2.83)
    assert st("binary_sensor.eh02_36839_charging").state == "on"
    assert st("binary_sensor.eh02_36839_motor_lock").state == "on"  # on = unlocked
    assert st("assist_level").state == "3"
    assert not any(e.endswith("motor_temperature") for e in states)  # unsupported → no entity
    assert set(entry.data["supported_fields"]) >= {"battery_level", "odometer", "assist_mode"}

    # bike goes to sleep: live values go unavailable, battery % stays
    dev._on_disconnect(None)
    await hass.async_block_till_done()
    assert hass.states.get(st("battery_charge_current").entity_id).state == STATE_UNAVAILABLE
    assert hass.states.get(st("sensor.eh02_36839_battery").entity_id).state == "57"
    assert hass.states.get(st("connected").entity_id).state == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)
