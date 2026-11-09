"""Recurrence observes bounded original live/historical facts without treating history as work."""

from dataclasses import replace

import pytest
from test_task_commands import counts
from test_task_events import prepared

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.task_commands import ReopenTask, VerifyTask
from domus.domain.errors import Forbidden, InvalidInput, StorageFailure
from domus.domain.task_events import TaskEventKind, TaskSourceRecord
from domus.domain.task_values import VerificationState
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def source(store):
    return RecurrenceSourceObservations(store, MaintenanceScope(store.installation, "home"))


def test_original_snapshots_are_bounded_ordered_and_independent_of_delivery(tmp_path):
    commands, store, actor, identifiers, oid, done = prepared(tmp_path, child=True)
    cid = done.result.decode()["cycle"]["cycle_id"]
    approved = commands.verify("approve", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    reopened = commands.reopen("reopen", ReopenTask(oid, 3, cid, "Perform again"))
    reader = source(store)
    before, allocated, actor_calls = counts(store), identifiers.count, actor.calls
    first = reader.read(limit=2)
    assert [v.event.event_id for v in first.items] == [done.operation_id, approved.operation_id]
    assert first.source_rows_examined == 2 and not first.complete
    second = reader.read(limit=2, after=first.after_position)
    assert [v.event.event_id for v in second.items] == [reopened.operation_id]
    assert second.complete and second.source_rows_examined == 1
    assert [v.event.kind for v in first.items + second.items] == list(TaskEventKind)
    assert [v.event.cycle.revision for v in first.items + second.items] == [1, 2, 3]
    assert all(v.original.current for v in first.items + second.items)
    assert len({v.event.cycle_key for v in first.items + second.items}) == 1
    assert counts(store) == before
    with store.write() as unit:
        unit.outbox.acknowledge(done.operation_id)
    after_delivery = counts(store)
    again = reader.read(limit=2)
    assert again.items[0].event == first.items[0].event
    assert again.items[0].original.evidence.delivered
    assert (
        counts(store) == after_delivery
        and identifiers.count == allocated
        and actor.calls == actor_calls
    )
    empty = reader.read(limit=2, after=second.after_position)
    assert empty.complete and empty.items == () and empty.after_position == second.after_position
    assert empty.source_rows_examined == 1


@pytest.mark.parametrize("layer", ["application", "repository"])
@pytest.mark.parametrize(
    "values",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"after": True},
        {"after": -1},
        {"after": 2**63},
    ],
)
def test_both_source_boundaries_reject_unbounded_or_noncanonical_requests(tmp_path, layer, values):
    _, store, _, _, _, _ = prepared(tmp_path)
    with pytest.raises(InvalidInput):
        if layer == "application":
            source(store).read(**values)
        else:
            with store.read() as unit:
                unit.tasks.lifecycle_sources("home", **values)


@pytest.mark.parametrize("change", ["installation", "channel", "household"])
def test_composition_scope_cannot_cross_installation_channel_or_household(tmp_path, change):
    _, store, _, _, _, _ = prepared(tmp_path)
    scope = source(store).scope
    if change == "household":
        scope = replace(scope, household_id="other")
    else:
        scope = replace(
            scope,
            installation=replace(
                scope.installation,
                **(
                    {"instance_id": "00000000-0000-0000-0000-000000000099"}
                    if change == "installation"
                    else {"channel": "stable"}
                ),
            ),
        )
    before = counts(store)
    with pytest.raises(Forbidden):
        RecurrenceSourceObservations(store, scope).read()
    assert counts(store) == before


