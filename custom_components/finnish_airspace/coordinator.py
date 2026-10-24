"""Polling ais.fi: the bulletin every half hour, ENR 5.1 once a day and each supplement once, and the event for news."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .aip import Area, parse_enr_5_1, parse_supplement
from .bulletin import Bulletin, Kind, Supplement, parse_bulletin
from .const import (
    AFTER_UPDATE,
    BULLETIN_URL,
    DOMAIN,
    ENR_5_1_POLL,
    ENR_5_1_URL,
    EVENT_NEW_RESTRICTION,
    LATE,
    POLL,
    SUPPLEMENT_KEPT,
    SUPPLEMENT_URL,
    USER_AGENT,
)
from .feed import Airspace, airspace, event_data, news

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
TIMEOUT = aiohttp.ClientTimeout(total=60)


def memory_store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    return Store(hass, STORAGE_VERSION, DOMAIN)


type AirspaceConfigEntry = ConfigEntry[AirspaceCoordinator]


class AirspaceCoordinator(DataUpdateCoordinator[Airspace]):
    """The parsed areas are kept in storage rather than the pages, so a day ais.fi's AIP is down doesn't empty the map."""

    config_entry: AirspaceConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AirspaceConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=POLL)
        self._session = async_get_clientsession(hass)
        self._store = memory_store(hass)
        # The page last read, kept only in memory: after a restart it is fetched again in full.
        self._bulletin: Bulletin | None = None
        self._bulletin_etag: str | None = None
        self._bulletin_modified: datetime | None = None
        self.enr: dict[str, Area] = {}
        self._enr_etag: str | None = None
        self._enr_checked: datetime | None = None
        self.supplements: dict[Supplement, dict[str, Area]] = {}
        self._supplements_named: dict[Supplement, datetime] = {}
        # Item key: when to forget it. None until the first poll has filled it, which fires no events.
        self.seen: dict[str, str] | None = None
        # Warned once when a source starts failing, not again until it has worked.
        self._failing: set[str] = set()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            return
        enr = stored["enr"]
        self.enr = {code: Area.from_dict(area) for code, area in enr["areas"].items()}
        self._enr_etag = enr["etag"]
        self._enr_checked = datetime.fromisoformat(enr["checked"]) if enr["checked"] else None
        for data in stored["supplements"]:
            supplement = Supplement(data["number"], data["year"], data["airac"])
            self.supplements[supplement] = {code: Area.from_dict(area) for code, area in data["areas"].items()}
            self._supplements_named[supplement] = datetime.fromisoformat(data["named"])
        self.seen = stored["seen"]

    async def async_save(self) -> None:
        """Writes the memory now, so a reload right after a poll can't lose it and fire its events again."""
        await self._store.async_save(self._stored())

    async def _async_update_data(self) -> Airspace:
        now = dt_util.utcnow()
        # Until the page says when its next update comes.
        self.update_interval = POLL
        try:
            bulletin = await self._fetch_bulletin()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"Couldn't read the NOTAM bulletin: {err}") from err
        await self._refresh_enr(now)
        await self._refresh_supplements(bulletin, now)

        result = airspace(bulletin, self.enr, self.supplements, (self.hass.config.latitude, self.hass.config.longitude), now)
        first_poll = self.seen is None
        if self.seen is None:
            self.seen = {}
        new = news(result.items, self.seen, now)
        if not first_poll:
            for item in new:
                self.hass.bus.async_fire(EVENT_NEW_RESTRICTION, event_data(item))
        self._store.async_delay_save(self._stored, 10)
        self.update_interval = next_poll(now, bulletin.next_update) - now
        _LOGGER.debug(
            "%s NOTAMs, %s items, %s in the feed, %s new%s",
            len(bulletin.notams),
            len(result.items),
            sum(item.in_feed for item in result.items),
            len(new),
            " (first poll, no events)" if first_poll else "",
        )
        return result

    async def _fetch_bulletin(self) -> Bulletin:
        headers = {"User-Agent": USER_AGENT}
        if self._bulletin and self._bulletin_etag:
            headers["If-None-Match"] = self._bulletin_etag
        async with self._session.get(BULLETIN_URL, headers=headers, timeout=TIMEOUT) as response:
            if response.status == 304 and self._bulletin:
                return self._bulletin
            response.raise_for_status()
            modified = last_modified(response.headers.get("Last-Modified"))
            # The CDN's nodes catch up with an update at different times, and one still behind answers even the new
            # page's ETag with the old page.
            if self._bulletin and self._bulletin_modified and modified and modified < self._bulletin_modified:
                _LOGGER.debug("The bulletin served was older than the one read before, keeping that")
                return self._bulletin
            page = await response.text(encoding="iso-8859-1")
            etag = response.headers.get("ETag")
        bulletin = await self.hass.async_add_executor_job(parse_bulletin, page)
        if bulletin.failed or bulletin.missed:
            _LOGGER.debug("%s NOTAMs didn't parse, %s were missed: %s", len(bulletin.failed), len(bulletin.missed), bulletin.missed)
        self._bulletin, self._bulletin_etag, self._bulletin_modified = bulletin, etag, modified
        return bulletin

    async def _refresh_enr(self, now: datetime) -> None:
        """Once a day. A failure keeps the areas read before, and tries again at the next poll."""
        if self.enr and self._enr_checked and now - self._enr_checked < ENR_5_1_POLL:
            return
        headers = {"User-Agent": USER_AGENT}
        if self.enr and self._enr_etag:
            headers["If-None-Match"] = self._enr_etag
        try:
            async with self._session.get(ENR_5_1_URL, headers=headers, timeout=TIMEOUT) as response:
                if response.status == 304 and self.enr:
                    self._worked("ENR 5.1")
                    self._enr_checked = now
                    return
                response.raise_for_status()
                page = await response.text(encoding="utf-8")
                etag = response.headers.get("ETag")
            areas = await self.hass.async_add_executor_job(parse_enr_5_1, page)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            outcome = "keeping the areas read before" if self.enr else "areas named by code are missing until it can be"
            self._failed("ENR 5.1", f"Couldn't read ENR 5.1, {outcome}: {err}")
            return
        self._worked("ENR 5.1")
        self.enr, self._enr_etag, self._enr_checked = areas, etag, now

    async def _refresh_supplements(self, bulletin: Bulletin, now: datetime) -> None:
        """Each supplement an activation names, once. One that fails is tried again at the next poll."""
        named = {notam.supplement for notam in bulletin.notams if notam.kind == Kind.ACTIVATION and notam.supplement}
        for supplement in named:
            self._supplements_named[supplement] = now
            if supplement in self.supplements:
                continue
            name = f"AIP SUP {supplement.number:03d}/{supplement.year}"
            url = SUPPLEMENT_URL.format(year=supplement.year, airac="A_" if supplement.airac else "", number=supplement.number)
            try:
                async with self._session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
                    response.raise_for_status()
                    pdf = await response.read()
                areas = await self.hass.async_add_executor_job(parse_supplement, pdf)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                self._failed(name, f"Couldn't read {name}, the areas it has are missing until it can be: {err}")
                continue
            self._worked(name)
            self.supplements[supplement] = areas
        for supplement, last in list(self._supplements_named.items()):
            if now - last > SUPPLEMENT_KEPT:
                del self._supplements_named[supplement]
                self.supplements.pop(supplement, None)

    def _failed(self, source: str, message: str) -> None:
        if source not in self._failing:
            _LOGGER.warning(message)
            self._failing.add(source)
        else:
            _LOGGER.debug(message)

    def _worked(self, source: str) -> None:
        if source in self._failing:
            _LOGGER.info("%s could be read again", source)
            self._failing.discard(source)

    def _stored(self) -> dict[str, Any]:
        return {
            "enr": {
                "etag": self._enr_etag,
                "checked": self._enr_checked.isoformat() if self._enr_checked else None,
                "areas": {code: area.as_dict() for code, area in self.enr.items()},
            },
            "supplements": [
                {
                    "number": supplement.number,
                    "year": supplement.year,
                    "airac": supplement.airac,
                    "named": self._supplements_named[supplement].isoformat(),
                    "areas": {code: area.as_dict() for code, area in areas.items()},
                }
                for supplement, areas in self.supplements.items()
            ],
            "seen": self.seen,
        }


def next_poll(fetched: datetime, next_update: time | None) -> datetime:
    """A little after the bulletin's next update. The page gives only a time of day, so it is the next such time after
    the fetch, unless that time passed within the last half hour: then the page is late to update, or came from a node
    of the CDN still behind, and the bulletin is polled again soon. A time further away than half an hour, or none,
    means polling again in half an hour.
    """
    if next_update is None:
        return fetched + POLL
    update = datetime.combine(fetched.date(), next_update, UTC)
    if update > fetched:
        update -= timedelta(days=1)
    if fetched - update < POLL:
        return fetched + LATE
    update += timedelta(days=1)
    return update + AFTER_UPDATE if update - fetched <= POLL else fetched + POLL


def last_modified(value: str | None) -> datetime | None:
    try:
        return parsedate_to_datetime(value) if value else None
    except ValueError:
        return None
