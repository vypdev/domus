"""Closure storage encoding preserves immutable original facts and rejects ambiguous data."""

import json
from dataclasses import replace

import pytest
from test_relative_lifecycle import closure
from test_relative_recurrence_records import values

from domus.domain.errors import StorageFailure
from domus.domain.relative_lifecycle import RelativeClosureKind
from domus.domain.relative_recurrence import RelativeOperation
from domus.domain.storage import JsonDocument, Receipt, RestorationProvenance
from domus.infrastructure.sqlite_relative_lifecycle import (
    read_relative_closure,
    relative_closure_document,
)


def date_only_closure():
    schedule, _, slot, cycle = values(False)
    original = closure()
    return replace(
        original,
        schedule=schedule,
        cycle=cycle,
        successor=slot,
        recorded_at=slot.created_at,
        operation=RelativeOperation(slot.command, original.operation.operation_id),
    )


@pytest.mark.parametrize(
    "value",
    [closure(kind=kind) for kind in RelativeClosureKind] + [date_only_closure()],
    ids=[kind.value for kind in RelativeClosureKind] + ["generated-date-only"],
)
def test_closed_roundtrip_preserves_full_snapshot_and_exact_original_proof(value):
    encoded = relative_closure_document(value)
    restored = read_relative_closure(encoded.encoded)
    assert restored == value and restored is not value
    assert restored.key == value.key and restored.document() == value.document()
    assert relative_closure_document(restored) == encoded
    assert restored.operation == value.operation
    assert restored.cycle == value.cycle and restored.schedule == value.schedule
    assert restored.successor == value.successor
    original = Receipt(
        value.operation.command,
        "a" * 64,
        value.operation.operation_id,
        JsonDocument.from_value({"relative_closure": value.document().decode()}),
        value.recorded_at,
    )
    assert restored.matches_receipt(original)
    assert restored.matches_receipt(
        replace(original, restoration=RestorationProvenance("restored", False))
    )
    assert encoded.decode()["operation"] == {
        "command": {
            "household_id": value.operation.command.household_id,
            "actor_id": value.operation.command.actor_id,
            "action": value.operation.command.action,
            "key": value.operation.command.key,
        },
        "operation_id": value.operation.operation_id,
    }


def change(document, path, value):
    for key in path[:-1]:
        document = document[key]
    document[path[-1]] = value


@pytest.mark.parametrize(
    "path,value",
    [
        (("version",), True),
        (("version",), 1.0),
        (("version",), 2),
        (("version",), "1"),
        (("kind",), "future"),
        (("recorded_at",), True),
        (("recorded_at",), -1),
        (("recorded_at",), 0),
        (("installation",), None),
        (("installation", "channel"), "unknown"),
        (("installation", "instance_id"), "invalid"),
        (("schedule",), []),
        (("schedule", "version"), 2),
        (("schedule", "definition_id"), "other"),
        (("schedule", "household_id"), "other"),
        (("schedule", "initial", "nominal", "local"), "20260301T120000"),
        (("cycle",), None),
        (("cycle", "version"), 2),
        (("cycle", "household_id"), "other"),
        (("cycle", "performed_at"), True),
        (("cycle", "cycle_id"), "other"),
        (("operation",), None),
        (("operation", "command", "household_id"), "other"),
        (("operation", "command", "actor_id"), "other"),
        (("operation", "command", "action"), "other"),
        (("operation", "command", "key"), "other"),
        (("operation", "operation_id"), ""),
        (("successor",), None),
        (("successor", "version"), 2),
        (("successor", "installation", "channel"), "stable"),
        (("successor", "schedule", "interval_days"), 31),
        (("successor", "source", "cycle", "cycle_id"), "other"),
        (("successor", "created_at"), 1),
    ],
)
def test_corrupt_or_inconsistent_original_record_fails_without_a_default(path, value):
    data = relative_closure_document(closure()).decode()
    change(data, path, value)
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(JsonDocument.from_value(data).encoded)


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("installation",),
        ("schedule",),
        ("cycle",),
        ("operation",),
        ("operation", "command"),
        ("successor",),
    ],
)
def test_unknown_fields_are_not_silently_discarded_at_any_record_boundary(path):
    data = relative_closure_document(closure()).decode()
    target = data
    for key in path:
        target = target[key]
    target["future_field"] = 1
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(JsonDocument.from_value(data).encoded)


@pytest.mark.parametrize(
    "field",
    [
        "version",
        "installation",
        "schedule",
        "cycle",
        "kind",
        "recorded_at",
        "operation",
        "successor",
    ],
)
def test_required_fields_have_no_implicit_legacy_values(field):
    data = relative_closure_document(closure()).decode()
    del data[field]
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(JsonDocument.from_value(data).encoded)


@pytest.mark.parametrize(
    "document",
    ["", "null", "true", "[]", '"record"', '{"version":1,"version":1}', '{"private":"\\ud800"}'],
)
def test_invalid_json_duplicate_keys_and_non_utf8_text_are_rejected(document):
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(document)


def test_noncanonical_json_spacing_is_rejected_without_repair_or_default():
    original = relative_closure_document(closure())
    spaced = json.dumps(original.decode(), indent=3, ensure_ascii=False)
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(spaced)
    assert relative_closure_document(read_relative_closure(original.encoded)) == original
    assert spaced != original.encoded


@pytest.mark.parametrize(
    "kind",
    [
        RelativeClosureKind.REJECTED,
        RelativeClosureKind.REOPENED,
        RelativeClosureKind.HISTORICAL_ABSENT,
    ],
)
def test_non_generated_closure_does_not_accept_a_successor_mapping(kind):
    data = relative_closure_document(closure(kind=kind)).decode()
    data["successor"] = relative_closure_document(closure()).decode()["successor"]
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_relative_closure(JsonDocument.from_value(data).encoded)
