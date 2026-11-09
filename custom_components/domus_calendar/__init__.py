"""Home Assistant setup for the read-only native Domus calendar."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import CalendarClient, CalendarUnavailable, Projection

DOMAIN = "domus_calendar"
_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CALENDAR]
type DomusEntry = ConfigEntry[tuple[CalendarClient, DataUpdateCoordinator[Projection]]]


async def async_setup_entry(hass: HomeAssistant, entry: DomusEntry) -> bool:
    """Start the calendar with the same verified identity from its config entry."""
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DomusEntry) -> bool:
    """Remove the calendar platform and shut down its scheduled refresh."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
