"""Home Assistant setup for the read-only Domus installation projections."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import CalendarClient, CalendarUnavailable, Projection
from .connection import ProjectionUnavailable
from .deadline_client import DeadlineClient, DeadlineCounts

DOMAIN = "domus_calendar"
CONF_PROJECTION = "projection"
CALENDAR = "calendar"
DEADLINES = "deadlines"
_LOGGER = logging.getLogger(__name__)
type DomusEntry = ConfigEntry[tuple[CalendarClient, DataUpdateCoordinator[Projection]]]
type DeadlineEntry = ConfigEntry[DataUpdateCoordinator[DeadlineCounts]]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start the projection selected by the verified config entry."""
    if entry.data.get(CONF_PROJECTION) == DEADLINES:
        return await _setup_deadlines(hass, entry)
    client = CalendarClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]
    )

    async def update() -> Projection:
        now = dt_util.now()
        try:
            return await client.read(now, now + timedelta(days=31), now.tzinfo)
        except CalendarUnavailable:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="calendar_unavailable"
            ) from None

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        config_entry=entry,
        update_method=update,
        update_interval=timedelta(minutes=1),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = (client, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.CALENDAR])
    return True


async def _setup_deadlines(hass: HomeAssistant, entry: DeadlineEntry) -> bool:
    client = DeadlineClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]
    )

    async def update() -> DeadlineCounts:
        try:
            return await client.read()
        except ProjectionUnavailable:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="deadlines_unavailable"
            ) from None

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Domus task deadlines",
        config_entry=entry,
        update_method=update,
        update_interval=timedelta(minutes=1),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the configured platform and shut down its scheduled refresh."""
    platform = (
        Platform.SENSOR if entry.data.get(CONF_PROJECTION) == DEADLINES else Platform.CALENDAR
    )
    return await hass.config_entries.async_unload_platforms(entry, [platform])
