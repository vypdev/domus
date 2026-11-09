"""Snapshot a relative pause or resume, including the bounded next-work backlog."""

from dataclasses import dataclass, replace

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.relative_materialization import RelativeSource, initial_source
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.identity import validate_revision
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_time import RelativeInterval
from domus.domain.relative_lifecycle import RelativeClosure
from domus.domain.relative_recurrence import (
    RelativeOperation,
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
    SuccessorVisibility,
)
from domus.domain.storage import JsonDocument, JsonObject, Receipt, validate_identifier
from domus.domain.task_values import DefinitionState
from domus.domain.tasks import TaskCycle


@dataclass(frozen=True, slots=True)
class RelativeStateChange:
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
                "kind": "relative_state",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "target": self.target.value,
            }
        )


@dataclass(frozen=True, slots=True)
class RelativeStatePlan:
    source: RelativeSource
    target: ScheduleState
    cycle: TaskCycle | None
    status: str
    snapshot: JsonDocument

    def backlog(self, planner: RelativeRecurrencePlanner) -> JsonObject:
        if self.status == "initial":
            return {"status": self.status, "next_slot": self.source.schedule.initial.value()}
        if self.cycle is not None and self.status == "source_ready":
            result = planner.plan(replace(self.source.schedule, state=self.target), self.cycle)
            return {
                "status": result.status,
                "next_slot": None if result.planned is None else result.planned.value(),
            }
        return {"status": self.status, "next_slot": None}


def state_plan(
    unit: UnitOfWork, scope: MaintenanceScope, request: RelativeStateChange
) -> RelativeStatePlan:
    source = initial_source(unit, scope, request.schedule_id)
    rule, definition = source.schedule, source.definition
    if rule.revision != request.schedule_revision:
        raise Conflict("recurrence_review_stale")
    if rule.state is ScheduleState.RETIRED or rule.state is request.target:
        raise Conflict("recurrence_state_change_unavailable")
    if request.target is ScheduleState.ACTIVE and definition.state is not DefinitionState.ACTIVE:
        raise Conflict("recurrence_state_change_unavailable")
    return _source_plan(unit, scope, source, request.target)


def _source_plan(
    unit: UnitOfWork, scope: MaintenanceScope, source: RelativeSource, target: ScheduleState
) -> RelativeStatePlan:
    rule, progress, definition = source.schedule, source.progress, source.definition
    home = rule.household_id
    work = (
        None
        if progress.current_occurrence_id is None
        else unit.tasks.occurrence(home, progress.current_occurrence_id)
    )
    slot = (
        None
        if progress.current_slot_key is None
        else unit.recurrence.relative_slot(home, progress.current_slot_key)
    )
    cycle = None
    closure = None
    if work is not None and work.current_cycle_id is not None and slot is not None:
        cycle = unit.tasks.cycle(home, work.current_cycle_id)
        if (
            cycle is None
            or cycle.occurrence_id != work.occurrence_id
            or cycle.revision != work.current_cycle_revision
        ):
            raise StorageFailure("invalid_recurrence_source")
        closure = unit.recurrence.relative_closure(
            home, RelativeClosure.cycle_key(rule, cycle, scope.installation)
        )
    # A relative chain can expose at most the initial obligation or the one next slot.
    if target is ScheduleState.PAUSED:
        status = "paused"
    elif progress.pristine:
        probe = RelativeSlot(scope.installation, rule, rule.initial, "pending", rule.created_at)
        original = unit.receipts.get(probe.command)
        if original is not None:
            status = "historical_absent" if original.historical else "original_pending"
        else:
            manual = unit.tasks.occurrences(home, definition_id=rule.definition_id, limit=1)
            status = "initial_review_required" if manual else "initial"
    elif slot is None:
        status = "historical_absent"
    elif closure is not None:
        status = "source_closed"
    elif cycle is None:
        status = "waiting_work"
    else:
        status = "source_ready"
    snapshot = JsonDocument.from_value(
        {
            "schedule_state": rule.state.value,
            "status": status,
            "definition_id": definition.definition_id,
            "definition_revision": definition.revision,
            "generation": rule.binding,
            "progress_revision": progress.revision,
            "retained_occurrence": None
            if work is None
            else {
                "occurrence_id": work.occurrence_id,
                "revision": work.revision,
                "state": work.state.value,
                "due_at": work.due_at,
            },
            "cycle": None
            if cycle is None
            else {
                "cycle_id": cycle.cycle_id,
                "revision": cycle.revision,
                "performed_at": cycle.performed_at,
                "verification": cycle.verification.value,
                "closed_at": cycle.closed_at,
            },
            "closure": None if closure is None else closure.key,
        }
    )
    return RelativeStatePlan(source, target, cycle, status, snapshot)


@dataclass(frozen=True, slots=True)
class RelativeSettings:
    schedule_id: str
    schedule_revision: int
    interval: RelativeInterval
    visibility: SuccessorVisibility

    def __post_init__(self) -> None:
        validate_identifier(self.schedule_id)
        validate_revision(self.schedule_revision)
        if not isinstance(self.interval, RelativeInterval) or not isinstance(
            self.visibility, SuccessorVisibility
        ):
            raise InvalidInput("invalid_recurrence_settings")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "relative_settings",
                "schedule_id": self.schedule_id,
                "schedule_revision": self.schedule_revision,
                "interval_days": self.interval.days,
                "visibility": self.visibility.value,
            }
        )


@dataclass(frozen=True, slots=True)
class RelativeSettingsPlan:
    schedule: RelativeSchedule
    progress: RelativeProgress
    snapshot: JsonDocument

    def save_progress(self, unit: UnitOfWork, receipt: Receipt) -> None:
        evidence = (
            None
            if self.progress.pristine
            else RelativeOperation(receipt.command, receipt.operation_id)
        )
        unit.recurrence.save_relative_progress(
            replace(self.progress, evidence=evidence), self.progress.revision - 1
        )


def settings_plan(
    unit: UnitOfWork, scope: MaintenanceScope, request: RelativeSettings
) -> RelativeSettingsPlan:
    source = initial_source(unit, scope, request.schedule_id)
    rule, progress = source.schedule, source.progress
    if rule.revision != request.schedule_revision:
        raise Conflict("recurrence_review_stale")
    if (
        rule.state is ScheduleState.RETIRED
        or source.definition.state is not DefinitionState.ACTIVE
        or (rule.interval == request.interval and rule.visibility is request.visibility)
    ):
        raise Conflict("recurrence_state_change_unavailable")
    current = _source_plan(unit, scope, source, ScheduleState.ACTIVE)
    if current.status in {"source_ready", "original_pending", "historical_absent"}:
        # An unclosed completion may already have been acknowledged under the old
        # visibility. An edit cannot replay it or make an absent obligation current.
        raise Conflict("recurrence_review_source_pending")
    updated = replace(
        rule,
        interval=request.interval,
        visibility=request.visibility,
        revision=rule.revision + 1,
        pattern_revision=rule.pattern_revision + 1,
    )
    next_progress = replace(
        progress,
        binding=updated.binding,
        pattern_revision=updated.pattern_revision,
        revision=progress.revision + 1,
    )
    snapshot = JsonDocument.from_value(
        {
            "current": current.snapshot.decode(),
            "previous_interval_days": rule.interval.days,
            "previous_visibility": rule.visibility.value,
            "retained_initial": rule.initial.value(),
            "applies_to": "future_successors",
        }
    )
    return RelativeSettingsPlan(updated, next_progress, snapshot)
