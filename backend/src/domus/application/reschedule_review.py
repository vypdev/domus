"""Plan a one-off schedule exception while preserving the original slot and task."""

from dataclasses import dataclass
from datetime import date

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.relative_recurrence_commands import resolve_initial
from domus.application.task_authorization import recorded_request
from domus.application.task_requests import RescheduleTask
from domus.domain.errors import Conflict, IntegrationUnavailable, InvalidInput, StorageFailure
from domus.domain.identity import validate_revision
from domus.domain.recurrence_membership import accepts_fixed_slot
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import FixedSchedule, ScheduledSlot, ScheduleState
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import LocalInstant, NominalTime
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.relative_recurrence import RelativeSchedule, RelativeSlot
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_values import OccurrenceState, validate_task_text
from domus.domain.tasks import TaskOccurrence

type ScheduledWork = ScheduledSlot | RelativeSlot


@dataclass(frozen=True, slots=True)
class RescheduleSelection:
    schedule_id: str
    schedule_revision: int
    slot_key: str
    occurrence_id: str
    occurrence_revision: int
    destination: NominalSlot
    reason: str

    def __post_init__(self) -> None:
        for identifier in (self.schedule_id, self.slot_key, self.occurrence_id):
            validate_identifier(identifier)
        validate_revision(self.schedule_revision)
        validate_revision(self.occurrence_revision)
        if not isinstance(self.destination, NominalDate | NominalTime):
            raise InvalidInput("invalid_recurrence_reschedule")
        validate_task_text(self.reason, 1000, required=True, multiline=True)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "reschedule",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "slot_key": self.slot_key,
                "occurrence_id": self.occurrence_id,
                "occurrence_revision": self.occurrence_revision,
                "destination": {
                    "kind": "date" if isinstance(self.destination, NominalDate) else "time",
                    "local": self.destination.local.isoformat(),
                },
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class EffectiveDeadline:
    document: JsonDocument
    due_at: int | None
    local_date: date | None


def effective_deadline(
    unit: UnitOfWork, work: TaskOccurrence, slot: ScheduledWork
) -> EffectiveDeadline:
    moved = unit.tasks.latest_reschedule(work.household_id, work.occurrence_id)
    if moved is None:
        planned = slot.planned
        return EffectiveDeadline(
            JsonDocument.from_value(planned.value()),
            None if planned.resolved is None else planned.resolved.instant_ms,
            planned.nominal.local if isinstance(planned.nominal, NominalDate) else None,
        )
    request = recorded_request(moved.evidence)
    value = moved.evidence.receipt.result.decode()
    destination = request.get("destination")
    if (
        request.get("slot_key") != slot.key
        or request.get("occurrence_id") != work.occurrence_id
        or request.get("due_at") != work.due_at
        or value.get("recurrence_reschedule") != request
        or not isinstance(destination, dict)
    ):
        raise StorageFailure("invalid_recurrence_effect")
    local_date = None
    if work.due_at is None:
        nominal = destination.get("nominal")
        if not isinstance(nominal, dict) or nominal.get("kind") != "date":
            raise StorageFailure("invalid_recurrence_effect")
        local = nominal.get("local")
        try:
            if not isinstance(local, str):
                raise ValueError
            local_date = date.fromisoformat(local)
        except ValueError:
            raise StorageFailure("invalid_recurrence_effect") from None
    return EffectiveDeadline(JsonDocument.from_value(destination), work.due_at, local_date)


@dataclass(frozen=True, slots=True)
class RescheduleSource:
    rule: FixedSchedule | RelativeSchedule
    work: TaskOccurrence
    slot: ScheduledWork

    def prepare(
        self, times: RecurrenceTimes, selection: RescheduleSelection, now: int
    ) -> PlannedSlot:
        policy = self.slot.schedule.policy
        planned = resolve_initial(times, selection.destination, policy)
        if isinstance(planned.nominal, NominalDate):
            local = times.local_at(now, policy)
            if (
                not isinstance(local, LocalInstant)
                or local.policy != policy
                or local.instant_ms != now
            ):
                raise IntegrationUnavailable("recurrence_time_source_invalid")
            future = planned.nominal.local >= local.local.date()
        else:
            assert planned.resolved is not None
            future = planned.resolved.instant_ms > now
        if not future:
            raise Conflict("recurrence_reschedule_in_past")
        return planned


