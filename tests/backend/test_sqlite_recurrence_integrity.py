"""Real corrupted owned records must fail repository and checkpoint verification safely."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from threading import Barrier

import pytest
from test_sqlite_recurrence import prepared, save_slot, slot, source7
from test_sqlite_snapshots import Clock

from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.recurrence_planning import FixedCursor, PlannedFixedSlot, cursor_binding
from domus.domain.recurrence_rules import NominalDate
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_recurrence_integrity import verify_recurrence_records
from domus.infrastructure.sqlite_recurrence_records import (
    progress_document,
    schedule_document,
    slot_document,
)
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def committed(tmp_path):
    store, rule, progress, work = prepared(tmp_path)
    value = slot(store, rule, work)
    with store.write() as unit:
        save_slot(unit, value)
    return store, rule, progress, value


def test_checkpoint_verifies_and_reopens_real_rule_progress_slot_and_original_receipt(tmp_path):
    store, rule, progress, value = committed(tmp_path)
    snapshots = SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock())
    before = store.path.read_bytes()
    checkpoint = snapshots.create("recurrence")
    assert checkpoint.schema_version == 8 and snapshots.inspect() == checkpoint
    assert store.path.read_bytes() == before
    reopened = SQLiteDatabase(tmp_path / "snapshot/domus.sqlite3", store.installation)
    with reopened.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == rule
        assert unit.recurrence.progress("home", "rule") == progress
        assert unit.recurrence.slot("home", value.key) == value
        assert unit.receipts.get(value.command).result.decode()["slot_key"] == value.key


def test_self_consistent_slot_headers_and_exact_receipt_cannot_bypass_nominal_count(tmp_path):
    store, rule, progress, value = committed(tmp_path)
    # Construct a legitimate second daily nominal under the original unlimited rule, then corrupt
    # both stored source snapshots to COUNT1. All keys, headers and evidence still agree.
    later = replace(value, planned=PlannedFixedSlot(NominalDate(date(2026, 1, 2)), None))
    bounded = replace(rule, pattern=replace(rule.pattern, count=1))
    document = slot_document(later).decode()
    document["schedule"]["pattern"]["count"] = 1
    result = json.dumps({"slot_key": later.key, "occurrence_id": later.occurrence_id})
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_rules SET document=?", (schedule_document(bounded).encoded,)
        )
        connection.execute(
            "UPDATE recurrence_progress SET document=?",
            (
                progress_document(
                    replace(
                        progress,
                        cursor=FixedCursor(cursor_binding(bounded.pattern, bounded.policy)),
                    )
                ).encoded,
            ),
        )
        connection.execute(
            "UPDATE recurrence_slots SET slot_key=?,nominal_value=?,document=?",
            (later.key, "2026-01-02", json.dumps(document)),
        )
        connection.execute(
            "UPDATE receipts SET command_key=?,result=? WHERE command_key=?",
            (later.key, result, value.key),
        )
        connection.execute(
            "UPDATE audit SET command_key=? WHERE command_key=?", (later.key, value.key)
        )
        connection.execute(
            "UPDATE outbox SET payload=? WHERE event_type='recurrence.materialize'", (result,)
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = store.path.read_bytes()
    with store.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == bounded
        assert unit.receipts.get(later.command).result.decode()["slot_key"] == later.key
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.slot("home", later.key)
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "bad-count", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "table,column,value,kind",
    [
        ("recurrence_rules", "state", "paused", "rule"),
        ("recurrence_progress", "revision", 2, "progress"),
        ("recurrence_slots", "nominal_value", "2026-01-02", "slot"),
    ],
)
def test_header_body_mismatch_is_rejected_by_independent_repository_and_checkpoint(
    tmp_path, table, column, value, kind
):
    store, _, _, original = committed(tmp_path)
    with store._connection() as connection:
        connection.execute(f"UPDATE {table} SET {column}=?", (value,))
    with store.read() as unit:
        query = {
            "rule": lambda: unit.recurrence.schedule("home", "rule"),
            "progress": lambda: unit.recurrence.progress("home", "rule"),
            "slot": lambda: unit.recurrence.slot("home", original.key),
        }[kind]
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            query()
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create("bad")


def test_record_with_self_consistent_foreign_installation_cannot_be_read_as_local(tmp_path):
    store, _, _, original = committed(tmp_path)
    foreign = replace(original, installation=replace(original.installation, channel="stable"))
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_slots SET slot_key=?,document=?",
            (foreign.key, slot_document(foreign).encoded),
        )
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.slot("home", foreign.key)


@pytest.mark.parametrize(
    "change",
    [
        "missing-progress",
        "pattern-revision",
        "binding",
        "missing-receipt",
        "wrong-slot",
        "wrong-occurrence",
    ],
)
def test_semantic_probe_rejects_missing_source_binding_or_original_effect(tmp_path, change):
    store, _, progress, value = committed(tmp_path)
    with store._connection() as connection:
        if change == "missing-progress":
            connection.execute("DELETE FROM recurrence_progress")
        elif change == "pattern-revision":
            changed = replace(progress, pattern_revision=2)
            connection.execute(
                "UPDATE recurrence_progress SET pattern_revision=2,document=?",
                (progress_document(changed).encoded,),
            )
        elif change == "binding":
            changed = replace(progress, cursor=replace(progress.cursor, binding="b" * 64))
            connection.execute(
                "UPDATE recurrence_progress SET document=?", (progress_document(changed).encoded,)
            )
        elif change == "missing-receipt":
            connection.execute("DELETE FROM receipts WHERE command_key=?", (value.key,))
        else:
            result = {"slot_key": value.key, "occurrence_id": value.occurrence_id}
            result["slot_key" if change == "wrong-slot" else "occurrence_id"] = "other"
            connection.execute(
                "UPDATE receipts SET result=? WHERE command_key=?", (json.dumps(result), value.key)
            )
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            verify_recurrence_records(connection, store.installation)


def test_stale_or_foreign_plans_cannot_write_slots_or_progress(tmp_path):
    store, rule, progress, work = prepared(tmp_path)
    original = slot(store, rule, work)
    invalid = [
        replace(original, installation=replace(store.installation, channel="stable")),
        replace(original, schedule=replace(rule, schedule_id="missing")),
        replace(original, schedule=replace(rule, definition_id="other")),
    ]
    with store.write() as unit:
        for value in invalid:
            with pytest.raises(Conflict):
                unit.recurrence.add_slot(value)
        for value, expected in [
            (replace(progress, revision=3), 1),
            (replace(progress, schedule_id="missing"), 0),
            (replace(progress, pattern_revision=2, revision=2), 1),
            (replace(progress, cursor=replace(progress.cursor, binding="b" * 64)), 0),
        ]:
            with pytest.raises(Conflict):
                unit.recurrence.save_progress(value, expected)
        with pytest.raises(Conflict):
            unit.recurrence.save_schedule(replace(rule, revision=3), 1)
        with pytest.raises(Conflict):
            unit.recurrence.save_schedule(replace(rule, definition_id="other", revision=2), 1)
        assert unit.recurrence.slots("home", "rule", after=original.key) == ()


@pytest.mark.parametrize("failure_at", [0, -1])
def test_schema7_ddl_failure_rolls_back_tables_version_and_original_business_records(
    tmp_path, monkeypatch, failure_at
):
    import domus.infrastructure.sqlite as implementation

    store = source7(tmp_path)
    with store._connection() as connection:
        original = tuple(
            tuple(row) for row in connection.execute("SELECT * FROM receipts ORDER BY operation_id")
        )
    statements = list(implementation.RECURRENCE_STATEMENTS)
    statements.insert(failure_at, "INVALID RECURRENCE DDL")
    monkeypatch.setattr(implementation, "RECURRENCE_STATEMENTS", tuple(statements))
    with pytest.raises(StorageFailure):
        store.initialize(require_existing=True)
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert (
            tuple(
                tuple(row)
                for row in connection.execute("SELECT * FROM receipts ORDER BY operation_id")
            )
            == original
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'recurrence_%'"
            ).fetchall()
            == []
        )


def test_pattern_edit_requires_matching_progress_and_preserves_existing_slot_snapshot(tmp_path):
    store, rule, progress, value = committed(tmp_path)
    changed = replace(
        rule, revision=2, pattern_revision=2, pattern=replace(rule.pattern, interval=2)
    )
    with pytest.raises(StorageFailure):
        with store.write() as unit:
            unit.recurrence.save_schedule(changed, 1)
    with store.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == rule
        assert unit.recurrence.progress("home", "rule") == progress
    next_progress = replace(
        progress,
        revision=2,
        pattern_revision=2,
        cursor=FixedCursor(cursor_binding(changed.pattern, changed.policy)),
    )
    with store.write() as unit:
        unit.recurrence.save_schedule(changed, 1)
        unit.recurrence.save_progress(next_progress, 1)
    with store.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == changed
        assert unit.recurrence.progress("home", "rule") == next_progress
        assert unit.recurrence.slot("home", value.key) == value
        assert unit.recurrence.slots("home", "rule", after=value.key) == ()
    assert (
        SQLiteSnapshots(store, tmp_path / "edited", store.installation, Clock())
        .create("edited")
        .schema_version
        == 8
    )


def test_rule_list_limit_and_keyset_return_only_the_requested_owned_rows(tmp_path):
    store, rule, progress, _ = prepared(tmp_path)
    with store.write() as unit:
        for key in ["a", "z"]:
            unit.recurrence.save_schedule(replace(rule, schedule_id=key), 0)
            unit.recurrence.save_progress(replace(progress, schedule_id=key), 0)
    with store.read() as unit:
        first = unit.recurrence.schedules("home", limit=1)
        assert [value.schedule_id for value in first] == ["a"]
        assert [
            value.schedule_id for value in unit.recurrence.schedules("home", after="a", limit=1)
        ] == ["rule"]
        assert [
            value.schedule_id
            for value in unit.recurrence.schedules("home", after="rule", limit=101)
        ] == ["z"]
        assert unit.recurrence.schedules("other", limit=101) == ()


@pytest.mark.parametrize("operation", ["rule", "slot"])
def test_independent_concurrent_writers_commit_one_revision_or_one_slot_with_its_proof(
    tmp_path, operation
):
    store, rule, _, work = prepared(tmp_path)
    original = slot(store, rule, work)
    barrier = Barrier(2, timeout=5)

    def write():
        independent = SQLiteDatabase(store.path, store.installation, busy_timeout=5)
        with independent.read() as unit:
            observed = unit.recurrence.schedule("home", "rule")
        barrier.wait()
        try:
            with independent.write() as unit:
                if operation == "rule":
                    unit.recurrence.save_schedule(replace(observed, revision=2), 1)
                else:
                    save_slot(unit, original)
            return "committed"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: write(), range(2))) == ["committed", "conflict"]
    with store.read() as unit:
        if operation == "rule":
            assert unit.recurrence.schedule("home", "rule").revision == 2
        else:
            assert unit.recurrence.slots("home", "rule") == (original,)
            assert unit.receipts.get(original.command).result.decode()["occurrence_id"] == work
            assert (
                len(
                    [
                        value
                        for value in unit.audit.entries("home")
                        if value.command == original.command
                    ]
                )
                == 1
            )
            assert (
                len(
                    [
                        value
                        for value in unit.outbox.pending()
                        if value.event_type == original.command.action
                    ]
                )
                == 1
            )


def test_bounded_count_refuses_impossible_progress_before_its_transaction_commits(tmp_path):
    store, rule, progress, _ = prepared(tmp_path)
    limited = replace(rule, revision=2, pattern_revision=2, pattern=replace(rule.pattern, count=1))
    invalid = replace(
        progress,
        revision=2,
        pattern_revision=2,
        cursor=replace(
            progress.cursor,
            binding=cursor_binding(limited.pattern, limited.policy),
            nominal_count=2,
        ),
    )
    with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
        with store.write() as unit:
            unit.recurrence.save_schedule(limited, 1)
            unit.recurrence.save_progress(invalid, 1)
    with store.read() as unit:
        assert unit.recurrence.schedule("home", "rule") == rule


@pytest.mark.parametrize("change", ["count", "future-slot", "different-pattern", "missing-rule"])
def test_impossible_source_relationships_cannot_pass_semantic_verification(tmp_path, change):
    store, rule, progress, value = committed(tmp_path)
    with store._connection() as connection:
        if change == "missing-rule":
            connection.execute("DELETE FROM recurrence_rules")
        elif change == "count":
            limited = replace(rule, pattern=replace(rule.pattern, count=1))
            invalid = replace(
                progress,
                cursor=replace(
                    progress.cursor,
                    binding=cursor_binding(limited.pattern, limited.policy),
                    nominal_count=2,
                ),
            )
            connection.execute(
                "UPDATE recurrence_rules SET document=?", (schedule_document(limited).encoded,)
            )
            connection.execute(
                "UPDATE recurrence_progress SET document=?", (progress_document(invalid).encoded,)
            )
            connection.execute(
                "UPDATE recurrence_slots SET document=?",
                (slot_document(replace(value, schedule=limited)).encoded,),
            )
        else:
            source = (
                replace(rule, revision=2, pattern_revision=2)
                if change == "future-slot"
                else replace(rule, pattern=replace(rule.pattern, interval=2))
            )
            changed = replace(value, schedule=source)
            result = json.dumps({"slot_key": changed.key, "occurrence_id": changed.occurrence_id})
            connection.execute(
                "UPDATE recurrence_slots SET slot_key=?,pattern_revision=?,document=?",
                (changed.key, source.pattern_revision, slot_document(changed).encoded),
            )
            connection.execute(
                "UPDATE receipts SET command_key=?,result=? WHERE command_key=?",
                (changed.key, result, value.key),
            )
            connection.execute(
                "UPDATE audit SET command_key=? WHERE command_key=?", (changed.key, value.key)
            )
            connection.execute(
                "UPDATE outbox SET payload=? WHERE event_type='recurrence.materialize'", (result,)
            )
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            verify_recurrence_records(connection, store.installation)
