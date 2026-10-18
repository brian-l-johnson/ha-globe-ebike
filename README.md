# Specialized Globe e-bike for Home Assistant

Local Bluetooth integration for Specialized **Globe** bikes (Haul ST/LT and others on the
Xplova / Acer MPS hub-drive system). This is not for Turbo bikes, which have the core
`specialized_turbo` integration.

No cloud, no pairing. It connects through any HA Bluetooth adapter or ESPHome Bluetooth
proxy that has **active connections** enabled.

## What you get
| Entity | Notes |
|---|---|
| Battery % | keeps its last value while the bike sleeps |
| Battery voltage, temperature | |
| Battery charge current, Charging power | live; positive = charging |
| Charging | binary sensor |
| Range, Odometer, Trip distance, Trip time | km internally; HA converts to miles |
| Speed, Rider power, Assist level | live / last value |
| Light | **switch**: toggles the bike's headlight (bike must be awake) |
| Motor lock | binary sensor (on = unlocked) |
| Connected | diagnostic; shows when the bike drops off Bluetooth |
| Error code, Assist speed limit, Wheel circumference | diagnostic |

Entities are created only for fields your bike's controller actually reports. The
supported list is remembered across restarts.

## Install
1. Copy `custom_components/globe_ebike` into your HA `config/custom_components/`, or add
   this repo to HACS as a custom repository.
2. Restart HA.
3. Turn the bike's display on and **close the Globe app on your phone**. The bike allows
   one connection at a time.
4. HA should discover it ("Specialized Globe e-bike"). If not: Settings → Devices &
   services → Add integration → Specialized Globe e-bike.

## Behaviour
- Connects when the bike advertises, then streams. It publishes to HA every 5 s at most
  (the bike sends ~10 frames/s), and status/charging changes publish immediately.
- When the bike sleeps or goes out of range, live sensors go unavailable. It reconnects
  on the next advertisement, with a 30 s cooldown.
- The light is controllable. The protocol also supports assist level and power-off
  (`GlobeDevice.async_send` + `protocol.cmd_*`); those aren't exposed.

## Debug
```yaml
logger:
  logs:
    custom_components.globe_ebike: debug
```

## Protocol
See `android-re-pipeline/findings/globe/PROTOCOL.md`.

## Tests
```bash
pip install pytest-homeassistant-custom-component
pytest            # parser tests + loads the integration in a real HA core
```
