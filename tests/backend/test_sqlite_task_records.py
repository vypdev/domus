"""Strict stored-record codecs retain snapshots and reject unsupported or corrupt payloads."""

import json
from collections.abc import Callable
from dataclasses import replace

import pytest
from test_tasks import cycle, definition, occurrence, restricted_cycle

from domus.domain.errors import StorageFailure
from domus.domain.identity import Role
from domus.domain.storage import JsonDocument
from domus.domain.task_values import (
    DependencyGate,
    MaterialRecording,
    TaskContent,
    TaskOverrides,
    TaskPerformer,
    TaskRules,
    VerificationMode,
    VerificationState,
)
from domus.domain.tasks import HouseholdTaskPolicy
from domus.infrastructure.sqlite_task_records import (
    cycle_document,
    definition_document,
    occurrence_document,
    policy_document,
    read_cycle,
    read_definition,
    read_occurrence,
    read_policy,
)


def test_policy_and_override_round_trip_preserves_inherited_and_explicit_values() -> None:
    policy = HouseholdTaskPolicy("home", TaskRules())
    assert read_policy(policy_document(policy).encoded) == policy
    explicit = TaskOverrides(
        False, (), VerificationMode.ADULT, False, False, MaterialRecording.SEPARATE, 333
    )
    changed = definition(
        content=TaskContent("Limpiar 🧹", "One\nTwo", tags=("kitchen",)), overrides=explicit
    )
    assert read_definition(definition_document(changed).encoded) == changed
    assert read_definition(definition_document(definition()).encoded).overrides == TaskOverrides()
    alternative = replace(policy, rules=explicit.resolve(policy.rules))
    assert read_policy(policy_document(alternative).encoded) == alternative
    gated = replace(policy, rules=replace(policy.rules, dependency_gate=DependencyGate.APPROVED))
    assert (
        read_policy(policy_document(gated).encoded).rules.dependency_gate is DependencyGate.APPROVED
    )
    task = definition(overrides=TaskOverrides(dependency_gate=DependencyGate.PERFORMED))
    assert (
        read_definition(definition_document(task).encoded).overrides.dependency_gate
        is DependencyGate.PERFORMED
    )


def test_occurrence_round_trip_retains_original_snapshot_lists_and_current_cycle_version() -> None:
    work = occurrence(prerequisite_ids=("before",), required_subtask_ids=("child",), due_at=99)
    assert read_occurrence(occurrence_document(work).encoded) == work
    done = occurrence().complete(cycle(), requirements=())
    restored = read_occurrence(occurrence_document(done).encoded)
    assert restored == done and restored.current_cycle_revision == 1


def test_cycle_round_trip_retains_actual_roles_policy_revisions_and_decision_clock() -> None:
    for original in [
        cycle(),
        restricted_cycle(),
        restricted_cycle().verify(
            VerificationState.APPROVED, TaskPerformer("adult", Role.ADULT), 50
        ),
        restricted_cycle()
        .verify(VerificationState.REJECTED, TaskPerformer("adult", Role.ADULT), 50, "Incomplete")
        .close(60),
    ]:
        assert read_cycle(cycle_document(original).encoded) == original


READERS: tuple[Callable[[str], object], ...] = (
    read_policy,
    read_definition,
    read_occurrence,
    read_cycle,
)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(
    "encoded",
    ["{", "[]", "null", '{"version":1,"version":1}', '{"body":"' + "x" * 65536 + '"}', "\ud800"],
)
def test_malformed_oversized_or_duplicate_encoded_documents_fail_closed(
    reader: Callable[[str], object], encoded: str
) -> None:
    with pytest.raises(StorageFailure, match="invalid_task_record"):
        reader(encoded)


@pytest.mark.parametrize(
    "document,reader",
    [
        (policy_document(HouseholdTaskPolicy("home", TaskRules())), read_policy),
        (definition_document(definition()), read_definition),
        (occurrence_document(occurrence()), read_occurrence),
        (cycle_document(cycle()), read_cycle),
    ],
)
@pytest.mark.parametrize("change", ["extra", "missing", "future", "boolean"])
def test_record_shape_and_version_are_never_guessed(
    document: JsonDocument, reader: Callable[[str], object], change: str
) -> None:
    value = document.decode()
    if change == "extra":
        value["unknown"] = "future semantics"
    elif change == "missing":
        del value["revision"]
    else:
        value["version"] = 2 if change == "future" else True
    with pytest.raises(StorageFailure):
        reader(json.dumps(value))


@pytest.mark.parametrize(
    "path,value",
    [
        (("content",), []),
        (("content", "priority"), "future"),
        (("content", "tags"), "kitchen"),
        (("content", "tags"), [1]),
        (("content", "tags"), ["same", "same"]),
        (("overrides",), {"claim_allowed": True}),
        (("overrides", "eligible_roles"), ["unknown"]),
        (("overrides", "verification"), "none"),
        (("overrides", "material_recording"), "automatic"),
        (("overrides", "claim_allowed"), 1),
        (("overrides", "point_value_minor"), 3.33),
    ],
)
def test_nested_definition_corruption_cannot_become_a_default_or_grant(
    path: tuple[str, ...], value: object
) -> None:
    body = definition_document(definition()).decode()
    target = body
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(StorageFailure):
        read_definition(json.dumps(body))


@pytest.mark.parametrize(
    "field,value",
    [
        ("assignee_ids", "member"),
        ("prerequisite_ids", [None]),
        ("household_id", "other"),
        ("definition_snapshot", {}),
        ("due_at", True),
        ("current_cycle_revision", 1),
        ("state", "completed"),
    ],
)
def test_occurrence_decode_rechecks_scope_and_state_facts(field: str, value: object) -> None:
    body = occurrence_document(occurrence()).decode()
    body[field] = value
    with pytest.raises(StorageFailure):
        read_occurrence(json.dumps(body))


@pytest.mark.parametrize(
    "field,value",
    [
        ("performers", "member"),
        ("performers", [None]),
        ("performers", [{"member_id": "member", "role": "unknown"}]),
        ("verified_by", []),
        ("verification", "approved"),
        ("rules", []),
        ("performed_at", True),
        ("definition_revision", 0),
    ],
)
def test_cycle_decode_never_coerces_partial_verification_or_policy(
    field: str, value: object
) -> None:
    body = cycle_document(cycle()).decode()
    body[field] = value
    with pytest.raises(StorageFailure):
        read_cycle(json.dumps(body))
