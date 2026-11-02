"""Relative repository fixtures use explicit synthetic proof, never claim consumer delivery."""

from dataclasses import replace
from datetime import date

import pytest
from test_task_commands import fixture, resource

from domus.application.task_requests import CreateTask
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.recurrence_planning import PlannedSlot
from domus.domain.recurrence_records import ScheduleState
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import RelativeInterval, TimePolicy
from domus.domain.relative_recurrence import (
    RelativeOperation,
    RelativeProgress,
    RelativeSchedule,
    RelativeSlot,
)
from domus.domain.storage import AuditEntry, JsonDocument, OutboxEvent, Receipt
from domus.domain.task_values import TaskContent
from domus.infrastructure.recurrence_time import TIMEZONE_DATA_IDENTITY
from domus.infrastructure.sqlite import SQLiteDatabase


def prepared(tmp_path):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, occurrence_id = resource(
        commands.create("base", CreateTask(TaskContent("Relative base")))
    )
    rule = RelativeSchedule(
        "relative",
        "home",
        definition_id,
        PlannedSlot(NominalDate(date(1970, 1, 1)), None),
        RelativeInterval(30),
        TimePolicy("UTC", TIMEZONE_DATA_IDENTITY),
        100,
    )
    progress = RelativeProgress(rule.schedule_id, rule.household_id, 1, rule.binding)
    with store.write() as unit:
        unit.recurrence.save_relative_schedule(rule, 0)
        unit.recurrence.save_relative_progress(progress, 0)
    return store, rule, progress, occurrence_id


def proof(unit, slot, progress, operation_id="relative-operation"):
    advanced = replace(
        progress,
        current_occurrence_id=slot.occurrence_id,
        current_slot_key=slot.key,
        revision=progress.revision + 1,
        last_run_at=slot.created_at,
        evidence=RelativeOperation(slot.command, operation_id),
    )
    result = JsonDocument.from_value(
        {
            "slot_key": slot.key,
            "occurrence_id": slot.occurrence_id,
            "schedule_id": slot.schedule.schedule_id,
            "definition_id": slot.schedule.definition_id,
            "relative_slot_fingerprint": slot.evidence_fingerprint,
            "relative_progress": advanced.state_document().decode(),
        }
    )
    receipt = Receipt(
        slot.command, JsonDocument.from_value({}).fingerprint, operation_id, result, slot.created_at
    )
    unit.receipts.add(receipt)
    unit.audit.append(
        AuditEntry(operation_id, slot.command, JsonDocument.from_value({}), slot.created_at)
    )
    unit.outbox.append(
        OutboxEvent(operation_id, "home", slot.command.action, result, slot.created_at)
    )
    return advanced, receipt


def test_relative_rule_and_unconsumed_progress_survive_an_independent_reopen(tmp_path):
    store, rule, progress, _ = prepared(tmp_path)
    reopened = SQLiteDatabase(store.path, store.installation)
    with reopened.read() as unit:
        assert unit.recurrence.relative_schedule("home", rule.schedule_id) == rule
        assert unit.recurrence.relative_progress("home", rule.schedule_id) == progress
        assert unit.recurrence.relative_schedules("home") == (rule,)
        assert unit.recurrence.relative_slots("home", rule.schedule_id) == ()
        assert unit.recurrence.schedule("home", rule.schedule_id) is None
        assert unit.recurrence.schedules("home") == ()


def test_initial_slot_progress_and_original_receipt_commit_and_read_together(tmp_path):
    store, rule, progress, work_id = prepared(tmp_path)
    slot = RelativeSlot(store.installation, rule, rule.initial, work_id, 100)
    with store.write() as unit:
        unit.recurrence.add_relative_slot(slot)
        advanced, receipt = proof(unit, slot, progress)
        unit.recurrence.save_relative_progress(advanced, 1)
    with store.read() as unit:
        assert unit.recurrence.relative_slot("home", slot.key) == slot
        assert unit.recurrence.relative_progress("home", rule.schedule_id) == advanced
        assert unit.receipts.get(slot.command) == receipt


def test_relative_progress_cannot_claim_a_run_or_skip_source_positions_without_original_proof(
    tmp_path,
):
    store, _, progress, _ = prepared(tmp_path)
    with pytest.raises(Conflict):
        with store.write() as unit:
            unit.recurrence.save_relative_progress(
                replace(progress, revision=2, source_after=100), 1
            )
    with store.read() as unit:
        assert unit.recurrence.relative_progress("home", progress.schedule_id) == progress


