"""Prepare one explicit fixed exception and revalidate its effect in the writer."""

from dataclasses import dataclass, replace
from datetime import date, datetime

from domus.application.commands import AtomicCommands, Change
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.relative_recurrence_commands import resolve_initial
from domus.application.reschedule_review import effective_deadline, future_until
from domus.application.task_authorization import TaskAccess, TaskCommandAuthorization
from domus.application.task_commands import transition_occurrence
from domus.application.task_requests import TransitionTask
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import validate_revision
from domus.domain.recurrence_membership import accepts_fixed_slot
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import (
    FixedException,
    FixedExceptionKind,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.storage import CommandKey, JsonDocument, JsonObject, validate_identifier
from domus.domain.task_values import DefinitionState, OccurrenceState
from domus.domain.tasks import TaskDefinition, TaskOccurrence


@dataclass(frozen=True, slots=True)
class FixedExceptionChange:
    schedule_id: str
    schedule_revision: int
    exception: FixedException

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if not isinstance(self.exception, FixedException):
            raise InvalidInput("invalid_recurrence_exception")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "fixed_exception",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "exception": self.exception.value(),
            }
        )


def exception_schedule(
    unit: UnitOfWork, scope: MaintenanceScope, selection: FixedExceptionChange
) -> FixedSchedule:
    rule = unit.recurrence.schedule(scope.household_id, selection.schedule_id)
    if rule is None:
        raise NotFound("recurrence_rule_missing")
    if rule.revision != selection.schedule_revision:
        raise Conflict("recurrence_review_stale")
    if rule.state is ScheduleState.RETIRED or type(selection.exception.nominal) is not type(
        rule.pattern.start
    ):
        raise Conflict("recurrence_exception_incompatible")
    return rule


@dataclass(frozen=True, slots=True)
class FixedExceptionPlan:
    rule: FixedSchedule
    updated: FixedSchedule
    definition: TaskDefinition
    planned: PlannedSlot
    affected: TaskOccurrence | None
    snapshot: JsonDocument

    def commit(
        self,
        unit: UnitOfWork,
        scope: MaintenanceScope,
        commands: AtomicCommands,
        command: CommandKey,
        access: TaskAccess,
        selection: FixedExceptionChange,
    ) -> JsonObject:
        unit.recurrence.save_schedule(self.updated, self.rule.revision)
        item = selection.exception
        work_id = None
        effect_id = None
        if self.affected is not None:
            work = self.affected
            work_id = work.occurrence_id
            transition = TransitionTask(
                work_id, work.revision, OccurrenceState.CANCELLED, item.reason
            )
            linked = CommandKey(
                command.household_id,
                command.actor_id,
                "task.transition",
                JsonDocument.from_value({"action": command.action, "key": command.key}).fingerprint,
            )
            task_authority = TaskCommandAuthorization(
                access,
                command.household_id,
                linked.action,
                work_id,
                transition_target=transition.target,
            )
            effect_id = (
                replace(commands, authorization=task_authority)
                .in_unit(
                    unit,
                    linked,
                    transition.document(),
                    lambda active: transition_occurrence(active, command.household_id, transition),
                )
                .operation_id
            )
        elif item.kind is FixedExceptionKind.ADD:
            due = None if self.planned.resolved is None else self.planned.resolved.instant_ms
            work = self.definition.new_occurrence(
                commands.identifiers.new(), commands.clock.now(), due_at=due
            )
            work_id = work.occurrence_id
            slot = ScheduledSlot(
                scope.installation, self.updated, self.planned, work_id, work.created_at, added=True
            )
            authority = _AdditionAuthority(scope, slot)
            payload = JsonDocument.from_value(
                {
                    "version": 1,
                    "slot_key": slot.key,
                    "review_key": command.key,
                    "review_actor": command.actor_id,
                    "exception": item.value(),
                }
            )

            def add(active: UnitOfWork) -> Change:
                active.tasks.save_occurrence(work, 0)
                active.recurrence.add_slot(slot)
                result = slot.addition_result()
                return Change(
                    result,
                    JsonDocument.from_value(
                        {"request": payload.decode(), "result": result.decode()}
                    ),
                    JsonDocument.from_value(
                        {
                            "version": 1,
                            "kind": slot.command.action,
                            "schedule_id": self.rule.schedule_id,
                            "slot_key": slot.key,
                            "occurrence_id": slot.occurrence_id,
                        }
                    ),
                )

            effect = replace(commands, authorization=authority).in_unit(
                unit, slot.command, payload, add
            )
            if not slot.matches_receipt(effect):
                raise Conflict("recurrence_exception_incompatible")
            effect_id = effect.operation_id
        return {
            "kind": "fixed_exception",
            "schedule_id": self.rule.schedule_id,
            "schedule_revision": self.updated.revision,
            "exception": item.value(),
            "occurrence_id": work_id,
            "effect_operation_id": effect_id,
        }


