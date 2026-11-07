"""Scoped schedule, continuation and immutable generated-slot facts contain no human grants."""

from dataclasses import dataclass
from enum import StrEnum

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.recurrence_membership import accepts_fixed_cursor, accepts_fixed_slot
from domus.domain.recurrence_planning import (
    CursorEvidence,
    FixedCursor,
    PlannedFixedSlot,
    cursor_binding,
)
from domus.domain.recurrence_rules import FixedPattern, NominalDate, NominalSlot, slot_datetime
from domus.domain.recurrence_time import NominalTime, TimePolicy
from domus.domain.storage import (
    CommandKey,
    Installation,
    JsonDocument,
    JsonObject,
    Receipt,
    validate_identifier,
)
from domus.domain.task_values import validate_task_text, validate_task_time

MAINTENANCE_ACTOR = "system:recurrence"


class ScheduleState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class FixedExceptionKind(StrEnum):
    EXCLUDE = "exclude"
    ADD = "add"


@dataclass(frozen=True, slots=True)
class FixedException:
    kind: FixedExceptionKind
    nominal: NominalSlot
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FixedExceptionKind) or not isinstance(
            self.nominal, NominalDate | NominalTime
        ):
            raise InvalidInput("invalid_recurrence_exception")
        validate_task_text(self.reason, 1000, required=True, multiline=True)

    def value(self) -> JsonObject:
        return {
            "kind": self.kind.value,
            "nominal": {
                "kind": "date" if isinstance(self.nominal, NominalDate) else "time",
                "local": self.nominal.local.isoformat(),
            },
            "reason": self.reason,
        }


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
    exceptions: tuple[FixedException, ...] = ()

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
        if type(self.exceptions) is not tuple or any(
            not isinstance(item, FixedException)
            or type(item.nominal) is not type(self.pattern.start)
            for item in self.exceptions
        ):
            raise InvalidInput("invalid_recurrence_exception")
        if len({item.nominal for item in self.exceptions}) != len(self.exceptions) or any(
            sum(item.kind is kind for item in self.exceptions) > 128 for kind in FixedExceptionKind
        ):
            raise InvalidInput("invalid_recurrence_exception")
        if self.exceptions:
            document = JsonDocument.from_value(
                {"exceptions": [item.value() for item in self.exceptions]}
            )
            if len(document.encoded.encode("utf-8")) > 48 * 1024:
                raise InvalidInput("invalid_recurrence_exception")
            object.__setattr__(
                self,
                "exceptions",
                tuple(sorted(self.exceptions, key=lambda item: slot_datetime(item.nominal))),
            )

    def exception(self, nominal: NominalSlot) -> FixedException | None:
        return next((item for item in self.exceptions if item.nominal == nominal), None)


@dataclass(frozen=True, slots=True)
class FixedProgress:
    schedule_id: str
    household_id: str
    pattern_revision: int
    cursor: FixedCursor
    revision: int = 1
    last_run_at: int | None = None
    range_complete: bool = False
    evidence: CursorEvidence | None = None

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
            or (self.evidence is not None and not isinstance(self.evidence, CursorEvidence))
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
                type(schedule.pattern.until) is not int
                or self.evidence is not None
                or self.pristine
            )
            and (
                schedule.pattern.count is None
                or self.cursor.nominal_count <= schedule.pattern.count
            )
            and (
                self.evidence is None
                or (
                    self.evidence.time.cursor == self.cursor
                    and self.evidence.time.policy == schedule.policy
                    and self.evidence.time.range_complete == self.range_complete
                    and self.evidence.command.household_id == self.household_id
                    and self.evidence.command.actor_id == MAINTENANCE_ACTOR
                    and self.evidence.command.action
                    in ("recurrence.materialize", "recurrence.scan")
                )
            )
            and accepts_fixed_cursor(
                schedule.pattern, self.cursor, None if self.evidence is None else self.evidence.time
            )
        )

    @property
    def pristine(self) -> bool:
        return (
            self.cursor.period_index == self.cursor.offset == self.cursor.nominal_count == 0
            and not self.cursor.closed
            and not self.range_complete
            and self.last_run_at is None
            and self.evidence is None
        )


@dataclass(frozen=True, slots=True)
class ScheduledSlot:
    installation: Installation
    schedule: FixedSchedule
    planned: PlannedFixedSlot
    occurrence_id: str
    created_at: int
    added: bool = False

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
            or type(self.added) is not bool
            or (
                self.addition is None
                if self.added
                else not accepts_fixed_slot(self.schedule.pattern, self.planned)
            )
        ):
            raise InvalidInput("invalid_recurrence_slot")

    @property
    def addition(self) -> FixedException | None:
        item = self.schedule.exception(self.planned.nominal)
        return item if item is not None and item.kind is FixedExceptionKind.ADD else None

    def addition_result(self) -> JsonDocument:
        item = self.addition
        assert self.added and item is not None
        return JsonDocument.from_value(
            {
                "slot_key": self.key,
                "occurrence_id": self.occurrence_id,
                "schedule_id": self.schedule.schedule_id,
                "definition_id": self.schedule.definition_id,
                "nominal": item.value()["nominal"],
                "addition": item.value(),
                "planned": self.planned.value(),
            }
        )

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
            and all(item in schedule.exceptions for item in source.exceptions)
            and (
                source.pattern_revision < schedule.pattern_revision
                or (source.pattern == schedule.pattern and source.policy == schedule.policy)
            )
        )

    def matches_receipt(self, receipt: Receipt | None) -> bool:
        """Original generation and realized facts must survive later rule edits unchanged."""
        if receipt is None or receipt.command != self.command or receipt.historical:
            return False
        if self.added:
            return receipt.result == self.addition_result()
        result = receipt.result.decode()
        core = result.get("cursor_evidence")
        if not isinstance(core, dict):
            return False
        cursor = core.get("cursor")
        if not isinstance(cursor, dict):
            return False
        actual = JsonDocument.from_value(
            {
                "slot_key": result.get("slot_key"),
                "occurrence_id": result.get("occurrence_id"),
                "schedule_id": result.get("schedule_id"),
                "definition_id": result.get("definition_id"),
                "binding": cursor.get("binding"),
                "policy": core.get("policy"),
                "planned": core.get("last"),
            }
        )
        expected = JsonDocument.from_value(
            {
                "slot_key": self.key,
                "occurrence_id": self.occurrence_id,
                "schedule_id": self.schedule.schedule_id,
                "definition_id": self.schedule.definition_id,
                "binding": cursor_binding(self.schedule.pattern, self.schedule.policy),
                "policy": {
                    "zone": self.schedule.policy.zone,
                    "data_identity": self.schedule.policy.data_identity,
                    "repeated_time": self.schedule.policy.repeated_time.value,
                    "revision": self.schedule.policy.revision,
                },
                "planned": self.planned.value(),
            }
        )
        return actual == expected

    @property
    def key(self) -> str:
        return JsonDocument.from_value(
            {
                "version": 1,
                "instance": self.installation.instance_id,
                "channel": self.installation.channel,
                "household": self.schedule.household_id,
                "schedule": self.schedule.schedule_id,
                **(
                    {"addition": True}
                    if self.added
                    else {"pattern_revision": self.schedule.pattern_revision}
                ),
                "kind": "date" if isinstance(self.planned.nominal, NominalDate) else "time",
                "nominal": self.planned.nominal.local.isoformat(),
            }
        ).fingerprint

    @property
    def command(self) -> CommandKey:
        return CommandKey(
            self.schedule.household_id, MAINTENANCE_ACTOR, "recurrence.materialize", self.key
        )
