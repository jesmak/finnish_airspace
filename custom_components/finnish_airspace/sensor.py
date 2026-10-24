"""The map feed: the areas in force and those starting within a day, for map-feed-card."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MAP_FEED_VERSION, TITLE
from .coordinator import AirspaceConfigEntry, AirspaceCoordinator
from .feed import feature


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirspaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MapFeedSensor(entry.runtime_data)])


class MapFeedSensor(CoordinatorEntity[AirspaceCoordinator], SensorEntity):
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    # The device's name: the integration has this one entity.
    _attr_name = None
    _attr_icon = "mdi:airplane-alert"
    # The feed and the lists of NOTAMs can be long: only the count goes to the database.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: AirspaceCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_map"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=TITLE,
            manufacturer="Fintraffic ANS",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.ais.fi",
        )

    @property
    def native_value(self) -> int:
        return sum(item.in_feed for item in self.coordinator.data.items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "map_feed_version": MAP_FEED_VERSION,
            "feed_type": "air",
            "updated": data.updated.isoformat(timespec="seconds"),
            "geojson": {"type": "FeatureCollection", "features": [feature(item) for item in data.items if item.in_feed]},
            # So a mismatch shows instead of vanishing.
            "not_found": [{"notam": notam.id, "codes": codes} for notam, codes in data.not_found],
            "without_act": [{"notam": notam.id, "codes": notam.codes, "text": notam.text} for notam in data.without_act],
            "failed": data.failed,
            "missed": data.missed,
        }
