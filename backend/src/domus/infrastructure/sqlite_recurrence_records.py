"""Closed versioned recurrence documents; imported/corrupt facts receive no guessed defaults."""

from collections.abc import Callable
from datetime import date, datetime
from typing import cast

from domus.domain.errors import DomusError, InvalidInput, StorageFailure
from domus.domain.recurrence_frontier import RecurrenceFrontier
from domus.domain.recurrence_planning import (
    CursorEvidence,
    CursorTimeEvidence,
    FixedCursor,
    PlannedFixedSlot,
)
from domus.domain.recurrence_records import (
    FixedException,
    FixedExceptionKind,
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
from domus.domain.storage import CommandKey, Installation, JsonDocument, JsonObject, JsonValue


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
        **({"exceptions": [item.value() for item in value.exceptions]} if value.exceptions else {}),
    }


def _exception(value: JsonValue) -> FixedException:
    row = _object(value, ("kind", "nominal", "reason"))
    return FixedException(
        FixedExceptionKind(cast(str, row["kind"])),
        _nominal(row["nominal"]),
        cast(str, row["reason"]),
    )


def _schedule(value: JsonValue) -> FixedSchedule:
    exceptions = type(value) is dict and "exceptions" in value
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
            *(("exceptions",) if exceptions else ()),
        ),
    )
    schedule = FixedSchedule(
        cast(str, row["schedule_id"]),
        cast(str, row["household_id"]),
        cast(str, row["definition_id"]),
        _pattern(row["pattern"]),
        _policy(row["policy"]),
        cast(int, row["created_at"]),
        ScheduleState(cast(str, row["state"])),
        cast(int, row["revision"]),
        cast(int, row["pattern_revision"]),
        tuple(_exception(item) for item in _array(row["exceptions"])) if exceptions else (),
    )
    if exceptions and (
        not schedule.exceptions
        or row["exceptions"] != [item.value() for item in schedule.exceptions]
    ):
        raise InvalidInput("noncanonical_recurrence_record")
    return schedule


def schedule_document(value: FixedSchedule) -> JsonDocument:
    return JsonDocument.from_value(_schedule_value(value))


def progress_document(value: FixedProgress) -> JsonDocument:
    data: JsonObject = {
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
        "evidence": None if value.evidence is None else value.evidence.document().decode(),
    }
    return JsonDocument.from_value(data)


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
            "evidence",
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
        None if row["evidence"] is None else _evidence(row["evidence"]),
    )


def _cursor(value: JsonValue) -> FixedCursor:
    row = _object(value, ("binding", "period_index", "offset", "nominal_count", "closed"))
    return FixedCursor(
        cast(str, row["binding"]),
        cast(int, row["period_index"]),
        cast(int, row["offset"]),
        cast(int, row["nominal_count"]),
        cast(bool, row["closed"]),
    )


def _planned(value: JsonValue) -> PlannedFixedSlot:
    row = _object(value, ("nominal", "resolved"))
    return PlannedFixedSlot(
        _nominal(row["nominal"]), None if row["resolved"] is None else _resolved(row["resolved"])
    )


def _evidence(value: JsonValue) -> CursorEvidence:
    row = _record(value, ("time", "command", "operation_id"))
    core = _record(row["time"], ("cursor", "policy", "range_complete", "last", "terminal"))
    command = _object(row["command"], ("household_id", "actor_id", "action", "key"))
    return CursorEvidence(
        CursorTimeEvidence(
            _cursor(core["cursor"]),
            _policy(core["policy"]),
            cast(bool, core["range_complete"]),
            None if core["last"] is None else _planned(core["last"]),
            None if core["terminal"] is None else _planned(core["terminal"]),
        ),
        CommandKey(
            cast(str, command["household_id"]),
            cast(str, command["actor_id"]),
            cast(str, command["action"]),
            cast(str, command["key"]),
        ),
        cast(str, row["operation_id"]),
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
            **({"added": True} if value.added else {}),
            "planned": {
                "nominal": _nominal_value(value.planned.nominal),
                "resolved": None
                if value.planned.resolved is None
                else _resolved_value(value.planned.resolved),
            },
        }
    )


def _slot(value: JsonValue) -> ScheduledSlot:
    added = type(value) is dict and "added" in value
    row = _record(
        value,
        (
            "installation",
            "schedule",
            "occurrence_id",
            "created_at",
            "planned",
            *(("added",) if added else ()),
        ),
    )
    if added and row["added"] is not True:
        raise InvalidInput("invalid_recurrence_record")
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
        added,
    )


def _read[T](document: str, build: Callable[[JsonValue], T]) -> T:
    try:
        canonical = JsonDocument(document)
        if canonical.encoded != document:
            raise InvalidInput("noncanonical_recurrence_record")
        return build(canonical.decode())
    except DomusError, KeyError, TypeError, ValueError, OverflowError:
        raise StorageFailure("invalid_recurrence_record") from None


def read_schedule(document: str) -> FixedSchedule:
    return _read(document, _schedule)


def read_progress(document: str) -> FixedProgress:
    return _read(document, _progress)


def read_slot(document: str) -> ScheduledSlot:
    return _read(document, _slot)


def frontier_document(value: RecurrenceFrontier) -> JsonDocument:
    return JsonDocument.from_value(
        {
            "version": 1,
            "household_id": value.household_id,
            "after_schedule_id": value.after_schedule_id,
            "selected_at": value.selected_at,
            "revision": value.revision,
        }
    )


def _frontier(value: JsonValue) -> RecurrenceFrontier:
    row = _record(value, ("household_id", "after_schedule_id", "selected_at", "revision"))
    return RecurrenceFrontier(
        cast(str, row["household_id"]),
        cast(str | None, row["after_schedule_id"]),
        cast(int, row["selected_at"]),
        cast(int, row["revision"]),
    )


def read_frontier(document: str) -> RecurrenceFrontier:
    return _read(document, _frontier)