def test_actual_restore_exposes_later_facts_without_rewriting_the_live_pending_cycle(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    commands, store, _, identifiers, oid, done = prepared(root, child=True)
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("pending")
    cid = done.result.decode()["cycle"]["cycle_id"]
    approved = commands.verify("approve", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    reopened = commands.reopen("reopen", ReopenTask(oid, 3, cid, "Perform again"))
    expected = source(store).read()
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-observations"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        before, allocated = counts(restored.database), identifiers.count
        rows = source(restored.database).read()
        assert [v.event for v in rows.items] == [v.event for v in expected.items]
        assert [v.original.current for v in rows.items] == [True, False, False]
        assert [v.event.event_id for v in rows.items] == [
            done.operation_id,
            approved.operation_id,
            reopened.operation_id,
        ]
        with restored.database.read() as unit:
            cycle = unit.tasks.cycle("home", cid)
            assert cycle.revision == 1 and cycle.verification is VerificationState.PENDING
            assert unit.tasks.occurrence("home", oid).current_cycle_id == cid
        assert counts(restored.database) == before and identifiers.count == allocated
    finally:
        restored.close()


@pytest.mark.parametrize("change", ["list", "extra", "order", "repeat", "foreign", "untyped"])
def test_invalid_semantic_port_pages_fail_closed_without_effects(tmp_path, monkeypatch, change):
    commands, store, _, _, oid, done = prepared(tmp_path)
    commands.reopen(
        "reopen", ReopenTask(oid, 2, done.result.decode()["cycle"]["cycle_id"], "Repeat")
    )
    with store.read() as unit:
        rows = unit.tasks.lifecycle_sources("home")
    if change == "list":
        bad = list(rows)
    elif change == "extra":
        bad = rows
    elif change == "order":
        bad = tuple(reversed(rows))
    elif change == "repeat":
        bad = (rows[0], rows[0])
    elif change == "foreign":
        bad = (replace(rows[0], cycle=replace(rows[0].cycle, household_id="other")),)
    else:
        bad = (None,)
    monkeypatch.setattr(SQLiteTasks, "lifecycle_sources", lambda *args, **kwargs: bad)
    before = counts(store)
    with pytest.raises(StorageFailure):
        source(store).read(limit=1 if change == "extra" else 2)
    assert counts(store) == before


@pytest.mark.parametrize("values", [(None, None), (None, "cycle")])
def test_source_records_require_typed_original_evidence_and_cycles(values):
    with pytest.raises(InvalidInput):
        TaskSourceRecord(*values)


def test_restored_away_completion_is_observed_without_inventing_a_live_cycle(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock
    from test_task_commands import fixture, resource

    from domus.application.task_commands import CompleteTask, CreateTask
    from domus.domain.task_values import TaskContent
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    commands, store, _, identifiers = fixture(root)
    oid = resource(commands.create("create", CreateTask(TaskContent("Restored work"))))[1]
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-work")
    done = commands.complete("complete", CompleteTask(oid, 1, ("child",), 90))
    expected = source(store).read().items[0].event
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore-source"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        before, allocated = counts(restored.database), identifiers.count
        rows = source(restored.database).read()
        assert len(rows.items) == 1 and rows.items[0].event == expected
        assert not rows.items[0].original.current
        assert rows.items[0].original.archived_by == "restore-source"
        with restored.database.read() as unit:
            assert unit.tasks.cycle("home", done.result.decode()["cycle"]["cycle_id"]) is None
            assert unit.tasks.occurrence("home", oid).current_cycle_id is None
        assert counts(restored.database) == before and identifiers.count == allocated
    finally:
        restored.close()


@pytest.mark.parametrize("damage", ["missing-audit", "missing-cycle", "invalid-cycle"])
def test_incomplete_original_source_fails_before_any_consumer_progress(tmp_path, damage):
    _, store, _, _, _, done = prepared(tmp_path)
    import json
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(store.path)) as connection, connection:
        if damage == "missing-audit":
            connection.execute("DELETE FROM audit WHERE operation_id=?", (done.operation_id,))
        else:
            result = done.result.decode()
            result["cycle"] = None if damage == "missing-cycle" else {"invalid": True}
            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?",
                (json.dumps(result), done.operation_id),
            )
    before = store.path.read_bytes()
    with pytest.raises(StorageFailure):
        source(store).read()
    assert store.path.read_bytes() == before
