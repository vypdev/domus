"""Bounded immutable task requests use domain values and canonical retry payloads."""

import json
from dataclasses import asdict, dataclass
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import JsonDocument, JsonObject, JsonValue, validate_identifier
from domus.domain.task_material_values import (
    MaterialAction,
    MaterialQuantity,
    MaterialSelection,
    MaterialUsage,
    validate_material_selections,
    validate_material_usage_values,
)
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
        value = asdict(self)
        if value.get("quantity") is not None:
            value["quantity"] = value["quantity"]["value"]
        for field, quantity in (("materials", "planned_quantity"), ("material_usages", "quantity")):
            if field in value:
                if value[field] is None:
                    del value[field]
                else:
                    for item in value[field]:
                        item[quantity] = item[quantity]["value"]
        return JsonDocument(json.dumps(value, ensure_ascii=False))


@dataclass(frozen=True, slots=True)
class CreateTask(TaskRequest):
    content: TaskContent
    overrides: TaskOverrides = TaskOverrides()
    state: DefinitionState = DefinitionState.ACTIVE
    expected_revision: int = 0
    materials: tuple[MaterialSelection, ...] | None = None

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
        if self.materials is not None:
            validate_material_selections(self.materials)


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
    material_usages: tuple[MaterialUsage, ...] | None = None

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_task_ids(self.performer_ids)
        if not self.performer_ids:
            raise InvalidInput("invalid_task_performer")
        validate_task_time(self.performed_at)
        if self.material_usages is not None:
            validate_material_usage_values(self.material_usages)


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
class ReviewTaskDependency(OccurrenceRequest):
    """The expected revision belongs to the cause: pending 1 becomes reviewed 2."""

    cycle_id: str
    source_operation_id: str
    reason: str

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_identifier(self.cycle_id)
        validate_identifier(self.source_operation_id)
        validate_task_text(self.reason, 1000, required=True, multiline=True)


@dataclass(frozen=True, slots=True)
class SettleTaskMaterial(OccurrenceRequest):
    """The expected revision belongs to the intent, never the occurrence or cycle."""

    cycle_id: str
    intent_id: str
    action: MaterialAction
    quantity: MaterialQuantity | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        OccurrenceRequest.__post_init__(self)
        validate_identifier(self.cycle_id)
        validate_identifier(self.intent_id)
        if (
            not isinstance(self.action, MaterialAction)
            or (
                self.action is MaterialAction.CORRECT
                and not isinstance(self.quantity, MaterialQuantity)
            )
            or (self.action is not MaterialAction.CORRECT and self.quantity is not None)
        ):
            raise InvalidInput("invalid_material_settlement")
        validate_task_text(
            self.reason, 1000, required=self.action is not MaterialAction.POST, multiline=True
        )


def read_material_settlement(request: JsonObject) -> SettleTaskMaterial:
    return SettleTaskMaterial(
        cast(str, request["occurrence_id"]),
        cast(int, request["expected_revision"]),
        cast(str, request["cycle_id"]),
        cast(str, request["intent_id"]),
        MaterialAction(cast(str, request["action"])),
        None if request["quantity"] is None else MaterialQuantity(cast(str, request["quantity"])),
        cast(str, request["reason"]),
    )


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
    materials: tuple[MaterialSelection, ...] | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.definition_id)
        validate_revision(self.expected_revision)
        if (
            not isinstance(self.content, TaskContent)
            or not isinstance(self.state, DefinitionState)
            or (self.overrides is not None and not isinstance(self.overrides, TaskOverrides))
        ):
            raise InvalidInput("invalid_task_definition")
        if self.materials is not None:
            validate_material_selections(self.materials)


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


def _material_rows(value: JsonValue, keys: tuple[str, str]) -> list[JsonObject]:
    if (
        type(value) is not list
        or len(value) > 32
        or any(type(item) is not dict or set(item) != set(keys) for item in value)
    ):
        raise InvalidInput("invalid_material_list")
    return cast(list[JsonObject], value)


def validate_recorded_material_request(request: JsonObject) -> None:
    """Decode new fields in immutable audit evidence, never execute a historical command."""
    if "materials" in request:
        validate_material_selections(
            tuple(
                MaterialSelection(
                    cast(str, value["reference_id"]),
                    MaterialQuantity(cast(str, value["planned_quantity"])),
                )
                for value in _material_rows(
                    request["materials"], ("reference_id", "planned_quantity")
                )
            )
        )
    if "material_usages" in request:
        validate_material_usage_values(
            tuple(
                MaterialUsage(
                    cast(str, value["line_id"]), MaterialQuantity(cast(str, value["quantity"]))
                )
                for value in _material_rows(request["material_usages"], ("line_id", "quantity"))
            )
        )
