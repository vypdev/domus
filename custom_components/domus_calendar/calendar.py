"""Present projected Domus dates and deadlines as one read-only calendar."""

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import DOMAIN, DomusEntry
from .client import CalendarUnavailable


async def async_setup_entry(
    _hass: HomeAssistant, entry: DomusEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DomusCalendar(entry)])


class DomusCalendar(CoordinatorEntity, CalendarEntity):
    """A local view of Domus calendar facts, with no write features."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule"
    _attr_suggested_object_id = "domus_schedule"

    def __init__(self, entry: DomusEntry) -> None:
        self.client, coordinator = entry.runtime_data
        super().__init__(coordinator)
        self._attr_unique_id = entry.unique_id

    @property
    def event(self) -> CalendarEvent | None:
        events = self.coordinator.data.events
        return events[0] if events else None

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"projection_pending": self.coordinator.data.pending}

    async def async_get_events(
        self, _hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        try:
            result = await self.client.read(start_date, end_date, dt_util.DEFAULT_TIME_ZONE)
        except CalendarUnavailable:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="calendar_unavailable"
            ) from None
        return list(result.events)
