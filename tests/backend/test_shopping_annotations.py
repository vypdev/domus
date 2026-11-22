"""Manual annotations survive exact replay, competing writers and real offline recovery."""

import json
import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_storage import setup
from test_rewards_storage import race
from test_shared_shopping import queries

from domus.application.inventory import CatalogAction, InventoryCommands
from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.shopping_annotations import (
    ShoppingAnnotation,
    ShoppingPriority,
    shopping_note,
    shopping_priority,
)
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_shopping import SQLiteShopping
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database

M = MaterialQuantity
FIXTURES = Path(__file__).parents[1] / "fixtures/sqlite"


@pytest.mark.parametrize(
    "note", ["", " \t\r\n ", "~\u00a0 text", "<script>alert(1)</script>", "😀" * 1000]
)
@pytest.mark.parametrize("priority", tuple(ShoppingPriority))
def test_literal_values_are_bounded_by_unicode_codepoints_and_immutable(note, priority):
    annotation = ShoppingAnnotation(shopping_note(note), shopping_priority(priority.value))
    assert annotation.note == note and annotation.priority is priority
    with pytest.raises(FrozenInstanceError):
        annotation.note = "changed"


@pytest.mark.parametrize(
    "note",
    [None, 1, True, "x" * 1001, "😀" * 1001, "\0", "\x1f", "\x7f", "\ud800"]
    + [chr(code) for code in range(0x80, 0xA0)],
)
def test_bad_notes_cannot_enter_an_annotation(note):
    with pytest.raises(InvalidInput, match="invalid_shopping_note"):
        ShoppingAnnotation(note)


@pytest.mark.parametrize("priority", [None, 1, True, "", "HIGH", "fast", [], {}])
def test_unknown_or_non_string_priority_is_rejected(priority):
    with pytest.raises(InvalidInput, match="invalid_shopping_priority"):
        shopping_priority(priority)
    with pytest.raises(InvalidInput, match="invalid_shopping_priority"):
        ShoppingAnnotation(priority=priority)


def facts(path):
    with closing(sqlite3.connect(path)) as db:
        return {
            name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall()
            for name in ("shopping_extras", "receipts", "audit", "outbox", "inventory_movements")
        }


def test_reopen_exact_and_changed_annotation_retries_preserve_one_original(tmp_path):
    _, store, commands = setup(tmp_path)
    annotation = ShoppingAnnotation("Keep this\r\nprecise note 😀", ShoppingPriority.HIGH)
    saved = commands.add_extra("same", None, "Fruit", M("2"), annotation=annotation)
    before = facts(store.path)
    reopened = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    assert reopened.add_extra("same", None, "Fruit", M("2"), annotation=annotation) == saved
    assert reopened.original(CatalogAction.ADD_EXTRA, "same", commands.actor.current()) == saved
    for changed in (
        replace(annotation, note="changed"),
        replace(annotation, priority=ShoppingPriority.LOW),
    ):
        with pytest.raises(Conflict, match="idempotency_conflict"):
            reopened.add_extra("same", None, "Fruit", M("2"), annotation=changed)
    legacy = commands.add_extra("legacy", None, "Rice", M("1"))
    assert reopened.add_extra("legacy", None, "Rice", M("1")) == legacy
    with pytest.raises(Conflict, match="idempotency_conflict"):
        reopened.add_extra("legacy", None, "Rice", M("1"), annotation=ShoppingAnnotation())
    for table, rows in before.items():
        actual = facts(store.path)[table]
        assert actual[: len(rows)] == rows
        assert len(actual) == len(rows) + (0 if table == "inventory_movements" else 1)
    with pytest.raises(InvalidInput, match="invalid_shopping_annotation"):
        commands.add_extra("bad-type", None, "Fruit", M("1"), annotation="note")