def test_genuine_prior_schema8_layout_is_refused_unchanged_before_relative_use(tmp_path):
    import hashlib
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    from domus.domain.storage import Installation

    fixture = Path("tests/fixtures/sqlite/unreleased-06b3b9f-schema8.sql")
    assert (
        hashlib.sha256(fixture.read_bytes()).hexdigest()
        == "aed613d7a6c2718827c05d44cd3fbbdb9d996fce44097f893b5c9bfd4dc28565"
    )
    path = tmp_path / "prior.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
        identity = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert (
            connection.execute("SELECT count(*) FROM recurrence_progress_evidence").fetchone()[0]
            == 1
        )
    store = SQLiteDatabase(path, identity)
    original = path.read_bytes()
    for operation in (store.read, store.write):
        with pytest.raises(DatabaseRejected):
            with operation():
                pytest.fail("Unknown development layout admitted")
        assert path.read_bytes() == original
    with pytest.raises(DatabaseRejected):
        store.initialize(require_existing=True)
    assert path.read_bytes() == original


def test_relative_cas_scope_kind_and_immutable_generation_are_independent(tmp_path):
    from test_recurrence_records import values

    from domus.domain.recurrence_planning import FixedCursor, cursor_binding
    from domus.domain.recurrence_records import FixedProgress

    store, rule, progress, _ = prepared(tmp_path)
    with store.write() as unit:
        for value, expected in [
            (replace(rule, revision=3), 1),
            (replace(rule, revision=2, created_at=101), 1),
            (replace(rule, revision=2, definition_id="other"), 1),
            (replace(rule, revision=2, pattern_revision=2), 1),
            (rule, 0),
        ]:
            with pytest.raises(Conflict):
                unit.recurrence.save_relative_schedule(value, expected)
        for value, expected in [
            (replace(progress, revision=3), 1),
            (replace(progress, revision=2, binding="a" * 64), 1),
            (replace(progress, schedule_id="missing"), 0),
        ]:
            with pytest.raises(Conflict):
                unit.recurrence.save_relative_progress(value, expected)
        for action in [
            lambda: unit.recurrence.save_relative_schedule(rule, True),
            lambda: unit.recurrence.save_relative_progress(progress, -1),
        ]:
            with pytest.raises(InvalidInput):
                action()
        fixed = replace(
            values()[0], schedule_id=rule.schedule_id, definition_id=rule.definition_id, revision=2
        )
        with pytest.raises(Conflict):
            unit.recurrence.save_schedule(fixed, 1)
        assert unit.recurrence.relative_schedule("home", rule.schedule_id) == rule
        assert unit.recurrence.progress("home", rule.schedule_id) is None
        assert unit.recurrence.relative_progress("other", rule.schedule_id) is None
        assert unit.recurrence.relative_schedule("other", rule.schedule_id) is None
        # Retiring releases the one current timing owner while preserving its original row.
        unit.recurrence.save_relative_schedule(
            replace(rule, revision=2, state=ScheduleState.RETIRED), 1
        )
        fixed = replace(fixed, schedule_id="fixed", revision=1)
        unit.recurrence.save_schedule(fixed, 0)
        unit.recurrence.save_progress(
            FixedProgress(
                "fixed", "home", 1, FixedCursor(cursor_binding(fixed.pattern, fixed.policy))
            ),
            0,
        )
        with pytest.raises(Conflict):
            unit.recurrence.save_relative_schedule(replace(rule, revision=3), 2)
        with pytest.raises(Conflict):
            unit.recurrence.save_relative_schedule(
                replace(rule, schedule_id="fixed", revision=2), 1
            )
        assert unit.recurrence.relative_schedule("home", "fixed") is None


def test_rule_and_progress_generation_must_change_together_and_fail_atomically(tmp_path):
    store, rule, progress, _ = prepared(tmp_path)
    with pytest.raises(StorageFailure):
        with store.write() as unit:
            unit.recurrence.save_relative_schedule(
                replace(rule, revision=2, pattern_revision=2, interval=RelativeInterval(31)), 1
            )
    with store.read() as unit:
        assert unit.recurrence.relative_schedule("home", rule.schedule_id) == rule
    changed = replace(rule, revision=2, pattern_revision=2, interval=RelativeInterval(31))
    with store.write() as unit:
        unit.recurrence.save_relative_schedule(changed, 1)
        unit.recurrence.save_relative_progress(
            replace(progress, revision=2, pattern_revision=2, binding=changed.binding), 1
        )
    with store.read() as unit:
        assert unit.recurrence.relative_schedule("home", rule.schedule_id) == changed


