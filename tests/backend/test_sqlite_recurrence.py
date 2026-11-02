"""Owned SQLite schedule records share the real task/receipt transaction boundary."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import date

import pytest
from test_task_commands import fixture, resource

from domus.application.task_commands import CreateTask
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot, cursor_binding
from domus.domain.recurrence_records import (
    FixedProgress,
    FixedSchedule,
    ScheduledSlot,
    ScheduleState,
)
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import TimePolicy
from domus.domain.storage import AuditEntry, JsonDocument, OutboxEvent, Receipt
from domus.domain.task_values import TaskContent
from domus.infrastructure.recurrence_time import TIMEZONE_DATA_IDENTITY
from domus.infrastructure.sqlite import SQLiteDatabase


def prepared(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    receipt = commands.create("manual", CreateTask(TaskContent("Water plants")))
    definition_id, occurrence_id = resource(receipt)
    rule = FixedSchedule(
        "rule",
        "home",
        definition_id,
        parse_fixed_pattern("FREQ=DAILY", NominalDate(date(2026, 1, 1))),
        TimePolicy("UTC", TIMEZONE_DATA_IDENTITY),
        100,
    )
    progress = FixedProgress(
        "rule", "home", 1, FixedCursor(cursor_binding(rule.pattern, rule.policy))
    )
    with store.write() as unit:
        unit.recurrence.save_schedule(rule, 0)
        unit.recurrence.save_progress(progress, 0)
    return store, rule, progress, occurrence_id


def slot(store, rule, occurrence_id):
    return ScheduledSlot(
        store.installation, rule, PlannedFixedSlot(rule.pattern.start, None), occurrence_id, 100
    )


def save_slot(unit, value):
    """Repository fixture records full synthetic technical evidence, not human authorization."""
    unit.recurrence.add_slot(value)
    command = value.command
    result = JsonDocument.from_value({"slot_key": value.key, "occurrence_id": value.occurrence_id})
    unit.receipts.add(
        Receipt(command, JsonDocument.from_value({}).fingerprint, "slot-operation", result, 100)
    )
    unit.audit.append(AuditEntry("slot-operation", command, JsonDocument.from_value({}), 100))
    unit.outbox.append(OutboxEvent("slot-operation", "home", command.action, result, 100))


def test_schedule_progress_and_slot_survive_an_independent_database_reopen(tmp_path):
    store, rule, progress, work = prepared(tmp_path)
    original = slot(store, rule, work)
    with store.write() as unit:
        save_slot(unit, original)
    reopened = SQLiteDatabase(store.path, store.installation)
    with reopened.read() as unit:
        assert unit.recurrence.installation == store.installation
        assert unit.recurrence.schedule("home", "rule") == rule
        assert unit.recurrence.progress("home", "rule") == progress
        assert unit.recurrence.slot("home", original.key) == original
        assert unit.recurrence.schedules("home") == (rule,)
        assert unit.recurrence.slots("home", "rule") == (original,)
        assert unit.receipts.get(original.command).result.decode()["occurrence_id"] == work
        assert unit.recurrence.schedule("other", "rule") is None
        assert unit.recurrence.progress("other", "rule") is None
        assert unit.recurrence.slot("other", original.key) is None


def test_rule_progress_slot_and_task_work_roll_back_as_one_transaction(tmp_path):
    store, rule, progress, work = prepared(tmp_path)
    original = replace(slot(store, rule, "generated-work"), created_at=110)
    with pytest.raises(RuntimeError, match="injected"):
        with store.write() as unit:
            generated = replace(
                unit.tasks.occurrence("home", work), occurrence_id="generated-work", created_at=110
            )
            unit.tasks.save_occurrence(generated, 0)
            unit.recurrence.save_schedule(replace(rule, state=ScheduleState.PAUSED, revision=2), 1)
            unit.recurrence.save_progress(replace(progress, revision=2, last_run_at=110), 1)
            save_slot(unit, original)
            raise RuntimeError("injected")
    with store.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == rule
        assert unit.recurrence.progress("home", "rule") == progress
        assert unit.recurrence.slot("home", original.key) is None
        assert unit.receipts.get(original.command) is None
        assert unit.tasks.occurrence("home", "generated-work") is None
        assert unit.tasks.occurrence("home", work) is not None


def test_rule_and_progress_compare_and_swap_preserve_immutable_scope_and_creation(tmp_path):
    store, rule, progress, _ = prepared(tmp_path)
    with store.write() as unit:
        changed = replace(rule, state=ScheduleState.PAUSED, revision=2)
        unit.recurrence.save_schedule(changed, 1)
        unit.recurrence.save_progress(replace(progress, revision=2, last_run_at=110), 1)
        for value, expected in [
            (rule, 0),
            (changed, 1),
            (replace(changed, created_at=101, revision=3), 2),
            (replace(changed, pattern_revision=2, revision=3), 2),
        ]:
            with pytest.raises(Conflict):
                unit.recurrence.save_schedule(value, expected)
        with pytest.raises(Conflict):
            unit.recurrence.save_progress(progress, 0)
        with pytest.raises(Conflict):
            unit.recurrence.save_progress(replace(progress, revision=4), 3)
        with pytest.raises(InvalidInput):
            unit.recurrence.save_schedule(changed, True)
        with pytest.raises(InvalidInput):
            unit.recurrence.save_progress(progress, -1)


def test_slot_identity_is_unique_and_requires_its_exact_task_and_receipt(tmp_path):
    store, rule, _, work = prepared(tmp_path)
    original = slot(store, rule, work)
    with pytest.raises(StorageFailure):
        with store.write() as unit:
            unit.recurrence.add_slot(original)
    with store.write() as unit:
        save_slot(unit, original)
    with pytest.raises(Conflict):
        with store.write() as unit:
            unit.recurrence.add_slot(original)
    with store.read() as unit:
        assert len(unit.recurrence.slots("home", "rule")) == 1


@pytest.mark.parametrize("kind", ["rule", "progress", "slot"])
def test_corrupt_or_future_stored_documents_never_gain_default_meanings(tmp_path, kind):
    store, rule, _, work = prepared(tmp_path)
    original = slot(store, rule, work)
    with store.write() as unit:
        save_slot(unit, original)
    table = {
        "rule": "recurrence_rules",
        "progress": "recurrence_progress",
        "slot": "recurrence_slots",
    }[kind]
    with store._connection() as connection:
        connection.execute(f"UPDATE {table} SET document='{{}}'")
    with store.read() as unit:
        query = {
            "rule": lambda: unit.recurrence.schedule("home", "rule"),
            "progress": lambda: unit.recurrence.progress("home", "rule"),
            "slot": lambda: unit.recurrence.slot("home", original.key),
        }[kind]
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            query()


def test_scoped_lists_are_exact_bounded_keysets_and_never_interpolate_caller_sql(tmp_path):
    store, rule, _, _ = prepared(tmp_path)
    with store.read() as unit:
        assert unit.recurrence.schedules("home", after="rule") == ()
        assert unit.recurrence.schedules("home", state=ScheduleState.ACTIVE) == (rule,)
        assert unit.recurrence.schedules("home", state=ScheduleState.PAUSED) == ()
        assert unit.recurrence.slots("other", "rule") == ()
        for bad in [0, 102, True, 1.5]:
            with pytest.raises(InvalidInput):
                unit.recurrence.schedules("home", limit=bad)
        with pytest.raises(InvalidInput):
            unit.recurrence.schedules("home", state="active")
        with pytest.raises(InvalidInput):
            unit.recurrence.schedules("home", after="x' OR 1=1")


def source7(tmp_path):
    from pathlib import Path

    from domus.domain.storage import Installation

    path = tmp_path / "schema7.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript((Path(__file__).parents[1] / "fixtures/sqlite/v7.sql").read_text())
        identity = connection.execute("SELECT instance_id,channel FROM installation").fetchone()
    return SQLiteDatabase(path, Installation(*identity))


def test_normal_transactions_refuse_schema7_until_explicit_atomic_upgrade(tmp_path):
    from domus.domain.errors import DatabaseRejected

    store = source7(tmp_path)
    before = store.path.read_bytes()
    for transaction in (store.read, store.write):
        with pytest.raises(DatabaseRejected, match="unsupported_schema"):
            with transaction():
                pytest.fail("Previous schema must not yield a current unit of work")
    assert store.path.read_bytes() == before
    with store._connection() as connection:
        original = tuple(connection.execute("SELECT * FROM receipts ORDER BY operation_id"))
    store.initialize(require_existing=True)
    with store.read() as unit:
        assert unit.recurrence.schedules("home") == ()
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert tuple(connection.execute("SELECT * FROM receipts ORDER BY operation_id")) == original
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("field", ["actor_id", "action", "key"])
def test_current_slot_requires_exact_original_evidence_namespace(tmp_path, field):
    store, rule, _, work = prepared(tmp_path)
    value = slot(store, rule, work)
    wrong = replace(value.command, **{field: "other"})
    result = JsonDocument.from_value({"slot_key": value.key, "occurrence_id": work})
    with pytest.raises(StorageFailure):
        with store.write() as unit:
            unit.recurrence.add_slot(value)
            unit.receipts.add(
                Receipt(wrong, JsonDocument.from_value({}).fingerprint, "wrong-proof", result, 100)
            )
            unit.audit.append(AuditEntry("wrong-proof", wrong, JsonDocument.from_value({}), 100))
            unit.outbox.append(OutboxEvent("wrong-proof", "home", wrong.action, result, 100))
    with store.read() as unit:
        assert unit.recurrence.slot("home", value.key) is None
        assert unit.receipts.get(wrong) is None
