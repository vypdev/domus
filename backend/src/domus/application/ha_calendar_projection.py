"""Format authorized calendar facts for Home Assistant without granting source access."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from domus.application.calendar_queries import CalendarEntry, CalendarPage
from domus.domain.calendar_values import CalendarKind, CalendarRange
from domus.domain.errors import StorageFailure
from domus.domain.task_values import OccurrenceState

_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True, slots=True)
class HACalendarEvent:
    uid: str
    kind: CalendarKind
    summary: str
    start: str
    all_day: bool
    task_state: OccurrenceState


@dataclass(frozen=True, slots=True)
class HACalendarPage:
    period: CalendarRange
    events: tuple[HACalendarEvent, ...]
    count: int
    next_cursor: str | None
    pending: bool
    external_sync: Literal["disabled"] = "disabled"


def _event(entry: CalendarEntry) -> HACalendarEvent:
    day = entry.local_date
    if day is None:
        raise StorageFailure("invalid_calendar_projection")
    instant = entry.instant_ms
    if instant is None:
        start = day.isoformat()
    else:
        if entry.local_time is None:
            raise StorageFailure("invalid_calendar_projection")
        try:
            # A whole-day gap can move the resolved wall date beyond the nominal grid day.
            wall = datetime.fromisoformat(
                entry.resolved_local or f"{day.isoformat()}T{entry.local_time}"
            )
            offset = wall - (_EPOCH + timedelta(milliseconds=instant))
            start = wall.replace(tzinfo=timezone(offset)).isoformat()
        except ValueError, OverflowError:
            raise StorageFailure("invalid_calendar_projection") from None
    return HACalendarEvent(
        entry.entry_id, entry.kind, entry.title, start, instant is None, entry.state
    )


def ha_calendar_projection(page: CalendarPage) -> HACalendarPage:
    return HACalendarPage(
        page.period,
        tuple(_event(entry) for entry in page.entries),
        page.count,
        page.next_cursor,
        page.pending,
    )
