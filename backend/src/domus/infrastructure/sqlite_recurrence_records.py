"""Closed versioned recurrence documents; imported/corrupt facts receive no guessed defaults."""

from collections.abc import Callable
from datetime import date, datetime
from typing import cast

from domus.domain.errors import DomusError, InvalidInput, StorageFailure
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot
from domus.domain.recurrence_records import (
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rules import (
    ByDay,
    FixedPattern,
    Frequency,
    NominalDate,
    NominalSlot,
    Weekday,
)
from domus.domain.recurrence_time import (
    FoldPolicy,
    NominalTime,
    ResolvedTime,
    TimePolicy,
    TimeResolution,
)
from domus.domain.storage import Installation, JsonDocument, JsonObject, JsonValue


def _object(value: JsonValue, keys: tuple[str, ...]) -> JsonObject:
    if type(value) is not dict or set(value) != set(keys):
        raise InvalidInput("invalid_recurrence_record")
    return value


def _record(value: JsonValue, keys: tuple[str, ...]) -> JsonObject:
    row = _object(value, ("version", *keys))
    if type(row["version"]) is not int or row["version"] != 1:
        raise InvalidInput("unsupported_recurrence_record")
    return row


def _array(value: JsonValue) -> list[JsonValue]:
    if type(value) is not list:
        raise InvalidInput("invalid_recurrence_record")
    return value


def _local(value: JsonValue, *, timed: bool) -> date | datetime:
    if type(value) is not str:
        raise InvalidInput("invalid_recurrence_record")
    result = datetime.fromisoformat(value) if timed else date.fromisoformat(value)
    if result.isoformat() != value:
        raise InvalidInput("invalid_recurrence_record")
    return result


def _nominal_value(value: NominalSlot) -> JsonObject:
    return {
        "kind": "date" if isinstance(value, NominalDate) else "time",
        "local": value.local.isoformat(),
    }


def _nominal(value: JsonValue) -> NominalSlot:
    row = _object(value, ("kind", "local"))
    if row["kind"] == "date":
        return NominalDate(_local(row["local"], timed=False))
    if row["kind"] == "time":
        return NominalTime(cast(datetime, _local(row["local"], timed=True)))
    raise InvalidInput("invalid_recurrence_record")


def _policy_value(value: TimePolicy) -> JsonObject:
    return {
        "zone": value.zone,
        "data_identity": value.data_identity,
        "repeated_time": value.repeated_time.value,
        "revision": value.revision,
    }


def _policy(value: JsonValue) -> TimePolicy:
    row = _object(value, ("zone", "data_identity", "repeated_time", "revision"))
    return TimePolicy(
        cast(str, row["zone"]),
        cast(str, row["data_identity"]),
        FoldPolicy(cast(str, row["repeated_time"])),
        cast(int, row["revision"]),
    )


def _pattern_value(value: FixedPattern) -> JsonObject:
    return {
        "start": _nominal_value(value.start),
        "frequency": value.frequency.value,
        "interval": value.interval,
        "week_start": value.week_start.value,
        "by_day": [
            {"weekday": item.weekday.value, "ordinal": item.ordinal} for item in value.by_day
        ],
        "by_month": list(value.by_month),
        "by_month_day": list(value.by_month_day),
        "by_set_position": list(value.by_set_position),
        "count": value.count,
        "until": _nominal_value(value.until)
        if isinstance(value.until, NominalDate)
        else value.until,
    }


def _day(value: JsonValue) -> ByDay:
    row = _object(value, ("weekday", "ordinal"))
    return ByDay(Weekday(cast(str, row["weekday"])), cast(int | None, row["ordinal"]))


def _pattern(value: JsonValue) -> FixedPattern:
    row = _object(
        value,
        (
            "start",
            "frequency",
            "interval",
            "week_start",
            "by_day",
            "by_month",
            "by_month_day",
            "by_set_position",
            "count",
            "until",
        ),
    )
    until = row["until"]
    return FixedPattern(
        _nominal(row["start"]),
        Frequency(cast(str, row["frequency"])),
        cast(int, row["interval"]),
        Weekday(cast(str, row["week_start"])),
        tuple(_day(item) for item in _array(row["by_day"])),
        tuple(cast(list[int], _array(row["by_month"]))),
        tuple(cast(list[int], _array(row["by_month_day"]))),
        tuple(cast(list[int], _array(row["by_set_position"]))),
        cast(int | None, row["count"]),
        cast(NominalDate, _nominal(until)) if type(until) is dict else cast(int | None, until),
    )


def _schedule_value(value: FixedSchedule) -> JsonObject:
    return {
        "version": 1,
        "schedule_id": value.schedule_id,
        "household_id": value.household_id,
        "definition_id": value.definition_id,
        "pattern": _pattern_value(value.pattern),
        "policy": _policy_value(value.policy),
        "created_at": value.created_at,
        "state": value.state.value,
        "revision": value.revision,
        "pattern_revision": value.pattern_revision,
    }


def _schedule(value: JsonValue) -> FixedSchedule:
    row = _record(
        value,
        (
            "schedule_id",
            "household_id",
            "definition_id",
            "pattern",
            "policy",
            "created_at",
            "state",
            "revision",
            "pattern_revision",
        ),
    )
    return FixedSchedule(
        cast(str, row["schedule_id"]),
        cast(str, row["household_id"]),
        cast(str, row["definition_id"]),
        _pattern(row["pattern"]),
        _policy(row["policy"]),
        cast(int, row["created_at"]),
        ScheduleState(cast(str, row["state"])),
        cast(int, row["revision"]),
        cast(int, row["pattern_revision"]),
    )


def schedule_document(value: FixedSchedule) -> JsonDocument:
    return JsonDocument.from_value(_schedule_value(value))


def progress_document(value: FixedProgress) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "schedule_id": value.schedule_id,
            "household_id": value.household_id,
            "pattern_revision": value.pattern_revision,
            "revision": value.revision,
            "last_run_at": value.last_run_at,
            "range_complete": value.range_complete,
            "cursor": {
                "binding": value.cursor.binding,
                "period_index": value.cursor.period_index,
                "offset": value.cursor.offset,
                "nominal_count": value.cursor.nominal_count,
                "closed": value.cursor.closed,
            },
        }
    )


