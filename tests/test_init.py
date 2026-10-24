"""The integration in Home Assistant, with ais.fi mocked: the feed, the event, polling and the memory across restarts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.finnish_airspace.const import BULLETIN_URL, DOMAIN, ENR_5_1_URL, EVENT_NEW_RESTRICTION, SUPPLEMENT_URL
from custom_components.finnish_airspace.coordinator import AirspaceCoordinator

from .pages import page, pdf, row, table

NOW = datetime(2026, 11, 2, 10, 5, tzinfo=UTC)
SUPPLEMENT = SUPPLEMENT_URL.format(year=2026, airac="", number=77)
ENTITY = "sensor.finnish_airspace"

ENR_5_1 = (
    "<html><body><table>"
    + row("EFR901 HONKANIEMI", "650000N 0260000E - 650000N 0261000E - 645000N 0261000E", "FL 240", "SFC")
    + row("EFD903 SALOKANGAS", "640000N 0250000E - 640000N 0251000E - 635000N 0251000E", "FL 95", "SFC")
    + "</table></body></html>"
)
SUPPLEMENT_PDF = pdf(
    [
        "EFD905A KORPIVAARA",
        "630000N 0270000E - 630000N 0271000E -",
        "625000N 0271000E - 630000N 0270000E",
        "FL 70",
        "1600 FT MSL UAV",
    ]
)

RESTRICTED = table(["EFR901 HONKANIEMI ACT."], "A9001/26", "02NOV26 0900", "02NOV26 1500", "SFC", "FL170")
DANGER = table(
    ["TEMPO DANGER AREA EFD905A KORPIVAARA ACT.", "REF AIP SUP 077/2026"], "A9002/26", "02NOV26 0600", "03NOV26 1500", "SFC", "FL070"
)
UNKNOWN = table(["EFR999 TAKAMAA ACT."], "A9003/26", "02NOV26 0900", "02NOV26 1500", "SFC", "FL100")
NEW_AREA = table(
    ["TEMPO RESTRICTED AREA EFR1901 ESTABLISHED AND ACT.", "PSN 640000N 0270000E, RADIUS 2KM"], "A9004/26", "02NOV26 1000", "02NOV26 1800"
)
ALL_MONTH = table(["EFR901 HONKANIEMI ACT."], "A9005/26", "02NOV26 0900", "30NOV26 1500", "SFC", "FL170")
AGAIN = table(["EFR901 HONKANIEMI ACT."], "A9101/26", "02NOV26 1100", "02NOV26 1500", "SFC", "FL170")


@pytest.fixture(autouse=True)
def frozen(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


def answer(
    aioclient_mock: AiohttpClientMocker,
    *notams: str,
    next_update: str = "1030",
    bulletin_status: int = 200,
    enr_status: int = 200,
    last_modified: str = "Mon, 02 Nov 2026 09:31:22 GMT",
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        BULLETIN_URL,
        status=bulletin_status,
        text=page(*notams, next_update=next_update),
        headers={"ETag": '"b1"', "Last-Modified": last_modified},
    )
    aioclient_mock.get(ENR_5_1_URL, status=enr_status, text=ENR_5_1, headers={"ETag": '"e1"'})
    aioclient_mock.get(SUPPLEMENT, content=SUPPLEMENT_PDF)


def fetched(aioclient_mock: AiohttpClientMocker) -> list[str]:
    return [str(call[1]) for call in aioclient_mock.mock_calls]


async def set_up(hass: HomeAssistant) -> MockConfigEntry:
    hass.config.latitude, hass.config.longitude = 64.5, 26.0
    entry = MockConfigEntry(domain=DOMAIN, title="Finnish Airspace", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def refresh(hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory, minutes: int = 30) -> None:
    freezer.tick(timedelta(minutes=minutes))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_the_feed_after_the_first_poll(enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    events = async_capture_events(hass, EVENT_NEW_RESTRICTION)
    answer(aioclient_mock, RESTRICTED, DANGER, UNKNOWN, NEW_AREA)
    entry = await set_up(hass)

    # The first poll fills the memory without events.
    assert events == []
    assert sorted(fetched(aioclient_mock)) == sorted([BULLETIN_URL, ENR_5_1_URL, SUPPLEMENT])
    state = hass.states.get(ENTITY)
    assert state.state == "3"
    assert state.attributes["map_feed_version"] == 1
    assert state.attributes["feed_type"] == "air"
    assert state.attributes["attribution"] == "Fintraffic ANS, ais.fi"
    features = state.attributes["geojson"]["features"]
    assert [feature["id"] for feature in features] == ["area:EFR901", "area:EFD905A", "area:EFR1901"]
    assert features[1]["properties"]["notams"][0]["upper"] == "FL 70"
    assert state.attributes["not_found"] == [{"notam": "A9003/26", "codes": ["EFR999"]}]
    assert (state.attributes["without_act"], state.attributes["failed"], state.attributes["missed"]) == ([], [], [])
    # 10:30 is the next update.
    assert entry.runtime_data.update_interval == timedelta(minutes=28)


async def test_a_new_restricted_area_fires_the_event_once(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, DANGER)
    entry = await set_up(hass)
    events = async_capture_events(hass, EVENT_NEW_RESTRICTION)

    answer(aioclient_mock, DANGER, RESTRICTED, NEW_AREA)
    await refresh(hass, entry, freezer)

    assert [event.data["notam"] for event in events] == ["A9001/26", "A9004/26"]
    assert events[0].data["codes"] == ["EFR901"]
    assert events[0].data["upper"] == "FL 170"
    # To its corner 645000N 0261000E: 37.1 km north and 8.0 km east.
    assert events[0].data["distance_km"] == 38.0
    assert events[1].data["new_area"] is True

    # Issued again under a new id: not news.
    answer(aioclient_mock, DANGER, AGAIN, NEW_AREA)
    await refresh(hass, entry, freezer)

    assert len(events) == 2


async def test_the_memory_across_a_reload(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED, DANGER)
    entry = await set_up(hass)
    events = async_capture_events(hass, EVENT_NEW_RESTRICTION)

    answer(aioclient_mock, RESTRICTED, DANGER, NEW_AREA)
    freezer.tick(timedelta(minutes=30))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # Only the area not seen before the reload is news.
    assert [event.data["notam"] for event in events] == ["A9004/26"]
    # The areas read from the AIP are kept, so only the bulletin is fetched.
    assert fetched(aioclient_mock) == [BULLETIN_URL]
    assert hass.states.get(ENTITY).state == "3"


async def test_the_memory_written_when_home_assistant_stops(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED, DANGER)
    entry = await set_up(hass)
    # A restart doesn't unload the entry: the polls stop, and the memory is written by the store's last write as Home
    # Assistant stops.
    await entry.runtime_data.async_shutdown()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    events = async_capture_events(hass, EVENT_NEW_RESTRICTION)

    started_again = AirspaceCoordinator(hass, entry)
    await started_again.async_load()
    answer(aioclient_mock, RESTRICTED, DANGER, NEW_AREA)
    freezer.tick(timedelta(minutes=30))
    await started_again.async_refresh()
    await hass.async_block_till_done()

    assert [event.data["notam"] for event in events] == ["A9004/26"]
    assert fetched(aioclient_mock) == [BULLETIN_URL]


async def test_a_supplement_no_notam_names_for_30_days_is_dropped(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, DANGER)
    entry = await set_up(hass)
    assert entry.runtime_data.supplements

    answer(aioclient_mock, RESTRICTED)
    await refresh(hass, entry, freezer, minutes=29 * 24 * 60)
    assert entry.runtime_data.supplements

    answer(aioclient_mock, RESTRICTED)
    await refresh(hass, entry, freezer, minutes=2 * 24 * 60)
    assert entry.runtime_data.supplements == {}


async def test_the_aip_once_a_day_and_each_supplement_once(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, DANGER)
    entry = await set_up(hass)

    answer(aioclient_mock, DANGER)
    await refresh(hass, entry, freezer)
    assert fetched(aioclient_mock) == [BULLETIN_URL]

    answer(aioclient_mock, DANGER)
    await refresh(hass, entry, freezer, minutes=24 * 60)
    assert fetched(aioclient_mock) == [BULLETIN_URL, ENR_5_1_URL]
    assert aioclient_mock.mock_calls[1][3]["If-None-Match"] == '"e1"'


async def test_an_unchanged_bulletin_is_not_read_again(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED)
    entry = await set_up(hass)

    aioclient_mock.clear_requests()
    aioclient_mock.get(BULLETIN_URL, status=304)
    await refresh(hass, entry, freezer)

    assert aioclient_mock.mock_calls[0][3]["If-None-Match"] == '"b1"'
    assert hass.states.get(ENTITY).state == "1"


async def test_an_older_bulletin_from_the_cdn_is_ignored(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED, last_modified="Mon, 02 Nov 2026 10:01:23 GMT")
    entry = await set_up(hass)

    answer(aioclient_mock, RESTRICTED, DANGER, next_update="1000", last_modified="Mon, 02 Nov 2026 09:31:22 GMT")
    await refresh(hass, entry, freezer, minutes=3)
    assert hass.states.get(ENTITY).state == "1"
    # The page kept still says 10:30.
    assert entry.runtime_data.update_interval == timedelta(minutes=25)

    answer(aioclient_mock, RESTRICTED, DANGER, next_update="1100", last_modified="Mon, 02 Nov 2026 10:31:22 GMT")
    await refresh(hass, entry, freezer, minutes=25)
    assert hass.states.get(ENTITY).state == "2"

    # The first page again, from a node still further behind: older than the one read last.
    answer(aioclient_mock, RESTRICTED, last_modified="Mon, 02 Nov 2026 10:01:23 GMT")
    await refresh(hass, entry, freezer, minutes=3)
    assert hass.states.get(ENTITY).state == "2"


async def test_unavailable_until_the_bulletin_can_be_read_at_setup(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_NEW_RESTRICTION)
    answer(aioclient_mock, RESTRICTED, bulletin_status=500)
    entry = await set_up(hass)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE

    answer(aioclient_mock, RESTRICTED)
    await refresh(hass, entry, freezer)
    assert hass.states.get(ENTITY).state == "1"
    # The first poll that worked fills the memory without events.
    assert events == []


async def test_a_failing_source_warns_once_until_it_works_again(
    enable_custom_integrations,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def warnings() -> int:
        return sum(1 for record in caplog.records if record.levelno == logging.WARNING and "ENR 5.1" in record.getMessage())

    answer(aioclient_mock, ALL_MONTH, enr_status=500)
    entry = await set_up(hass)
    assert warnings() == 1

    answer(aioclient_mock, ALL_MONTH, enr_status=500)
    await refresh(hass, entry, freezer)
    assert warnings() == 1

    answer(aioclient_mock, ALL_MONTH)
    await refresh(hass, entry, freezer)
    assert [record.levelno for record in caplog.records if "ENR 5.1 could be read again" in record.getMessage()] == [logging.INFO]

    answer(aioclient_mock, ALL_MONTH, enr_status=500)
    await refresh(hass, entry, freezer, minutes=24 * 60)
    assert warnings() == 2
    # The areas read before stay.
    state = hass.states.get(ENTITY)
    assert (state.state, state.attributes["not_found"]) == ("1", [])

    # Tried again at the next poll, which finds it unchanged: working again all the same.
    answer(aioclient_mock, ALL_MONTH, enr_status=304)
    await refresh(hass, entry, freezer)
    assert ENR_5_1_URL in fetched(aioclient_mock)
    assert [record.levelno for record in caplog.records if "ENR 5.1 could be read again" in record.getMessage()] == [
        logging.INFO,
        logging.INFO,
    ]

    answer(aioclient_mock, ALL_MONTH, enr_status=500)
    await refresh(hass, entry, freezer, minutes=24 * 60)
    assert warnings() == 3


async def test_unavailable_when_the_bulletin_cant_be_read(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED)
    entry = await set_up(hass)

    answer(aioclient_mock, RESTRICTED, bulletin_status=500)
    await refresh(hass, entry, freezer)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE

    # A page without NOTAMs is not an empty sky.
    answer(aioclient_mock)
    await refresh(hass, entry, freezer)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE

    answer(aioclient_mock, RESTRICTED)
    await refresh(hass, entry, freezer)
    assert hass.states.get(ENTITY).state == "1"


async def test_without_enr_5_1_its_areas_are_not_found(
    enable_custom_integrations, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    answer(aioclient_mock, RESTRICTED, DANGER, enr_status=500)
    entry = await set_up(hass)

    state = hass.states.get(ENTITY)
    assert state.state == "1"
    assert state.attributes["not_found"] == [{"notam": "A9001/26", "codes": ["EFR901"]}]

    # Tried again at the next poll, not a day later.
    answer(aioclient_mock, RESTRICTED, DANGER)
    await refresh(hass, entry, freezer)
    assert hass.states.get(ENTITY).state == "2"