@pytest.mark.parametrize("changed", [False, True])
def test_two_real_writers_keep_annotations_with_the_single_winning_request(tmp_path, changed):
    _, store, commands = setup(tmp_path)
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    first = ShoppingAnnotation("first", ShoppingPriority.HIGH)
    second = replace(first, note="second") if changed else first
    before = facts(store.path)
    outcomes = race(
        lambda: commands.add_extra("racing", None, "Fruit", M("1"), annotation=first),
        lambda: other.add_extra("racing", None, "Fruit", M("1"), annotation=second),
    )
    (saved, *_) = (outcome for outcome in outcomes if isinstance(outcome, Receipt))
    assert outcomes.count("idempotency_conflict") == int(changed)
    if not changed:
        assert outcomes == (saved, saved)
    assert other.original(CatalogAction.ADD_EXTRA, "racing", commands.actor.current()) == saved
    with store.read() as unit:
        extra = unit.shopping.extra("home", saved.result.decode()["extra_id"])
        assert extra.annotation in (first, second)
        command_payload = {
            "product_id": None,
            "name": "Fruit",
            "quantity": "1",
            "note": extra.annotation.note,
            "priority": extra.annotation.priority.value,
        }
        assert unit.audit.entries("home")[-1].detail.decode() == command_payload
    for table, rows in before.items():
        assert len(facts(store.path)[table]) == len(rows) + (
            0 if table == "inventory_movements" else 1
        )


@pytest.mark.parametrize(
    "owner,method",
    [
        (SQLiteShopping, "add_extra"),
        (SQLiteReceipts, "add"),
        (storage.SQLiteAudit, "append"),
        (storage.SQLiteOutbox, "append"),
    ],
)
def test_interruption_after_each_write_rolls_back_every_fact_and_allows_exact_retry(
    tmp_path, monkeypatch, owner, method
):
    _, store, commands = setup(tmp_path)
    annotation = ShoppingAnnotation("Two lines\nfor later", ShoppingPriority.URGENT)
    original = getattr(owner, method)

    def fail_after_write(self, *args):
        original(self, *args)
        raise StorageFailure("annotation_interrupted")

    before = facts(store.path)
    with monkeypatch.context() as patch:
        patch.setattr(owner, method, fail_after_write)
        with pytest.raises(StorageFailure, match="annotation_interrupted"):
            commands.add_extra("retry", None, "Fruit", M("1"), annotation=annotation)
    assert facts(store.path) == before
    saved = commands.add_extra("retry", None, "Fruit", M("1"), annotation=annotation)
    assert commands.add_extra("retry", None, "Fruit", M("1"), annotation=annotation) == saved
    with store.read() as unit:
        assert (
            unit.shopping.extra("home", saved.result.decode()["extra_id"]).annotation == annotation
        )


def frozen_source(root, version):
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture_kind = "shopping-annotations" if version == 36 else "inventory-history"
    fixture = FIXTURES / f"v{version}-{fixture_kind}-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        db.row_factory = sqlite3.Row
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert db.execute("PRAGMA user_version").fetchone()[0] == version
    path.chmod(0o600)
    identity_at(root, installation)
    return SQLiteDatabase(path, installation)


