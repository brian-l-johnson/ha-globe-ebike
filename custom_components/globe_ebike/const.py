"""Constants for the Specialized Globe e-bike integration."""

DOMAIN = "globe_ebike"
MANUFACTURER = "Specialized"

# The bike streams ~10 frames/s per page. Push to HA at most this often.
PUBLISH_INTERVAL = 5.0
# After a disconnect, wait this long before trying again on the next advertisement.
RECONNECT_COOLDOWN = 30.0

CONF_SUPPORTED = "supported_fields"

SIGNAL_NEW_FIELDS = f"{DOMAIN}_new_fields_{{}}"
