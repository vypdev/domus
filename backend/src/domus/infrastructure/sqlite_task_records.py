"""Versioned task record mapping; corrupt or future data never receives guessed defaults."""

from collections.abc import Callable
from typing import cast

from domus.domain.errors import DomusError, InvalidInput, StorageFailure
from domus.domain.identity import Role
from domus.domain.storage import JsonDocument, JsonObject, JsonValue
from domus.domain.task_values import (
    DefinitionState,
    DependencyGate,
    MaterialRecording,
    OccurrenceState,
    Priority,
    TaskContent,
    TaskOverrides,
    TaskPerformer,
    TaskRules,
    VerificationMode,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy, TaskCycle, TaskDefinition, TaskOccurrence

_RULE_FIELDS = (
    "claim_allowed",
    "eligible_roles",
    "verification",
    "adult_performer_may_approve",
    "task_scoped_material_consumption",
    "material_recording",
    "point_value_minor",
    "dependency_gate",
)


def _object(value: JsonValue, keys: tuple[str, ...]) -> JsonObject:
    if type(value) is not dict or set(value) != set(keys):
        raise InvalidInput("invalid_task_record")
    return value


def _record(value: JsonValue, keys: tuple[str, ...]) -> JsonObject:
    result = _object(value, ("version", *keys))
    if type(result["version"]) is not int or result["version"] != 1:
        raise InvalidInput("unsupported_task_record")
    return result


def _array(value: JsonValue) -> list[JsonValue]:
    if type(value) is not list:
        raise InvalidInput("invalid_task_record")
    return value


def _strings(value: JsonValue) -> tuple[str, ...]:
    values = _array(value)
    if any(type(item) is not str for item in values):
        raise InvalidInput("invalid_task_record")
    return tuple(cast(list[str], values))


def _rule_value(value: TaskRules | TaskOverrides) -> JsonObject:
    return {
        "claim_allowed": value.claim_allowed,
        "eligible_roles": None
        if value.eligible_roles is None
        else [role.value for role in value.eligible_roles],
        "verification": None if value.verification is None else value.verification.value,
        "adult_performer_may_approve": value.adult_performer_may_approve,
        "task_scoped_material_consumption": value.task_scoped_material_consumption,
        "material_recording": None
        if value.material_recording is None
        else value.material_recording.value,
        "point_value_minor": value.point_value_minor,
        "dependency_gate": None if value.dependency_gate is None else value.dependency_gate.value,
    }


def _rules(value: JsonValue) -> TaskRules:
    row = _object(value, _RULE_FIELDS)
    return TaskRules(
        cast(bool, row["claim_allowed"]),
        tuple(Role(role) for role in _strings(row["eligible_roles"])),
        VerificationMode(cast(str, row["verification"])),
        cast(bool, row["adult_performer_may_approve"]),
        cast(bool, row["task_scoped_material_consumption"]),
        MaterialRecording(cast(str, row["material_recording"])),
        cast(int, row["point_value_minor"]),
        DependencyGate(cast(str, row["dependency_gate"])),
    )


def _overrides(value: JsonValue) -> TaskOverrides:
    row = _object(value, _RULE_FIELDS)
    return TaskOverrides(
        cast(bool | None, row["claim_allowed"]),
        None
        if row["eligible_roles"] is None
        else tuple(Role(role) for role in _strings(row["eligible_roles"])),
        None if row["verification"] is None else VerificationMode(cast(str, row["verification"])),
        cast(bool | None, row["adult_performer_may_approve"]),
        cast(bool | None, row["task_scoped_material_consumption"]),
        None
        if row["material_recording"] is None
        else MaterialRecording(cast(str, row["material_recording"])),
        cast(int | None, row["point_value_minor"]),
        None
        if row["dependency_gate"] is None
        else DependencyGate(cast(str, row["dependency_gate"])),
    )


def _definition_value(value: TaskDefinition) -> JsonObject:
    return {
        "version": 1,
        "definition_id": value.definition_id,
        "household_id": value.household_id,
        "content": {
            "title": value.content.title,
            "description": value.content.description,
            "priority": value.content.priority.value,
            "tags": list(value.content.tags),
        },
        "created_at": value.created_at,
        "overrides": _rule_value(value.overrides),
        "state": value.state.value,
        "revision": value.revision,
    }


def _definition(value: JsonValue) -> TaskDefinition:
    row = _record(
        value,
        (
            "definition_id",
            "household_id",
            "content",
            "created_at",
            "overrides",
            "state",
            "revision",
        ),
    )
    content = _object(row["content"], ("title", "description", "priority", "tags"))
    return TaskDefinition(
        cast(str, row["definition_id"]),
        cast(str, row["household_id"]),
        TaskContent(
            cast(str, content["title"]),
            cast(str, content["description"]),
            Priority(cast(str, content["priority"])),
            _strings(content["tags"]),
        ),
        cast(int, row["created_at"]),
        _overrides(row["overrides"]),
        DefinitionState(cast(str, row["state"])),
        cast(int, row["revision"]),
    )


def policy_document(value: HouseholdTaskPolicy) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "household_id": value.household_id,
            "rules": _rule_value(value.rules),
            "revision": value.revision,
        }
    )


