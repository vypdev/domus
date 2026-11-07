"""An explicit overdue fixed-slot exception preserves its original calendar identity."""

from dataclasses import asdict, dataclass

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.reschedule_review import EffectiveDeadline, effective_deadline
from domus.domain.errors import Conflict, IntegrationUnavailable, NotFound
from domus.domain.identity import validate_revision
from domus.domain.recurrence_records import ScheduledSlot, ScheduleState
from domus.domain.recurrence_time import LocalInstant
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_values import OccurrenceState, validate_task_text


@dataclass(frozen=True, slots=True)
class FixedSkip:
    schedule_id: str
    schedule_revision: int
    slot_key: str
    occurrence_id: str
    occurrence_revision: int
    reason: str

    def __post_init__(self) -> None:
        for identifier in (self.schedule_id, self.slot_key, self.occurrence_id):
            validate_identifier(identifier)
        validate_revision(self.schedule_revision)
        validate_revision(self.occurrence_revision)
        validate_task_text(self.reason, 1000, required=True, multiline=True)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value({"version": 1, "kind": "fixed_skip", **asdict(self)})


@dataclass(frozen=True, slots=True)
class FixedSkipPlan:
    slot: ScheduledSlot
    deadline: EffectiveDeadline
    snapshot: JsonDocument

    def require_overdue(self, times: RecurrenceTimes, now: int) -> None:
        if self.deadline.local_date is not None:
            local = times.local_at(now, self.slot.schedule.policy)
            if (
                not isinstance(local, LocalInstant)
                or local.instant_ms != now
                or local.policy != self.slot.schedule.policy
            ):
                raise IntegrationUnavailable("recurrence_time_source_invalid")
            overdue = local.local.date() > self.deadline.local_date
        else:
            assert self.deadline.due_at is not None
            overdue = now > self.deadline.due_at
        if not overdue:
            raise Conflict("recurrence_slot_not_overdue")


def fixed_skip_plan(
    unit: UnitOfWork, scope: MaintenanceScope, selection: FixedSkip
) -> FixedSkipPlan:
    home = scope.household_id
    rule = unit.recurrence.schedule(home, selection.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    slot = unit.recurrence.slot(home, selection.slot_key)
    work = unit.tasks.occurrence(home, selection.occurrence_id)
    if (
        rule.revision != selection.schedule_revision
        or slot is None
        or work is None
        or work.revision != selection.occurrence_revision
    ):
        raise Conflict("recurrence_review_stale")
    if (
        rule.state is ScheduleState.RETIRED
        or not slot.consistent_with(rule)
        or slot.occurrence_id != work.occurrence_id
        or work.definition_snapshot.definition_id != rule.definition_id
        or work.state not in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
    ):
        raise Conflict("recurrence_skip_incompatible")
    deadline = effective_deadline(unit, work, slot)
    if (
        work.due_at != deadline.due_at
        or occurrence_work_history(unit, work) is not WorkHistory.UNSTARTED
    ):
        raise Conflict("recurrence_skip_incompatible")
    effective = (
        {}
        if deadline.document.decode() == slot.planned.value()
        else {"rescheduled_due": deadline.document.decode()}
    )
    return FixedSkipPlan(
        slot,
        deadline,
        JsonDocument.from_value(
            {
                "schedule_state": rule.state.value,
                "pattern_revision": rule.pattern_revision,
                "slot_key": slot.key,
                "nominal": slot.planned.value(),
                "due_at": deadline.due_at,
                **effective,
                "occurrence_id": work.occurrence_id,
                "occurrence_revision": work.revision,
                "occurrence_state": work.state.value,
                "target_state": OccurrenceState.SKIPPED.value,
            }
        ),
    )
