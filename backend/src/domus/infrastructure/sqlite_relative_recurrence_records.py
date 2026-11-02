"""Closed canonical relative records retain original cycle and actual local-time facts."""

from datetime import datetime
from typing import cast

from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_time import LocalInstant, RelativeInterval
from domus.domain.relative_recurrence import (
    RelativeOperation,
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
    RelativeSource,
    SuccessorVisibility,
)
from domus.domain.storage import CommandKey, Installation, JsonDocument, JsonObject, JsonValue
from domus.infrastructure.sqlite_recurrence_records import (
    _local,
    _object,
    _planned,
    _policy,
    _policy_value,
    _read,
    _record,
)
from domus.infrastructure.sqlite_task_records import cycle_document, read_cycle


def _schedule_value(value: RelativeSchedule) -> JsonObject:
    return {
        "version": 1,
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "definition_id": value.definition_id,
        "initial": value.initial.value(),
        "interval_days": value.interval.days,
        "policy": _policy_value(value.policy),
        "created_at": value.created_at,
        "visibility": value.visibility.value,
        "state": value.state.value,
        "revision": value.revision,
        "pattern_revision": value.pattern_revision,
    }


def _schedule(value: JsonValue) -> RelativeSchedule:
    row = _record(
        value,
        (
            "schedule_id",
            "household_id",
            "definition_id",
            "initial",
            "interval_days",
            "policy",
            "created_at",
            "visibility",
            "state",
            "revision",
            "pattern_revision",
        ),
    )
    return RelativeSchedule(
        cast(str, row["schedule_id"]),
        cast(str, row["household_id"]),
        cast(str, row["definition_id"]),
        _planned(row["initial"]),
        RelativeInterval(cast(int, row["interval_days"])),
        _policy(row["policy"]),
        cast(int, row["created_at"]),
        SuccessorVisibility(cast(str, row["visibility"])),
        ScheduleState(cast(str, row["state"])),
        cast(int, row["revision"]),
        cast(int, row["pattern_revision"]),
    )


def relative_schedule_document(value: RelativeSchedule) -> JsonDocument:
    return JsonDocument.from_value(_schedule_value(value))


def relative_progress_document(value: RelativeProgress) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "schedule_id": value.schedule_id,
            "household_id": value.household_id,
            "pattern_revision": value.pattern_revision,
            "binding": value.binding,
            "current_occurrence_id": value.current_occurrence_id,
            "current_slot_key": value.current_slot_key,
            "source_after": value.source_after,
            "last_run_at": value.last_run_at,
            "revision": value.revision,
            "evidence": None
            if value.evidence is None
            else {
                "command": {
                    "household_id": value.evidence.command.household_id,
                    "actor_id": value.evidence.command.actor_id,
                    "action": value.evidence.command.action,
                    "key": value.evidence.command.key,
                },
                "operation_id": value.evidence.operation_id,
            },
        }
    )


def _progress(value: JsonValue) -> RelativeProgress:
    row = _record(
        value,
        (
            "schedule_id",
            "household_id",
            "pattern_revision",
            "binding",
            "current_occurrence_id",
            "current_slot_key",
            "source_after",
            "last_run_at",
            "revision",
            "evidence",
        ),
    )
    return RelativeProgress(
        cast(str, row["schedule_id"]),
        cast(str, row["household_id"]),
        cast(int, row["pattern_revision"]),
        cast(str, row["binding"]),
        cast(str | None, row["current_occurrence_id"]),
        cast(str | None, row["current_slot_key"]),
        cast(int, row["source_after"]),
        cast(int | None, row["last_run_at"]),
        cast(int, row["revision"]),
        None if row["evidence"] is None else _operation(row["evidence"]),
    )


def _operation(value: JsonValue) -> RelativeOperation:
    row = _object(value, ("command", "operation_id"))
    command = _object(row["command"], ("household_id", "actor_id", "action", "key"))
    return RelativeOperation(
        CommandKey(
            cast(str, command["household_id"]),
            cast(str, command["actor_id"]),
            cast(str, command["action"]),
            cast(str, command["key"]),
        ),
        cast(str, row["operation_id"]),
    )


def _source_value(value: RelativeSource) -> JsonObject:
    local = value.performed_local
    return {
        "cycle": cycle_document(value.cycle).decode(),
        "performed_local": {
            "instant_ms": local.instant_ms,
            "local": local.local.isoformat(),
            "offset_seconds": local.offset_seconds,
            "policy": _policy_value(local.policy),
            "zone_digest": local.zone_digest,
        },
    }


def _source(value: JsonValue) -> RelativeSource:
    row = _object(value, ("cycle", "performed_local"))
    local = _object(
        row["performed_local"],
        (
            "instant_ms",
            "local",
            "offset_seconds",
            "policy",
            "zone_digest",
        ),
    )
    return RelativeSource(
        read_cycle(JsonDocument.from_value(row["cycle"]).encoded),
        LocalInstant(
            cast(int, local["instant_ms"]),
            cast(datetime, _local(local["local"], timed=True)),
            cast(int, local["offset_seconds"]),
            _policy(local["policy"]),
            cast(str, local["zone_digest"]),
        ),
    )


def relative_slot_document(value: RelativeSlot) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "installation": {
                "instance_id": value.installation.instance_id,
                "channel": value.installation.channel,
            },
            "schedule": _schedule_value(value.schedule),
            "planned": value.planned.value(),
            "occurrence_id": value.occurrence_id,
            "created_at": value.created_at,
            "source": None if value.source is None else _source_value(value.source),
        }
    )


def _slot(value: JsonValue) -> RelativeSlot:
    row = _record(
        value, ("installation", "schedule", "planned", "occurrence_id", "created_at", "source")
    )
    installation = _object(row["installation"], ("instance_id", "channel"))
    return RelativeSlot(
        Installation(cast(str, installation["instance_id"]), cast(str, installation["channel"])),
        _schedule(row["schedule"]),
        _planned(row["planned"]),
        cast(str, row["occurrence_id"]),
        cast(int, row["created_at"]),
        None if row["source"] is None else _source(row["source"]),
    )


def read_relative_schedule(document: str) -> RelativeSchedule:
    return _read(document, _schedule)


def read_relative_progress(document: str) -> RelativeProgress:
    return _read(document, _progress)


def read_relative_slot(document: str) -> RelativeSlot:
    return _read(document, _slot)