@pytest.mark.parametrize("version", [20, 36])
def test_genuine_previous_and_v20_migrate_atomically_preserving_every_original_column(
    tmp_path, monkeypatch, version
):
    store = frozen_source(tmp_path / "root", version)
    with store._connection() as db:
        assert _verify_database(db, store, previous=True) == version
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
        columns = {
            table: [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]
            for table in tables
        }
        rows = {table: db.execute(f'SELECT * FROM "{table}"').fetchall() for table in tables}
        assert "shopping_extras" not in tables or "note" not in columns["shopping_extras"]
    baseline = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage,
            "SHOPPING_ANNOTATION_STATEMENTS",
            (storage.SHOPPING_ANNOTATION_STATEMENTS[0], "invalid SQL"),
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with store._connection() as db:
        assert _verify_database(db, store, previous=False) == 37
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in tables:
            selection = ",".join('"' + column + '"' for column in columns[table])
            assert db.execute(f'SELECT {selection} FROM "{table}"').fetchall() == rows[table]
        assert all(
            tuple(row) == ("", "normal")
            for row in db.execute("SELECT note,priority FROM shopping_extras")
        )
    commands = InventoryCommands(store, Actor(), Clock(), SecureIdentifiers())
    if version == 36:
        provenance = json.loads(
            (FIXTURES / "v36-shopping-annotations-source.provenance.json").read_text()
        )["fixtures"]
        tracked = commands.add_extra(
            "v36-active-tracked", provenance["product"], None, M("0.000001")
        )
        free = commands.add_extra("v36-active-free", None, "Schema36 fruit", M("2"))
        assert tracked.operation_id == provenance["activeTrackedOperation"]
        assert free.operation_id == provenance["activeFreeOperation"]
        assert (
            commands.clear_extra("v36-clear", provenance["clearedFreeExtra"]).operation_id
            == provenance["clearOperation"]
        )
        with pytest.raises(Conflict, match="idempotency_conflict"):
            commands.add_extra(
                "v36-active-free", None, "Schema36 fruit", M("2"), annotation=ShoppingAnnotation()
            )
        with store.read() as unit:
            assert unit.shopping.extra("home", provenance["clearedFreeExtra"]).cleared_at == 100
    saved = commands.add_extra(
        "new",
        None,
        "After migration",
        M("1"),
        annotation=ShoppingAnnotation("new\nnote", ShoppingPriority.LOW),
    )
    assert (
        queries(commands).annotated_shopping_list(limit=25, cursor=None).items[-1].annotation.note
        == "new\nnote"
    )
    assert (
        replace(commands, transactions=SQLiteDatabase(store.path, store.installation)).add_extra(
            "new",
            None,
            "After migration",
            M("1"),
            annotation=ShoppingAnnotation("new\nnote", ShoppingPriority.LOW),
        )
        == saved
    )


def test_actual_restore_keeps_literal_annotations_and_historical_command_outcomes(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    _, store, commands = setup(root)
    path = root / "domus.sqlite3"
    assert store.path == path
    identity_at(root, store.installation)
    annotation = ShoppingAnnotation("Literal\r\n\t😀 <img>", ShoppingPriority.HIGH)
    added = commands.add_extra("add", None, "Fruit", M("2"), annotation=annotation)
    extra_id = added.result.decode()["extra_id"]
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock()).create("annotated")
    cleared = commands.clear_extra("clear", extra_id)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), snapshot).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        assert recovery.add_extra("add", None, "Fruit", M("2"), annotation=annotation) == added
        assert recovery.clear_extra("clear", extra_id).operation_id == cleared.operation_id
        assert recovery.original(
            CatalogAction.CLEAR_EXTRA, "clear", commands.actor.current()
        ).historical
        with restored.database.read() as unit:
            extra = unit.shopping.extra("home", extra_id)
            assert extra.annotation == annotation and extra.cleared_at is None
        recovery.clear_extra("new-clear", extra_id)
        assert queries(recovery).annotated_shopping_list(limit=25, cursor=None).items == ()
    finally:
        restored.close()


@pytest.mark.parametrize(
    "field,value", [("note", "unsafe\0text"), ("note", "x" * 1001), ("priority", "unknown")]
)
def test_snapshot_rejects_damaged_annotation_records(tmp_path, field, value):
    _, store, commands = setup(tmp_path)
    commands.add_extra("add", None, "Fruit", M("1"), annotation=ShoppingAnnotation())
    with store._connection() as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(f"UPDATE shopping_extras SET {field}=?", (value,))
        db.execute("PRAGMA ignore_check_constraints=OFF")
        with pytest.raises(DatabaseRejected):
            _verify_database(db, store, previous=False)
