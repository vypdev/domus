"""Closed closure snapshots prepare durable storage without granting consumer authority."""

from typing import cast

from domus.domain.relative_lifecycle import RelativeClosure, RelativeClosureKind
from domus.domain.storage import Installation, JsonDocument, JsonObject, JsonValue
from domus.infrastructure.sqlite_recurrence_records import _object, _read, _record
from domus.infrastructure.sqlite_relative_recurrence_records import (
    _operation,
    read_relative_schedule,
    read_relative_slot,
    relative_schedule_document,
    relative_slot_document,
)
from domus.infrastructure.sqlite_task_records import cycle_document, read_cycle


def relative_closure_document(value: RelativeClosure) -> JsonDocument:
    document: JsonObject = {
        "version": 1,
        "installation": {
            "instance_id": value.installation.instance_id,
            "channel": value.installation.channel,
        },
        "schedule": relative_schedule_document(value.schedule).decode(),
        "cycle": cycle_document(value.cycle).decode(),
        "kind": value.kind.value,
        "recorded_at": value.recorded_at,
        "operation": {
            "command": {
                "household_id": value.operation.command.household_id,
                "actor_id": value.operation.command.actor_id,
                "action": value.operation.command.action,
                "key": value.operation.command.key,
            },
            "operation_id": value.operation.operation_id,
        },
        "successor": None
        if value.successor is None
        else relative_slot_document(value.successor).decode(),
    }
    return JsonDocument.from_value(document)


def _closure(value: JsonValue) -> RelativeClosure:
    row = _record(
        value,
        ("installation", "schedule", "cycle", "kind", "recorded_at", "operation", "successor"),
    )
    installation = _object(row["installation"], ("instance_id", "channel"))
    return RelativeClosure(
        Installation(cast(str, installation["instance_id"]), cast(str, installation["channel"])),
        read_relative_schedule(JsonDocument.from_value(row["schedule"]).encoded),
        read_cycle(JsonDocument.from_value(row["cycle"]).encoded),
        RelativeClosureKind(cast(str, row["kind"])),
        cast(int, row["recorded_at"]),
        _operation(row["operation"]),
        None
        if row["successor"] is None
        else read_relative_slot(JsonDocument.from_value(row["successor"]).encoded),
    )


def read_relative_closure(document: str) -> RelativeClosure:
    return _read(document, _closure)
