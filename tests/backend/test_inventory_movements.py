"""Exact corrections across real SQLite writers, upgrades and activated restores."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_storage import register, setup
from test_rewards_storage import race

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory import CatalogAction, InventoryCommands
from domus.application.inventory_queries import InventoryQueries
from domus.domain.errors import Conflict, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.inventory import MovementKind
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory, verify_inventory_records
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor


def history(store, commands, product_id):
    queries = InventoryQueries(
        store,
        MaintenanceScope(store.installation, "home"),
        commands.actor.current(),
        TaskCursor(Clock(), b"x" * 32),
    )
    return queries.history(product_id, limit=25, cursor=None).movements


@pytest.mark.parametrize("same_key", [True, False])
def test_racing_corrections_and_restart_reuse_one_compensation(tmp_path, same_key):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    source = commands.intake("intake", product, MaterialQuantity("2.000001"))
    original = source.result.decode()["movement_id"]
    reopened = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    second_key = "first" if same_key else "second"
    results = race(
        lambda: commands.correct_intake("first", product, original, "Duplicate"),
        lambda: reopened.correct_intake(second_key, product, original, "Duplicate"),
    )
    winning_key, receipt = next(
        (key, item)
        for key, item in zip(("first", second_key), results, strict=True)
        if isinstance(item, Receipt)
    )
    if same_key:
        assert results == (receipt, receipt)
    else:
        assert results.count("inventory_intake_corrected") == 1
    assert (
        reopened.original(CatalogAction.CORRECT_INTAKE, winning_key, commands.actor.current())
        == receipt
    )
    assert reopened.correct_intake(winning_key, product, original, "Duplicate") == receipt
    correction, intake = history(reopened.transactions, reopened, product)
    assert intake.movement_id == original and intake.quantity == "2.000001"
    assert correction.corrects == original and intake.corrected_by == correction.movement_id
    assert correction.quantity == "-2.000001"
    assert correction.reason == "Duplicate"


def legacy(root, monkeypatch):
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v20-inventory-history-source.sql"
    path = root / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        db.row_factory = sqlite3.Row
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        product, reference = db.execute(
            "SELECT product_id,reference_id FROM inventory_products"
        ).fetchone()
        previous = [
            tuple(row) for row in db.execute("SELECT * FROM inventory_movements ORDER BY position")
        ]
        assert db.execute("PRAGMA user_version").fetchone()[0] == 20
        verify_inventory_records(db)
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            storage, "MOVEMENT_HISTORY_STATEMENTS", (*storage.MOVEMENT_HISTORY_STATEMENTS, "broken")
        )
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == original
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (29,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [
            row[:-1] for row in db.execute("SELECT * FROM inventory_movements ORDER BY position")
        ] == previous
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    return store, commands, product, reference


def test_upgrade_reservations_rollback_and_activated_restore(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    store, commands, product, reference = legacy(root, monkeypatch)
    identity_at(root, store.installation)
    task_correction, task_consumption, original = history(store, commands, product)
    assert [entry.kind for entry in (task_correction, task_consumption, original)] == [
        MovementKind.TASK_CORRECTION,
        MovementKind.TASK_CONSUMPTION,
        MovementKind.INTAKE,
    ]
    assert task_correction.corrects == task_consumption.movement_id
    assert task_correction.task_occurrence_id == task_consumption.task_occurrence_id
    assert task_consumption.quantity == "-1.125" and task_correction.quantity == "0.125"
    human = commands.actor.current()
    migrated = commands.original(CatalogAction.INTAKE, "intake-v20", human)
    assert migrated.result.decode()["movement_id"] == original.movement_id
    assert commands.intake("intake-v20", product, MaterialQuantity("4.250001")) == migrated

    with pytest.raises(InvalidInput, match="inventory_correction_requires_intake"):
        commands.correct_intake("wrong-source", product, task_consumption.movement_id, "Check")
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.correct_intake("correction", product, original.movement_id, "Wrong intake")
    with pytest.raises(Conflict, match="inventory_insufficient_stock"):
        commands.adjust("decrease", product, "-3", "Count")
    with store.read() as unit:
        assert unit.inventory.balance("home", reference) == 3_250_001
        assert unit.inventory.reserved("home", reference) == 875_000
    assert history(store, commands, product) == (task_correction, task_consumption, original)

    commands.adjust("funds", product, "3", "Physical count")
    append = SQLiteInventory.append

    def fail_after_append(records, movement, balance):
        append(records, movement, balance)
        raise StorageFailure("injected_after_append")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "append", fail_after_append)
        with pytest.raises(StorageFailure, match="injected_after_append"):
            commands.correct_intake("correction", product, original.movement_id, "Wrong intake")
    with store.read() as unit:
        assert unit.inventory.balance("home", reference) == 6_250_001
        assert unit.inventory.reserved("home", reference) == 875_000
        assert unit.inventory.correction_id("home", original.movement_id) is None
    accepted = commands.correct_intake("correction", product, original.movement_id, "Wrong intake")
    before = history(store, commands, product)
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("inventory")
    later_intake = commands.intake("later-intake", product, MaterialQuantity("1"))
    later_id = later_intake.result.decode()["movement_id"]
    later = commands.correct_intake("later-correction", product, later_id, "Test restore")
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        assert recovery.original(CatalogAction.CORRECT_INTAKE, "correction", human) == accepted
        assert (
            recovery.correct_intake("correction", product, original.movement_id, "Wrong intake")
            == accepted
        )
        historical = recovery.original(CatalogAction.CORRECT_INTAKE, "later-correction", human)
        assert historical.historical and historical.operation_id == later.operation_id
        assert (
            recovery.correct_intake("later-correction", product, later_id, "Test restore")
            == historical
        )
        assert history(restored.database, recovery, product) == before
        with restored.database.read() as unit:
            assert unit.inventory.balance("home", reference) == 2_000_000
            assert unit.inventory.reserved("home", reference) == 875_000
    finally:
        restored.close()


@pytest.mark.parametrize("damage", ["missing", "wrong-source", "wrong-delta"])
def test_snapshot_verifier_rejects_inconsistent_intake_compensation(tmp_path, damage):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    source = commands.intake("original", product, MaterialQuantity("1")).result.decode()[
        "movement_id"
    ]
    adjustment = commands.adjust("adjust", product, "1", "Count").result.decode()["movement_id"]
    correction = commands.correct_intake("correct", product, source, "Duplicate")
    corrected = correction.result.decode()["movement_id"]
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        if damage == "wrong-delta":
            db.execute("UPDATE inventory_movements SET delta=-1 WHERE movement_id=?", (corrected,))
        else:
            db.execute(
                "UPDATE inventory_movements SET corrects=? WHERE movement_id=?",
                ("missing" if damage == "missing" else adjustment, corrected),
            )
        with pytest.raises(StorageFailure, match="invalid_inventory_movement"):
            verify_inventory_records(db)
