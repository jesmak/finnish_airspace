"""Finnish Airspace: the airspace restrictions in force in Finland, from Fintraffic ANS's NOTAMs and the AIP.

One config entry covers the whole country, so there is nothing to set up. The areas read from the AIP and the memory
of the areas already announced are kept in its storage.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AirspaceConfigEntry, AirspaceCoordinator, memory_store

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AirspaceConfigEntry) -> bool:
    coordinator = AirspaceCoordinator(hass, entry)
    await coordinator.async_load()
    # Not the first refresh that fails setup: Home Assistant would retry setup within seconds, and keep calling ais.fi
    # every few minutes while it's down. The sensor is unavailable until the next update succeeds instead.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_save)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AirspaceConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: AirspaceConfigEntry) -> None:
    await memory_store(hass).async_remove()
