"""Review a prospective fixed-pattern change past the issued-work frontier."""

from dataclasses import dataclass, replace
from datetime import timedelta

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
from domus.domain.recurrence_planning import FixedCursor, cursor_binding
from domus.domain.recurrence_records import FixedProgress, FixedSchedule, ScheduleState
from domus.domain.recurrence_rules import FixedPattern, NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime
from domus.domain.storage import JsonDocument, JsonObject, validate_identifier
from domus.domain.task_values import DefinitionState


@dataclass(frozen=True, slots=True)
class FixedPatternChange:
    schedule_id: str
    schedule_revision: int
    pattern: FixedPattern

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if not isinstance(self.pattern, FixedPattern):
            raise InvalidInput("invalid_recurrence_pattern")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "fixed_pattern",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "pattern": self.pattern.document().decode(),
            }
        )


@dataclass(frozen=True, slots=True)
class FixedPatternPlan:
    schedule: FixedSchedule
    progress: FixedProgress
    snapshot: JsonDocument

    def backlog(self, times: RecurrenceTimes, now: int) -> JsonObject:
        rule, start = self.schedule, self.schedule.pattern.start
        local = times.local_at(now, rule.policy)
        if (
            not isinstance(local, LocalInstant)
            or local.policy != rule.policy
            or local.instant_ms != now
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        current = local.local.date() if isinstance(start, NominalDate) else local.local
        if start.local < current:
            raise Conflict("recurrence_reschedule_in_past")
        planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)
        check = planner.check_start(rule.pattern, rule.policy)
        if not check.matches:
            if not check.search_complete:
                raise IntegrationUnavailable("recurrence_start_unresolved")
            raise InvalidInput("recurrence_start_mismatch")
        try:
            before = (
                NominalDate(start.local + timedelta(days=60))
                if isinstance(start, NominalDate)
                else NominalTime(start.local + timedelta(days=60))
            )
        except OverflowError:
            raise Conflict("recurrence_review_too_large") from None
        batch = planner.expand(
            rule.pattern, rule.policy, before=before, slot_limit=101, period_limit=1000
        )
        if len(batch.slots) > 100 or not batch.range_complete:
            raise Conflict("recurrence_review_too_large")
        instants = [slot.resolved.instant_ms for slot in batch.slots if slot.resolved is not None]
        if len(instants) != len(set(instants)):
            raise Conflict("recurrence_reschedule_collision")
        return {
            "before": before.local.isoformat(),
            "prospective_slots": [
                slot.value() for slot in batch.slots if rule.exception(slot.nominal) is None
            ],
        }


def fixed_pattern_plan(
    unit: UnitOfWork, scope: MaintenanceScope, request: FixedPatternChange
) -> FixedPatternPlan:
    home = scope.household_id
    rule = unit.recurrence.schedule(home, request.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    if rule.revision != request.schedule_revision:
        raise Conflict("recurrence_review_stale")
    if rule.state is ScheduleState.RETIRED or rule.pattern == request.pattern:
        raise Conflict("recurrence_state_change_unavailable")
    progress = unit.recurrence.progress(home, rule.schedule_id)
    definition = unit.tasks.definition(home, rule.definition_id)
    if progress is None or definition is None or not progress.matches_schedule(rule):
        raise StorageFailure("invalid_recurrence_source")
    if definition.state is not DefinitionState.ACTIVE:
        raise Conflict("recurrence_state_change_unavailable")
    start = request.pattern.start
    if type(start) is not type(
        rule.pattern.start
    ) or unit.recurrence.has_fixed_materialization_from(
        home, rule.schedule_id, start.local.isoformat()
    ):
        raise Conflict("recurrence_pattern_requires_replacement")
    work = unit.tasks.occurrences(home, definition_id=rule.definition_id, open_only=True, limit=101)
    if len(work) == 101:
        raise Conflict("recurrence_review_too_large")
    retained = []
    for item in work:
        slot = unit.recurrence.fixed_slot_for_occurrence(home, item.occurrence_id)
        if slot is not None:
            # The original may be before the frontier while its explicit deadline is after it.
            deadline = effective_deadline(unit, item, slot)
            nominal = deadline.document.decode().get("nominal")
            if not isinstance(nominal, dict) or not isinstance(nominal.get("local"), str):
                raise StorageFailure("invalid_recurrence_effect")
            if str(nominal["local"]) >= start.local.isoformat():
                raise Conflict("recurrence_pattern_requires_replacement")
        retained.append({"occurrence_id": item.occurrence_id, "revision": item.revision})
    updated = replace(
        rule,
        pattern=request.pattern,
        revision=rule.revision + 1,
        pattern_revision=rule.pattern_revision + 1,
    )
    reset = FixedProgress(
        rule.schedule_id,
        home,
        updated.pattern_revision,
        FixedCursor(cursor_binding(updated.pattern, updated.policy)),
        progress.revision + 1,
    )
    return FixedPatternPlan(
        updated,
        reset,
        JsonDocument.from_value(
            {
                "previous_pattern": rule.pattern.document().decode(),
                "previous_progress_revision": progress.revision,
                "previous_binding": progress.cursor.binding,
                "definition_revision": definition.revision,
                "retained_work": retained,
                "replaces_issued_work": False,
            }
        ),
    )