def reschedule_source(
    unit: UnitOfWork, scope: MaintenanceScope, selection: RescheduleSelection
) -> RescheduleSource:
    home = scope.household_id
    slot: ScheduledWork | None = unit.recurrence.slot(
        home, selection.slot_key
    ) or unit.recurrence.relative_slot(home, selection.slot_key)
    rule: FixedSchedule | RelativeSchedule
    if isinstance(slot, ScheduledSlot):
        fixed = unit.recurrence.schedule(home, selection.schedule_id)
        if fixed is None or not slot.consistent_with(fixed):
            raise Conflict("recurrence_review_stale")
        rule = fixed
    else:
        relative = unit.recurrence.relative_schedule(home, selection.schedule_id)
        if slot is None or relative is None or not slot.consistent_with(relative):
            raise Conflict("recurrence_review_stale")
        rule = relative
    work = unit.tasks.occurrence(home, selection.occurrence_id)
    if (
        work is None
        or rule.revision != selection.schedule_revision
        or work.revision != selection.occurrence_revision
        or slot.occurrence_id != work.occurrence_id
        or work.definition_snapshot.definition_id != rule.definition_id
    ):
        raise Conflict("recurrence_review_stale")
    if (
        rule.state is ScheduleState.RETIRED
        or type(slot.planned.nominal) is not type(selection.destination)
        or work.state not in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
        or occurrence_work_history(unit, work) is not WorkHistory.UNSTARTED
    ):
        raise Conflict("recurrence_reschedule_incompatible")
    return RescheduleSource(rule, work, slot)


def reschedule_plan(
    unit: UnitOfWork,
    source: RescheduleSource,
    selection: RescheduleSelection,
    destination: PlannedSlot,
) -> tuple[JsonDocument, RescheduleTask]:
    work, slot, rule = source.work, source.slot, source.rule
    previous = effective_deadline(unit, work, slot)
    proposed = JsonDocument.from_value(destination.value())
    due_at = None if destination.resolved is None else destination.resolved.instant_ms
    if (
        destination.nominal != selection.destination
        or (
            destination.resolved is not None and destination.resolved.policy != slot.schedule.policy
        )
        or previous.due_at != work.due_at
    ):
        raise Conflict("recurrence_review_stale")
    if proposed == previous.document:
        raise Conflict("recurrence_reschedule_incompatible")
    if (
        isinstance(rule, FixedSchedule)
        and destination.nominal != slot.planned.nominal
        and accepts_fixed_slot(rule.pattern, destination)
    ):
        raise Conflict("recurrence_reschedule_collision")
    candidates = unit.tasks.occurrences(
        work.household_id, definition_id=rule.definition_id, open_only=True, limit=101
    )
    if len(candidates) == 101:
        raise Conflict("recurrence_review_too_large")
    for candidate in candidates:
        if candidate.occurrence_id == work.occurrence_id:
            continue
        if due_at is not None:
            collision = candidate.due_at == due_at
        else:
            candidate_slot = unit.recurrence.fixed_slot_for_occurrence(
                work.household_id, candidate.occurrence_id
            ) or unit.recurrence.relative_slot_for_occurrence(
                work.household_id, candidate.occurrence_id
            )
            collision = (
                candidate_slot is not None
                and effective_deadline(unit, candidate, candidate_slot).local_date
                == destination.nominal.local
            )
        if collision:
            raise Conflict("recurrence_reschedule_collision")
    return (
        JsonDocument.from_value(
            {
                "slot_key": slot.key,
                "original": slot.planned.value(),
                "previous": previous.document.decode(),
                "destination": proposed.decode(),
                "due_at": due_at,
                "state": work.state.value,
                "assignee_ids": list(work.assignee_ids),
                "effect": "move",
            }
        ),
        RescheduleTask(
            work.occurrence_id, work.revision, slot.key, proposed, due_at, selection.reason
        ),
    )
