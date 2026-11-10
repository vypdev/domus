"""Pantry policy follows authoritative availability across writes, upgrades and restoration."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Actor, Clock
from test_inventory_catalog_storage import register, setup
from test_rewards_storage import race
from test_task_commands import resource

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory import CatalogAction, InventoryCommands, InventorySettlement
from domus.application.inventory_queries import InventoryQueries, ReplenishmentView
from domus.application.task_requests import CompleteTask, CreateTask
from domus.domain.errors import Conflict, DatabaseRejected, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.inventory import BaseUnit, EffectKind
from domus.domain.storage import Installation, Receipt
from domus.domain.task_material_values import MaterialQuantity, MaterialSelection, MaterialUsage
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor

ACTION = CatalogAction.CONFIGURE_REPLENISHMENT


def report(commands, product):
    store = commands.transactions
    queries = InventoryQueries(
        store,
        MaintenanceScope(store.installation, "home"),
        commands.actor.current(),
        TaskCursor(Clock(), b"x" * 32),
    )
    return next(
        row for row in queries.report(limit=25, cursor=None).products if row.product_id == product
    )


def configure(commands, key, product, minimum, target, expected=0):
    return commands.configure_replenishment(
        key, product, MaterialQuantity(minimum), MaterialQuantity(target), expected
    )


def test_replenishment_reopens_and_does_not_modify_task_effects_or_pending_usage(tmp_path):
    tasks, store, commands = setup(tmp_path)
    product = register(commands)
    commands.intake("stock", product, MaterialQuantity("2"))
    with store.read() as unit:
        reference = unit.inventory.product("home", product).reference_id
        actor = unit.members.by_user("home", "ha_admin")
    tasks = replace(
        tasks,
        inventory_factory=lambda unit: InventorySettlement(
            unit.inventory, Clock(), commands.identifiers
        ),
    )
    _, occurrence = resource(
        tasks.create(
            "work",
            CreateTask(
                TaskContent("Refill jar"),
                materials=(MaterialSelection(reference, MaterialQuantity("1.5")),),
            ),
        )
    )
    reserve = commands.commit_effect(
        "reserve",
        EffectKind.RESERVATION,
        reference,
        MaterialQuantity("1.5"),
        occurrence_id=occurrence,
    ).result.decode()["effect_id"]
    demand = commands.commit_effect(
        "demand",
        EffectKind.DEMAND,
        reference,
        MaterialQuantity("1.25"),
        occurrence_id=occurrence,
    ).result.decode()["effect_id"]
    with store.read() as unit:
        (line,) = unit.tasks.occurrence("home", occurrence).definition_snapshot.materials
    tasks.complete(
        "use",
        CompleteTask(
            occurrence,
            1,
            (actor.member_id,),
            95,
            material_usages=(MaterialUsage(line.line_id, MaterialQuantity("3")),),
        ),
    )
    with closing(sqlite3.connect(store.path)) as db:
        (intent_id,) = db.execute("SELECT intent_id FROM task_material_intents").fetchone()
    with store.read() as unit:
        intent = unit.task_materials.get("home", intent_id)
        assert intent.state == "pending_regularization"
        effects = unit.inventory.effects("home", (occurrence,))
        assert {row.effect_id for row in effects} == {reserve, demand}

    configure(commands, "set", product, "0.500001", "1.750001")
    initial = report(commands, product)
    assert (initial.recorded, initial.reserved, initial.available) == ("2", "1.5", "0.5")
    assert initial.replenishment == ReplenishmentView(
        product, "0.500001", "1.750001", "1", "1.250001"
    )
    assert report(commands, product) == initial
    commands.intake("restock", product, MaterialQuantity("0.000001"))
    assert report(commands, product).replenishment == replace(initial.replenishment, needed="0")
    commands.adjust("count", product, "-0.000001", "Check count")
    assert report(commands, product) == initial
    configure(commands, "disable", product, "0", "1.750001", 1)
    assert report(commands, product).replenishment == ReplenishmentView(
        product, "0", "1.750001", "2", "0"
    )
    with store.read() as unit:
        assert unit.task_materials.get("home", intent_id) == intent
        assert unit.inventory.effects("home", (occurrence,)) == effects


@pytest.mark.parametrize("same_key", [True, False])
def test_independent_policy_writers_and_restart(tmp_path, same_key):
    _, store, commands = setup(tmp_path)
    product = register(commands)
    restarted = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    second = "first" if same_key else "second"
    results = race(
        lambda: configure(commands, "first", product, "1", "2"),
        lambda: configure(restarted, second, product, "1", "2"),
    )
    winning, receipt = next(
        (key, result)
        for key, result in zip(("first", second), results, strict=True)
        if isinstance(result, Receipt)
    )
    assert results == (receipt, receipt) if same_key else results.count("revision_conflict") == 1
    human = commands.actor.current()
    assert restarted.original(ACTION, winning, human) == receipt
    assert configure(restarted, winning, product, "1", "2") == receipt
    with pytest.raises(Conflict, match="idempotency_conflict"):
        configure(restarted, winning, product, "1", "3")
    assert report(restarted, product).replenishment == ReplenishmentView(
        product, "1", "2", "1", "2"
    )


def test_upgrade_and_activated_restore_preserve_stock_and_policy_receipts(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v21-pantry-replenishment-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture.read_text())
        assert db.execute("PRAGMA user_version").fetchone() == (21,)
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        (oil,) = db.execute("SELECT product_id FROM inventory_products WHERE name='Oil'").fetchone()
        (oats,) = db.execute(
            "SELECT product_id FROM inventory_products WHERE name='Oats'"
        ).fetchone()
        existing = {
            table: db.execute("SELECT * FROM " + table).fetchall()
            for table in (
                "inventory_movements",
                "inventory_effects",
                "task_material_intents",
                "receipts",
            )
        }
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "REPLENISHMENT_STATEMENT", "invalid schema change")
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (22,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in existing.items():
            assert db.execute("SELECT * FROM " + table).fetchall() == rows
    identity_at(root, installation)
    actor = Actor()
    actor.human = HumanIdentity("ha_admin", True, True, False)
    commands = InventoryCommands(store, actor, Clock(), SecureIdentifiers())
    assert report(commands, oil).replenishment == ReplenishmentView(oil, "0", "0", "0", "0")
    old = commands.original(
        CatalogAction.CORRECT_INTAKE, "replenishment-v21-correction", actor.human
    )
    assert (
        commands.correct_intake(
            "replenishment-v21-correction",
            oats,
            old.result.decode()["corrects"],
            "Duplicate intake",
        )
        == old
    )

    save = SQLiteInventory.save_replenishment

    def reject_after_write(records, home, product, policy):
        save(records, home, product, policy)
        raise StorageFailure("injected_after_policy")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteInventory, "save_replenishment", reject_after_write)
        before = report(commands, oil)
        with pytest.raises(StorageFailure, match="injected_after_policy"):
            configure(commands, "initial", oil, "3", "4")
        assert report(commands, oil) == before
    accepted = configure(commands, "initial", oil, "3", "4")
    saved = report(commands, oil)
    assert (saved.recorded, saved.reserved, saved.available) == ("3.250001", "0.875", "2.375001")
    assert saved.replenishment == ReplenishmentView(oil, "3", "4", "1", "1.624999")
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("pantry")
    later = configure(commands, "later", oil, "0", "6", 1)
    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare("restore")
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        assert report(recovery, oil) == saved
        assert recovery.original(ACTION, "initial", actor.human) == accepted
        assert configure(recovery, "initial", oil, "3", "4") == accepted
        historical = recovery.original(ACTION, "later", actor.human)
        assert historical.historical and historical.operation_id == later.operation_id
        assert configure(recovery, "later", oil, "0", "6", 1) == historical
        assert (
            recovery.original(
                CatalogAction.CORRECT_INTAKE, "replenishment-v21-correction", actor.human
            )
            == old
        )
    finally:
        restored.close()


@pytest.mark.parametrize(("minimum", "target"), [(1, 2_000_000), (1_000_000, 2_000_001)])
def test_snapshot_rejects_fractional_piece_threshold(tmp_path, minimum, target):
    _, store, commands = setup(tmp_path)
    product = commands.register("pieces", "Boxes", BaseUnit.PIECE).result.decode()["product_id"]
    configure(commands, "policy", product, "1", "2")
    archive = tmp_path / "archive"
    snapshots = SQLiteSnapshots(store, archive, store.installation, Clock())
    assert snapshots.create("valid").schema_version == 22
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute("UPDATE inventory_replenishment SET minimum=?,target=?", (minimum, target))
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        snapshots.create("damaged")
