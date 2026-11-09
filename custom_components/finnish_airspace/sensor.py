"""The map feed: the areas in force and those starting within a day, for map-feed-card."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, BORDER_ATTRIBUTION, DOMAIN, MAP_FEED_VERSION, TITLE
from .coordinator import AirspaceConfigEntry, AirspaceCoordinator
from .map_feed import feature, feed_attributes, language_of, standing_attributes, standing_feature


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirspaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MapFeedSensor(entry.runtime_data), PermanentFeedSensor(entry.runtime_data)])


class AirspaceSensor(CoordinatorEntity[AirspaceCoordinator], SensorEntity):
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    # The feeds can be long: only the count goes to the database.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: AirspaceCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=TITLE,
            manufacturer="Fintraffic ANS",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.ais.fi",
        )


class PermanentFeedSensor(AirspaceSensor):
    """The areas in force without a NOTAM, as a feed of their own, so a card can keep them out of its list."""

    _attr_translation_key = "permanent_areas"
    _attr_icon = "mdi:shield-airplane-outline"
    _attr_attribution = f"{ATTRIBUTION} · {BORDER_ATTRIBUTION}"

    def __init__(self, coordinator: AirspaceCoordinator) -> None:
        super().__init__(coordinator, "permanent")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.standing)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        language = language_of(self.hass.config.language)
        return {
            "map_feed_version": MAP_FEED_VERSION,
            "feed_type": "air",
            **standing_attributes(language),
            "geojson": {"type": "FeatureCollection", "features": [standing_feature(standing, language) for standing in data.standing]},
            # So an area the border line couldn't draw shows instead of vanishing.
            "incomplete": data.standing_incomplete,
        }


class MapFeedSensor(AirspaceSensor):
    # Named by the device, as the integration's main feed.
    _attr_name = None
    _attr_icon = "mdi:airplane-alert"

    def __init__(self, coordinator: AirspaceCoordinator) -> None:
        super().__init__(coordinator, "map")

    @property
    def native_value(self) -> int:
        return sum(item.in_feed for item in self.coordinator.data.items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        language = language_of(self.hass.config.language)
        zone = dt_util.get_default_time_zone()
        features = [feature(item, language, data.updated, zone) for item in data.items if item.in_feed]
        return {
            "map_feed_version": MAP_FEED_VERSION,
            "feed_type": "air",
            **feed_attributes(language),
            "updated": data.updated.isoformat(timespec="seconds"),
            "geojson": {"type": "FeatureCollection", "features": features},
            # So a mismatch shows instead of vanishing.
            "not_found": [{"notam": notam.id, "codes": codes} for notam, codes in data.not_found],
            "without_act": [{"notam": notam.id, "codes": notam.codes, "text": notam.text} for notam in data.without_act],
            "failed": data.failed,
            "missed": data.missed,
        }
