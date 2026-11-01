"""Scoped schedule, continuation and immutable generated-slot facts contain no human grants."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot, cursor_binding
from domus.domain.recurrence_rules import FixedPattern, NominalDate
from domus.domain.recurrence_time import TimePolicy
from domus.domain.storage import CommandKey, Installation, JsonDocument, validate_identifier
from domus.domain.task_values import validate_task_time

MAINTENANCE_ACTOR = "system:recurrence"


class ScheduleState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class FixedSchedule:
    schedule_id: str
    household_id: str
    definition_id: str
    pattern: FixedPattern
    policy: TimePolicy
    created_at: int
    state: ScheduleState = ScheduleState.ACTIVE
    revision: int = 1
    pattern_revision: int = 1

    def __post_init__(self) -> None:
        for value in (self.schedule_id, self.household_id, self.definition_id):
            validate_identifier(value)
        for revision in (self.revision, self.pattern_revision):
            validate_revision(revision)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.pattern, FixedPattern)
            or not isinstance(self.policy, TimePolicy)
            or not isinstance(self.state, ScheduleState)
            or self.pattern_revision > self.revision
        ):
            raise InvalidInput("invalid_recurrence_schedule")


@dataclass(frozen=True, slots=True)
class FixedProgress:
    schedule_id: str
    household_id: str
    pattern_revision: int
    cursor: FixedCursor
    revision: int = 1
    last_run_at: int | None = None
    range_complete: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_identifier(self.household_id)
        validate_revision(self.pattern_revision)
        validate_revision(self.revision)
        if self.last_run_at is not None:
            validate_task_time(self.last_run_at)
        if (
            not isinstance(self.cursor, FixedCursor)
            or type(self.range_complete) is not bool
            or (self.cursor.closed and not self.range_complete)
        ):
            raise InvalidInput("invalid_recurrence_progress")

    def matches_schedule(self, schedule: FixedSchedule) -> bool:
        """A typed source relationship is an integrity fact, never caller authorization."""
        return (
            self.schedule_id == schedule.schedule_id
            and self.household_id == schedule.household_id
            and self.pattern_revision == schedule.pattern_revision
            and self.cursor.binding == cursor_binding(schedule.pattern, schedule.policy)
            and (
                schedule.pattern.count is None
                or self.cursor.nominal_count <= schedule.pattern.count
            )
        )


@dataclass(frozen=True, slots=True)
class ScheduledSlot:
    installation: Installation
    schedule: FixedSchedule
    planned: PlannedFixedSlot
    occurrence_id: str
    created_at: int

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_task_time(self.created_at)
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.schedule, FixedSchedule)
            or not isinstance(self.planned, PlannedFixedSlot)
            or type(self.planned.nominal) is not type(self.schedule.pattern.start)
            or (
                self.planned.resolved is not None
                and self.planned.resolved.policy != self.schedule.policy
            )
            or self.created_at < self.schedule.created_at
        ):
            raise InvalidInput("invalid_recurrence_slot")

    def consistent_with(self, schedule: FixedSchedule) -> bool:
        """Older snapshots survive edits; future or contradictory generations do not."""
        source = self.schedule
        return (
            source.schedule_id == schedule.schedule_id
            and source.household_id == schedule.household_id
            and source.definition_id == schedule.definition_id
            and source.created_at == schedule.created_at
            and source.revision <= schedule.revision
            and source.pattern_revision <= schedule.pattern_revision
            and (
                source.pattern_revision < schedule.pattern_revision
                or (source.pattern == schedule.pattern and source.policy == schedule.policy)
            )
        )

    @property
    def key(self) -> str:
        return JsonDocument.from_value(
            {
                "version": 1,
                "instance": self.installation.instance_id,
                "channel": self.installation.channel,
                "household": self.schedule.household_id,
                "schedule": self.schedule.schedule_id,
                "pattern_revision": self.schedule.pattern_revision,
                "kind": "date" if isinstance(self.planned.nominal, NominalDate) else "time",
                "nominal": self.planned.nominal.local.isoformat(),
            }
        ).fingerprint

    @property
    def command(self) -> CommandKey:
        return CommandKey(
            self.schedule.household_id, MAINTENANCE_ACTOR, "recurrence.materialize", self.key
        )
