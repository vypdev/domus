"""Bounded immutable task requests use domain values and canonical retry payloads."""

import json
from dataclasses import asdict, dataclass

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import JsonDocument, validate_identifier
from domus.domain.task_values import (
    DefinitionState,
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    TaskRules,
    VerificationState,
    validate_task_ids,
    validate_task_text,
    validate_task_time,
)


@dataclass(frozen=True, slots=True)
class TaskRequest:
    def document(self) -> JsonDocument:
        # Tuples and string enums become JSON arrays and exact enum values.
        return JsonDocument(json.dumps(asdict(self), ensure_ascii=False))


@dataclass(frozen=True, slots=True)
class CreateTask(TaskRequest):
    content: TaskContent
    overrides: TaskOverrides = TaskOverrides()
    state: DefinitionState = DefinitionState.ACTIVE
    expected_revision: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.expected_revision) is not int
            or self.expected_revision != 0
            or not isinstance(self.content, TaskContent)
            or not isinstance(self.overrides, TaskOverrides)
            or not isinstance(self.state, DefinitionState)
            or self.state not in (DefinitionState.DRAFT, DefinitionState.ACTIVE)
        ):
            raise InvalidInput("invalid_task_create")


@dataclass(frozen=True, slots=True)
class OccurrenceRequest(TaskRequest):
    occurrence_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.occurrence_id)
        validate_revision(self.expected_revision)


@dataclass(frozen=True, slots=True)
class AssignTask(OccurrenceRequest):
    assignee_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_task_ids(self.assignee_ids)


@dataclass(frozen=True, slots=True)
class ClaimTask(OccurrenceRequest):
    pass


@dataclass(frozen=True, slots=True)
class TransitionTask(OccurrenceRequest):
    target: OccurrenceState
    reason: str = ""

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        if not isinstance(self.target, OccurrenceState) or self.target in (
            OccurrenceState.DRAFT,
            OccurrenceState.COMPLETED,
        ):
            raise InvalidInput("invalid_task_transition")
        validate_task_text(
            self.reason,
            1000,
            required=self.target
            in (OccurrenceState.BLOCKED, OccurrenceState.CANCELLED, OccurrenceState.SKIPPED),
            multiline=True,
        )


@dataclass(frozen=True, slots=True)
class CompleteTask(OccurrenceRequest):
    performer_ids: tuple[str, ...]
    performed_at: int

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_task_ids(self.performer_ids)
        if not self.performer_ids:
            raise InvalidInput("invalid_task_performer")
        validate_task_time(self.performed_at)


@dataclass(frozen=True, slots=True)
class VerifyTask(OccurrenceRequest):
    cycle_id: str
    decision: VerificationState
    reason: str = ""

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_identifier(self.cycle_id)
        if not isinstance(self.decision, VerificationState) or self.decision not in (
            VerificationState.APPROVED,
            VerificationState.REJECTED,
        ):
            raise InvalidInput("invalid_task_verification")
        validate_task_text(
            self.reason, 1000, required=self.decision is VerificationState.REJECTED, multiline=True
        )


@dataclass(frozen=True, slots=True)
class ReopenTask(OccurrenceRequest):
    cycle_id: str
    reason: str

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_identifier(self.cycle_id)
        validate_task_text(self.reason, 1000, required=True, multiline=True)


@dataclass(frozen=True, slots=True)
class UpdateTaskPolicy(TaskRequest):
    expected_revision: int
    rules: TaskRules

    def __post_init__(self) -> None:
        if (
            type(self.expected_revision) is not int
            or not 0 <= self.expected_revision <= 2**63 - 1
            or not isinstance(self.rules, TaskRules)
        ):
            raise InvalidInput("invalid_task_policy")


@dataclass(frozen=True, slots=True)
class UpdateTaskDefinition(TaskRequest):
    definition_id: str
    expected_revision: int
    content: TaskContent
    state: DefinitionState
    overrides: TaskOverrides | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.definition_id)
        validate_revision(self.expected_revision)
        if (
            not isinstance(self.content, TaskContent)
            or not isinstance(self.state, DefinitionState)
            or (self.overrides is not None and not isinstance(self.overrides, TaskOverrides))
        ):
            raise InvalidInput("invalid_task_definition")


@dataclass(frozen=True, slots=True)
class CreateTaskOccurrence(TaskRequest):
    definition_id: str
    expected_revision: int = 0
    assignee_ids: tuple[str, ...] = ()
    prerequisite_ids: tuple[str, ...] = ()
    required_subtask_ids: tuple[str, ...] = ()
    due_at: int | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.definition_id)
        if type(self.expected_revision) is not int or self.expected_revision != 0:
            raise InvalidInput("invalid_revision")
        for values in (self.assignee_ids, self.prerequisite_ids, self.required_subtask_ids):
            validate_task_ids(values)
        if self.due_at is not None:
            validate_task_time(self.due_at)


@dataclass(frozen=True, slots=True)
class UpdateTaskDependencies(OccurrenceRequest):
    prerequisite_ids: tuple[str, ...] = ()
    required_subtask_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_task_ids(self.prerequisite_ids)
        validate_task_ids(self.required_subtask_ids)
