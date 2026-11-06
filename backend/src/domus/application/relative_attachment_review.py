"""Bind an existing task to a new completion-relative rule through an explicit review."""

from dataclasses import dataclass
from enum import StrEnum

from domus.application.commands import AtomicCommands
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.relative_lifecycle import occurrence_work_history
from domus.application.relative_materialization import RelativeSource, adopt_initial
from domus.application.relative_recurrence_commands import resolve_initial
from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_rules import NominalDate, NominalSlot
from domus.domain.recurrence_time import FoldPolicy, NominalTime, RelativeInterval, TimePolicy
from domus.domain.relative_lifecycle import WorkHistory
from domus.domain.relative_recurrence import (
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
    SuccessorVisibility,
)
from domus.domain.storage import JsonDocument, JsonObject, validate_identifier
from domus.domain.task_values import DefinitionState, OccurrenceState
from domus.domain.tasks import TaskDefinition, TaskOccurrence

_CLOSED_WORK = frozenset(
    {OccurrenceState.COMPLETED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED}
)


class AttachmentChoice(StrEnum):
    ADOPT = "adopt"
    RETAIN = "retain_manual"


@dataclass(frozen=True, slots=True)
class AttachRelative:
    definition_id: str
    definition_revision: int
    occurrence_id: str
    occurrence_revision: int
    initial: NominalSlot
    interval: RelativeInterval
    zone: str
    repeated_time: FoldPolicy
    visibility: SuccessorVisibility
    choice: AttachmentChoice

    def __post_init__(self) -> None:
        validate_identifier(self.definition_id)
        validate_identifier(self.occurrence_id)
        validate_revision(self.definition_revision)
        validate_revision(self.occurrence_revision)
        if (
            not isinstance(self.initial, NominalDate | NominalTime)
            or not isinstance(self.interval, RelativeInterval)
            or not isinstance(self.visibility, SuccessorVisibility)
            or not isinstance(self.choice, AttachmentChoice)
        ):
            raise InvalidInput("invalid_recurrence_attachment")
        # Validate submitted policy fields without consulting the provider.
        TimePolicy(self.zone, "pending", self.repeated_time)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "version": 1,
                "kind": "attach_relative",
                "definition_id": self.definition_id,
                "definition_revision": self.definition_revision,
                "occurrence_id": self.occurrence_id,
                "occurrence_revision": self.occurrence_revision,
                "initial": {
                    "kind": "date" if isinstance(self.initial, NominalDate) else "time",
                    "local": self.initial.local.isoformat(),
                },
                "interval_days": self.interval.days,
                "zone": self.zone,
                "repeated_time": self.repeated_time.value,
                "visibility": self.visibility.value,
                "choice": self.choice.value,
            }
        )

    def prepare(self, times: RecurrenceTimes) -> AttachmentTiming:
        policy = TimePolicy(self.zone, times.data_identity, self.repeated_time)
        return AttachmentTiming(policy, resolve_initial(times, self.initial, policy))


@dataclass(frozen=True, slots=True)
class AttachmentTiming:
    policy: TimePolicy
    initial: PlannedSlot

    @property
    def due_at(self) -> int | None:
        return None if self.initial.resolved is None else self.initial.resolved.instant_ms


def _work_fact(work: TaskOccurrence) -> JsonObject:
    return {
        "occurrence_id": work.occurrence_id,
        "revision": work.revision,
        "state": work.state.value,
        "due_at": work.due_at,
    }


@dataclass(frozen=True, slots=True)
class AttachmentPlan:
    definition: TaskDefinition
    work: TaskOccurrence
    timing: AttachmentTiming
    document: JsonDocument


def attachment_plan(
    unit: UnitOfWork,
    scope: MaintenanceScope,
    selection: AttachRelative,
    timing: AttachmentTiming,
) -> AttachmentPlan:
    home = scope.household_id
    definition = unit.tasks.definition(home, selection.definition_id)
    work = unit.tasks.occurrence(home, selection.occurrence_id)
    if (
        definition is None
        or definition.revision != selection.definition_revision
        or work is None
        or work.revision != selection.occurrence_revision
        or work.definition_snapshot.definition_id != definition.definition_id
    ):
        raise Conflict("recurrence_review_stale")
    if unit.recurrence.has_current_schedule(home, definition.definition_id):
        raise Conflict("recurrence_attachment_already_scheduled")
    if definition.state is not DefinitionState.ACTIVE or unit.recurrence.occurrence_is_scheduled(
        home, work.occurrence_id
    ):
        raise Conflict("recurrence_attachment_incompatible")
    retained: tuple[TaskOccurrence, ...] = ()
    if selection.choice is AttachmentChoice.ADOPT:
        if (
            work.definition_snapshot != definition
            or work.due_at != timing.due_at
            or work.state not in (OccurrenceState.AVAILABLE, OccurrenceState.ASSIGNED)
            or occurrence_work_history(unit, work) is not WorkHistory.UNSTARTED
        ):
            raise Conflict("recurrence_adoption_incompatible")
    else:
        candidates = unit.tasks.occurrences(home, definition_id=definition.definition_id, limit=101)
        if len(candidates) == 101:
            raise Conflict("recurrence_review_too_large")
        retained = tuple(item for item in candidates if item.state not in _CLOSED_WORK)
        if any(
            timing.due_at is None or item.due_at is None or item.due_at >= timing.due_at
            for item in retained
        ):
            raise Conflict("recurrence_attachment_overlap")
    return AttachmentPlan(
        definition,
        work,
        timing,
        JsonDocument.from_value(
            {
                "manual": _work_fact(work),
                "open_work_retained": [_work_fact(item) for item in retained],
                "initial": timing.initial.value(),
                "due_at": timing.due_at,
                "time_data_identity": timing.policy.data_identity,
                "creates_first_occurrence": selection.choice is AttachmentChoice.RETAIN,
            }
        ),
    )


def attach_relative(
    unit: UnitOfWork,
    commands: AtomicCommands,
    scope: MaintenanceScope,
    selection: AttachRelative,
    plan: AttachmentPlan,
) -> JsonObject:
    home = scope.household_id
    now = commands.clock.now()
    adopted = selection.choice is AttachmentChoice.ADOPT
    # For adoption the rule's time origin belongs to the original obligation.
    # The human review receipt records when the rule was actually attached.
    rule = RelativeSchedule(
        commands.identifiers.new(),
        home,
        plan.definition.definition_id,
        plan.timing.initial,
        selection.interval,
        plan.timing.policy,
        plan.definition.created_at if adopted else now,
        selection.visibility,
    )
    progress = RelativeProgress(rule.schedule_id, home, rule.pattern_revision, rule.binding)
    unit.recurrence.save_relative_schedule(rule, 0)
    unit.recurrence.save_relative_progress(progress, 0)
    work = plan.work
    if not adopted:
        work = plan.definition.new_occurrence(
            commands.identifiers.new(), now, due_at=plan.timing.due_at
        )
        unit.tasks.save_occurrence(work, 0)
    source = RelativeSource(rule, progress, plan.definition)
    slot = RelativeSlot(scope.installation, rule, rule.initial, work.occurrence_id, work.created_at)
    proof = adopt_initial(unit, commands, scope, source, slot)
    return {
        "kind": "attach_relative",
        "choice": selection.choice.value,
        "schedule_id": rule.schedule_id,
        "schedule_revision": rule.revision,
        "definition_id": rule.definition_id,
        "manual_occurrence_id": plan.work.occurrence_id,
        "first_occurrence_id": work.occurrence_id,
        "materialization_operation_id": proof.operation_id,
    }