def definition_document(value: TaskDefinition) -> JsonDocument:
    return JsonDocument.from_value(_definition_value(value))


def occurrence_document(value: TaskOccurrence) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "occurrence_id": value.occurrence_id,
            "household_id": value.household_id,
            "definition_snapshot": _definition_value(value.definition_snapshot),
            "created_at": value.created_at,
            "state": value.state.value,
            "revision": value.revision,
            "assignee_ids": list(value.assignee_ids),
            "prerequisite_ids": list(value.prerequisite_ids),
            "required_subtask_ids": list(value.required_subtask_ids),
            "due_at": value.due_at,
            "current_cycle_id": value.current_cycle_id,
            "current_cycle_revision": value.current_cycle_revision,
            "state_reason": value.state_reason,
        }
    )


def _performer_value(value: TaskPerformer) -> JsonObject:
    return {"member_id": value.member_id, "role": value.role.value}


def _performer(value: JsonValue) -> TaskPerformer:
    row = _object(value, ("member_id", "role"))
    return TaskPerformer(cast(str, row["member_id"]), Role(cast(str, row["role"])))


def cycle_document(value: TaskCycle) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "cycle_id": value.cycle_id,
            "household_id": value.household_id,
            "occurrence_id": value.occurrence_id,
            "recorded_by": value.recorded_by,
            "performers": [_performer_value(performer) for performer in value.performers],
            "rules": _rule_value(value.rules),
            "definition_revision": value.definition_revision,
            "task_policy_revision": value.task_policy_revision,
            "identity_policy_revision": value.identity_policy_revision,
            "performed_at": value.performed_at,
            "recorded_at": value.recorded_at,
            "verification": value.verification.value,
            "verified_by": None
            if value.verified_by is None
            else _performer_value(value.verified_by),
            "verified_at": value.verified_at,
            "verification_reason": value.verification_reason,
            "closed_at": value.closed_at,
            "revision": value.revision,
        }
    )


def _policy(value: JsonValue) -> HouseholdTaskPolicy:
    row = _record(value, ("household_id", "rules", "revision"))
    return HouseholdTaskPolicy(
        cast(str, row["household_id"]), _rules(row["rules"]), cast(int, row["revision"])
    )


def _occurrence(value: JsonValue) -> TaskOccurrence:
    row = _record(
        value,
        (
            "occurrence_id",
            "household_id",
            "definition_snapshot",
            "created_at",
            "state",
            "revision",
            "assignee_ids",
            "prerequisite_ids",
            "required_subtask_ids",
            "due_at",
            "current_cycle_id",
            "current_cycle_revision",
            "state_reason",
        ),
    )
    return TaskOccurrence(
        cast(str, row["occurrence_id"]),
        cast(str, row["household_id"]),
        _definition(row["definition_snapshot"]),
        cast(int, row["created_at"]),
        OccurrenceState(cast(str, row["state"])),
        cast(int, row["revision"]),
        _strings(row["assignee_ids"]),
        _strings(row["prerequisite_ids"]),
        _strings(row["required_subtask_ids"]),
        cast(int | None, row["due_at"]),
        cast(str | None, row["current_cycle_id"]),
        cast(int | None, row["current_cycle_revision"]),
        cast(str, row["state_reason"]),
    )


def _cycle(value: JsonValue) -> TaskCycle:
    row = _record(
        value,
        (
            "cycle_id",
            "household_id",
            "occurrence_id",
            "recorded_by",
            "performers",
            "rules",
            "definition_revision",
            "task_policy_revision",
            "identity_policy_revision",
            "performed_at",
            "recorded_at",
            "verification",
            "verified_by",
            "verified_at",
            "verification_reason",
            "closed_at",
            "revision",
        ),
    )
    return TaskCycle(
        cast(str, row["cycle_id"]),
        cast(str, row["household_id"]),
        cast(str, row["occurrence_id"]),
        cast(str, row["recorded_by"]),
        tuple(_performer(item) for item in _array(row["performers"])),
        _rules(row["rules"]),
        cast(int, row["definition_revision"]),
        cast(int, row["task_policy_revision"]),
        cast(int, row["identity_policy_revision"]),
        cast(int, row["performed_at"]),
        cast(int, row["recorded_at"]),
        VerificationState(cast(str, row["verification"])),
        None if row["verified_by"] is None else _performer(row["verified_by"]),
        cast(int | None, row["verified_at"]),
        cast(str, row["verification_reason"]),
        cast(int | None, row["closed_at"]),
        cast(int, row["revision"]),
    )


def _decode[T](encoded: str, parse: Callable[[JsonValue], T]) -> T:
    try:
        return parse(JsonDocument(encoded).decode())
    except DomusError, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_task_record") from None


def read_policy(encoded: str) -> HouseholdTaskPolicy:
    return _decode(encoded, _policy)


def read_definition(encoded: str) -> TaskDefinition:
    return _decode(encoded, _definition)


def read_occurrence(encoded: str) -> TaskOccurrence:
    return _decode(encoded, _occurrence)


def read_cycle(encoded: str) -> TaskCycle:
    return _decode(encoded, _cycle)
