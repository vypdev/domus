"""Verify exact drafts and replay through SQLite migration, activation and rollback."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_automation_drafts import DRAFTS, read, save
from test_automation_preview import USER
from test_household_commands import Actor
from test_sqlite_snapshots import Clock
from test_task_runtime import api as api

from domus.application.automation_drafts import SAVE_DRAFT, AutomationDrafts, SaveDraft
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.automation import AutomationRule, StockCondition
from domus.domain.errors import DatabaseRejected, Forbidden, InvalidInput, StorageFailure
from domus.domain.storage import CommandKey, Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database
from domus.infrastructure.task_cursor import TaskCursor


def service(store):
    actor, clock = Actor(), Clock()
    return AutomationDrafts(
        store,
        MaintenanceScope(store.installation, "home"),
        actor,
        actor.current,
        clock,
        SecureIdentifiers(),
        TaskCursor(clock, b"d" * 32),
    )


@pytest.mark.parametrize(
    ("version", "filename"),
    [
        (20, "v20-inventory-history-source.sql"),
        (31, "v31-automation-drafts-source.sql"),
    ],
)
def test_migration_restoration_and_rollback_keep_exact_drafts_and_receipts(
    tmp_path, monkeypatch, version, filename
):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite" / filename
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        identity = db.execute("SELECT instance_id,channel FROM installation").fetchone()
        installation = Installation(*identity)
        product = db.execute("SELECT product_id FROM inventory_products").fetchone()[0]
        tables = ("households", "members", "receipts", "inventory_materials", "task_occurrences")
        if version == 31:
            tables += ("shopping_sessions",)
        prior = {name: db.execute("SELECT * FROM " + name).fetchall() for name in tables}
    path.chmod(0o600)
    identity_at(root, installation)
    store = SQLiteDatabase(path, installation)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=True) == version
    original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "AUTOMATION_DRAFT_STATEMENT", "invalid SQL")
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == original
    store.initialize(require_existing=True)

    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (38,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {name: db.execute("SELECT * FROM " + name).fetchall() for name in tables} == prior
    rule = AutomationRule(1, "manual", StockCondition(product), TaskContent("Buy oil"))
    drafts = service(store)
    first = drafts.save("initial", SaveDraft(None, 0, rule))
    rule_id = first.result.decode()["rule_id"]
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    snapshotter = SQLiteSnapshots(store, archive, installation, Clock())
    checkpoint = snapshotter.create("first-draft")
    assert checkpoint.schema_version == 38 and snapshotter.inspect() == checkpoint
    edit = SaveDraft(rule_id, 1, replace(rule, task=TaskContent("Review the pantry")))
    second = drafts.save("edit", edit)
    restarted = service(SQLiteDatabase(path, installation))
    assert restarted.reopen(rule_id).rule == edit.rule
    assert restarted.original("initial") == first
    assert restarted.original("edit") == second

    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare(
        "restore-draft"
    )
    result = SQLiteActivation(root, installation, Clock(), target).activate()
    assert result.state == "active"
    selected = open_storage(root, "edge")
    try:
        restored = service(selected.database)
        draft = restored.reopen(rule_id)
        assert (draft.revision, draft.rule) == (1, rule)
        evidence = restored.original("initial")
        assert not evidence.historical and evidence.operation_id == first.operation_id
        historical = restored.save("edit", edit)
        assert historical == restored.original("edit")
        assert historical.historical and historical.operation_id == second.operation_id
        assert restored.reopen(rule_id) == draft
        with selected.database.read() as unit:
            assert unit.outbox.delivered(first.operation_id)
            assert all(event.event_id != second.operation_id for event in unit.outbox.pending())

        rollback_target = tmp_path / "rollback"
        SQLiteRestorations(
            selected.database,
            root / "activations/restore-draft/source-checkpoint",
            rollback_target,
            installation,
            Clock(),
            result.record.rollback_snapshot,
        ).prepare("rollback-draft")
    finally:
        selected.close()
    rollback = SQLiteActivation(root, installation, Clock(), rollback_target).activate()
    assert rollback.state == "active"
    reopened = open_storage(root, "edge")
    try:
        restored = service(reopened.database)
        draft = restored.reopen(rule_id)
        assert (draft.revision, draft.rule) == (2, edit.rule)
        restored_second = restored.original("edit")
        assert not restored_second.historical
        assert restored_second.operation_id == second.operation_id
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "corruption",
    ["revision=3", "definition='{}'", "definition=' ' || definition"],
)
def test_snapshot_rejects_invalid_draft_storage(api, corruption):
    api.user(USER, True)
    assert save(api, "single").status_code == 200
    with closing(sqlite3.connect(api.store.path, autocommit=True)) as connection:
        connection.execute(f"UPDATE automation_draft_revisions SET {corruption}")
        connection.row_factory = sqlite3.Row
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            _verify_database(connection, api.store, previous=False)


def test_authority_binds_the_original_to_the_current_member(api):
    api.user(USER, True)
    assert save(api, "single").status_code == 200
    drafts = service(api.store)
    with pytest.raises(InvalidInput, match="invalid_page_size"):
        drafts.list(limit=0, cursor=None)
    actor = Actor()
    with api.store.read() as unit, pytest.raises(Forbidden, match="permission_denied"):
        authority = drafts._authority(actor.current(), "single")
        authority.require(CommandKey("home", actor.human.ha_user_id, SAVE_DRAFT, "other"), unit)
    with closing(sqlite3.connect(api.store.path, autocommit=True)) as connection:
        connection.execute(
            "UPDATE receipts SET result=json_set(result,'$.member_id','previous-member') "
            "WHERE action=?",
            (SAVE_DRAFT,),
        )
    response = read(api, f"{DRAFTS}/requests/single")
    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