@dataclass(frozen=True, slots=True)
class _AdditionAuthority:
    scope: MaintenanceScope
    slot: ScheduledSlot

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        self.scope.require(unit)
        rule = self.slot.schedule
        if (
            command != self.slot.command
            or unit.recurrence.schedule(self.scope.household_id, rule.schedule_id) != rule
        ):
            raise Forbidden("maintenance_scope_denied")


def exception_timing(
    times: RecurrenceTimes, rule: FixedSchedule, selection: FixedExceptionChange
) -> tuple[PlannedSlot, int | None]:
    planned = resolve_initial(times, selection.exception.nominal, rule.policy)
    deadline = (
        future_until(times, planned, rule.policy)
        if selection.exception.kind is FixedExceptionKind.ADD
        else None
    )
    if deadline is not None and planned.resolved is not None:
        _require_unique_instant(
            times, rule, planned.resolved.instant_ms, planned.resolved.nominal.local.date()
        )
    return planned, deadline


def _require_unique_instant(
    times: RecurrenceTimes, rule: FixedSchedule, instant: int, day: date
) -> None:
    # A local gap may move a nominal to a later wall date. A three-day margin
    # covers the resolver's gap bound and both legal offsets.
    start = rule.pattern.start
    assert isinstance(start, NominalTime)
    first = max(start.local.date().toordinal(), day.toordinal() - 3)
    last = min(date.max.toordinal(), day.toordinal() + 3)
    for index in range(first, last + 1):
        nominal = NominalTime(datetime.combine(date.fromordinal(index), start.local.time()))
        resolved = resolve_initial(times, nominal, rule.policy)
        assert resolved.resolved is not None
        if resolved.resolved.instant_ms == instant and accepts_fixed_slot(rule.pattern, resolved):
            raise Conflict("recurrence_reschedule_collision")


def exception_plan(
    unit: UnitOfWork, rule: FixedSchedule, selection: FixedExceptionChange, planned: PlannedSlot
) -> FixedExceptionPlan:
    home, item = rule.household_id, selection.exception
    definition = unit.tasks.definition(home, rule.definition_id)
    if definition is None:
        raise StorageFailure("invalid_recurrence_source")
    if (
        definition.state is not DefinitionState.ACTIVE
        or rule.exception(item.nominal) is not None
        or unit.recurrence.has_historical_fixed_exception(
            home, rule.schedule_id, item.nominal.local.isoformat()
        )
    ):
        raise Conflict("recurrence_exception_incompatible")
    adding = item.kind is FixedExceptionKind.ADD
    if accepts_fixed_slot(rule.pattern, planned) == adding:
        raise Conflict(
            "recurrence_reschedule_collision" if adding else "recurrence_exception_incompatible"
        )
    try:
        updated = replace(rule, revision=rule.revision + 1, exceptions=(*rule.exceptions, item))
    except InvalidInput:
        raise Conflict("recurrence_review_too_large") from None
    slots = unit.recurrence.fixed_slots_at(home, rule.schedule_id, item.nominal.local.isoformat())
    if len(slots) == 101:
        raise Conflict("recurrence_review_too_large")
    affected = None
    if adding:
        if slots:
            raise Conflict("recurrence_reschedule_collision")
        _require_unique_deadline(unit, rule, planned)
    else:
        for slot in slots:
            work = unit.tasks.occurrence(home, slot.occurrence_id)
            if work is None:
                raise StorageFailure("invalid_recurrence_source")
            if work.state in (OccurrenceState.CANCELLED, OccurrenceState.SKIPPED):
                continue
            if (
                affected is not None
                or work.state not in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
                or occurrence_work_history(unit, work) is not WorkHistory.UNSTARTED
                or effective_deadline(unit, work, slot).document.decode() != slot.planned.value()
                or unit.tasks.has_current_dependents(home, work.occurrence_id)
            ):
                raise Conflict("recurrence_exception_incompatible")
            affected = work
    snapshot = JsonDocument.from_value(
        {
            "definition_revision": definition.revision,
            "planned": planned.value(),
            **(
                {"cancelled_work": [] if affected is None else [affected.occurrence_id]}
                if not adding
                else {}
            ),
            "affected": None
            if affected is None
            else {
                "occurrence_id": affected.occurrence_id,
                "revision": affected.revision,
                "state": affected.state.value,
            },
        }
    )
    return FixedExceptionPlan(rule, updated, definition, planned, affected, snapshot)


def _require_unique_deadline(unit: UnitOfWork, rule: FixedSchedule, planned: PlannedSlot) -> None:
    work = unit.tasks.occurrences(
        rule.household_id, definition_id=rule.definition_id, open_only=True, limit=101
    )
    if len(work) == 101:
        raise Conflict("recurrence_review_too_large")
    for candidate in work:
        if planned.resolved is not None:
            collision = candidate.due_at == planned.resolved.instant_ms
        else:
            assert isinstance(planned.nominal, NominalDate)
            slot = unit.recurrence.fixed_slot_for_occurrence(
                rule.household_id, candidate.occurrence_id
            )
            collision = (
                slot is not None
                and effective_deadline(unit, candidate, slot).local_date == planned.nominal.local
            )
        if collision:
            raise Conflict("recurrence_reschedule_collision")
