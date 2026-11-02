"""Persisted cursor position and consumed nominal rank cannot contradict each other."""

from dataclasses import replace
from datetime import date

import pytest
from test_fixed_materialization import configured
from test_fixed_recurrence_planning import pattern, planner, policy
from test_recurrence_records import values
from test_sqlite_snapshots import Clock

from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.recurrence_planning import FixedCursor, cursor_binding
from domus.domain.recurrence_records import FixedProgress
from domus.domain.recurrence_rules import NominalDate
from domus.infrastructure.sqlite_recurrence_records import progress_document
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


@pytest.mark.parametrize(
    "raw",
    [
        "FREQ=DAILY",
        "FREQ=WEEKLY;BYDAY=MO,TH",
        "FREQ=MONTHLY;BYMONTHDAY=1,2",
        "FREQ=YEARLY;BYMONTH=1,2;BYMONTHDAY=1",
    ],
)
def test_a_correct_binding_and_plausible_count_cannot_hide_skipped_original_periods(raw):
    value = pattern(raw)
    first = planner().expand(value, policy(), slot_limit=1)
    rule = replace(values()[0], pattern=value, policy=policy())
    original = FixedProgress(rule.schedule_id, rule.household_id, 1, first.cursor)
    assert original.matches_schedule(rule)
    changed = replace(
        original, cursor=replace(first.cursor, period_index=first.cursor.period_index + 10)
    )
    assert not changed.matches_schedule(rule)


@pytest.mark.parametrize(
    "cursor",
    [
        {"period_index": 10},
        {"offset": 1},
        {"offset": 2},
        {"period_index": 2**63 - 1},
        {"period_index": 1, "nominal_count": 0},
        {"closed": True},
    ],
)
def test_initial_progress_cannot_claim_a_false_position_or_an_unlimited_closed_rule(cursor):
    rule, progress, _ = values()
    proposed = replace(
        progress,
        cursor=replace(progress.cursor, **cursor),
        range_complete=bool(cursor.get("closed")),
    )
    assert not proposed.matches_schedule(rule)


@pytest.mark.parametrize("mode", ["read", "write", "snapshot", "step"])
def test_canonical_cursor_corruption_is_refused_without_work_or_byte_repair(tmp_path, mode):
    service, store, _, _, rule_id, before = configured(tmp_path, count=None)
    with store.read() as unit:
        original = unit.recurrence.progress("home", rule_id)
    altered = replace(original, cursor=replace(original.cursor, period_index=100))
    if mode == "write":
        with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
            with store.write() as unit:
                unit.recurrence.save_progress(replace(altered, revision=2), 1)
        with store.read() as unit:
            assert unit.recurrence.progress("home", rule_id) == original
        return
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_progress SET document=?", (progress_document(altered).encoded,)
        )
    source = store.path.read_bytes()
    if mode == "read":
        with store.read() as unit:
            with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
                unit.recurrence.progress("home", rule_id)
    elif mode == "snapshot":
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    else:
        with pytest.raises(StorageFailure):
            service.step(rule_id, before)
    assert store.path.read_bytes() == source
    with store.read() as unit:
        assert unit.tasks.occurrences("home") == () and unit.recurrence.slots("home", rule_id) == ()


@pytest.mark.parametrize(
    "raw,start",
    [
        ("FREQ=MONTHLY;BYMONTHDAY=31", date(2026, 1, 31)),
        ("FREQ=WEEKLY;BYDAY=MO,WE,SU;INTERVAL=3", date(2026, 1, 7)),
        ("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29", date(2024, 2, 29)),
        ("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30", date(2026, 1, 1)),
        ("FREQ=DAILY;COUNT=2", date(2026, 1, 1)),
        ("FREQ=DAILY;UNTIL=20260103", date(2026, 1, 1)),
        ("FREQ=DAILY", date(9999, 12, 31)),
    ],
)
def test_actual_bounded_progress_remains_valid_through_empty_periods_count_until_and_exhaustion(
    raw, start
):
    value = pattern(raw, NominalDate(start))
    rule = replace(values()[0], pattern=value)
    cursor = FixedCursor(cursor_binding(value, rule.policy))
    for _ in range(6):
        batch = planner().expand(value, rule.policy, cursor=cursor, slot_limit=1, period_limit=2)
        cursor = batch.cursor
        assert FixedProgress(
            rule.schedule_id, rule.household_id, 1, cursor, range_complete=batch.range_complete
        ).matches_schedule(rule)
        if cursor.closed:
            break


@pytest.mark.parametrize(
    "raw,index,offset,count",
    [
        ("FREQ=DAILY;COUNT=5", 0, 1, 1),
        ("FREQ=DAILY;UNTIL=20260103", 0, 0, 0),
        ("FREQ=DAILY;UNTIL=20260103", 4, 1, 5),
        ("FREQ=MONTHLY;BYMONTHDAY=1,2,3;UNTIL=20260102", 0, 3, 3),
        ("FREQ=MONTHLY;BYMONTHDAY=1,2,3;UNTIL=20260102", 1, 0, 3),
        ("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30;UNTIL=20260103", 2, 0, 0),
    ],
)
def test_correct_nominal_rank_does_not_allow_false_count_or_date_until_exhaustion(
    raw, index, offset, count
):
    value = pattern(raw)
    rule = replace(values()[0], pattern=value)
    cursor = FixedCursor(cursor_binding(value, rule.policy), index, offset, count, True)
    assert not FixedProgress(
        rule.schedule_id, rule.household_id, 1, cursor, range_complete=True
    ).matches_schedule(rule)