def _progress(value: JsonValue) -> FixedProgress:
    row = _record(
        value,
        (
            "schedule_id",
            "household_id",
            "pattern_revision",
            "revision",
            "last_run_at",
            "range_complete",
            "cursor",
        ),
    )
    cursor = _object(
        row["cursor"], ("binding", "period_index", "offset", "nominal_count", "closed")
    )
    return FixedProgress(
        cast(str, row["schedule_id"]),
        cast(str, row["household_id"]),
        cast(int, row["pattern_revision"]),
        FixedCursor(
            cast(str, cursor["binding"]),
            cast(int, cursor["period_index"]),
            cast(int, cursor["offset"]),
            cast(int, cursor["nominal_count"]),
            cast(bool, cursor["closed"]),
        ),
        cast(int, row["revision"]),
        cast(int | None, row["last_run_at"]),
        cast(bool, row["range_complete"]),
    )


def _resolved_value(value: ResolvedTime) -> JsonObject:
    return {
        "nominal": _nominal_value(value.nominal),
        "policy": _policy_value(value.policy),
        "resolved_local": value.resolved_local.isoformat(),
        "offset_seconds": value.offset_seconds,
        "resolution": value.resolution.value,
        "zone_digest": value.zone_digest,
    }


def _resolved(value: JsonValue) -> ResolvedTime:
    row = _object(
        value,
        ("nominal", "policy", "resolved_local", "offset_seconds", "resolution", "zone_digest"),
    )
    nominal = _nominal(row["nominal"])
    if not isinstance(nominal, NominalTime):
        raise InvalidInput("invalid_recurrence_record")
    return ResolvedTime(
        nominal,
        _policy(row["policy"]),
        cast(datetime, _local(row["resolved_local"], timed=True)),
        cast(int, row["offset_seconds"]),
        TimeResolution(cast(str, row["resolution"])),
        cast(str, row["zone_digest"]),
    )


def slot_document(value: ScheduledSlot) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "installation": {
                "instance_id": value.installation.instance_id,
                "channel": value.installation.channel,
            },
            "schedule": _schedule_value(value.schedule),
            "occurrence_id": value.occurrence_id,
            "created_at": value.created_at,
            "planned": {
                "nominal": _nominal_value(value.planned.nominal),
                "resolved": None
                if value.planned.resolved is None
                else _resolved_value(value.planned.resolved),
            },
        }
    )


def _slot(value: JsonValue) -> ScheduledSlot:
    row = _record(value, ("installation", "schedule", "occurrence_id", "created_at", "planned"))
    installation = _object(row["installation"], ("instance_id", "channel"))
    planned = _object(row["planned"], ("nominal", "resolved"))
    return ScheduledSlot(
        Installation(cast(str, installation["instance_id"]), cast(str, installation["channel"])),
        _schedule(row["schedule"]),
        PlannedFixedSlot(
            _nominal(planned["nominal"]),
            None if planned["resolved"] is None else _resolved(planned["resolved"]),
        ),
        cast(str, row["occurrence_id"]),
        cast(int, row["created_at"]),
    )


def _read[T](document: str, build: Callable[[JsonValue], T]) -> T:
    try:
        return build(JsonDocument(document).decode())
    except DomusError, KeyError, TypeError, ValueError, OverflowError:
        raise StorageFailure("invalid_recurrence_record") from None


def read_schedule(document: str) -> FixedSchedule:
    return _read(document, _schedule)


def read_progress(document: str) -> FixedProgress:
    return _read(document, _progress)


def read_slot(document: str) -> ScheduledSlot:
    return _read(document, _slot)
