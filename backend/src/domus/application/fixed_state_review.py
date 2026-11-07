"""Review fixed-rule pause or resume without advancing its durable cursor."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.ports import UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.reschedule_review import effective_deadline
from domus.domain.errors import (
    Conflict,
    IntegrationUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import validate_revision
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_records import FixedProgress, FixedSchedule, ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime
from domus.domain.storage import JsonDocument, JsonObject, validate_identifier
from domus.domain.task_values import DefinitionState


@dataclass(frozen=True, slots=True)
class FixedStateChange:
    schedule_id: str
    schedule_revision: int
    target: ScheduleState

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if self.target is not ScheduleState.ACTIVE and self.target is not ScheduleState.PAUSED:
            raise InvalidInput("invalid_recurrence_state_change")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "fixed_state",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "target": self.target.value,
            }
        )


@dataclass(frozen=True, slots=True)
class FixedStatePlan:
    schedule: FixedSchedule
    progress: FixedProgress
    target: ScheduleState
    snapshot: JsonDocument

    def backlog(self, times: RecurrenceTimes, now: int) -> JsonObject:
        if self.target is ScheduleState.PAUSED:
            return {"status": "paused", "pending_slots": []}
        rule = self.schedule
        local = times.local_at(now, rule.policy)
        if (
            not isinstance(local, LocalInstant)
            or local.instant_ms != now
            or local.policy != rule.policy
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        try:
            following_day = local.local.date() + timedelta(days=1)
        except OverflowError:
            raise Conflict("recurrence_review_too_large") from None
        before = (
            NominalDate(following_day)
            if isinstance(rule.pattern.start, NominalDate)
            else NominalTime(datetime.combine(following_day, time.min))
        )
        batch = FixedRecurrencePlanner(CalendarNominalExpansion(), times).expand(
            rule.pattern,
            rule.policy,
            cursor=self.progress.cursor,
            before=before,
            slot_limit=101,
            period_limit=1000,
        )
        if len(batch.slots) > 100 or not batch.range_complete:
            raise Conflict("recurrence_review_too_large")
        instants = [slot.resolved.instant_ms for slot in batch.slots if slot.resolved is not None]
        if len(set(instants)) != len(instants):
            raise Conflict("recurrence_reschedule_collision")
        return {
            "status": "resume",
            "before": before.local.isoformat(),
            "pending_slots": [slot.value() for slot in batch.slots],
        }


def fixed_state_plan(
    unit: UnitOfWork, scope: MaintenanceScope, request: FixedStateChange
) -> FixedStatePlan:
    home = scope.household_id
    rule = unit.recurrence.schedule(home, request.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    if rule.revision != request.schedule_revision:
        raise Conflict("recurrence_review_stale")
    if rule.state is ScheduleState.RETIRED or rule.state is request.target:
        raise Conflict("recurrence_state_change_unavailable")
    definition = unit.tasks.definition(home, rule.definition_id)
    progress = unit.recurrence.progress(home, rule.schedule_id)
    if definition is None or progress is None or not progress.matches_schedule(rule):
        raise StorageFailure("invalid_recurrence_source")
    if request.target is ScheduleState.ACTIVE and definition.state is not DefinitionState.ACTIVE:
        raise Conflict("recurrence_state_change_unavailable")
    work = unit.tasks.occurrences(home, definition_id=rule.definition_id, open_only=True, limit=101)
    if len(work) == 101:
        raise Conflict("recurrence_review_too_large")
    retained = []
    for item in work:
        slot = unit.recurrence.fixed_slot_for_occurrence(home, item.occurrence_id)
        retained.append(
            {
                "occurrence_id": item.occurrence_id,
                "revision": item.revision,
                "state": item.state.value,
                "slot_key": None if slot is None else slot.key,
                "due_at": item.due_at,
                "deadline": None
                if slot is None
                else effective_deadline(unit, item, slot).document.decode(),
            }
        )
    return FixedStatePlan(
        rule,
        progress,
        request.target,
        JsonDocument.from_value(
            {
                "schedule_state": rule.state.value,
                "pattern_revision": rule.pattern_revision,
                "cursor_binding": progress.cursor.binding,
                "progress_revision": progress.revision,
                "definition_id": definition.definition_id,
                "definition_revision": definition.revision,
                "retained_work": retained,
            }
        ),
    )