@pytest.mark.parametrize(
    "change",
    ["installation", "channel", "missing-rule", "generation", "missing-work", "wrong-creation"],
)
def test_relative_slot_write_requires_current_scope_generation_and_real_work(tmp_path, change):
    store, rule, _, work = prepared(tmp_path)
    value = RelativeSlot(store.installation, rule, rule.initial, work, 100)
    if change in ("installation", "channel"):
        installation = replace(
            store.installation,
            **(
                {"channel": "stable"}
                if change == "channel"
                else {"instance_id": "00000000-0000-0000-0000-000000000001"}
            ),
        )
        value = replace(value, installation=installation)
    elif change == "missing-rule":
        value = replace(value, schedule=replace(rule, schedule_id="missing"))
    elif change == "generation":
        value = replace(value, schedule=replace(rule, revision=2, pattern_revision=2))
    elif change == "missing-work":
        value = replace(value, occurrence_id="missing")
    else:
        value = replace(value, created_at=101)
    with pytest.raises(Conflict):
        with store.write() as unit:
            unit.recurrence.add_relative_slot(value)
    with store.read() as unit:
        assert unit.recurrence.relative_slots("home", rule.schedule_id) == ()


def test_scoped_relative_pages_and_duplicate_slot_originals_are_bounded(tmp_path):
    from test_sqlite_relative_integrity import committed

    store, rule, progress, slot, _ = committed(tmp_path)
    with pytest.raises(Conflict):
        with store.write() as unit:
            unit.recurrence.add_relative_slot(slot)
    with store.read() as unit:
        assert unit.recurrence.relative_schedules("home", state=ScheduleState.ACTIVE) == (rule,)
        assert unit.recurrence.relative_schedules("home", state=ScheduleState.PAUSED) == ()
        assert unit.recurrence.relative_schedules("home", after=rule.schedule_id) == ()
        assert unit.recurrence.relative_slots("home", rule.schedule_id, after=slot.key) == ()
        assert unit.recurrence.relative_slot("other", slot.key) is None
        assert unit.recurrence.relative_slots("other", rule.schedule_id) == ()
        for call in [
            lambda: unit.recurrence.relative_schedules("home", state="active"),
            lambda: unit.recurrence.relative_slots("home", rule.schedule_id, limit=True),
            lambda: unit.recurrence.relative_schedules("home", after="';DROP"),
        ]:
            with pytest.raises(InvalidInput):
                call()
        assert unit.recurrence.relative_progress("home", rule.schedule_id) == progress


def test_missing_exact_slot_receipt_and_late_failure_leave_no_partial_relative_records(tmp_path):
    store, rule, progress, work = prepared(tmp_path)
    slot = RelativeSlot(store.installation, rule, rule.initial, work, 100)
    with pytest.raises(StorageFailure):
        with store.write() as unit:
            unit.recurrence.add_relative_slot(slot)
    with pytest.raises(RuntimeError, match="injected"):
        with store.write() as unit:
            unit.recurrence.add_relative_slot(slot)
            advanced, receipt = proof(unit, slot, progress)
            unit.recurrence.save_relative_progress(advanced, 1)
            raise RuntimeError("injected")
    with store.read() as unit:
        assert unit.recurrence.relative_slot("home", slot.key) is None
        assert unit.recurrence.relative_progress("home", rule.schedule_id) == progress
        assert unit.receipts.get(slot.command) is None


@pytest.mark.parametrize("operation", ["rule", "slot"])
def test_independent_relative_writers_have_one_complete_winner(tmp_path, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from domus.domain.errors import StorageBusy

    store, rule, progress, work = prepared(tmp_path)
    slot = RelativeSlot(store.installation, rule, rule.initial, work, 100)
    gate = Barrier(2)

    def write(_):
        independent = SQLiteDatabase(store.path, store.installation, busy_timeout=5)
        with independent.read() as unit:
            seen = unit.recurrence.relative_schedule("home", rule.schedule_id)
        gate.wait(timeout=5)
        try:
            with independent.write() as unit:
                if operation == "rule":
                    unit.recurrence.save_relative_schedule(replace(seen, revision=2), 1)
                else:
                    unit.recurrence.add_relative_slot(slot)
                    advanced, _ = proof(unit, slot, progress)
                    unit.recurrence.save_relative_progress(advanced, 1)
            return "committed"
        except Conflict:
            return "conflict"
        except StorageBusy:
            return "busy"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, range(2)))
    assert outcomes.count("committed") == 1 and len(set(outcomes) & {"conflict", "busy"}) == 1
    with store.read() as unit:
        if operation == "rule":
            assert unit.recurrence.relative_schedule("home", rule.schedule_id).revision == 2
        else:
            assert unit.recurrence.relative_slots("home", rule.schedule_id) == (slot,)
            assert unit.recurrence.relative_progress("home", rule.schedule_id).revision == 2
            assert (
                len([x for x in unit.outbox.pending() if x.event_type == slot.command.action]) == 1
            )
