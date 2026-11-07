"""Discover current revisioned recurrence review targets without creating effects."""

from dataclasses import dataclass
from typing import Literal

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.task_authorization import TaskAccess
from domus.domain.errors import Forbidden, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.relative_recurrence import SuccessorVisibility
from domus.domain.task_values import DefinitionState

ReviewKind = Literal[
    "adoption",
    "attachment",
    "state",
    "fixed-state",
    "relative-settings",
    "fixed-pattern",
    "fixed-replacement",
    "reschedule",
    "fixed-skip",
]


@dataclass(frozen=True, slots=True)
class ReviewSchedule:
    schedule_id: str
    revision: int
    state: ScheduleState
    nominal_kind: Literal["date", "time"]
    local: str
    zone: str
    interval_days: int | None = None
    visibility: SuccessorVisibility | None = None


@dataclass(frozen=True, slots=True)
class ReviewTarget:
    occurrence_id: str
    occurrence_revision: int
    definition_id: str
    definition_revision: int
    zone: str
    schedule: ReviewSchedule | None
    slot_key: str | None
    actions: tuple[ReviewKind, ...]


def review_target(
    unit: UnitOfWork, scope: MaintenanceScope, human: HumanIdentity, occurrence_id: str
) -> ReviewTarget:
    home = scope.household(unit)
    if home is None:
        raise Forbidden("maintenance_scope_denied")
    TaskAccess(human).require(unit, scope.household_id, Permission.TASKS_MANAGE)
    work = unit.tasks.occurrence(scope.household_id, occurrence_id)
    if work is None:
        raise NotFound("task_occurrence_missing")
    definition_id = work.definition_snapshot.definition_id
    definition = unit.tasks.definition(scope.household_id, definition_id)
    if definition is None:
        raise StorageFailure("invalid_recurrence_source")
    schedule_id = unit.recurrence.current_schedule_id(scope.household_id, definition_id)
    fixed_slot = unit.recurrence.fixed_slot_for_occurrence(scope.household_id, occurrence_id)
    relative_slot = unit.recurrence.relative_slot_for_occurrence(scope.household_id, occurrence_id)
    slot = fixed_slot or relative_slot
    common = (occurrence_id, work.revision, definition_id, definition.revision, home.time_zone)
    if definition.state is not DefinitionState.ACTIVE:
        return ReviewTarget(*common, None, None, ())
    if schedule_id is None:
        return ReviewTarget(*common, None, None, ("attachment",) if slot is None else ())
    slot_key = slot.key if slot is not None and slot.schedule.schedule_id == schedule_id else None
    fixed = unit.recurrence.schedule(scope.household_id, schedule_id)
    if fixed is not None:
        nominal = fixed.pattern.start
        actions: tuple[ReviewKind, ...] = ("fixed-state", "fixed-pattern", "fixed-replacement")
        if slot_key is not None:
            actions += ("reschedule", "fixed-skip")
        return ReviewTarget(
            *common,
            ReviewSchedule(
                schedule_id,
                fixed.revision,
                fixed.state,
                "date" if isinstance(nominal, NominalDate) else "time",
                nominal.local.isoformat(),
                fixed.policy.zone,
            ),
            slot_key,
            actions,
        )
    relative = unit.recurrence.relative_schedule(scope.household_id, schedule_id)
    if relative is None:
        raise StorageFailure("invalid_recurrence_source")
    nominal = relative.initial.nominal
    actions = ("state", "relative-settings")
    if slot_key is not None:
        actions += ("reschedule",)
    elif slot is None:
        progress = unit.recurrence.relative_progress(scope.household_id, schedule_id)
        if progress is not None and progress.pristine:
            actions += ("adoption",)
    return ReviewTarget(
        *common,
        ReviewSchedule(
            schedule_id,
            relative.revision,
            relative.state,
            "date" if isinstance(nominal, NominalDate) else "time",
            nominal.local.isoformat(),
            relative.policy.zone,
            relative.interval.days,
            relative.visibility,
        ),
        slot_key,
        actions,
    )
