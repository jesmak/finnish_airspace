"""Finnish Airspace: the airspace restrictions in force in Finland, from Fintraffic ANS's NOTAMs and the AIP.

One config entry covers the whole country, so there is nothing to set up.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
