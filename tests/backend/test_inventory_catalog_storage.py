"""Catalog migration, contention and recovery use the real Inventory and SQLite writers."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_activation_compatibility import identity_at
from test_household_commands import Clock
from test_rewards_storage import race
from test_task_commands import fixture, resource

from domus.application.inventory import CatalogAction, InventoryCommands, InventorySettlement
from domus.application.task_requests import CompleteTask, CreateTask
from domus.domain.errors import DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.inventory import BaseUnit, CatalogProduct, EffectKind
from domus.domain.storage import Installation
from domus.domain.task_material_values import MaterialQuantity, MaterialSelection, MaterialUsage
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_inventory import SQLiteInventory
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def setup(root):
    tasks, store, actor, ids = fixture(root)
    return tasks, store, InventoryCommands(store, actor, Clock(), ids)


def register(commands, *, key="new"):
    return commands.register(key, "Oil", BaseUnit.MILLILITRE).result.decode()["product_id"]


def test_two_writers_and_restart_recover_one_exact_movement(tmp_path):
    _, store, commands = setup(tmp_path)
    product_id = register(commands)
    other = replace(commands, transactions=SQLiteDatabase(store.path, store.installation))
    request = MaterialQuantity("1.250001")
    first, second = race(
        lambda: commands.intake("intake", product_id, request),
        lambda: other.intake("intake", product_id, request),
    )
    assert (
        first == second == other.original(CatalogAction.INTAKE, "intake", commands.actor.current())
    )
    assert other.intake("intake", product_id, request) == first
    a, b = race(
        lambda: commands.intake("second", product_id, MaterialQuantity("1")),
        lambda: other.intake("third", product_id, MaterialQuantity("0.1")),
    )
    assert a.operation_id != b.operation_id
    with store.read() as unit:
        product = unit.inventory.product("home", product_id)
        assert unit.inventory.balance("home", product.reference_id) == 2_350_001
        assert unit.inventory.product("different-home", product_id) is None
        assert unit.inventory.products("different-home", "", 25) == ()
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM inventory_movements").fetchone() == (3,)
        assert db.execute(
            "SELECT delta,reason,member_id,created_at FROM inventory_movements WHERE movement_id=?",
            (first.result.decode()["movement_id"],),
        ).fetchone() == (1_250_001, "receipt", "identity-1", 100)


def test_new_binding_participates_in_existing_task_reservation_and_usage(tmp_path):
    tasks, store, commands = setup(tmp_path)
    product_id = register(commands)
    commands.intake("stock", product_id, MaterialQuantity("2"))
    with store.read() as unit:
        product = unit.inventory.product("home", product_id)
        binding = unit.inventory.material("home", product.reference_id)
        actor = unit.members.by_user("home", "ha_admin")
    assert binding == product.binding("home") and binding.location_id == "pantry"
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
                materials=(MaterialSelection(binding.reference_id, MaterialQuantity("1.5")),),
            ),
        )
    )
    reservation = commands.commit_effect(
        "reserve",
        EffectKind.RESERVATION,
        binding.reference_id,
        MaterialQuantity("1.5"),
        occurrence_id=occurrence,
    ).result.decode()["effect_id"]
    with store.read() as unit:
        (line,) = unit.tasks.occurrence("home", occurrence).definition_snapshot.materials
        assert unit.inventory.reserved("home", binding.reference_id) == 1_500_000
    tasks.complete(
        "use",
        CompleteTask(
            occurrence,
            1,
            (actor.member_id,),
            95,
            material_usages=(MaterialUsage(line.line_id, MaterialQuantity("1")),),
        ),
    )
    with store.read() as unit:
        assert unit.inventory.balance("home", binding.reference_id) == 1_000_000
        assert unit.inventory.effect("home", reservation).remaining == 500_000
        assert unit.inventory.reserved("home", binding.reference_id) == 500_000


def test_failed_catalog_write_rolls_back_binding_and_retains_retry(tmp_path, monkeypatch):
    _, store, commands = setup(tmp_path)
    with monkeypatch.context() as patch:

        def fail(*_):
            raise StorageFailure("catalog_unavailable")

        patch.setattr(SQLiteInventory, "add_product", fail)
        with pytest.raises(StorageFailure, match="catalog_unavailable"):
            register(commands)
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM inventory_materials").fetchone() == (0,)
    assert register(commands) == register(commands)
    with pytest.raises(InvalidInput, match="invalid_inventory_unit"):
        commands.register("bad", "Oil", "litre")
    with pytest.raises(InvalidInput, match="invalid_inventory_unit"):
        CatalogProduct("product", "reference", "Oil", "litre")


def test_schema19_upgrade_preserves_legacy_stock_and_rewards(tmp_path, monkeypatch):
    path = tmp_path / "domus.sqlite3"
    fixture_path = Path(__file__).parents[1] / "fixtures/sqlite/v19-inventory-catalog-source.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript(fixture_path.read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
        assert db.execute("PRAGMA user_version").fetchone() == (19,)
        previous = db.execute("SELECT * FROM inventory_movements").fetchall()
    path.chmod(0o600)
    store = SQLiteDatabase(path, installation)
    baseline = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "CATALOG_STATEMENTS", (*storage.CATALOG_STATEMENTS, "broken"))
        with pytest.raises(StorageFailure):
            store.initialize(require_existing=True)
    assert path.read_bytes() == baseline
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (26,)
        assert [row[:-1] for row in db.execute("SELECT * FROM inventory_movements")] == previous
    with store.read() as unit:
        assert unit.inventory.products("home", "", 25) == ()
        binding = unit.inventory.material("home", "legacy-material")
        assert binding.location_id == "utility-room" and binding.unit_id == "litre"
        assert unit.inventory.balance("home", binding.reference_id) == 2_125_000
        assert unit.rewards.setting("home").enabled


def test_restore_preserves_current_stock_and_historical_receipt(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    _, store, commands = setup(root)
    identity_at(root, store.installation)
    product_id = register(commands)
    commands.intake("original", product_id, MaterialQuantity("1.25"))
    archive, target = tmp_path / "archive", tmp_path / "prepared"
    snapshot = SQLiteSnapshots(store, archive, store.installation, Clock()).create("catalog")
    after = commands.intake("later", product_id, MaterialQuantity("2"))
    SQLiteRestorations(store, archive, target, store.installation, Clock(), snapshot).prepare(
        "restore-catalog"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        recovery = replace(commands, transactions=restored.database)
        human = commands.actor.current()
        retained = recovery.original(CatalogAction.INTAKE, "later", human)
        assert retained.historical and retained.operation_id == after.operation_id
        assert recovery.intake("later", product_id, MaterialQuantity("2")) == retained
        with restored.database.read() as unit:
            product = unit.inventory.product("home", product_id)
            assert unit.inventory.balance("home", product.reference_id) == 1_250_000
    finally:
        restored.close()


def test_snapshot_rejects_catalog_pointing_to_inconsistent_unit(tmp_path):
    _, store, commands = setup(tmp_path)
    register(commands)
    with closing(sqlite3.connect(store.path, autocommit=True)) as db:
        db.execute("UPDATE inventory_products SET base_unit='piece'")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "invalid", store.installation, Clock()).create("catalog")
