"""Reopen and restore the exact automation control and original command result."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_automation_draft_storage import service as draft_service
from test_automation_execution import configure, initial_draft, result
from test_household_commands import Actor
from test_sqlite_snapshots import Clock
from test_task_runtime import api as api

from domus.application.automation_drafts import SaveDraft
from domus.application.automation_execution import (
    RUN_AUTOMATION,
    AutomationExecution,
    ConfigureAutomation,
    RunAutomation,
)
from domus.application.automation_run_history import AutomationRunHistory
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.task_commands import TaskCommands
from domus.domain.automation import AutomationControl, AutomationRule
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database
from domus.infrastructure.task_cursor import TaskCursor

FIXTURES = Path(__file__).parents[1] / "fixtures/sqlite"


def execution_service(store):
    actor, clock, identifiers = Actor(), Clock(), SecureIdentifiers()
    return AutomationExecution(
        store,
        MaintenanceScope(store.installation, "home"),
        actor,
        actor.current,
        clock,
        identifiers,
        TaskCommands(store, actor, clock, identifiers),
    )


@pytest.mark.parametrize(
    ("version", "filename"),
    [
        (20, "v20-inventory-history-source.sql"),
        (32, "v32-automation-execution-source.sql"),
    ],
)
def test_runtime_migration_restoration_and_rollback_preserve_exact_outcomes(
    tmp_path, monkeypatch, version, filename
):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript((FIXTURES / filename).read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        tables = ("households", "members", "receipts", "inventory_products", "task_occurrences")
        if version == 32:
            tables += ("automation_draft_revisions",)
        before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    path.chmod(0o600)
    identity_at(root, installation)
    store = SQLiteDatabase(path, installation)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=True) == version
    original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "AUTOMATION_CONTROL_STATEMENT", "invalid SQL")
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == original
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (33,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {
            table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables
        } == before

    drafts = draft_service(store)
    execution = execution_service(store)
    if version == 32:
        first = drafts.original("pinned-edge37-draft")
        rule_id = first.result.decode()["rule_id"]
        with store.read() as unit:
            assert (
                unit.automation_drafts.revision("home", rule_id, 1).rule.task.title
                == "Check pantry oil"
            )
            assert (
                unit.automation_drafts.revision("home", rule_id, 2).rule.task.title
                == "Review pantry oil"
            )
        assert execution.state(rule_id).control is None
        assert drafts.original("pinned-edge37-update").result.decode()["revision"] == "2"

    rule = AutomationRule(1, "manual", None, TaskContent("Inspect pantry"))
    draft = drafts.save("execution-draft", SaveDraft(None, 0, rule))
    rule_id = draft.result.decode()["rule_id"]
    execution.configure("execution-enable", ConfigureAutomation(rule_id, 1, 0, True))
    request = RunAutomation(rule_id, 1, 1)
    current_run = execution.run("before-restore", request)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    snapshotter = SQLiteSnapshots(store, archive, installation, Clock())
    checkpoint = snapshotter.create("before-run")
    assert checkpoint.schema_version == 33 and snapshotter.inspect() == checkpoint
    complete = execution.run("record-run", request)
    occurrence_id = complete.result.decode()["task_occurrence_id"]
    restarted = execution_service(SQLiteDatabase(path, installation))
    assert restarted.state(rule_id).control.enabled
    assert restarted.original(RUN_AUTOMATION, "record-run") == complete
    assert restarted.run("record-run", request) == complete
    history = AutomationRunHistory(
        restarted.transactions,
        restarted.scope,
        restarted.read_actor,
        TaskCursor(Clock(), b"s" * 32),
    )
    live = history.page(rule_id, limit=25, cursor=None)
    assert [run.operation_id for run in live.items] == [
        complete.operation_id,
        current_run.operation_id,
    ]
    assert live.items[0].task_occurrence_id == occurrence_id

    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare(
        "restore-execution"
    )
    activated = SQLiteActivation(root, installation, Clock(), target).activate()
    assert activated.state == "active"
    selected = open_storage(root, "edge")
    try:
        restored = execution_service(selected.database)
        assert restored.state(rule_id).control.enabled
        historical = restored.run("record-run", request)
        assert historical == restored.original(RUN_AUTOMATION, "record-run")
        assert historical.historical and historical.operation_id == complete.operation_id
        assert historical.result == complete.result
        history = AutomationRunHistory(
            selected.database, restored.scope, restored.read_actor, TaskCursor(Clock(), b"r" * 32)
        )
        selected_head = history.page(rule_id, limit=1, cursor=None)
        assert selected_head.items == (
            replace(live.items[0], historical=True, task_occurrence_id=None),
        )
        selected_tail = history.page(rule_id, limit=1, cursor=selected_head.next_cursor)
        assert selected_tail.items == (live.items[1],) and selected_tail.next_cursor is None
        with selected.database.read() as unit:
            assert unit.tasks.occurrence("home", occurrence_id) is None
            assert all(event.event_id != complete.operation_id for event in unit.outbox.pending())
        rollback_target = tmp_path / "rollback"
        SQLiteRestorations(
            selected.database,
            root / "activations/restore-execution/source-checkpoint",
            rollback_target,
            installation,
            Clock(),
            activated.record.rollback_snapshot,
        ).prepare("rollback-execution")
    finally:
        selected.close()
    assert (
        SQLiteActivation(root, installation, Clock(), rollback_target).activate().state == "active"
    )
    rolled_back = open_storage(root, "edge")
    try:
        service = execution_service(rolled_back.database)
        recovered = service.original(RUN_AUTOMATION, "record-run")
        assert not recovered.historical and recovered.operation_id == complete.operation_id
        with rolled_back.database.read() as unit:
            assert (
                unit.tasks.occurrence("home", occurrence_id).definition_snapshot.content.title
                == "Inspect pantry"
            )
    finally:
        rolled_back.close()


def test_control_compares_revision_for_insert_and_update(api):
    rule_id = initial_draft(api)
    control = AutomationControl(rule_id, 1, 1, True)
    with api.store.write() as unit:
        unit.automation_controls.save("home", control, 0)
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.automation_controls.save("home", control, 0)
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.automation_controls.save("home", AutomationControl(rule_id, 1, 3, False), 2)
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.automation_controls.save("home", control, 2)
        assert unit.automation_controls.get("home", rule_id) == control
        assert unit.automation_drafts.revision("home", rule_id, 2) is None


@pytest.mark.parametrize(
    ("column", "error"),
    [
        ("enabled=7", "invalid_snapshot_records"),
        ("rule_revision=99", "invalid_snapshot_database"),
    ],
)
def test_snapshot_rejects_corrupt_control(api, column, error):
    rule_id = initial_draft(api)
    result(configure(api, rule_id, "enable"))
    with closing(sqlite3.connect(api.store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE automation_rule_controls SET {column}")
        connection.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match=error):
            _verify_database(connection, api.store, previous=False)


def test_domain_control_rejects_coercions_and_unknown_receipt_actions(api):
    with pytest.raises(InvalidInput, match="invalid_automation_control"):
        AutomationControl("draft", 1, 1, 1)
    with pytest.raises(InvalidInput, match="invalid_automation_control"):
        ConfigureAutomation("draft", 1, True, False)
    with pytest.raises(InvalidInput, match="invalid_automation_action"):
        execution_service(api.store).original("task.create", "foreign-key")
