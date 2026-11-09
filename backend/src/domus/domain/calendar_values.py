"""Calendar ranges and filters preserve date-only facts and stable event identity."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_values import OccurrenceState, Priority, validate_task_text

MAX_CALENDAR_DAYS = 366


class CalendarKind(StrEnum):
    PLANNED = "planned"
    DUE = "due"
    PERFORMED = "performed"
    APPROVAL = "approval"


class CalendarTiming(StrEnum):
    MANUAL = "manual"
    FIXED = "fixed_calendar"
    RELATIVE = "completion_relative"


@dataclass(frozen=True, slots=True)
class CalendarRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if (
            type(self.start) is not date
            or type(self.end) is not date
            or self.start.year < 1970
            or not 1 <= (self.end - self.start).days <= MAX_CALENDAR_DAYS
        ):
            raise InvalidInput("invalid_calendar_range")


@dataclass(frozen=True, slots=True)
class CalendarFilters:
    kind: CalendarKind | None = None
    timing: CalendarTiming | None = None
    state: OccurrenceState | None = None
    priority: Priority | None = None
    member_id: str | None = None
    category: str | None = None

    def __post_init__(self) -> None:
        for value, expected in (
            (self.kind, CalendarKind),
            (self.timing, CalendarTiming),
            (self.state, OccurrenceState),
            (self.priority, Priority),
        ):
            if value is not None and not isinstance(value, expected):
                raise InvalidInput("invalid_calendar_filter")
        if self.member_id is not None:
            validate_identifier(self.member_id)
        if self.category is not None:
            validate_task_text(self.category, 64, required=True, multiline=False)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "kind": None if self.kind is None else self.kind.value,
                "timing": None if self.timing is None else self.timing.value,
                "state": None if self.state is None else self.state.value,
                "priority": None if self.priority is None else self.priority.value,
                "member_id": self.member_id,
                "category": self.category,
            }
        )


@dataclass(frozen=True, slots=True)
class CalendarPosition:
    kind: CalendarKind
    source_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.source_id)


@dataclass(frozen=True, slots=True)
class CalendarCandidate:
    position: CalendarPosition
    occurrence_id: str
    timing: CalendarTiming
    slot_key: str | None


class WeekStart(StrEnum):
    MONDAY = "monday"
    SUNDAY = "sunday"


@dataclass(frozen=True, slots=True)
class CalendarPreference:
    household_id: str
    member_id: str
    week_start: WeekStart = WeekStart.MONDAY
    revision: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.household_id)
        validate_identifier(self.member_id)
        validate_revision(self.revision)
        if not isinstance(self.week_start, WeekStart):
            raise InvalidInput("invalid_calendar_week_start")
