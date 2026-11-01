"""Closed persistence codecs preserve every nominal/time-policy fact and reject corrupt bytes."""

import json
from dataclasses import replace
from datetime import date

import pytest
from test_recurrence_records import values

from domus.domain.errors import StorageFailure
from domus.domain.recurrence_planning import cursor_binding
from domus.domain.recurrence_rules import ByDay, FixedPattern, Frequency, NominalDate, Weekday
from domus.domain.recurrence_time import MAX_INSTANT_MS
from domus.infrastructure.sqlite_recurrence_records import (
    progress_document,
    read_progress,
    read_schedule,
    read_slot,
    schedule_document,
    slot_document,
)

CODECS = [
    (0, schedule_document, read_schedule),
    (1, progress_document, read_progress),
    (2, slot_document, read_slot),
]


@pytest.mark.parametrize("timed", [False, True])
def test_closed_codecs_round_trip_every_pattern_selector_and_time_snapshot(timed):
    rule, progress, slot = values(timed)
    pattern = FixedPattern(
        rule.pattern.start,
        Frequency.YEARLY,
        2,
        Weekday.SU,
        (ByDay(Weekday.MO, 1), ByDay(Weekday.TH)),
        (1, 12),
        (-1, 1),
        (-1, 1),
        until=MAX_INSTANT_MS if timed else NominalDate(date(2027, 1, 1)),
    )
    rule = replace(rule, pattern=pattern)
    progress = replace(
        progress,
        cursor=replace(progress.cursor, binding=cursor_binding(pattern, rule.policy)),
        last_run_at=101,
    )
    slot = replace(slot, schedule=rule)
    for value, encode, decode in [
        (rule, schedule_document, read_schedule),
        (progress, progress_document, read_progress),
        (slot, slot_document, read_slot),
    ]:
        document = encode(value)
        assert decode(document.encoded) == value
        assert encode(decode(document.encoded)) == document
    limited = replace(rule, pattern=replace(pattern, until=None, count=5))
    assert read_schedule(schedule_document(limited).encoded) == limited


@pytest.mark.parametrize("index,encode,decode", CODECS)
@pytest.mark.parametrize("field,value", [("version", True), ("version", 2), ("unexpected", None)])
def test_unknown_or_extra_record_fields_never_receive_defaults(index, encode, decode, field, value):
    row = encode(values()[index]).decode()
    row[field] = value
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        decode(json.dumps(row))


@pytest.mark.parametrize("index,encode,decode", CODECS)
@pytest.mark.parametrize(
    "document",
    ["null", "[]", "{", '{"version":1,"version":1}', '{"payload":"' + "a" * 65536 + '"}'],
)
def test_nonobjects_duplicate_keys_and_oversized_input_fail_safely(index, encode, decode, document):
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        decode(document)


@pytest.mark.parametrize(
    "timed,local",
    [
        (False, None),
        (False, "2026-W01-4"),
        (False, "20260101"),
        (False, "2026-01-01T00:00:00"),
        (True, "2026-01-01 12:00:00"),
        (True, "2026-01-01T12:00:00+00:00"),
        (True, "2026-01-01T12:00:00.001"),
    ],
)
def test_stored_nominal_values_require_canonical_tagged_date_or_naive_time(timed, local):
    row = schedule_document(values(timed)[0]).decode()
    row["pattern"]["start"]["local"] = local
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_schedule(json.dumps(row))


@pytest.mark.parametrize(
    "field,value",
    [
        ("by_day", None),
        ("by_month", "1"),
        ("frequency", "HOURLY"),
        ("interval", True),
        ("start", {"kind": "other", "local": "2026-01-01"}),
        ("until", {"kind": "date", "local": "2025-01-01", "unknown": True}),
    ],
)
def test_corrupt_nested_pattern_values_are_not_coerced(field, value):
    row = schedule_document(values()[0]).decode()
    row["pattern"][field] = value
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_schedule(json.dumps(row))


def test_a_resolved_time_cannot_be_retagged_as_a_date():
    row = slot_document(values(True)[2]).decode()
    row["planned"]["resolved"]["nominal"] = {"kind": "date", "local": "2026-01-01"}
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_slot(json.dumps(row))
